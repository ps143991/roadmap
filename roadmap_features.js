'use strict';

const UNDO_LIMIT = 50;
const undoStack = [];
const redoStack = [];
let branchDrag = null;
let suppressedBranchClick = null;
let notesMarkdown = null;

function captureUndoState(label) {
    return { label, data: JSON.stringify(thesisData), selected: selectedNodeId, collapsed: [...collapsedIds], notesOpen: document.getElementById('notes-panel').open };
}

function rememberUndo(label) {
    undoStack.push(captureUndoState(label));
    if (undoStack.length > UNDO_LIMIT) {
        undoStack.shift();
    }
    redoStack.length = 0;
    updateUndoButtons();
}

function updateUndoButtons() {
    const undo = document.getElementById('undo-change');
    const redo = document.getElementById('redo-change');
    undo.disabled = !thesisData || (!editorDirty && !undoStack.length);
    redo.disabled = editorDirty || !redoStack.length;
    undo.title = undoStack.length ? `Undo: ${undoStack.at(-1).label} (Ctrl+Z)` : 'Undo (Ctrl+Z)';
    redo.title = redoStack.length ? `Redo: ${redoStack.at(-1).label} (Ctrl+Y)` : 'Redo (Ctrl+Y)';
}

function restoreChange(source, destination, action) {
    if (!thesisData) {
        return;
    }
    cancelBranchDrag();
    commitEditor();
    const previous = source.pop();
    if (!previous) {
        updateUndoButtons();
        return;
    }
    const focused = document.activeElement;
    const focusId = focused?.id;
    const selectedBefore = selectedNodeId;
    const notesSelection = getNotesSelection();
    const notesBlockStart = notesEditor.active?.start;
    const selection = typeof focused?.selectionStart === 'number' ? [focused.selectionStart, focused.selectionEnd] : null;
    destination.push(captureUndoState(previous.label));
    thesisData = JSON.parse(previous.data);
    selectedNodeId = previous.selected;
    collapsedIds = new Set(previous.collapsed);
    editorDirty = false;
    document.getElementById('notes-panel').open = previous.notesOpen;
    renderAll(true);
    if (focusId && selectedBefore === selectedNodeId) {
        if (focusId === 'notes-active-block' && notesSelection) {
            focusNotesAtOffset(...notesSelection, notesBlockStart);
        }
        const input = focusId === 'notes-active-block' ? null : document.getElementById(focusId);
        input?.focus({ preventScroll: true });
        if (selection && input?.setSelectionRange) {
            input.setSelectionRange(Math.min(selection[0], input.value.length), Math.min(selection[1], input.value.length));
        }
    }
    showToast(`${action}: ${previous.label}`, 'info');
}

function undoChange() {
    restoreChange(undoStack, redoStack, 'Undid');
}

function redoChange() {
    restoreChange(redoStack, undoStack, 'Redid');
}

function reorderBranch(id, position) {
    const found = findDataById(id);
    if (!found?.parent) {
        return false;
    }
    const siblings = found.parent.children;
    const oldPosition = siblings.indexOf(found.node);
    const nextPosition = Math.max(0, Math.min(siblings.length - 1, position));
    if (oldPosition === nextPosition) {
        return false;
    }
    commitEditor();
    rememberUndo(`Reorder "${found.node.name}"`);
    siblings.splice(oldPosition, 1);
    siblings.splice(nextPosition, 0, found.node);
    found.parent.updatedAt = todayISO();
    selectedNodeId = id;
    recordHistory('reorder', found.node, `Moved from position ${oldPosition + 1} to ${nextPosition + 1} under "${found.parent.name}".`);
    renderAll(true);
    return true;
}

function suppressBranchClick(id) {
    return suppressedBranchClick?.id === id && performance.now() < suppressedBranchClick.until;
}

function updateBranchDrag(event) {
    const drag = branchDrag;
    if (!drag || event.pointerId !== drag.pointerId) {
        return;
    }
    drag.lastEvent = event;
    const point = d3.pointer(event, drag.group.node());
    const dx = point[0] - drag.start[0];
    const dy = point[1] - drag.start[1];
    if (!drag.active && (!drag.ready || Math.hypot(dx, dy) < 5)) {
        return;
    }
    event.preventDefault();
    if (!drag.active) {
        commitEditor();
        drag.active = true;
        document.body.classList.add('branch-dragging');
        drag.group.selectAll('g.node').filter(d => drag.ids.has(d.data.id)).classed('branch-dragging', true).raise();
        drag.marker = drag.group.append('line').attr('class', 'branch-drop-marker');
        drag.frame = requestAnimationFrame(scrollBranchDrag);
    }
    drag.group.selectAll('g.node').filter(d => drag.ids.has(d.data.id)).attr('transform', d => `translate(${d.x + dx},${d.y + dy})`);
    const moved = d => drag.ids.has(d.data.id) ? { x: d.x + dx, y: d.y + dy } : d;
    drag.group.selectAll('path.link').attr('d', d => diagonal(moved(d.source), moved(d.target)));
    const siblings = drag.node.parent.children.filter(d => d !== drag.node);
    const center = drag.node.x + dx;
    let index = siblings.findIndex(d => center < d.x);
    if (index === -1) {
        index = siblings.length;
    }
    drag.index = index;
    const bounds = document.getElementById('tree-container').getBoundingClientRect();
    drag.valid = Math.abs(dy) < 130 && event.clientX >= bounds.left && event.clientX <= bounds.right && event.clientY >= bounds.top && event.clientY <= bounds.bottom;
    const x = index === 0 ? siblings[0].x - 110 : index === siblings.length ? siblings.at(-1).x + 110 : (siblings[index - 1].x + siblings[index].x) / 2;
    drag.marker.attr('x1', x).attr('x2', x).attr('y1', drag.node.y - 20).attr('y2', drag.node.y + 120).attr('visibility', drag.valid ? 'visible' : 'hidden');
}

