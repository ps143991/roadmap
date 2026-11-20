"""Exercise the single-panel live Notes editor using an isolated profile.

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
        const input = (element, data = null) => element.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'insertText', data}));
        const readDisk = async () => (await fetch('/api/roadmap')).json();
        const styles = element => {
            const computed = getComputedStyle(element);
            return JSON.stringify(['fontFamily','fontSize','fontWeight','fontStyle','color','opacity','webkitTextFillColor'].map(key => computed[key]));
        };
        const finishBlock = async () => {
            document.getElementById('notes-preview-toggle').focus({preventScroll:true});
            await wait(150);
        };
        const clickBlock = text => {
            const block = [...document.querySelectorAll('.notes-rendered-block')].find(element => element.textContent.includes(text));
            assert(block, 'Rendered block not found: ' + text);
            const start = Number(block.dataset.start);
            const end = Number(block.dataset.end);
            assert(Number.isInteger(start) && Number.isInteger(end) && start <= end, 'Rendered block lacks source offsets');
            block.click();
            const active = document.getElementById('notes-active-block');
            assert(active && document.activeElement === active, 'Clicking a rendered block did not focus its editable source');
            return {active, start, end};
        };
        const setSource = source => {
            const notes = document.getElementById('field-notes');
            notes.value = source;
            input(notes);
            updateNotesPreview();
        };
        await wait(600);
        assert(thesisData?.name === 'My Thesis', 'Test profile did not load generic data');
        assert(typeof syncActiveNotes === 'function', 'Single-panel Notes synchronization is unavailable');
        document.getElementById('notes-panel').open = true;
        const canonical = document.getElementById('field-notes');
        const toggle = document.getElementById('notes-preview-toggle');
        const surface = document.getElementById('notes-preview');
        const rootId = thesisData.id;
        const childId = thesisData.children[0].id;
        if (!toggle.checked) toggle.click();
        const sample = '# Sample Notes\n\nA paragraph with **bold** and *emphasis*.\n\n$$\\frac{a}{b}$$\n\n- First item\n- Second item\n\nTrailing spaces stay here.  \n';
        setSource(sample);
        await finishBlock();
        assert(canonical.value === sample, 'Rendering changed the Markdown source or whitespace');
        assert(!visible(canonical) && visible(surface), 'Live mode still shows a separate source panel');
        assert(surface.querySelector('.katex .mfrac'), 'The sample TeX did not render as an actual fraction');
        assert(surface.querySelector('strong')?.textContent === 'bold', 'Finished bold text was not rendered');
        assert(surface.querySelector('em')?.textContent === 'emphasis', 'Finished italic text was not rendered');
        assert(surface.getBoundingClientRect().height >= 850, 'Notes surface is smaller than the requested minimum');
        report({kind:'pass', message:'One live surface, finished Markdown/math, and exact source whitespace'});
        await wait(800);
        await saveQueue;

        const {active, start, end} = clickBlock('A paragraph');
        const before = canonical.value;
        const raw = active.value;
        assert(before.slice(start, start + raw.length) === raw, 'Editable block offset mismatch: ' + JSON.stringify({start,end,activeStart:active.dataset.start,activeEnd:active.dataset.end,raw,slice:before.slice(start,start+raw.length)}));
        assert(start + raw.length <= end, 'Editable source extends beyond its block offsets');
        const originalStyle = styles(active);
        const computed = getComputedStyle(active);
        assert(Number(computed.opacity) === 1, 'Active source is faded');
        assert(['400','normal'].includes(computed.fontWeight), 'Active source inherits bold formatting');
        assert(computed.fontStyle === 'normal', 'Active source inherits italic formatting');
        let insertion = raw.search(/\s*$/);
        const typed = ' text entered without flicker';
        for (const character of typed) {
            active.value = active.value.slice(0, insertion) + character + active.value.slice(insertion);
            insertion++;
            active.setSelectionRange(insertion, insertion);
            input(active, character);
            await wait(20);
            assert(document.getElementById('notes-active-block') === active, 'Typing replaced the focused textarea');
            assert(document.activeElement === active, 'Typing removed editor focus');
            assert(active.selectionStart === insertion && active.selectionEnd === insertion, 'Typing moved the caret');
            assert(styles(active) === originalStyle, 'Typing changed source font, weight, color, or opacity');
        }
        const changed = before.slice(0, start) + active.value + before.slice(start + raw.length);
        assert(canonical.value === changed, 'Active typing did not update the canonical Markdown exactly');
        await wait(1100);
        await saveQueue;
        assert((await readDisk()).notes === changed, 'Autosave missed active-block text');
        assert(document.getElementById('notes-active-block') === active && document.activeElement === active, 'Autosave replaced the active editor or lost focus');
        assert(styles(active) === originalStyle, 'Autosave changed the active text style');
        report({kind:'pass', message:'Rapid keystrokes preserve editor DOM, caret, focus, and ordinary styling; active text autosaves'});

        shortcut('z');
        await wait(80);
        assert(canonical.value === sample, 'Undo did not restore source before the typing burst');
        let restored = document.getElementById('notes-active-block');
        assert(restored && document.activeElement === restored, 'Undo did not leave the active Notes editor focused');
        shortcut('y');
        await wait(80);
        assert(canonical.value === changed, 'Redo did not restore the typing burst');
        restored = document.getElementById('notes-active-block');
        assert(restored && document.activeElement === restored, 'Redo did not leave the active Notes editor focused');
        report({kind:'pass', message:'Undo/redo preserves active-block source editing and focus'});

        toggle.click();
        await wait(100);
        assert(!toggle.checked && visible(canonical) && !visible(surface), 'Disabling preview did not show a single plain source editor');
        assert(canonical.value === changed, 'Disabling preview lost the active edits');
        assert(localStorage.getItem(`${STORAGE_KEY}:notes-preview`) === 'false', 'Disabled preview preference was not saved');
        const rawExtra = '\nPlain source addition with $x^2$.  \n';
        canonical.value += rawExtra;
        input(canonical);
        const fullSource = changed + rawExtra;
        updateNotesPreview();
        assert(!toggle.checked && visible(canonical) && !visible(surface), 'Editing source unexpectedly reenabled preview');
        toggle.click();
        await wait(150);
        assert(toggle.checked && !visible(canonical) && visible(surface), 'Enabling preview did not restore the live surface');
        assert(canonical.value === fullSource, 'Toggling preview changed the Markdown source');
        assert(localStorage.getItem(`${STORAGE_KEY}:notes-preview`) === 'true', 'Enabled preview preference was not saved');
        assert(!notesEditorWindowErrors.length, 'Preview toggle raised a window error: ' + JSON.stringify(notesEditorWindowErrors));
        const mathBlock = [...surface.querySelectorAll('.notes-rendered-block')].find(element => element.querySelector('.katex-display'));
        assert(mathBlock, 'Display equation not rendered after switching source mode');
        mathBlock.click();
        const mathSource = document.getElementById('notes-active-block');
        assert(mathSource?.value.includes('\\frac{a}{b}'), 'Clicking an equation did not expose its TeX source');
        await finishBlock();
        assert(surface.querySelector('.katex-display'), 'Leaving a finished equation did not render it again');
        assert(canonical.value === fullSource, 'Equation editing roundtrip changed source whitespace');
        report({kind:'pass', message:'Preview toggle and equation source/render roundtrips preserve Markdown exactly'});

        const references = fullSource + '\n[Example][r]\n\n[r]: https://example.org/research\n';
        setSource(references);
        await finishBlock();
        let reference = [...surface.querySelectorAll('a')].find(link => link.textContent === 'Example');
        assert(reference?.getAttribute('href') === 'https://example.org/research', 'A reference-style link lost its full-document definition');
        const shortened = clickBlock('A paragraph');
        shortened.active.value = 'Short paragraph.\n\n';
        input(shortened.active);
        const afterDelete = canonical.value;
        surface.dispatchEvent(new MouseEvent('click', {bubbles:true}));
        const atEnd = document.getElementById('notes-active-block');
        assert(atEnd && document.activeElement === atEnd, 'Clicking empty Notes space did not open an editor');
        assert(Number(atEnd.dataset.start) + atEnd.selectionStart === afterDelete.length, 'Blank-space click after deletion did not place the caret at document EOF');
        assert(atEnd.selectionStart === atEnd.selectionEnd, 'Blank-space click unexpectedly selected source text');
        assert(canonical.value === afterDelete, 'Blank-space click after deletion changed the source');
        await finishBlock();
        reference = [...surface.querySelectorAll('a')].find(link => link.textContent === 'Example');
        assert(reference?.getAttribute('href') === 'https://example.org/research', 'Editing another block broke a reference-style link');

        setSource(references);
        await finishBlock();
        const heading = clickBlock('Sample Notes').active;
        heading.setSelectionRange(heading.value.replace(/\s+$/, '').length, heading.value.replace(/\s+$/, '').length);
        const headingEnter = new KeyboardEvent('keydown', {key:'Enter',bubbles:true,cancelable:true});
        heading.dispatchEvent(headingEnter);
        await wait(80);
        let next = document.getElementById('notes-active-block');
        assert(headingEnter.defaultPrevented, 'Enter did not finish the completed heading');
        assert(surface.querySelector('.notes-rendered-block h1')?.textContent === 'Sample Notes', 'Completed heading was not rendered on Enter');
        assert(next && next !== heading && document.activeElement === next && !next.value.trim(), 'Enter after a heading did not open a new empty editing block');

        setSource(references);
        await finishBlock();
        const equationBlock = [...surface.querySelectorAll('.notes-rendered-block')].find(element => element.querySelector('.katex-display'));
        assert(equationBlock, 'Equation missing before completion test');
        equationBlock.click();
        const equation = document.getElementById('notes-active-block');
        const equationEnd = equation.value.replace(/\s+$/, '').length;
        equation.setSelectionRange(equationEnd, equationEnd);
        const equationEnter = new KeyboardEvent('keydown', {key:'Enter',bubbles:true,cancelable:true});
        equation.dispatchEvent(equationEnter);
        await wait(80);
        next = document.getElementById('notes-active-block');
        assert(equationEnter.defaultPrevented && surface.querySelector('.notes-rendered-block .katex-display .mfrac'), 'Enter did not render the completed display equation');
        assert(next && next !== equation && document.activeElement === next && !next.value.trim(), 'Enter after an equation did not open a new empty editing block');
        const beforeSelectAll = canonical.value;
        const selectAll = new KeyboardEvent('keydown', {key:'a',ctrlKey:true,bubbles:true,cancelable:true});
        next.dispatchEvent(selectAll);
        const allSource = document.getElementById('notes-active-block');
        assert(selectAll.defaultPrevented && allSource && document.activeElement === allSource, 'Ctrl+A did not focus the complete Notes source');
        assert(allSource.value === beforeSelectAll && Number(allSource.dataset.start) === 0, 'Ctrl+A exposed only the current block rather than the complete source');
        assert(allSource.selectionStart === 0 && allSource.selectionEnd === beforeSelectAll.length, 'Ctrl+A did not select every source character');
        await finishBlock();
        assert(canonical.value === beforeSelectAll, 'Selecting the complete source changed the notes');
        const navigationSource = 'First navigation paragraph.\n\nMiddle navigation paragraph.\n\nLast navigation paragraph.\n';
        setSource(navigationSource);
        await finishBlock();
        const middle = clickBlock('Middle navigation paragraph').active;
        const middleSource = middle.value;
        for (const modifier of ['shiftKey','ctrlKey','metaKey','altKey']) {
            for (const key of ['ArrowUp','ArrowDown']) {
                const cursor = key === 'ArrowUp' ? 0 : middle.value.replace(/\n+$/, '').length;
                middle.setSelectionRange(cursor, cursor);
                const event = new KeyboardEvent('keydown', {key,[modifier]:true,bubbles:true,cancelable:true});
                middle.dispatchEvent(event);
                assert(!event.defaultPrevented, modifier + '+' + key + ' was prevented instead of retaining native editing');
                assert(document.getElementById('notes-active-block') === middle && document.activeElement === middle, modifier + '+' + key + ' switched the active Notes editor');
                assert(canonical.value === navigationSource && middle.value === middleSource, modifier + '+' + key + ' changed the Notes source');
            }
        }
        for (const key of ['Home','End']) {
            for (const modifier of ['ctrlKey','metaKey']) {
                const event = new KeyboardEvent('keydown', {key,[modifier]:true,shiftKey:true,bubbles:true,cancelable:true});
                middle.dispatchEvent(event);
                assert(!event.defaultPrevented && document.getElementById('notes-active-block') === middle, modifier + '+Shift+' + key + ' overrode native selection');
            }
        }
        const middleEnd = middle.value.replace(/\n+$/, '').length;
        middle.setSelectionRange(middleEnd, middleEnd);
        const down = new KeyboardEvent('keydown', {key:'ArrowDown',bubbles:true,cancelable:true});
        middle.dispatchEvent(down);
        const last = document.getElementById('notes-active-block');
        assert(down.defaultPrevented && last !== middle && last?.value.includes('Last navigation paragraph.') && last.selectionStart === 0, 'Plain ArrowDown did not enter the following paragraph at its start');
        const up = new KeyboardEvent('keydown', {key:'ArrowUp',bubbles:true,cancelable:true});
        last.dispatchEvent(up);
        const previous = document.getElementById('notes-active-block');
        assert(up.defaultPrevented && previous !== last && previous?.value.includes('Middle navigation paragraph.') && previous.selectionStart === previous.value.length, 'Plain ArrowUp did not enter the preceding paragraph at its end');
        assert(document.activeElement === previous && canonical.value === navigationSource, 'Paragraph navigation changed source or lost focus');
        setSource(references);
        await finishBlock();
        assert(!notesEditorWindowErrors.length, 'Editor interactions raised window errors: ' + JSON.stringify(notesEditorWindowErrors));
        report({kind:'pass', message:'Reference links, EOF after deletion, Enter completion, complete-source Ctrl+A, native modified arrows, paragraph navigation, and preview preferences'});

        const edited = clickBlock('A paragraph');
        edited.active.value = edited.active.value.replace('A paragraph', 'A preserved paragraph');
        input(edited.active);
        const beforeSwitch = canonical.value;
        selectNode(childId);
        await saveQueue;
        assert((await readDisk()).notes === beforeSwitch, 'Switching nodes lost active Notes edits');
        assert(canonical.value === findDataById(childId).node.notes, 'Previous node source leaked into the selected node');
        assert(toggle.checked && visible(surface) && !visible(canonical), 'Changing nodes changed the selected live-preview mode');
        selectNode(rootId);
        await wait(100);
        assert(canonical.value === beforeSwitch, 'Returning to a node lost its notes');
        assert(surface.textContent.includes('A preserved paragraph'), 'Returning to a node left stale rendered content');
        document.getElementById('notes-panel').open = false;
        document.querySelector('#notes-panel summary').click();
        assert(document.getElementById('notes-panel').open, 'Notes panel did not reopen with one click');
        assert(canonical.value === beforeSwitch, 'Reopening the Notes panel changed its source');
        report({kind:'pass', message:'Switching nodes and reopening Notes preserve active edits and fresh rendered content'});
        assert(!notesEditorWindowErrors.length, 'Window errors were captured: ' + JSON.stringify(notesEditorWindowErrors));
        window.notesEditorFinalCheck = () => {
            const block = [...document.querySelectorAll('.notes-rendered-block')].find(element => element.textContent.includes('A preserved paragraph'));
            assert(block, 'Final paragraph is not rendered');
            block.click();
            const field = document.getElementById('notes-active-block');
            field.value = field.value.replace('A preserved paragraph', 'A final paragraph saved before close');
            input(field);
            assert(editorDirty, 'The final close test needs an unsaved active edit');
            assert(!notesEditorWindowErrors.length, 'Final active edit raised a window error: ' + JSON.stringify(notesEditorWindowErrors));
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
        GLib.timeout_add_seconds(60, lambda: fail('Single-panel Notes checks timed out'))
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
