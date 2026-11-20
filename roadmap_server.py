#!/usr/bin/env python3

"""Local server for the thesis roadmap.

It serves the static HTML files and exposes a small JSON API so the browser can
save roadmap_data.json directly instead of forcing a download/export cycle.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import threading
import webbrowser
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from roadmap_storage import default_data_directory, initialize_data


ROOT = Path(__file__).resolve().parent
DATA_FILE = default_data_directory() / "roadmap_data.json"
BACKUP_FILE = DATA_FILE.with_name("roadmap_data.backup.json")
STATIC_FILES = {"/roadmap_these.html", "/gantt.html", "/roadmap_features.js", "/notes_editor.js", "/roadmap.svg", "/roadmap.png"}
MAX_BODY_SIZE = 5 * 1024 * 1024
SAVE_LOCK = threading.Lock()
SAVE_REVISIONS = {}


def configure_storage(directory=None):
    global DATA_FILE, BACKUP_FILE
    directory = initialize_data(directory)
    DATA_FILE = directory / 'roadmap_data.json'
    BACKUP_FILE = directory / 'roadmap_data.backup.json'
    SAVE_REVISIONS.clear()
    return directory


class RoadmapHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_request(self, code="-", size="-") -> None:
        if str(code).isdigit() and int(code) >= 400:
            super().log_request(code, size)

    def log_message(self, format, *args) -> None:
        print(f"Roadmap: {format % args}", file=sys.stderr)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/health":
            self.send_json({"ok": True})
            return
        if path == "/api/roadmap":
            self.send_roadmap()
            return
        if path == "/":
            self.path = "/roadmap_these.html"
        if not self.allowed_static_path():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        super().do_GET()

    def allowed_static_path(self):
        path = unquote(urlparse(self.path).path)
        if path in STATIC_FILES:
            return True
        return path.startswith('/vendor/') and Path(self.translate_path(path)).resolve().is_relative_to((ROOT / 'vendor').resolve())

    def do_HEAD(self):
        if self.allowed_static_path():
            super().do_HEAD()
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def list_directory(self, path):
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/roadmap":
            self.save_roadmap()
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Unknown API endpoint")

    def send_roadmap(self) -> None:
        try:
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except FileNotFoundError:
            self.send_error(HTTPStatus.NOT_FOUND, "roadmap_data.json not found")
            return
        except json.JSONDecodeError as error:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Invalid JSON: {error}")
            return
        self.send_json(data)

    def save_roadmap(self) -> None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid Content-Length")
            return

        if content_length <= 0:
            self.send_error(HTTPStatus.BAD_REQUEST, "Empty request body")
            return
        if content_length > MAX_BODY_SIZE:
            self.send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Roadmap JSON is too large")
            return

        raw_body = self.rfile.read(content_length)
        try:
            data = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            self.send_error(HTTPStatus.BAD_REQUEST, f"Invalid JSON: {error}")
            return

        if not isinstance(data, dict):
            self.send_error(HTTPStatus.BAD_REQUEST, "Roadmap JSON must be an object")
            return

        query = parse_qs(urlparse(self.path).query)
        session = query.get("session", [""])[0]
        try:
            revision = int(query.get("revision", ["0"])[0])
        except ValueError:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid save revision")
            return

        try:
            with SAVE_LOCK:
                if not session or revision > SAVE_REVISIONS.get(session, -1):
                    self.write_json_file(data)
                    if session:
                        SAVE_REVISIONS[session] = revision
        except OSError as error:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Unable to save: {error}")
            return
        self.send_json({"ok": True, "file": DATA_FILE.name})

    def write_json_file(self, data: dict) -> None:
        payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        if DATA_FILE.exists():
            if DATA_FILE.read_text(encoding="utf-8") == payload:
                return
            mode = DATA_FILE.stat().st_mode & 0o777
            shutil.copy2(DATA_FILE, BACKUP_FILE)
        else:
            mode = 0o600

        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=DATA_FILE.parent,
            delete=False,
            prefix=".roadmap_data.",
            suffix=".tmp",
        ) as temp_file:
            temp_file.write(payload)
            temp_file.flush()
            os.fsync(temp_file.fileno())
            temp_name = temp_file.name

        os.chmod(temp_name, mode)
        os.replace(temp_name, DATA_FILE)

    def send_json(self, data: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('port', nargs='?', type=int, default=8766)
    parser.add_argument('--data-dir', type=Path, help='Store user work in this directory')
    parser.add_argument('--open', action='store_true', help='Open the app in the default browser')
    options = parser.parse_args()
    configure_storage(options.data_dir)
    server = ThreadingHTTPServer(("127.0.0.1", options.port), RoadmapHandler)
    url = f"http://127.0.0.1:{server.server_port}/roadmap_these.html"
    print(f"Thesis Roadmap: {url} (Ctrl+C to stop)")
    print(f"Your work: {DATA_FILE}")
    if options.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
