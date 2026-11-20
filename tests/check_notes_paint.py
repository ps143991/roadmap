"""Check actual on-screen Notes text pixels while moving only the caret.

Uses the production native RoadmapApp and temporary generic data. Run in a desktop
session or under Xvfb; --output saves fictional screenshots and frame metadata.
--frontend-root changes only the served frontend, never the private native backend.
"""

import argparse
import json
import math
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FIXTURE = '''# Fictional chapter notes

- Experimental planning uses a stable ordinary font while the cursor moves through this sentence. The purpose is to check every piece of this long line before and after repainting, including wrapped continuation lines, while the equation $a+b$ stays rendered and the source is never changed. We collect several repeated observations at each cursor position to distinguish drawing artifacts from intentional Markdown formatting.
- Describe the beam line and the instrument layout. A formatted equation $x^2+y^2$ is kept away from the cursor. The explanatory prose stays normal and opaque throughout the experiment, even when the cursor moves toward the middle and end of this list item.
  - Nested item with ordinary prose, used as another unchanged text patch.
  - Another nested item uses the same font and color without strong markup.
- The next paragraph links detector calibration, timing, and normalization. Here is a deliberately long sequence of ordinary words to wrap onto the following line while retaining the exact same text content at every frame.

## Another section

A plain paragraph with a display equation below it. This paragraph supplies a second independent text patch for comparison.

$$\\frac{a}{b}$$

'''
FIXTURE += '\n'.join('- Additional observation %d: ordinary prose remains unchanged, with a small $p+q$ equation and several words to wrap naturally.' % number for number in range(1, 17))

SETUP = r'''
void (async () => {
    const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
    await wait(700);
    document.getElementById('notes-panel').open = true;
    if (document.getElementById('sidebar-toggle').getAttribute('aria-expanded') === 'true') document.getElementById('sidebar-toggle').click();
    if (thesisData?.name !== 'My Thesis') throw new Error('The paint check did not load isolated generic data');
    const canonical = document.getElementById('field-notes');
    canonical.value = __FIXTURE__;
    canonical.dispatchEvent(new Event('input', {bubbles:true}));
    updateNotesPreview();
    await document.fonts.ready;
    await wait(500);
    document.getElementById('notes-panel').scrollIntoView({block:'start'});
    const editor = notesEditor.view;
    const text = editor.state.doc.toString();
    const start = text.indexOf('Experimental planning');
    const end = text.indexOf('We collect several');
    const third = text.indexOf('The next paragraph');
    window.probePositions = [start+4, start+22, start+45, start+82, start+135, start+182, end+8, third+15, start+45, start+45, start+45, start+45];
    window.probeContentDOM = editor.contentDOM;
    const before = editor.domAtPos(start+4);
    window.probeLineDOM = (before.node.nodeType===Node.TEXT_NODE ? before.node.parentElement : before.node).closest('.cm-line');
    window.paintProbeStep = index => {
        const position = probePositions[index];
        focusNotesAtOffset(position);
        // Keep the scroll and geometry identical instead of letting caret scrolling move a patch.
        document.querySelector('.cm-scroller').scrollTop = 0;
        document.getElementById('notes-panel').scrollIntoView({block:'start'});
        setTimeout(() => {
            const point = editor.domAtPos(start+4);
            const element = point.node.nodeType===Node.TEXT_NODE ? point.node.parentElement : point.node;
            const style = getComputedStyle(element);
            let opacity = 1;
            for (let ancestor = element; ancestor; ancestor = ancestor.parentElement) opacity *= Number(getComputedStyle(ancestor).opacity);
            const line = element.closest('.cm-line');
            const rect = line.getBoundingClientRect();
            const cursor = editor.coordsAtPos(position);
            const surface = document.getElementById('notes-preview').getBoundingClientRect();
            window.webkit.messageHandlers.paintProbe.postMessage({kind:'frame',index,position,style:{font:style.font,fontFamily:style.fontFamily,fontWeight:style.fontWeight,fontSize:style.fontSize,color:style.color,opacity,fontStyle:style.fontStyle,webkitTextFillColor:style.webkitTextFillColor},lineRect:{x:rect.x,y:rect.y,width:rect.width,height:rect.height},surface:{x:surface.x,y:surface.y,width:surface.width,height:surface.height},cursor:{left:cursor.left,right:cursor.right,top:cursor.top,bottom:cursor.bottom},scrollTop:document.querySelector('.cm-scroller').scrollTop,scrollY,zoom:document.documentElement.style.zoom,dpr:devicePixelRatio,contentSame:editor.contentDOM===probeContentDOM,lineSame:line===probeLineDOM,sourceUnchanged:editor.state.doc.toString()===__FIXTURE__ && canonical.value===__FIXTURE__,readOnly:editor.state.readOnly,editable:editor.contentDOM.isContentEditable,preview:document.getElementById('notes-preview-toggle').checked,hasFocus:editor.hasFocus});
        }, 180);
    };
    paintProbeStep(0);
})().catch(error => window.webkit.messageHandlers.paintProbe.postMessage({kind:'error',message:String(error.stack||error)}));
'''

