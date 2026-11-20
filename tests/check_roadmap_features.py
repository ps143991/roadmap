"""Run desktop integration checks on temporary data: python3 tests/check_roadmap_features.py.

Requires the app's GTK/WebKit runtime, an X11 display, and libXtst for real mouse
and keyboard input. The live roadmap and its backup are never used for saves.
"""

import ctypes
import ctypes.util
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import roadmap_app
import roadmap_server
from gi.repository import Gdk, Gio, GLib, WebKit2

original_hashes = {'examples/starter-roadmap.json': hashlib.sha256((ROOT / 'examples/starter-roadmap.json').read_bytes()).hexdigest()}
temporary = tempfile.TemporaryDirectory(prefix='roadmap-features-check-')
test_root = Path(temporary.name)
for name in ['roadmap_these.html', 'roadmap_features.js', 'notes_editor.js', 'gantt.html', 'roadmap.svg', 'roadmap.png']:
    shutil.copy2(ROOT / name, test_root / name)
shutil.copytree(ROOT / 'vendor', test_root / 'vendor')
roadmap_server.ROOT = test_root
roadmap_server.DATA_FILE = test_root / 'roadmap_data.json'
roadmap_server.BACKUP_FILE = test_root / 'roadmap_data.backup.json'
app = roadmap_app.RoadmapApp(0, data_dir=test_root)
app.set_application_id('org.local.ThesisRoadmap.FeaturesCheck')
app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
failures = []
started = False
phase = 'functional'

xlib = ctypes.CDLL(ctypes.util.find_library('X11'))
xtest = ctypes.CDLL(ctypes.util.find_library('Xtst'))
xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
xlib.XOpenDisplay.restype = ctypes.c_void_p
xlib.XFlush.argtypes = [ctypes.c_void_p]
xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]
xlib.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
xlib.XKeysymToKeycode.restype = ctypes.c_uint
xtest.XTestFakeMotionEvent.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ulong]
xtest.XTestFakeButtonEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
xtest.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
display = xlib.XOpenDisplay(None)


def finish(error=None):
    if error:
        failures.append(str(error))
        print('FAIL:', error, flush=True)
    xtest.XTestFakeButtonEvent(display, 1, 0, 0)
    xlib.XFlush(display)
    app.window.destroy()
    app.quit()
    return False


def evaluate(script):
    def done(view, result):
        try:
            view.evaluate_javascript_finish(result)
        except Exception as error:
            finish(error)
    app.view.evaluate_javascript(script + '; undefined;', -1, None, None, None, done)
    return False


def screenshot(name):
    allocation = app.view.get_allocation()
    pixbuf = Gdk.pixbuf_get_from_window(app.view.get_window(), 0, 0, allocation.width, allocation.height)
    pixbuf.savev('/tmp/roadmap-features-' + name + '.png', 'png', [], [])


