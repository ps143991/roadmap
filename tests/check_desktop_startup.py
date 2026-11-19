"""Check first-run UI, offline preview, autosave, and native save-before-close.

Uses a temporary XDG profile. Run under Xvfb in CI, or in a desktop session.
An optional --screenshot PATH captures only the generated sample roadmap.
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--screenshot', type=Path)
    parser.add_argument('--frontend-root', type=Path, help='Serve an explicitly selected frontend while using temporary test data')
    options = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='roadmap-first-launch-') as temporary:
        profile = Path(temporary)
        os.environ['XDG_DATA_HOME'] = str(profile / 'share')
        os.environ['XDG_CACHE_HOME'] = str(profile / 'cache')
        os.environ['XDG_CONFIG_HOME'] = str(profile / 'config')
        os.environ['GSETTINGS_BACKEND'] = 'memory'
        import roadmap_app
        import roadmap_server
        if options.frontend_root:
            roadmap_server.ROOT = options.frontend_root.resolve()
        from gi.repository import Gio, GLib, WebKit2
        data = profile / 'share/thesis-roadmap/data'
        application = roadmap_app.RoadmapApp(0, data_dir=data)
        application.set_application_id('org.thesisroadmap.App.StartupCheck')
        application.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        failures, ready = [], []

        def fail(message):
            failures.append(str(message))
            print('FAIL:', message, flush=True)
            application.window.destroy()
            application.quit()
            return False

        def evaluate(script):
            def done(view, result):
                try:
                    view.evaluate_javascript_finish(result)
                except Exception as error:
                    fail(error)
            application.view.evaluate_javascript(script + '; undefined;', -1, None, None, None, done)
            return False

        def take_snapshot():
            def captured(view, result):
                try:
                    surface = view.get_snapshot_finish(result)
                    options.screenshot.parent.mkdir(parents=True, exist_ok=True)
                    surface.write_to_png(str(options.screenshot))
                    evaluate("document.getElementById('field-notes').value='Final edit saved before close'; document.getElementById('field-notes').dispatchEvent(new Event('input', {bubbles:true})); window.webkit.messageHandlers.startupCheck.postMessage({kind:'close'});")
                except Exception as error:
                    fail(error)
            application.view.get_snapshot(WebKit2.SnapshotRegion.FULL_DOCUMENT, WebKit2.SnapshotOptions.NONE, None, captured)

        def received(manager, result):
            message = json.loads(result.get_js_value().to_json(0))
            if message['kind'] == 'error':
                fail(message['message'])
            elif message['kind'] == 'ready':
                print('PASS: Second/third/fourth-level accordion, generic roadmap, live equations, and independent autosave', flush=True)
                if options.screenshot:
                    take_snapshot()
                else:
                    evaluate("document.getElementById('field-notes').value='Final edit saved before close'; document.getElementById('field-notes').dispatchEvent(new Event('input', {bubbles:true})); window.webkit.messageHandlers.startupCheck.postMessage({kind:'close'});")
            elif message['kind'] == 'close':
                ready.append(True)
                application.request_close()

        def loaded(view, event):
            if event != WebKit2.LoadEvent.FINISHED:
                return
            script = r'''
                void (async () => {
                    const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
                    const assert = (condition, message) => { if (!condition) throw new Error(message); };
                    await wait(500);
                    assert(thesisData?.name === 'My Thesis', 'Fresh profile did not use the generic starter');
                    assert(thesisData.children.length === 6, 'Starter chapter structure is missing');
                    assert(document.querySelectorAll('g.node').length === 7, 'Map failed to render');
                    // Regression: accordion expansion must work below the second level.
                    const originalData = thesisData;
                    const originalCollapsed = [...collapsedIds];
                    const leaf = id => ({id, name:id, type:'task', children:[]});
                    const deep = id => ({id, name:id, children:[leaf(id + '-leaf')]});
                    const section = id => ({id, name:id, children:[deep(id + '-left'), deep(id + '-right')]});
                    thesisData = {id:'accordion-root', name:'Accordion test', children:[
                        {id:'parent-a', name:'Parent A', children:[section('section-a'), section('section-b')]},
                        {id:'parent-b', name:'Parent B', children:[section('section-c'), section('section-d')]}
                    ]};
                    normalizeData(thesisData);
                    selectedNodeId = thesisData.id;
                    collapseAll();
                    const visible = id => root.descendants().some(d => d.data.id === id);
                    const doubleClick = id => {
                        const element = [...document.querySelectorAll('g.node')].find(e => e.__data__.data.id === id);
                        assert(element, 'Missing visible branch ' + id);
                        element.dispatchEvent(new MouseEvent('dblclick', {bubbles:true}));
                    };
                    doubleClick('parent-a');
                    doubleClick('parent-b');
                    assert(!visible('section-a') && visible('section-c'), 'Second-level accordion changed');
                    doubleClick('parent-a');
                    doubleClick('section-a');
                    assert(visible('section-a-left'), 'Third-level branch did not expand');
                    doubleClick('section-b');
                    assert(!visible('section-a-left') && visible('section-b-left'), 'Third-level sibling stayed expanded');
                    doubleClick('section-b-left');
                    assert(visible('section-b-left-leaf'), 'Fourth-level branch did not expand');
                    doubleClick('section-b-right');
                    assert(!visible('section-b-left-leaf') && visible('section-b-right-leaf'), 'Fourth-level sibling stayed expanded');
                    doubleClick('section-b-right');
                    assert(!visible('section-b-right-leaf') && visible('section-b-left'), 'Collapsing a branch affected its parent');
                    expandAll();
                    assert(root.descendants().length === flattenData(thesisData).length, 'Expand All no longer shows the whole map');
                    doubleClick('section-a');
                    doubleClick('section-a');
                    assert(!visible('section-b-left') && visible('section-c-left'), 'Opening a branch collapsed unrelated parents or kept a sibling open');
                    thesisData = originalData;
                    selectedNodeId = thesisData.id;
                    collapsedIds = new Set(originalCollapsed);
                    renderAll(false);
                    console.log('Accordion checks passed at the second, third, and fourth levels.');
                    document.getElementById('notes-panel').open = true;
                    const notes = document.getElementById('field-notes');
                    const starterNotes = notes.value;
                    notes.value = '# My research notes\n\nInline $y=mx+b$.\n\n$$\\bar{x}=\\frac{1}{n}\\sum_{i=1}^{n}x_i$$\n\nMy roadmap is saved automatically.';
                    notes.dispatchEvent(new Event('input', {bubbles:true}));
                    await wait(1000);
                    await saveQueue;
                    assert(document.querySelectorAll('#notes-preview .katex').length === 2, 'Offline equation preview failed');
                    const saved = await (await fetch('/api/roadmap')).json();
                    assert(saved.notes === notes.value, 'Autosave did not reach the user profile');
                    await document.fonts.ready;
                    notes.value = starterNotes;
                    notes.dispatchEvent(new Event('input', {bubbles:true}));
                    updateNotesPreview();
                    window.scrollTo(0, 0);
                    window.webkit.messageHandlers.startupCheck.postMessage({kind:'ready'});
                })().catch(error => window.webkit.messageHandlers.startupCheck.postMessage({kind:'error',message:error.message + ' | ' + error.stack}));
            '''
            evaluate(script)

        def activated(app):
            manager = application.view.get_user_content_manager()
            manager.register_script_message_handler('startupCheck')
            manager.connect('script-message-received::startupCheck', received)
            application.view.connect('load-changed', loaded)

        application.connect_after('activate', activated)
        GLib.timeout_add_seconds(60, lambda: fail('Desktop startup check timed out'))
        application.run([])
        if not failures:
            assert ready, 'Close path was not exercised'
            assert json.loads((data / 'roadmap_data.json').read_text())['notes'] == 'Final edit saved before close'
            assert (data / 'roadmap_data.backup.json').is_file()
            print('PASS: Native close waits until the final edit is saved; backup is in the user-data folder', flush=True)
        return bool(failures)


if __name__ == '__main__':
    raise SystemExit(main())
