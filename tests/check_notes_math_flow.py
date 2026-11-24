"""Check that neighboring live-preview equations reflow with edited source.

Uses the production GTK/WebKit app with temporary generic data. --output saves
fictional on-screen screenshots and geometry; --frontend-root serves another
frontend without ever opening that frontend's working roadmap data.
"""

import argparse
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
    const errors = [];
    window.addEventListener('error', event => errors.push(event.error?.stack || event.message));
    window.addEventListener('unhandledrejection', event => errors.push(String(event.reason?.stack || event.reason)));
    const report = message => window.webkit.messageHandlers.mathFlowCheck.postMessage(message);
    const shot = metadata => new Promise(resolve => {
        window.resumeMathFlowCheck = resolve;
        report({kind:'frame', ...metadata});
    });
    const rect = element => {
        const box = element.getBoundingClientRect ? element.getBoundingClientRect() : element;
        return {left:box.left,right:box.right,top:box.top,bottom:box.bottom,width:box.width,height:box.height};
    };
    const rangeRect = (from, to) => {
        const first = notesEditor.view.domAtPos(from);
        const last = notesEditor.view.domAtPos(to);
        const range = document.createRange();
        range.setStart(first.node, first.offset);
        range.setEnd(last.node, last.offset);
        return {...rect(range),fragments:[...range.getClientRects()].map(rect).filter(box => box.width > 0 && box.height > 0)};
    };
    const overlaps = (first, second) => Math.min(first.right, second.right) - Math.max(first.left, second.left) > 1 && Math.min(first.bottom, second.bottom) - Math.max(first.top, second.top) > 3;
    const formula = from => [...document.querySelectorAll('.notes-math-widget')].find(element => Number(element.dataset.from) === from);
    const measure = (from, following) => {
        const widget = formula(from);
        assert(widget, 'The neighboring formula is no longer rendered');
        const outer = rect(widget);
        const bases = [...widget.querySelectorAll('.katex-html')].map(rect);
        const tail = rangeRect(following, following + 5);
        assert(bases.length && bases.every(box => box.width > 0), 'The formula has no visible KaTeX geometry');
        for (const base of bases) {
            assert(base.left >= outer.left - 2 && base.right <= outer.right + 2, 'Formula glyphs escaped their flow box: ' + JSON.stringify({outer,base}));
            assert(!tail.fragments.some(fragment => overlaps(base, fragment)), 'The neighboring formula overlaps following prose: ' + JSON.stringify({base,tail}));
        }
        return {outer,bases,tail};
    };
    const at = async position => {
        focusNotesAtOffset(position);
        await wait(160);
        assert(notesEditor.view.hasFocus, 'Moving the caret lost editor focus');
        assert(notesEditor.view.state.selection.main.head === position, 'The caret moved to the wrong source offset');
    };
    await wait(650);
    assert(thesisData?.name === 'My Thesis', 'Math-flow check did not load isolated generic data');
    assert(notesEditor.view, 'The Notes source editor did not initialize');
    document.getElementById('notes-panel').open = true;
    if (document.getElementById('sidebar-toggle').getAttribute('aria-expanded') === 'true') document.getElementById('sidebar-toggle').click();
    const canonical = document.getElementById('field-notes');
    const surface = document.getElementById('notes-preview');
    const toggle = document.getElementById('notes-preview-toggle');
    if (!toggle.checked) toggle.click();
    const cases = [
        {name:'inline-dollar',width:1100,first:'$^{70}\\mathrm{Zn}$',second:'$^{68}\\mathrm{Ni}$',prefix:'Compare the production of ',between:' with ',tail:' in the measured counts.'},
        {name:'inline-double-dollar',width:1100,first:'$$^{70}\\mathrm{Zn}$$',second:'$$^{68}\\mathrm{Ni}$$',prefix:'Compare the production of ',between:' with ',tail:' in the measured counts.'},
        {name:'wrapped-source',width:430,first:'$\\color{blue}{\\operatorname{LongName}}$',second:'$^{68}\\mathrm{Ni}$',prefix:'Observe ',between:' beside ',tail:' and following prose.'}
    ];
    for (const fixture of cases) {
        surface.style.width = `${fixture.width}px`;
        surface.style.maxWidth = '100%';
        const line = fixture.prefix + fixture.first + fixture.between + fixture.second + fixture.tail;
        const text = line + '\n\nPlain tail for the caret.\n';
        canonical.value = text;
        canonical.dispatchEvent(new Event('input', {bubbles:true}));
        updateNotesPreview();
        await document.fonts.ready;
        const firstFrom = text.indexOf(fixture.first);
        const secondFrom = text.indexOf(fixture.second);
        const following = text.indexOf(fixture.name === 'wrapped-source' ? 'following' : 'measured');
        await at(text.indexOf('Plain tail') + 5);
        surface.scrollIntoView({block:'start'});
        await wait(120);
        const originalWidget = formula(secondFrom);
        const before = measure(secondFrom, following);
        await shot({fixture:fixture.name,phase:'rendered',geometry:before});
        await at(firstFrom + (fixture.first.startsWith('$$') ? 3 : 2));
        assert(!formula(firstFrom), 'The first equation did not expose its source');
        assert(formula(secondFrom) === originalWidget, 'Editing the first equation replaced the neighboring rendered equation');
        const during = measure(secondFrom, following);
        const displacement = Math.hypot(during.outer.left - before.outer.left, during.outer.top - before.outer.top);
        assert(displacement > 15, 'The neighboring equation did not move when preceding source expanded');
        if (fixture.name !== 'wrapped-source') {
            assert(Math.abs(during.tail.top - before.tail.top) < 2, 'The wide equation fixture unexpectedly wrapped');
            const formulaDelta = during.outer.left - before.outer.left;
            const proseDelta = during.tail.left - before.tail.left;
            assert(Math.abs(formulaDelta - proseDelta) < 2, 'The neighboring equation did not shift with its following prose: ' + JSON.stringify({formulaDelta,proseDelta}));
        }
        const patch = rect(formula(secondFrom).closest('.cm-line'));
        const caret = notesEditor.view.coordsAtPos(notesEditor.view.state.selection.main.head);
        await shot({fixture:fixture.name,phase:'first-source',geometry:during,patch,caret});
        // A full repaint supplies a fresh visual reference without changing text,
        // selection, focus, layout, or the identities of neighboring math widgets.
        notesEditor.view.contentDOM.style.opacity = '0';
        await wait(160);
        notesEditor.view.contentDOM.style.opacity = '';
        await wait(200);
        assert(notesEditor.view.hasFocus && notesEditor.view.state.selection.main.head === firstFrom + (fixture.first.startsWith('$$') ? 3 : 2), 'Reference repaint changed the active source selection');
        const fresh = measure(secondFrom, following);
        assert(JSON.stringify(fresh) === JSON.stringify(during), 'Reference repaint changed formula or prose geometry');
        await shot({fixture:fixture.name,phase:'first-source-repaint',geometry:fresh,patch:rect(formula(secondFrom).closest('.cm-line')),caret:notesEditor.view.coordsAtPos(notesEditor.view.state.selection.main.head)});
        await at(text.indexOf('Plain tail') + 5);
        const restored = measure(secondFrom, following);
        assert(Math.abs(restored.outer.left - before.outer.left) < 2 && Math.abs(restored.outer.top - before.outer.top) < 2, 'Leaving source did not restore equation placement');
        await at(secondFrom + (fixture.second.startsWith('$$') ? 3 : 2));
        assert(!formula(secondFrom) && formula(firstFrom), 'Entering the second formula changed the wrong rendered formula');
        const tail = rangeRect(following, following + 5);
        for (const base of formula(firstFrom).querySelectorAll('.katex-html')) assert(!tail.fragments.some(fragment => overlaps(rect(base), fragment)), 'The first formula overlapped prose when the second entered source');
        await shot({fixture:fixture.name,phase:'second-source',geometry:{first:rect(formula(firstFrom)),tail}});
        await at(text.indexOf('Plain tail') + 5);
        assert(canonical.value === text && notesEditor.view.state.doc.toString() === text, 'Reflow changed the exact Markdown/LaTeX source');
        assert(!errors.length, 'Live-preview reflow raised a browser error: ' + errors.join('\n'));
        report({kind:'pass',message:fixture.name + ': neighboring equation follows expanded source, preserves output, and avoids prose overlap'});
    }
    surface.style.width = '900px';
    const displayText = 'Display equation:\n\n$$\\frac{a}{b}$$\n\nFollowing standalone prose.\n';
    canonical.value = displayText;
    canonical.dispatchEvent(new Event('input', {bubbles:true}));
    updateNotesPreview();
    await at(displayText.indexOf('Following') + 3);
    const display = formula(displayText.indexOf('$$'));
    assert(display?.querySelector('.katex-display .mfrac'), 'Standalone display math lost its displayed fraction');
    const displayBase = rect(display.querySelector('.mfrac'));
    const displayBox = rect(display);
    assert(Math.abs((displayBase.left + displayBase.right) / 2 - (displayBox.left + displayBox.right) / 2) < 4, 'Standalone equation is no longer centered');
    assert(displayBase.bottom < rangeRect(displayText.indexOf('Following'), displayText.indexOf('Following') + 5).top, 'Standalone equation overlaps its following paragraph');
    assert(canonical.value === displayText && notesEditor.view.state.doc.toString() === displayText, 'Standalone display rendering changed source');
    await shot({fixture:'standalone-display',phase:'rendered',geometry:{displayBase,displayBox}});
    report({kind:'pass',message:'Standalone display math remains centered and source stays exact'});
    report({kind:'done'});
})().catch(error => window.webkit.messageHandlers.mathFlowCheck.postMessage({kind:'error',message:String(error.message || error) + ' | ' + String(error.stack || '')}));
'''


def compare_repaint(original, fresh):
    import math
    scale = original['scale']
    patch = original['metadata']['patch']
    left = max(0, math.floor(patch['left'] * scale) - 2)
    right = min(original['width'], math.ceil(patch['right'] * scale) + 2)
    top = max(0, math.floor(patch['top'] * scale) - 8)
    bottom = min(original['height'], math.ceil(patch['bottom'] * scale) + 8)
    masks = []
    for frame in (original, fresh):
        caret = frame['metadata']['caret']
        masks.append((math.floor(caret['left'] * scale) - 4, math.floor(caret['top'] * scale) - 3, math.ceil(caret['right'] * scale) + 4, math.ceil(caret['bottom'] * scale) + 3))
    changed, changed20, maximum, ink = 0, 0, 0, 0
    for y in range(top, bottom):
        for x in range(left, right):
            if any(x0 <= x <= x1 and y0 <= y <= y1 for x0, y0, x1, y1 in masks):
                continue
            a = y * original['stride'] + x * original['channels']
            b = y * fresh['stride'] + x * fresh['channels']
            before = original['pixels'][a:a + 3]
            after = fresh['pixels'][b:b + 3]
            difference = max(abs(first - second) for first, second in zip(before, after))
            changed += difference > 0
            changed20 += difference > 20
            maximum = max(maximum, difference)
            ink += min(after) < 180
    if ink < 300:
        raise AssertionError('The repaint comparison patch contains too little text')
    return {'patch':[left,top,right,bottom],'changedPixels':changed,'changedOver20':changed20,'maximumDifference':maximum}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frontend-root', type=Path)
    parser.add_argument('--output', type=Path)
    options = parser.parse_args()
    if options.output:
        options.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='roadmap-math-flow-') as temporary:
        profile = Path(temporary)
        for variable, directory in [('XDG_DATA_HOME','share'),('XDG_CACHE_HOME','cache'),('XDG_CONFIG_HOME','config')]:
            os.environ[variable] = str(profile / directory)
        os.environ['GSETTINGS_BACKEND'] = 'memory'
        import roadmap_app
        import roadmap_server
        if options.frontend_root:
            roadmap_server.ROOT = options.frontend_root.resolve()
        from gi.repository import Gdk, Gio, GLib, WebKit2
        application = roadmap_app.RoadmapApp(0, data_dir=profile / 'data')
        application.set_application_id('org.thesisroadmap.App.MathFlowCheck')
        application.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        failures, frames, started, completed = [], [], [], []
        images, pixel_checks = {}, []

        def stop(message=None):
            if message:
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
                    stop(error)
            application.view.evaluate_javascript(script + '; undefined;', -1, None, None, None, done)
            return False

        def received(manager, result):
            message = json.loads(result.get_js_value().to_json(0))
            if message['kind'] == 'error':
                stop(message['message'])
            elif message['kind'] == 'pass':
                print('PASS:', message['message'], flush=True)
            elif message['kind'] == 'frame':
                frames.append(message)
                allocation = application.view.get_allocation()
                image = Gdk.pixbuf_get_from_window(application.view.get_window(), 0, 0, allocation.width, allocation.height)
                captured = {'pixels':bytes(image.get_pixels()),'width':image.get_width(),'height':image.get_height(),'stride':image.get_rowstride(),'channels':image.get_n_channels(),'metadata':message,'scale':application.view.get_zoom_level() * image.get_width() / allocation.width}
                if options.output:
                    name = '%s-%s.png' % (message['fixture'], message['phase'])
                    image.savev(str(options.output / name), 'png', [], [])
                if message['phase'] == 'first-source':
                    images[message['fixture']] = captured
                elif message['phase'] == 'first-source-repaint':
                    original = images[message['fixture']]
                    result = compare_repaint(original, captured)
                    pixel_checks.append({'fixture':message['fixture'],**result})
                    if result['changedPixels']:
                        stop('Neighboring formula pixels differ from a fresh repaint after source expansion: ' + json.dumps(result))
                        return
                evaluate('window.resumeMathFlowCheck();')
            elif message['kind'] == 'done':
                completed.append(True)
                stop()

        def loaded(view, event):
            if event != WebKit2.LoadEvent.FINISHED or started:
                return
            started.append(True)
            evaluate(CHECKS)

        def activated(app):
            manager = application.view.get_user_content_manager()
            manager.register_script_message_handler('mathFlowCheck')
            manager.connect('script-message-received::mathFlowCheck', received)
            application.view.connect('load-changed', loaded)

        application.connect_after('activate', activated)
        GLib.timeout_add_seconds(45, lambda: stop('Math-flow checks timed out'))
        application.run([])
        if options.output:
            (options.output / 'result.json').write_text(json.dumps({'frames':frames,'pixelChecks':pixel_checks,'errors':failures,'completed':bool(completed)}, indent=2) + '\n')
        if not failures and not completed:
            raise AssertionError('Math-flow checks did not complete')
        return bool(failures)


if __name__ == '__main__':
    raise SystemExit(main())