function scrollBranchDrag() {
    const drag = branchDrag;
    if (!drag?.active) {
        return;
    }
    const container = document.getElementById('tree-container');
    const bounds = container.getBoundingClientRect();
    const event = drag.lastEvent;
    const x = event.clientX < bounds.left + 48 ? -12 : event.clientX > bounds.right - 48 ? 12 : 0;
    const y = event.clientY < bounds.top + 36 ? -8 : event.clientY > bounds.bottom - 36 ? 8 : 0;
    const before = [container.scrollLeft, container.scrollTop];
    container.scrollBy(x, y);
    if (container.scrollLeft !== before[0] || container.scrollTop !== before[1]) {
        updateBranchDrag(event);
    }
    drag.frame = requestAnimationFrame(scrollBranchDrag);
}

function clearBranchDrag() {
    const drag = branchDrag;
    if (!drag) {
        return null;
    }
    branchDrag = null;
    window.clearTimeout(drag.timer);
    cancelAnimationFrame(drag.frame);
    document.body.classList.remove('branch-dragging');
    drag.element.classList.remove('branch-ready');
    if (drag.element.hasPointerCapture(drag.pointerId)) {
        drag.element.releasePointerCapture(drag.pointerId);
    }
    if (drag.active) {
        suppressedBranchClick = { id: drag.node.data.id, until: performance.now() + 450 };
    }
    return drag;
}

function cancelBranchDrag() {
    const drag = clearBranchDrag();
    if (drag?.active) {
        renderTree();
    }
}

function finishBranchDrag(event, cancelled = false) {
    if (!branchDrag || event.pointerId !== branchDrag.pointerId) {
        return;
    }
    if (branchDrag.active && !cancelled) {
        updateBranchDrag(event);
    }
    const drag = clearBranchDrag();
    if (!drag.active) {
        return;
    }
    if (cancelled || !drag.valid || !reorderBranch(drag.node.data.id, drag.index)) {
        renderTree();
    }
}

function bindBranchDrag(nodes, group) {
    nodes.on('pointerdown.reorder', function (event, d) {
        if (event.button !== 0 || !d.parent || d.parent.children.length < 2 || branchDrag) {
            return;
        }
        const drag = { pointerId: event.pointerId, element: this, node: d, group, start: d3.pointer(event, group.node()), ids: new Set(d.descendants().map(item => item.data.id)), ready: false, active: false, lastEvent: event };
        branchDrag = drag;
        this.setPointerCapture(event.pointerId);
        drag.timer = window.setTimeout(() => {
            if (branchDrag !== drag) {
                return;
            }
            drag.ready = true;
            drag.element.classList.add('branch-ready');
            updateBranchDrag(drag.lastEvent);
        }, 280);
    }).on('pointermove.reorder', updateBranchDrag)
        .on('pointerup.reorder', event => finishBranchDrag(event))
        .on('pointercancel.reorder', event => finishBranchDrag(event, true))
        .on('lostpointercapture.reorder', event => finishBranchDrag(event, true));
}

function mathToken(source, block) {
    const delimiters = block ? [['$$', '$$', true], ['\\[', '\\]', true]] : [['$$', '$$', true], ['\\[', '\\]', true], ['\\(', '\\)', false], ['$', '$', false]];
    for (const [left, right, display] of delimiters) {
        if (!source.startsWith(left)) {
            continue;
        }
        let end = source.indexOf(right, left.length);
        while (end !== -1) {
            let escapes = 0;
            for (let index = end - 1; index >= 0 && source[index] === '\\'; index--) {
                escapes++;
            }
            if (escapes % 2 === 0 && end > left.length) {
                const text = source.slice(left.length, end);
                if (!display && text.includes('\n')) {
                    return;
                }
                return { type: block ? 'notesMathBlock' : 'notesMathInline', raw: source.slice(0, end + right.length), text, display };
            }
            end = source.indexOf(right, end + right.length);
        }
    }
}

function createNotesMarkdown() {
    const mathRenderer = token => katex.renderToString(token.text, { displayMode: token.display, throwOnError: false, trust: false, strict: 'ignore', maxExpand: 1000 });
    return new marked.Marked({
        breaks: true,
        gfm: true,
        renderer: { html: token => escapeHTML(token.text) },
        extensions: [
            { name: 'notesMathBlock', level: 'block', start: source => source.search(/\$\$|\\\[/), tokenizer: source => mathToken(source, true), renderer: mathRenderer },
            { name: 'notesMathInline', level: 'inline', start: source => source.search(/\$|\\\(|\\\[/), tokenizer: source => mathToken(source, false), renderer: mathRenderer }
        ]
    });
}

function bindRoadmapFeatures() {
    notesMarkdown = createNotesMarkdown();
    bindNotesEditor();
    document.getElementById('undo-change').addEventListener('click', undoChange);
    document.getElementById('redo-change').addEventListener('click', redoChange);
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && branchDrag) {
            event.preventDefault();
            cancelBranchDrag();
            return;
        }
        if (event.isComposing || event.altKey || !(event.ctrlKey || event.metaKey)) {
            return;
        }
        const key = event.key.toLowerCase();
        if (key === 'z' || key === 'y') {
            event.preventDefault();
            event.stopPropagation();
            if (key === 'y' || event.shiftKey) {
                redoChange();
            } else {
                undoChange();
            }
        }
    }, true);
    updateUndoButtons();
}