FUNCTIONAL = r'''
    void (async () => {
        window.check = (condition, message) => { if (!condition) throw new Error(message); };
        window.pause = ms => new Promise(resolve => setTimeout(resolve, ms));
        window.disk = async () => (await fetch('/api/roadmap')).json();
        window.report = message => window.webkit.messageHandlers.featuresCheck.postMessage(message);
        window.fail = error => report({kind:'error', message:error.message + ' | ' + error.stack});
        window.shortcut = key => document.dispatchEvent(new KeyboardEvent('keydown', {key, ctrlKey:true, bubbles:true, cancelable:true}));
        window.edit = (key, value) => {
            const field = document.getElementById(`field-${key}`);
            field.value = value;
            field.dispatchEvent(new Event('input', {bubbles:true}));
        };
        window.initialData = JSON.stringify(thesisData);
        window.initialCollapsed = [...collapsedIds];
        window.resetFixture = () => {
            window.clearTimeout(autosaveTimer);
            thesisData = JSON.parse(initialData);
            selectedNodeId = thesisData.id;
            collapsedIds = new Set(initialCollapsed);
            editorDirty = false;
            undoStack.length = redoStack.length = 0;
            renderAll(false);
        };
        check(typeof notesMarkdown?.parse === 'function', 'Preview parser did not load');
        check(document.getElementById('undo-change').disabled, 'Undo should start disabled');
        document.getElementById('notes-panel').open = true;
        const notes = document.getElementById('field-notes');
        const preview = document.getElementById('notes-preview');
        const sample = String.raw`# Research notes

Inline $E=mc^2$ and \(x_1+x_2\).

$$\frac{d\sigma}{d\Omega}=\frac{N}{N_b N_t\Delta\Omega}$$

\[\begin{aligned} a &= b+c \\ c &= d \end{aligned}\]

Markdown *emphasis* and **bold**.
` + '\n`$literal$`\n\n```tex\n$not_math$\n```\n\n<img src="invalid" onerror="window.notesInjected=true">\n\n[bad](javascript:alert(1))\n';
        edit('notes', sample);
        await pause(250);
        check(preview.querySelectorAll('.katex').length === 4, 'Expected four rendered inline/display equations; got ' + preview.querySelectorAll('.katex').length);
        check(preview.querySelectorAll('.katex-display').length === 2, 'Display equations did not render');
        check(preview.querySelector('strong')?.textContent === 'bold' && preview.querySelector('em')?.textContent === 'emphasis', 'Markdown did not render');
        check(preview.querySelector('code')?.textContent === '$literal$', 'Math inside code should stay literal');
        check(!preview.querySelector('img, script, iframe') && !window.notesInjected, 'Preview executed or loaded raw HTML');
        check(![...preview.querySelectorAll('a')].some(a => a.getAttribute('href')?.startsWith('javascript:')), 'Unsafe Markdown link survived');
        check(notes.value === sample, 'Preview changed the source');
        check(notes.hidden && !preview.hidden && preview.getBoundingClientRect().height >= 850, 'The single Notes surface became smaller or still shows split panels');
        await pause(800);
        await saveQueue;
        check((await disk()).notes === sample, 'Autosave did not preserve exact math source and whitespace');
        shortcut('z');
        check(notes.value === JSON.parse(initialData).notes, 'Ctrl+Z did not undo a text edit');
        shortcut('y');
        check(notes.value === sample && preview.querySelectorAll('.katex').length === 4, 'Ctrl+Y did not restore source and preview');
        shortcut('z');
        edit('notes', 'A new edit invalidates redo');
        commitEditor();
        check(redoStack.length === 0 && document.getElementById('redo-change').disabled, 'A new edit kept obsolete redo');
        edit('notes', '$unfinished');
        await pause(150);
        check(preview.textContent.includes('$unfinished'), 'Incomplete math should remain editable');
        report({kind:'pass', message:'Live math, Markdown, literal code, incomplete input, safe HTML, exact autosave, and text undo/redo'});
        resetFixture();

        const order = thesisData.children.map(n => n.id);
        const last = order.at(-1);
        const count = flattenData(thesisData).length;
        check(reorderBranch(last, 0), 'Reorder operation failed');
        check(thesisData.children[0].id === last && flattenData(thesisData).length === count, 'Reorder lost or misplaced a branch');
        shortcut('z');
        check(thesisData.children.map(n => n.id).join() === order.join(), 'Undo did not restore branch order');
        shortcut('y');
        check(thesisData.children[0].id === last, 'Redo did not restore branch order');
        selectNode(last);
        addChildNode();
        const addedId = selectedNodeId;
        check(findDataById(addedId), 'Add failed');
        shortcut('z');
        check(!findDataById(addedId), 'Undo add failed');
        shortcut('y');
        check(findDataById(addedId), 'Redo add failed');
        const realConfirm = window.confirm;
        window.confirm = () => true;
        deleteSelectedNode();
        window.confirm = realConfirm;
        check(!findDataById(addedId), 'Delete failed');
        shortcut('z');
        check(findDataById(addedId), 'Undo delete failed');
        shortcut('y');
        check(!findDataById(addedId), 'Redo delete failed');
        resetFixture();
        const parent = thesisData.children.find(n => n.children.length);
        selectNode(parent.id);
        const parentBefore = JSON.stringify(findDataById(parent.id).node);
        edit('status', 'completed');
        commitEditor();
        check(flattenData(findDataById(parent.id).node).every(row => row.node.status === 'completed'), 'Status propagation failed');
        shortcut('z');
        check(JSON.stringify(findDataById(parent.id).node) === parentBefore, 'Undo did not restore the whole subtree status');
        shortcut('y');
        check(flattenData(findDataById(parent.id).node).every(row => row.node.status === 'completed'), 'Redo status propagation failed');
        resetFixture();
        const imported = new File([JSON.stringify({id:'import-check', name:'Imported roadmap', children:[], notes:'$x^2$'})], 'import-check.json', {type:'application/json'});
        importData(imported);
        await pause(200);
        check(thesisData.id === 'import-check', 'Import failed');
        shortcut('z');
        check(thesisData.id === JSON.parse(initialData).id, 'Undo import failed');
        shortcut('y');
        check(thesisData.id === 'import-check', 'Redo import failed');
        await saveQueue;
        report({kind:'pass', message:'Undo/redo of reordering, adding, deleting, propagated statuses, and importing'});
        resetFixture();
        edit('notes', String.raw`Final unsaved equation $\alpha+\beta$`);
        check(await window.prepareToClose(), 'Save before close failed');
        check((await disk()).notes === notes.value, 'Close-time save lost the final edit');
        resetFixture();
        await document.fonts.ready;
        window.scrollTo(0, 0);
        await pause(200);
        const source = [...thesisData.children].reverse().find(n => n.children.length);
        check(source && source.children.length > 0, 'The native drag check needs a nonempty branch');
        const movingFirst = source.id === thesisData.children[0].id;
        window.dragId = source.id;
        window.dragOriginalOrder = thesisData.children.map(n => n.id);
        window.dragOriginalSubtree = JSON.stringify(source);
        window.dragExpectedOrder = dragOriginalOrder.filter(id => id !== dragId);
        dragExpectedOrder.splice(movingFirst ? dragExpectedOrder.length : 0, 0, dragId);
        const element = [...document.querySelectorAll('g.node')].find(e => e.__data__.data.id === dragId);
        const first = [...document.querySelectorAll('g.node')].find(e => e.__data__.data.id === (movingFirst ? thesisData.children.at(-1).id : thesisData.children[0].id));
        const bounds = element.querySelector('rect').getBoundingClientRect();
        const target = first.querySelector('rect').getBoundingClientRect();
        report({kind:'drag', x:bounds.left + bounds.width / 2, y:bounds.top + 45, target:target.left + target.width / 2 + (movingFirst ? 40 : -40)});
    })().catch(error => window.webkit.messageHandlers.featuresCheck.postMessage({kind:'error',message:error.message + ' | ' + error.stack}));
'''


