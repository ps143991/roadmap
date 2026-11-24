"""Exercise real branch dragging from labels and card backgrounds.

Uses production GTK/WebKit with temporary fictional data. Requires X11/libXtst.
--frontend-root selects alternate static assets without opening their working data.
"""

import argparse
import ctypes
import ctypes.util
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CHECKS = r'''
void (async () => {
    const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
    const assert = (condition, message) => { if (!condition) throw new Error(message); };
    const report = message => window.webkit.messageHandlers.branchDragCheck.postMessage(message);
    const native = gesture => new Promise(resolve => {
        window.resumeBranchDragCheck = resolve;
        report({kind:'native',...gesture});
    });
    const findElement = id => [...document.querySelectorAll('g.node')].find(element => element.__data__.data.id === id);
    const order = parent => parent.children.map(node => node.id).join();
    const disk = async () => (await fetch('/api/roadmap')).json();
    const leaf = id => ({id,name:'A detailed nested task label for ' + id,type:'task',children:[]});
    const chapter = letter => ({id:'chapter-'+letter,name:'Chapter '+letter+': a descriptive multi line branch title',type:'chapter',children:[0,1,2].map(index => ({...leaf('task-'+letter+'-'+index),children:[leaf('detail-'+letter+'-'+index)]}))});
    const fixture = {id:'drag-root',name:'Fictional drag test',type:'root',notes:'',children:['a','b','c','d','e'].map(chapter)};
    await wait(650);
    assert(thesisData?.name === 'My Thesis', 'The drag check did not load isolated generic data');
    if (document.getElementById('sidebar-toggle').getAttribute('aria-expanded') === 'true') document.getElementById('sidebar-toggle').click();
    await wait(450);
    window.dragPointerEvents = [];
    for (const type of ['pointerdown','gotpointercapture','lostpointercapture','pointercancel','pointerup']) document.addEventListener(type, event => {
        const node = event.target.closest?.('g.node');
        if (node) dragPointerEvents.push({type,id:node.__data__?.data.id,target:event.target.tagName});
    }, true);
    const reset = async nested => {
        cancelBranchDrag();
        window.clearTimeout(autosaveTimer);
        thesisData = JSON.parse(JSON.stringify(fixture));
        normalizeData(thesisData);
        selectedNodeId = thesisData.id;
        collapsedIds = new Set(thesisData.children.map(node => node.id));
        if (nested) collapsedIds.delete('chapter-a');
        editorDirty = false;
        undoStack.length = redoStack.length = 0;
        suppressedBranchClick = null;
        document.getElementById('notes-panel').open = false;
        renderAll(false);
        window.getSelection().removeAllRanges();
        window.dragPointerEvents.length = 0;
        await document.fonts.ready;
        await wait(220);
    };
    const point = (id, label) => {
        const element = findElement(id);
        assert(element, 'Missing visible branch '+id);
        element.scrollIntoView({block:'center',inline:'nearest'});
        const box = element.querySelector('rect').getBoundingClientRect();
        if (!label) return {x:box.left+box.width/2,y:box.top+64};
        const spans = [...element.querySelectorAll('text:not(.node-subtitle) tspan')];
        const text = spans[1] || spans[0];
        const bounds = text.getBoundingClientRect();
        for (let x = Math.ceil(bounds.left)+1; x < bounds.right-1; x += 2) {
            const y = Math.round(bounds.top+bounds.height/2);
            const hit = document.elementFromPoint(x,y);
            if (hit?.closest('text') && hit.closest('g.node') === element) return {x,y};
        }
        throw new Error('Could not find an actual SVG label hit point for '+id);
    };
    const cases = [
        {name:'first sibling label to middle',id:'chapter-a',target:'chapter-c',after:true,label:true},
        {name:'middle sibling label to first',id:'chapter-c',target:'chapter-a',after:false,label:true},
        {name:'last sibling label with early movement',id:'chapter-e',target:'chapter-b',after:true,label:true,early:true},
        {name:'first sibling card background to last',id:'chapter-a',target:'chapter-e',after:true,label:false},
        {name:'nested first sibling label to last',id:'task-a-0',target:'task-a-2',after:true,label:true,nested:true}
    ];
    for (const item of cases) {
        await reset(item.nested);
        const moving = findDataById(item.id);
        const before = order(moving.parent);
        const subtree = JSON.stringify(moving.node);
        const ids = moving.parent.children.map(node => node.id).filter(id => id !== item.id);
        const index = ids.indexOf(item.target)+(item.after?1:0);
        ids.splice(index,0,item.id);
        const expected = ids.join();
        point(item.id,item.label);
        point(item.target,false);
        // Both cards must be visible at the same time; convert the start after any scrolling.
        const current = point(item.id,item.label);
        const bounds = document.getElementById('tree-container').getBoundingClientRect();
        const sourceBox = findElement(item.id).querySelector('rect').getBoundingClientRect();
        const targetBox = findElement(item.target).querySelector('rect').getBoundingClientRect();
        const grabOffset = current.x-sourceBox.left-sourceBox.width/2;
        const targetX = Math.max(bounds.left+16,Math.min(bounds.right-16,targetBox.left+targetBox.width/2+(item.after?55:-55)+grabOffset));
        await native({action:'drag',...current,targetX,targetY:current.y,early:Boolean(item.early)});
        const actual = order(findDataById(item.id).parent);
        assert(actual === expected, item.name+' failed: '+JSON.stringify({before,expected,actual,selection:String(window.getSelection()),events:dragPointerEvents,drag:Boolean(branchDrag)}));
        assert(!String(window.getSelection()), item.name+' selected page text');
        assert(JSON.stringify(findDataById(item.id).node) === subtree, item.name+' changed its descendants');
        await saveQueue;
        const saved = await disk();
        const locate = node => node.id === moving.parent.id ? node : (node.children||[]).map(locate).find(Boolean);
        assert(order(locate(saved)) === expected, item.name+' did not autosave the order');
        await native({action:'key',key:'z',control:true});
        assert(order(findDataById(item.id).parent) === before, item.name+' Ctrl+Z failed');
        await native({action:'key',key:'y',control:true});
        assert(order(findDataById(item.id).parent) === expected, item.name+' Ctrl+Y failed');
        report({kind:'pass',message:item.name+': real mouse drag, intact descendants, no selection, autosave, undo/redo'});
    }
    for (const cancel of ['outside','escape']) {
        await reset(false);
        const original = order(thesisData);
        const start = point('chapter-b',true);
        const bounds = document.getElementById('tree-container').getBoundingClientRect();
        await native({action:'drag',...start,targetX:cancel==='outside'?bounds.left-12:start.x+150,targetY:start.y,cancel});
        assert(order(thesisData) === original, cancel+' cancellation changed branch order');
        assert(!branchDrag && !document.body.classList.contains('branch-dragging'), cancel+' cancellation left dragging active');
        assert(!String(window.getSelection()), cancel+' cancellation selected page text');
        report({kind:'pass',message:cancel+' cancellation leaves order and selection unchanged'});
    }
    await reset(false);
    const click = point('chapter-a',true);
    await native({action:'click',...click});
    assert(selectedNodeId === 'chapter-a', 'A normal label click no longer selects the branch');
    assert(document.activeElement === findElement('chapter-a'), 'A label click did not preserve keyboard focus');
    const keyboardOrder = order(thesisData);
    await native({action:'key',key:'Right',alt:true});
    assert(thesisData.children[1].id === 'chapter-a', 'Alt+Right no longer reorders the focused branch');
    await native({action:'key',key:'z',control:true});
    assert(order(thesisData) === keyboardOrder, 'Undo did not restore keyboard reordering');
    await native({action:'doubleclick',...point('chapter-a',true)});
    assert(findElement('task-a-0'), 'A label double-click no longer expands the branch');
    await native({action:'doubleclick',...point('chapter-a',true)});
    assert(!findElement('task-a-0'), 'A second label double-click no longer collapses the branch');
    report({kind:'pass',message:'Normal label clicks and double-click expansion/collapse remain usable'});
    report({kind:'done'});
})().catch(error => window.webkit.messageHandlers.branchDragCheck.postMessage({kind:'error',message:String(error.message||error)+' | '+String(error.stack||'')}));
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frontend-root', type=Path)
    options = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='roadmap-branch-drag-') as temporary:
        profile = Path(temporary)
        for variable, folder in [('XDG_DATA_HOME','share'),('XDG_CACHE_HOME','cache'),('XDG_CONFIG_HOME','config')]:
            os.environ[variable] = str(profile/folder)
        os.environ['GSETTINGS_BACKEND'] = 'memory'
        import roadmap_app
        import roadmap_server
        if options.frontend_root:
            roadmap_server.ROOT = options.frontend_root.resolve()
        from gi.repository import Gio, GLib, WebKit2
        app = roadmap_app.RoadmapApp(0,data_dir=profile/'data')
        app.set_application_id('org.thesisroadmap.App.BranchDragCheck')
        app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        xlib = ctypes.CDLL(ctypes.util.find_library('X11'))
        xtest = ctypes.CDLL(ctypes.util.find_library('Xtst'))
        xlib.XOpenDisplay.argtypes, xlib.XOpenDisplay.restype = [ctypes.c_char_p], ctypes.c_void_p
        xlib.XFlush.argtypes = [ctypes.c_void_p]
        xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]
        xlib.XKeysymToKeycode.argtypes, xlib.XKeysymToKeycode.restype = [ctypes.c_void_p,ctypes.c_ulong], ctypes.c_uint
        xtest.XTestFakeMotionEvent.argtypes = [ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_ulong]
        xtest.XTestFakeButtonEvent.argtypes = [ctypes.c_void_p,ctypes.c_uint,ctypes.c_int,ctypes.c_ulong]
        xtest.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p,ctypes.c_uint,ctypes.c_int,ctypes.c_ulong]
        display = xlib.XOpenDisplay(None)
        failures, completed, started = [], [], []

        def motion(x,y):
            origin = app.view.get_window().get_origin()
            xtest.XTestFakeMotionEvent(display,-1,round(origin[1]+x),round(origin[2]+y),0)
            xlib.XFlush(display)
            return False

        def button(down):
            xtest.XTestFakeButtonEvent(display,1,int(down),0)
            xlib.XFlush(display)
            return False

        def key(symbol,control=False,alt=False):
            modifier = xlib.XKeysymToKeycode(display,0xffe9 if alt else 0xffe3)
            code = xlib.XKeysymToKeycode(display,symbol)
            if control or alt: xtest.XTestFakeKeyEvent(display,modifier,1,0)
            xtest.XTestFakeKeyEvent(display,code,1,0)
            xtest.XTestFakeKeyEvent(display,code,0,0)
            if control or alt: xtest.XTestFakeKeyEvent(display,modifier,0,0)
            xlib.XFlush(display)
            return False

        def stop(error=None):
            if error:
                failures.append(str(error))
                print('FAIL:',error,flush=True)
            button(False)
            app.window.destroy()
            app.quit()
            return False

        def evaluate(script):
            def done(view,result):
                try: view.evaluate_javascript_finish(result)
                except Exception as error: stop(error)
            app.view.evaluate_javascript(script+';undefined;',-1,None,None,None,done)
            return False

        def resume():
            return evaluate('window.resumeBranchDragCheck();')

        def gesture(message):
            action = message['action']
            if action == 'key':
                key({'Left':0xff51,'Right':0xff53}.get(message['key'],ord(message['key']) if len(message['key']) == 1 else 0),message.get('control',False),message.get('alt',False))
                GLib.timeout_add(220,resume)
                return
            motion(message['x'],message['y'])
            if action in ('click','doubleclick'):
                GLib.timeout_add(60,lambda:button(True))
                GLib.timeout_add(100,lambda:button(False))
                if action == 'doubleclick':
                    GLib.timeout_add(180,lambda:button(True))
                    GLib.timeout_add(220,lambda:button(False))
                GLib.timeout_add(500,resume)
                return
            def press():
                button(True)
                delay = 25 if message.get('early') else 350
                for index in range(1,13):
                    x = message['x']+(message['targetX']-message['x'])*index/12
                    y = message['y']+(message['targetY']-message['y'])*index/12
                    GLib.timeout_add(delay+index*42,lambda x=x,y=y:motion(x,y))
                if message.get('cancel') == 'escape': GLib.timeout_add(delay+530,lambda:key(0xff1b))
                GLib.timeout_add(delay+580,lambda:button(False))
                GLib.timeout_add(delay+900,resume)
                return False
            GLib.timeout_add(80,press)

        def received(manager,result):
            message = json.loads(result.get_js_value().to_json(0))
            if message['kind'] == 'error': stop(message['message'])
            elif message['kind'] == 'native': gesture(message)
            elif message['kind'] == 'pass': print('PASS:',message['message'],flush=True)
            elif message['kind'] == 'done': completed.append(True);stop()

        def loaded(view,event):
            if event == WebKit2.LoadEvent.FINISHED and not started:
                started.append(True)
                evaluate(CHECKS)

        def activated(application):
            manager = app.view.get_user_content_manager()
            manager.register_script_message_handler('branchDragCheck')
            manager.connect('script-message-received::branchDragCheck',received)
            app.view.connect('load-changed',loaded)

        app.connect_after('activate',activated)
        GLib.timeout_add_seconds(75,lambda:stop('Native branch drag checks timed out'))
        app.run([])
        xlib.XCloseDisplay(display)
        if not completed and not failures:
            failures.append('Drag checks did not complete')
        return bool(failures)


if __name__ == '__main__':
    raise SystemExit(main())
