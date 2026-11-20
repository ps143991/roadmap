"""Exercise cursor-local Markdown and math Notes editing using an isolated profile.

Run in a desktop session, or with xvfb-run. --frontend-root can select another
frontend checkout while all saves still go to temporary generic test data.
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
        window.notesEditorWindowErrors = [];
        window.addEventListener('error', event => {
            if (event.error || event.message) notesEditorWindowErrors.push(event.error?.stack || event.message);
        });
        window.addEventListener('unhandledrejection', event => notesEditorWindowErrors.push(event.reason?.stack || String(event.reason)));
        const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
        const assert = (condition, message) => { if (!condition) throw new Error(message); };
        const report = message => window.webkit.messageHandlers.notesEditorCheck.postMessage(message);
        const visible = element => element && element.getClientRects().length > 0 && getComputedStyle(element).visibility !== 'hidden';
        const shortcut = key => document.dispatchEvent(new KeyboardEvent('keydown', {key, ctrlKey:true, bubbles:true, cancelable:true}));
        const readDisk = async () => (await fetch('/api/roadmap')).json();
        const view = () => notesEditor.view;
        const source = () => view().state.doc.toString();
        const selected = () => view().state.selection.main;
        const setSource = text => {
            const canonical = document.getElementById('field-notes');
            canonical.value = text;
            canonical.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'insertText'}));
            updateNotesPreview();
        };
        const at = async position => {
            focusNotesAtOffset(position);
            await wait(90);
            assert(view().hasFocus, 'Moving the cursor did not focus the Notes editor');
            assert(selected().from === position && selected().to === position, 'Cursor position changed unexpectedly');
        };
        const elementAt = position => {
            const point = view().domAtPos(position);
            if (point.node.nodeType === Node.TEXT_NODE) return point.node.parentElement;
            return point.node;
        };
        const lineTextAt = position => elementAt(position).closest('.cm-line')?.textContent || '';
        const plainStyle = position => {
            const element = elementAt(position);
            const computed = getComputedStyle(element);
            let opacity = 1;
            for (let current = element; current; current = current.parentElement) opacity *= Number(getComputedStyle(current).opacity);
            return {family:computed.fontFamily,size:computed.fontSize,weight:computed.fontWeight,style:computed.fontStyle,color:computed.color,fill:computed.webkitTextFillColor,opacity};
        };
        const mathAt = position => [...document.querySelectorAll('.notes-math-widget')].find(element => Number(element.dataset.from) === position);
        const ordinaryStyles = (text, labels) => {
            const expected = plainStyle(text.indexOf(labels[0]) + 3);
            assert(['400','normal'].includes(expected.weight) && expected.style === 'normal' && expected.opacity === 1, 'Ordinary prose is bold, italic, or faded: ' + JSON.stringify(expected));
            for (const label of labels) {
                const current = plainStyle(text.indexOf(label) + 3);
                assert(JSON.stringify(current) === JSON.stringify(expected), 'Plain text styling differs for ' + label + ': ' + JSON.stringify(current));
            }
            return JSON.stringify(expected);
        };
        await wait(600);
        assert(thesisData?.name === 'My Thesis', 'Test profile did not load generic data');
        assert(typeof syncActiveNotes === 'function' && notesEditor.view, 'Cursor-local Notes editor did not initialize');
        document.getElementById('notes-panel').open = true;
        const canonical = document.getElementById('field-notes');
        const toggle = document.getElementById('notes-preview-toggle');
        const surface = document.getElementById('notes-preview');
        const rootId = thesisData.id;
        const childId = thesisData.children[0].id;
        if (!toggle.checked) toggle.click();
        const sample = '# Sample Notes\n\nA plain paragraph before **bold text**, *emphasized words*, math $x^2$ and $y^2$, then ordinary text.\n\n- Tight first item with **tight strong** and $a+b$.\n- Tight second item stays ordinary.\n  - Nested item stays ordinary.\n\nA list break.\n\n- Loose first item stays ordinary.\n\n- Loose second item stays ordinary.\n\n$$\n\\frac{a}{b}\n$$\n\nTrailing spaces stay here.  \n';
        const plainLabels = ['A plain paragraph', 'Tight first item', 'Tight second item', 'Nested item', 'Loose first item', 'Loose second item', 'Trailing spaces'];
        setSource(sample);
        await at(sample.indexOf('Trailing spaces') + 4);
        assert(canonical.value === sample && source() === sample, 'Rendering changed source text or whitespace');
        assert(!visible(canonical) && visible(surface), 'Notes shows a second source panel');
        assert(surface.querySelectorAll('.cm-editor').length === 1, 'Notes did not create exactly one source editor');
        assert(surface.getBoundingClientRect().height >= 850, 'Notes surface is smaller than the requested minimum');
        assert(surface.querySelector('.notes-math-widget .mfrac'), 'Display TeX did not render as an actual fraction');
        const strong = [...surface.querySelectorAll('.notes-strong')].find(element => element.textContent === 'bold text');
        const emphasis = [...surface.querySelectorAll('.notes-emphasis')].find(element => element.textContent === 'emphasized words');
        assert(strong && Number(getComputedStyle(strong).fontWeight) >= 600, 'Explicit strong syntax did not render bold');
        assert(emphasis && getComputedStyle(emphasis).fontStyle === 'italic', 'Explicit emphasis syntax did not render italic');
        assert(surface.querySelector('.notes-heading'), 'Heading syntax did not render as a heading');
        const originalStyle = ordinaryStyles(sample, plainLabels);
        report({kind:'pass', message:'One cursor-based source editor, rendered Markdown/math, exact whitespace, and uniform ordinary prose across paragraph/list types'});

        const xFrom = sample.indexOf('$x^2$');
        const yFrom = sample.indexOf('$y^2$');
        const listMathFrom = sample.indexOf('$a+b$');
        const yWidget = mathAt(yFrom);
        const listWidget = mathAt(listMathFrom);
        assert(mathAt(xFrom) && yWidget && listWidget, 'Inactive inline formulas were not rendered');
        await at(xFrom + 2);
        assert(!mathAt(xFrom), 'The formula under the cursor did not expose its source');
        assert(lineTextAt(xFrom + 2).includes('$x^2$'), 'Active formula source is missing');
        assert(mathAt(yFrom) === yWidget && mathAt(listMathFrom) === listWidget, 'Entering one formula replaced unrelated formula widgets');
        assert(!lineTextAt(xFrom + 2).includes('**bold text**') && !lineTextAt(xFrom + 2).includes('*emphasized words*'), 'Editing a formula exposed sibling Markdown syntax in the same paragraph');
        await at(sample.indexOf('ordinary text') + 3);
        assert(mathAt(xFrom) && mathAt(yFrom) === yWidget, 'Leaving one formula did not restore it while keeping its sibling stable');
        const boldFrom = sample.indexOf('**bold text**');
        await at(boldFrom + 4);
        assert(lineTextAt(boldFrom + 4).includes('**bold text**'), 'The strong span under the cursor did not expose its markers');
        assert(!lineTextAt(boldFrom + 4).includes('*emphasized words*') && mathAt(xFrom) && mathAt(yFrom) === yWidget, 'Editing strong text exposed unrelated same-line syntax');
        const emphasisFrom = sample.indexOf('*emphasized words*');
        await at(emphasisFrom + 5);
        assert(lineTextAt(emphasisFrom + 5).includes('*emphasized words*') && !lineTextAt(emphasisFrom + 5).includes('**bold text**'), 'Source exposure did not follow the smallest inline span');
        await at(listMathFrom + 2);
        assert(!mathAt(listMathFrom) && mathAt(xFrom) && mathAt(yFrom) === yWidget, 'Editing one list formula changed formulas in other items');
        assert(!lineTextAt(listMathFrom + 2).includes('**tight strong**'), 'Editing a list formula exposed the rest of its list item');
        await at(sample.indexOf('Tight second item') + 5);
        assert(mathAt(listMathFrom), 'Leaving a list formula did not restore its output');
        assert(ordinaryStyles(sample, plainLabels) === originalStyle, 'Cursor movement changed ordinary text styling');
        assert(canonical.value === sample && source() === sample, 'Cursor-local preview modified the source');
        report({kind:'pass', message:'Only the inline token at the cursor exposes source; same-paragraph and same-list neighbors keep rendered output and stable widget DOM'});

        const displayFrom = sample.indexOf('$$');
        const display = mathAt(displayFrom);
        assert(display?.querySelector('.mfrac'), 'Display equation disappeared before click test');
        display.dispatchEvent(new PointerEvent('pointerdown', {bubbles:true,cancelable:true,button:0,pointerId:1}));
        await wait(90);
        assert(view().hasFocus && selected().head > displayFrom && selected().head < sample.indexOf('$$', displayFrom + 2) + 2, 'Clicking a rendered equation did not place the caret inside its own source');
        assert(!mathAt(displayFrom) && mathAt(xFrom) && mathAt(yFrom) === yWidget, 'Clicking display math exposed or replaced unrelated source');
        await at(sample.indexOf('Trailing spaces') + 4);
        assert(mathAt(displayFrom)?.querySelector('.mfrac'), 'Moving out of display math did not restore its rendered fraction');
        report({kind:'pass', message:'Clicking a rendered equation exposes that equation alone and restores it when the cursor leaves'});


        const punctuationSample = 'Math punctuation $a_b+c$ ordinary_word stays ordinary.\n\nMath multiplication $p*q$ plain*word remains ordinary.\n\n**Strong wrapper around $u_v$ stays intentional.**\n';
        setSource(punctuationSample);
        await at(punctuationSample.indexOf('ordinary_word') + 3);
        ordinaryStyles(punctuationSample, ['Math punctuation', 'ordinary_word', 'Math multiplication', 'plain*word']);
        assert(surface.querySelectorAll('.notes-math-widget').length === 3, 'TeX punctuation prevented an equation from rendering');
        assert(!surface.querySelector('.notes-emphasis'), 'Underscores or stars inside TeX leaked into surrounding Markdown emphasis');
        const intentionalStrong = [...surface.querySelectorAll('.notes-strong')].find(element => element.textContent.includes('Strong wrapper'));
        assert(intentionalStrong && Number(getComputedStyle(intentionalStrong).fontWeight) >= 600, 'Explicit strong markup surrounding math lost its intended formatting');
        assert(canonical.value === punctuationSample && source() === punctuationSample, 'TeX punctuation handling changed source');
        report({kind:'pass', message:'Math underscores/stars are opaque to Markdown without affecting ordinary prose or explicit surrounding strong markup'});


        const autoLink = '<https://example.org/auto>';
        const explicitLink = '[Explicit label](https://example.org/target "Target title")';
        const referenceLink = '[Reference label][paper]';
        const linkSample = 'Links ' + autoLink + ' and ' + explicitLink + ' plus ' + referenceLink + '.\n\n[paper]: https://example.org/reference "Reference title"\n\nPlain link tail.\n';
        setSource(linkSample);
        await at(linkSample.indexOf('Plain link tail') + 4);
        const output = surface.querySelector('.cm-content').textContent;
        assert(output.includes('https://example.org/auto') && !output.includes(autoLink), 'Inactive autolink lost its visible URL or retained its angle markers');
        assert(output.includes('Explicit label') && !output.includes('https://example.org/target') && !output.includes('Target title'), 'Inactive explicit link did not hide only its destination and title');
        assert(output.includes('Reference label') && !output.includes('[paper]') && !output.includes('https://example.org/reference') && !output.includes('Reference title'), 'Reference label or hidden definition rendered incorrectly');
        await at(linkSample.indexOf('Explicit label') + 4);
        let linkLine = lineTextAt(linkSample.indexOf('Links ') + 2);
        assert(linkLine.includes(explicitLink) && !linkLine.includes(referenceLink) && !linkLine.includes(autoLink), 'Entering one explicit link exposed sibling link syntax');
        await at(linkSample.indexOf('Reference label') + 4);
        linkLine = lineTextAt(linkSample.indexOf('Links ') + 2);
        assert(linkLine.includes(referenceLink) && !linkLine.includes(explicitLink) && !linkLine.includes('https://example.org/target') && !linkLine.includes(autoLink), 'Reference-link source exposure did not stay local to that link');
        await at(linkSample.indexOf('https://example.org/auto') + 4);
        linkLine = lineTextAt(linkSample.indexOf('Links ') + 2);
        assert(linkLine.includes(autoLink) && !linkLine.includes(referenceLink) && !linkLine.includes(explicitLink), 'Autolink source exposure did not stay local to that link');
        await at(linkSample.indexOf('Plain link tail') + 4);
        const restoredLinks = surface.querySelector('.cm-content').textContent;
        assert(restoredLinks.includes('https://example.org/auto') && !restoredLinks.includes('https://example.org/target') && !restoredLinks.includes('https://example.org/reference'), 'Leaving links did not restore their output form');
        assert(canonical.value === linkSample && source() === linkSample, 'Link rendering or cursor movement changed Markdown source');
        report({kind:'pass', message:'Autolinks retain their URL, explicit/reference links hide targets and definitions, and only the cursor link exposes source'});
        setSource(sample);
        await at(sample.indexOf('Trailing spaces') + 4);
        await wait(800);
        await saveQueue;

        const editorDOM = view().contentDOM;
        const caret = sample.indexOf('A plain paragraph') + 'A plain paragraph'.length;
        await at(caret);
        let insertion = caret;
        const typed = ' entered without flicker';
        for (const character of typed) {
            view().dispatch({changes:{from:insertion,insert:character},selection:{anchor:insertion + 1}});
            insertion++;
            await wait(20);
            assert(view().contentDOM === editorDOM && document.activeElement === editorDOM, 'Typing replaced the editor or lost focus');
            assert(selected().from === insertion && selected().to === insertion, 'Typing moved the caret');
            assert(JSON.stringify(plainStyle(insertion - 1)) === originalStyle, 'Typing changed ordinary text weight, color, or opacity');
            assert(surface.querySelectorAll('.notes-math-widget').length === 4, 'Typing plain text exposed unrelated math');
            assert(!lineTextAt(insertion).includes('**bold text**'), 'Typing plain text exposed sibling strong markers');
        }
        const changed = sample.slice(0, caret) + typed + sample.slice(caret);
        assert(canonical.value === changed && source() === changed, 'Typing did not synchronize exact canonical Markdown');
        await wait(1100);
        await saveQueue;
        assert((await readDisk()).notes === changed, 'Autosave missed focused Notes edits');
        assert(view().contentDOM === editorDOM && view().hasFocus && selected().head === insertion, 'Autosave replaced the editor or moved the caret');
        assert(JSON.stringify(plainStyle(insertion - 1)) === originalStyle, 'Autosave changed ordinary text styling');
        report({kind:'pass', message:'Rapid typing and autosave preserve editor DOM, caret, focus, and ordinary text styling'});

        shortcut('z');
        await wait(90);
        assert(canonical.value === sample && source() === sample, 'Ctrl+Z did not undo the typing burst');
        assert(view().hasFocus, 'Undo lost Notes focus');
        shortcut('y');
        await wait(90);
        assert(canonical.value === changed && source() === changed, 'Ctrl+Y did not restore the typing burst');
        assert(view().hasFocus && view().contentDOM === editorDOM, 'Redo replaced the Notes editor or lost focus');
        report({kind:'pass', message:'App-level undo/redo preserves the full source and the cursor-based editor'});

        toggle.click();
        await wait(90);
        assert(!toggle.checked && !visible(canonical) && visible(surface), 'Disabling preview did not keep the same single editor');
        assert(view().contentDOM === editorDOM && !surface.querySelector('.notes-math-widget'), 'Disabling preview replaced the editor or left rendered formulas');
        assert(surface.querySelector('.cm-content').textContent.includes('**bold text**'), 'Plain source mode did not expose Markdown markers');
        assert(canonical.value === changed && source() === changed, 'Toggling preview changed source');
        assert(localStorage.getItem(`${STORAGE_KEY}:notes-preview`) === 'false', 'Disabled preview preference was not saved');
        const extra = '\nPlain source addition with $z+1$.  \n';
        view().dispatch({changes:{from:source().length,insert:extra},selection:{anchor:source().length}});
        const fullSource = changed + extra;
        assert(canonical.value === fullSource && source() === fullSource, 'Source mode edits were not synchronized');
        selectNode(childId);
        await wait(90);
        assert(!toggle.checked && !surface.querySelector('.notes-math-widget'), 'Node switching changed the disabled preview preference');
        selectNode(rootId);
        await wait(90);
        assert(canonical.value === fullSource && source() === fullSource, 'Node switching lost source-mode edits');
        toggle.click();
        await at(fullSource.indexOf('Trailing spaces') + 4);
        assert(toggle.checked && view().contentDOM === editorDOM && surface.querySelector('.notes-math-widget .mfrac'), 'Reenabling preview did not restore rendering in the same editor');
        assert(localStorage.getItem(`${STORAGE_KEY}:notes-preview`) === 'true', 'Enabled preview preference was not saved');
        const selectAll = new KeyboardEvent('keydown', {key:'a',code:'KeyA',ctrlKey:true,bubbles:true,cancelable:true});
        view().contentDOM.dispatchEvent(selectAll);
        await wait(60);
        assert(selected().from === 0 && selected().to === fullSource.length, 'Ctrl+A did not select the complete Markdown source');
        assert(canonical.value === fullSource && source() === fullSource, 'Selecting all text changed the source');
        await at(fullSource.indexOf('Trailing spaces') + 4);
        report({kind:'pass', message:'Live preview toggles decorations in one stable editor, preserves source and preferences, and Ctrl+A selects the whole note'});

        const beforeSwitch = source().replace('A plain paragraph', 'A preserved paragraph');
        setSource(beforeSwitch);
        await at(beforeSwitch.indexOf('A preserved paragraph') + 5);
        selectNode(childId);
        await saveQueue;
        assert((await readDisk()).notes === beforeSwitch, 'Switching nodes lost unsaved focused Notes edits');
        assert(canonical.value === findDataById(childId).node.notes && source() === canonical.value, 'Previous node source leaked into the selected node');
        assert(toggle.checked && visible(surface) && !visible(canonical), 'Changing nodes changed the enabled preview mode');
        selectNode(rootId);
        await wait(90);
        assert(canonical.value === beforeSwitch && source() === beforeSwitch, 'Returning to a node lost its notes');
        assert(surface.textContent.includes('A preserved paragraph'), 'Returning to a node left stale rendered content');
        document.getElementById('notes-panel').open = false;
        document.querySelector('#notes-panel summary').click();
        assert(document.getElementById('notes-panel').open, 'Notes did not reopen with one click');
        assert(canonical.value === beforeSwitch && source() === beforeSwitch, 'Reopening Notes changed its source');
        assert(!notesEditorWindowErrors.length, 'Editor raised window errors: ' + JSON.stringify(notesEditorWindowErrors));
        report({kind:'pass', message:'Node switching and reopening Notes preserve focused edits and the selected preview mode'});
        window.notesEditorFinalCheck = () => {
            const start = source().indexOf('A preserved paragraph');
            focusNotesAtOffset(start + 4);
            view().dispatch({changes:{from:start,to:start + 'A preserved paragraph'.length,insert:'A final paragraph saved before close'}});
            assert(editorDirty, 'The native-close check needs an unsaved focused edit');
            assert(!notesEditorWindowErrors.length, 'Final edit raised a window error: ' + JSON.stringify(notesEditorWindowErrors));
            report({kind:'close', expected:canonical.value});
        };
        document.getElementById('notes-panel').scrollIntoView({block:'start'});
        await document.fonts.ready;
        report({kind:'ready'});
    })().catch(error => window.webkit.messageHandlers.notesEditorCheck.postMessage({kind:'error', message:error.message + ' | ' + error.stack + ' | Window errors: ' + JSON.stringify(window.notesEditorWindowErrors || [])}));
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frontend-root', type=Path)
    parser.add_argument('--screenshot', type=Path)
    options = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='roadmap-notes-editor-') as temporary:
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
        application.set_application_id('org.thesisroadmap.App.NotesEditorCheck')
        application.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        failures, expected = [], []
        started = False

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

        def capture():
            def captured(view, result):
                try:
                    surface = view.get_snapshot_finish(result)
                    options.screenshot.parent.mkdir(parents=True, exist_ok=True)
                    surface.write_to_png(str(options.screenshot))
                    evaluate('window.notesEditorFinalCheck();')
                except Exception as error:
                    fail(error)
            application.view.get_snapshot(WebKit2.SnapshotRegion.VISIBLE, WebKit2.SnapshotOptions.NONE, None, captured)

        def received(manager, result):
            message = json.loads(result.get_js_value().to_json(0))
            if message['kind'] == 'error':
                fail(message['message'])
            elif message['kind'] == 'pass':
                print('PASS:', message['message'], flush=True)
            elif message['kind'] == 'ready':
                if options.screenshot:
                    capture()
                else:
                    evaluate('window.notesEditorFinalCheck();')
            elif message['kind'] == 'close':
                expected.append(message['expected'])
                application.request_close()

        def loaded(view, event):
            nonlocal started
            if event == WebKit2.LoadEvent.FINISHED and not started:
                started = True
                evaluate(CHECKS)

        def activated(app):
            manager = application.view.get_user_content_manager()
            manager.register_script_message_handler('notesEditorCheck')
            manager.connect('script-message-received::notesEditorCheck', received)
            application.view.connect('load-changed', loaded)

        application.connect_after('activate', activated)
        GLib.timeout_add_seconds(60, lambda: fail('Cursor-local Notes checks timed out'))
        application.run([])
        if not failures:
            assert expected, 'Save-before-close was not exercised'
            saved = json.loads((data / 'roadmap_data.json').read_text())
            assert saved['notes'] == expected[0], 'Native close lost the final active Notes edit'
            assert 'A final paragraph saved before close' in saved['notes']
            print('PASS: Native close saves the final active edit before the debounce timer', flush=True)
        return bool(failures)


if __name__ == '__main__':
    raise SystemExit(main())