def native_key(symbol, control=False):
    modifier = xlib.XKeysymToKeycode(display, 0xffe3)
    keycode = xlib.XKeysymToKeycode(display, symbol)
    if control:
        xtest.XTestFakeKeyEvent(display, modifier, 1, 0)
    xtest.XTestFakeKeyEvent(display, keycode, 1, 0)
    xtest.XTestFakeKeyEvent(display, keycode, 0, 0)
    if control:
        xtest.XTestFakeKeyEvent(display, modifier, 0, 0)
    xlib.XFlush(display)
    return False


def native_drag(message):
    origin = app.view.get_window().get_origin()
    x = origin[1] + message['x']
    y = origin[2] + message['y']
    target = origin[1] + message['target']
    def move(position):
        xtest.XTestFakeMotionEvent(display, -1, round(position), round(y), 0)
        xlib.XFlush(display)
        return False
    def press():
        xtest.XTestFakeButtonEvent(display, 1, 1, 0)
        xlib.XFlush(display)
        for step in range(1, 9):
            GLib.timeout_add(320 + step * 45, lambda step=step: move(x + (target - x) * step / 8))
        GLib.timeout_add(760, release)
        return False
    def release():
        xtest.XTestFakeButtonEvent(display, 1, 0, 0)
        xlib.XFlush(display)
        GLib.timeout_add(450, lambda: evaluate(r'''
            void (async () => {
                check(!branchDrag, 'Drag did not finish');
                check(thesisData.children.map(n => n.id).join() === dragExpectedOrder.join(), 'Real hold-and-drag did not move the branch');
                check(JSON.stringify(findDataById(dragId).node) === dragOriginalSubtree, 'Dragging changed the branch contents or descendants');
                await saveQueue;
                check((await disk()).children.map(n => n.id).join() === dragExpectedOrder.join(), 'Dragged order was not saved');
                report({kind:'native-undo'});
            })().catch(fail);
        '''))
        return False
    move(x)
    GLib.timeout_add(100, press)