def compare_frames(frames):
    """Compare unchanged prose, excluding every captured caret rectangle."""
    baseline = frames[0]
    scale = baseline['pixelScale']
    rectangle = baseline['metadata']['lineRect']
    left = max(0, math.floor(rectangle['x'] * scale))
    top = max(0, math.floor(rectangle['y'] * scale))
    right = min(baseline['width'], math.ceil((rectangle['x'] + rectangle['width']) * scale))
    bottom = min(baseline['height'], math.ceil((rectangle['y'] + rectangle['height']) * scale))
    excluded = []
    for frame in frames:
        cursor = frame['metadata']['cursor']
        excluded.append((math.floor(cursor['left'] * scale) - 4, math.floor(cursor['top'] * scale) - 3, math.ceil(cursor['right'] * scale) + 4, math.ceil(cursor['bottom'] * scale) + 3))
    rows = []
    for frame in frames:
        changed, changed20, maximum, ink = 0, 0, 0, 0
        for y in range(top, bottom):
            for x in range(left, right):
                if any(x0 <= x <= x1 and y0 <= y <= y1 for x0, y0, x1, y1 in excluded):
                    continue
                first = y * baseline['stride'] + x * baseline['channels']
                current = y * frame['stride'] + x * frame['channels']
                original = baseline['pixels'][first:first + 3]
                actual = frame['pixels'][current:current + 3]
                difference = max(abs(a - b) for a, b in zip(original, actual))
                changed += difference > 0
                changed20 += difference > 20
                maximum = max(maximum, difference)
                ink += min(actual) < 180
        metadata = frame['metadata']
        if metadata['style'] != baseline['metadata']['style'] or metadata['lineRect'] != rectangle:
            raise AssertionError('Ordinary text style or line geometry changed during caret movement')
        if metadata['scrollTop'] != baseline['metadata']['scrollTop'] or metadata['scrollY'] != baseline['metadata']['scrollY'] or metadata['dpr'] != baseline['metadata']['dpr'] or metadata['webViewZoom'] != baseline['metadata']['webViewZoom']:
            raise AssertionError('Scrolling or device scale moved the text comparison patch')
        if not all(metadata[name] for name in ('contentSame', 'lineSame', 'sourceUnchanged', 'hasFocus', 'editable', 'preview')) or metadata['readOnly']:
            raise AssertionError('Caret movement changed source, editability, editor DOM, focus, or preview mode')
        if metadata['style']['fontWeight'] not in ('400', 'normal') or metadata['style']['fontStyle'] != 'normal' or metadata['style']['opacity'] != 1:
            raise AssertionError('Ordinary text became bold, italic, or faded')
        if ink < 500:
            raise AssertionError('The comparison patch does not contain enough visible text')
        rows.append({'frame':metadata['index'],'changedPixels':changed,'changedOver20':changed20,'maxChannelDifference':maximum,'inkPixels':ink})
    return {'patch':[left,top,right,bottom],'frames':rows,'maxChangedPixels':max(row['changedPixels'] for row in rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frontend-root', type=Path)
    parser.add_argument('--zoom', type=float, default=1.0)
    parser.add_argument('--output', type=Path)
    options = parser.parse_args()
    if options.output:
        options.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='roadmap-paint-check-') as temporary:
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
        application.set_application_id('org.thesisroadmap.App.PaintCheck')
        application.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        frames, failures, started = [], [], []
        settings = {}

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
            message['webViewZoom'] = application.view.get_zoom_level()
            if message['kind'] == 'error':
                stop(message['message'])
                return
            index = message['index']
            allocation = application.view.get_allocation()
            image = Gdk.pixbuf_get_from_window(application.view.get_window(), 0, 0, allocation.width, allocation.height)
            if options.output:
                image.savev(str(options.output / ('frame-%02d.png' % index)), 'png', [], [])
            frames.append({'metadata':message,'pixels':bytes(image.get_pixels()),'width':image.get_width(),'height':image.get_height(),'stride':image.get_rowstride(),'channels':image.get_n_channels(),'pixelScale':application.view.get_zoom_level() * image.get_width() / allocation.width})
            if index + 1 == 12:
                stop()
            else:
                GLib.timeout_add(160, lambda: evaluate('paintProbeStep(%d)' % (index + 1)))

        def loaded(view, event):
            if event != WebKit2.LoadEvent.FINISHED or started:
                return
            started.append(True)
            evaluate(SETUP.replace('__FIXTURE__', json.dumps(FIXTURE)))

        def activated(app):
            manager = application.view.get_user_content_manager()
            manager.register_script_message_handler('paintProbe')
            manager.connect('script-message-received::paintProbe', received)
            application.view.set_zoom_level(options.zoom)
            settings['hardwareAccelerationPolicy'] = application.view.get_settings().get_hardware_acceleration_policy().value_nick
            application.view.connect('load-changed', loaded)

        application.connect_after('activate', activated)
        GLib.timeout_add_seconds(35, lambda: stop('Paint check timed out'))
        application.run([])
        summary = {'zoom':options.zoom,**settings,'metadata':[frame['metadata'] for frame in frames],'errors':failures}
        if not failures:
            try:
                if len(frames) != 12:
                    raise AssertionError('The paint check did not capture all caret positions')
                summary.update(compare_frames(frames))
                if summary['maxChangedPixels']:
                    raise AssertionError('Unchanged prose changed at %d screen pixels while only the caret moved (excluding all caret positions)' % summary['maxChangedPixels'])
            except AssertionError as error:
                failures.append(str(error))
                print('FAIL:', error, flush=True)
        if options.output:
            (options.output / 'result.json').write_text(json.dumps(summary, indent=2) + '\n')
        if not failures:
            print('PASS: Production native app at zoom %.2f keeps unchanged text pixel-identical across 12 caret frames; source, styles, geometry, DOM, focus, and editability stay unchanged (renderer: %s)' % (options.zoom, settings['hardwareAccelerationPolicy']), flush=True)
        return bool(failures)


if __name__ == '__main__':
    raise SystemExit(main())
