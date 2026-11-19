#!/usr/bin/env python3
"""Desktop window for the local roadmap, with an acknowledged save before exit."""

import argparse
import json
import signal
import threading
from functools import partial
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
try:
    gi.require_version("WebKit2", "4.1")
except ValueError:
    gi.require_version("WebKit2", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk, WebKit2

from roadmap_server import ROOT, RoadmapHandler, ThreadingHTTPServer, configure_storage
from roadmap_storage import xdg_directory


class RoadmapApp(Gtk.Application):
    def __init__(self, port=8766, data_dir=None):
        super().__init__(application_id="org.thesisroadmap.App", flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.port = port
        self.data_dir = data_dir
        self.window = None
        self.server = None
        self.closing = False
        self.close_attempt = 0
        self.close_timeout = None
        self.connect("activate", self.activate_window)
        self.connect("shutdown", self.stop_server)

    def activate_window(self, application):
        if self.window:
            self.window.present()
            return

        self.data_dir = configure_storage(self.data_dir)
        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), RoadmapHandler)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

        self.window = Gtk.ApplicationWindow(application=self, title="Thesis Roadmap")
        self.window.set_default_size(1440, 960)
        self.window.set_icon_from_file(str(ROOT / "roadmap.svg"))
        self.window.connect("delete-event", self.request_close)
        self.window.connect("key-press-event", self.zoom_key)

        data_dir = str(self.data_dir / "webview")
        cache_dir = str(xdg_directory("XDG_CACHE_HOME", ".cache") / "thesis-roadmap" / "webview")
        data_manager = WebKit2.WebsiteDataManager(base_data_directory=data_dir, base_cache_directory=cache_dir)
        context = WebKit2.WebContext.new_with_website_data_manager(data_manager)
        context.connect("download-started", self.download_started)
        manager = WebKit2.UserContentManager()
        manager.connect("script-message-received::roadmapClose", self.close_result)
        manager.register_script_message_handler("roadmapClose")
        self.view = WebKit2.WebView(web_context=context, user_content_manager=manager)
        self.view.connect("decide-policy", self.navigation_policy)
        self.view.connect("scroll-event", self.zoom_scroll)
        self.window.add(self.view)
        self.window.maximize()
        self.window.show_all()
        self.view.load_uri(f"{self.base_url}/roadmap_these.html")

    def change_zoom(self, steps):
        zoom = self.view.get_zoom_level() * 1.1 ** steps
        self.view.set_zoom_level(max(0.5, min(3.0, zoom)))

    def zoom_key(self, window, event):
        if not event.state & Gdk.ModifierType.CONTROL_MASK:
            return False
        if event.keyval in (Gdk.KEY_plus, Gdk.KEY_equal, Gdk.KEY_KP_Add):
            self.change_zoom(1)
        elif event.keyval in (Gdk.KEY_minus, Gdk.KEY_KP_Subtract):
            self.change_zoom(-1)
        elif event.keyval in (Gdk.KEY_0, Gdk.KEY_KP_0):
            self.view.set_zoom_level(1.0)
        else:
            return False
        return True

    def zoom_scroll(self, view, event):
        if not event.state & Gdk.ModifierType.CONTROL_MASK:
            return False
        if event.direction == Gdk.ScrollDirection.UP:
            self.change_zoom(1)
        elif event.direction == Gdk.ScrollDirection.DOWN:
            self.change_zoom(-1)
        elif event.direction == Gdk.ScrollDirection.SMOOTH:
            success, delta_x, delta_y = event.get_scroll_deltas()
            if not success or delta_y == 0:
                return False
            self.change_zoom(-max(-1, min(1, delta_y)))
        else:
            return False
        return True

    def navigation_policy(self, view, decision, decision_type):
        if decision_type != WebKit2.PolicyDecisionType.NAVIGATION_ACTION:
            return False
        uri = decision.get_navigation_action().get_request().get_uri()
        if uri.startswith(self.base_url + "/") or uri.startswith("blob:" + self.base_url + "/") or uri == "about:blank":
            return False
        decision.ignore()
        return True

    def download_started(self, context, download):
        download.connect("decide-destination", self.choose_download)

    def choose_download(self, download, suggested_filename):
        dialog = Gtk.FileChooserDialog(title="Export roadmap", transient_for=self.window, action=Gtk.FileChooserAction.SAVE)
        dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Save", Gtk.ResponseType.ACCEPT)
        dialog.set_current_name(suggested_filename)
        dialog.set_do_overwrite_confirmation(True)
        if dialog.run() == Gtk.ResponseType.ACCEPT:
            download.set_allow_overwrite(True)
            download.set_destination(Path(dialog.get_filename()).as_uri())
        else:
            download.cancel()
        dialog.destroy()
        return True

    def request_close(self, *args):
        if self.closing:
            return True
        self.closing = True
        self.close_attempt += 1
        self.window.set_title("Saving… — Thesis Roadmap")
        self.view.set_sensitive(False)
        self.close_timeout = GLib.timeout_add_seconds(15, self.close_failed)
        script = """
            void (async () => {
                const closeAttempt = __CLOSE_ATTEMPT__;
                let saved = false;
                try {
                    saved = typeof window.prepareToClose === 'function' ? await window.prepareToClose() : true;
                } catch (error) {
                    saved = false;
                }
                window.webkit.messageHandlers.roadmapClose.postMessage({ saved, attempt: closeAttempt });
            })();
        """.replace("__CLOSE_ATTEMPT__", str(self.close_attempt))
        self.view.evaluate_javascript(script, -1, None, None, None, self.close_script_finished, self.close_attempt)
        return True

    def close_script_finished(self, view, result, attempt):
        try:
            view.evaluate_javascript_finish(result)
        except GLib.Error:
            if self.closing and attempt == self.close_attempt:
                self.close_failed()

    def close_result(self, manager, result):
        if not self.closing:
            return
        message = json.loads(result.get_js_value().to_json(0))
        if message.get("attempt") != self.close_attempt:
            return
        if not message.get("saved", False):
            self.close_failed()
            return
        self.cancel_close_timeout()
        self.window.destroy()
        self.quit()

    def cancel_close_timeout(self):
        if self.close_timeout is not None:
            GLib.source_remove(self.close_timeout)
            self.close_timeout = None

    def close_failed(self):
        self.cancel_close_timeout()
        if not self.closing:
            return False
        self.closing = False
        self.window.set_title("Thesis Roadmap — save needs attention")
        self.view.set_sensitive(True)
        dialog = Gtk.MessageDialog(transient_for=self.window, modal=True, message_type=Gtk.MessageType.ERROR,
                                   buttons=Gtk.ButtonsType.OK, text="The roadmap could not be saved.")
        dialog.format_secondary_text("The window is still open. Check the save status, then retry Save before closing.")
        dialog.run()
        dialog.destroy()
        return False

    def stop_server(self, application):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server_thread.join()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--data-dir", type=Path, help="Store user work in this directory")
    options = parser.parse_args()
    GLib.set_prgname("thesis-roadmap")
    application = RoadmapApp(options.port, options.data_dir)
    for sig in (signal.SIGINT, signal.SIGTERM):
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, partial(application.request_close))
    return application.run([])


if __name__ == "__main__":
    raise SystemExit(main())