def report(manager, result):
    global phase
    message = json.loads(result.get_js_value().to_json(0))
    kind = message['kind']
    if kind == 'error':
        finish(message['message'])
    elif kind == 'pass':
        print('PASS:', message['message'], flush=True)
    elif kind == 'drag':
        native_drag(message)
    elif kind == 'native-undo':
        print('PASS: Real hold-and-drag reorders a branch with all descendants and saves it', flush=True)
        native_key(ord('z'), control=True)
        GLib.timeout_add(350, lambda: evaluate("try { check(thesisData.children.map(n=>n.id).join() === dragOriginalOrder.join(), 'Native Ctrl+Z failed'); report({kind:'native-redo'}); } catch(error) { fail(error); }"))
    elif kind == 'native-redo':
        native_key(ord('y'), control=True)
        GLib.timeout_add(350, lambda: evaluate("try { check(thesisData.children.map(n => n.id).join() === dragExpectedOrder.join(), 'Native Ctrl+Y failed'); report({kind:'preview-screenshot'}); } catch(error) { fail(error); }"))
    elif kind == 'preview-screenshot':
        print('PASS: Native Ctrl+Z and Ctrl+Y restore branch order', flush=True)
        evaluate(r'''
            selectNode(thesisData.id);
            edit('notes', String.raw`# Equations

Inline $E=mc^2$ and $^{68}\mathrm{Ni}(d,p)^{69}\mathrm{Ni}$.

$$\frac{d\sigma}{d\Omega}=\frac{N}{N_b\,N_t\,\Delta\Omega}$$

- **Source** and rendered equations stay together.
- Notes save automatically.
`);
            updateNotesPreview();
            document.getElementById('notes-panel').scrollIntoView({block:'start'});
            setTimeout(() => report({kind:'done'}), 350);
        ''')
    elif kind == 'done':
        screenshot('notes')
        finish()


def loaded(view, event):
    global started
    if event == WebKit2.LoadEvent.FINISHED and not started:
        started = True
        GLib.timeout_add(700, lambda: evaluate(FUNCTIONAL))


def activated(application):
    manager = app.view.get_user_content_manager()
    manager.register_script_message_handler('featuresCheck')
    manager.connect('script-message-received::featuresCheck', report)
    app.view.connect('load-changed', loaded)


app.connect_after('activate', activated)
GLib.timeout_add_seconds(45, lambda: finish('Feature checks timed out'))
app.run([])
xlib.XCloseDisplay(display)
for name, digest in original_hashes.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, 'Live data changed: ' + name
print('Versioned starter template unchanged; all writes used a temporary profile.', flush=True)
temporary.cleanup()
raise SystemExit(bool(failures))
