'use strict';

const notesEditor = { source: null, nodeId: null, active: null, composing: false, rendering: false };

function notesPreviewEnabled() {
    return document.getElementById('notes-preview-toggle').checked;
}

function renderNotesHTML(source, token = null, links = null) {
    const tokens = token ? [token] : null;
    if (tokens) {
        tokens.links = links;
    }
    return DOMPurify.sanitize(tokens ? notesMarkdown.parser(tokens) : notesMarkdown.parse(source), { USE_PROFILES: { html: true, svg: true, mathMl: true }, FORBID_TAGS: ['img', 'form', 'input', 'button', 'textarea', 'video', 'audio', 'source', 'style'] });
}

function notesBlocks(source) {
    const blocks = [];
    let offset = 0;
    const tokens = notesMarkdown.lexer(source);
    for (const token of tokens) {
        const raw = token.raw || '';
        if (!source.startsWith(raw, offset)) {
            return [{ start: 0, end: source.length }];
        }
        if (token.type !== 'space' && raw.length) {
            blocks.push({ start: offset, end: offset + raw.length, token, links: tokens.links });
        }
        offset += raw.length;
    }
    if (offset !== source.length) {
        return [{ start: 0, end: source.length }];
    }
    return blocks;
}

function getNotesSelection() {
    const active = notesEditor.active;
    if (active && document.activeElement === active.area) {
        return [active.start + active.area.selectionStart, active.start + active.area.selectionEnd];
    }
    const source = document.getElementById('field-notes');
    return document.activeElement === source ? [source.selectionStart, source.selectionEnd] : null;
}

function resizeActiveNotes() {
    const area = notesEditor.active?.area;
    if (!area) {
        return;
    }
    const surface = document.getElementById('notes-preview');
    const scroll = surface.scrollTop;
    area.style.height = '0px';
    area.style.height = `${Math.max(48, area.scrollHeight + 2)}px`;
    surface.scrollTop = scroll;
}

function syncActiveNotes() {
    const active = notesEditor.active;
    if (!active || notesEditor.rendering || notesEditor.nodeId !== selectedNodeId) {
        return;
    }
    const source = document.getElementById('field-notes');
    const value = active.prefix + active.area.value + active.suffix;
    if (source.value !== value) {
        source.value = value;
        notesEditor.source = value;
        active.end = active.start + active.area.value.length;
        active.area.dataset.end = active.end;
        source.dispatchEvent(new Event('input', { bubbles: true }));
    }
}

function renderNotesBlocks() {
    const surface = document.getElementById('notes-preview');
    const source = document.getElementById('field-notes');
    const scroll = surface.scrollTop;
    notesEditor.rendering = true;
    notesEditor.active = null;
    notesEditor.source = source.value;
    notesEditor.nodeId = selectedNodeId;
    const fragment = document.createDocumentFragment();
    const blocks = notesBlocks(source.value);
    if (!blocks.length) {
        blocks.push({ start: 0, end: source.value.length });
    }
    for (const block of blocks) {
        const element = document.createElement('div');
        element.className = 'notes-rendered-block';
        element.dataset.start = block.start;
        element.dataset.end = block.end;
        element.tabIndex = source.disabled ? -1 : 0;
        element.setAttribute('role', 'button');
        element.setAttribute('aria-label', 'Edit this part of the notes');
        const raw = source.value.slice(block.start, block.end);
        if (raw.trim()) {
            element.innerHTML = renderNotesHTML(raw, block.token, block.links);
        } else {
            element.textContent = 'Click to write notes, Markdown, or equations…';
            element.classList.add('notes-empty');
        }
        fragment.append(element);
    }
    surface.replaceChildren(fragment);
    surface.setAttribute('aria-disabled', String(source.disabled));
    surface.scrollTop = scroll;
    notesEditor.rendering = false;
}

function finishActiveNotes() {
    if (!notesEditor.active) {
        return;
    }
    syncActiveNotes();
    notesEditor.composing = false;
    renderNotesBlocks();
}

function focusNotesAtOffset(start, end = start, preferredStart = null, wholeDocument = false) {
    const source = document.getElementById('field-notes');
    if (source.disabled) {
        return;
    }
    start = Math.max(0, Math.min(source.value.length, start));
    end = Math.max(start, Math.min(source.value.length, end));
    if (!notesPreviewEnabled()) {
        source.focus({ preventScroll: true });
        source.setSelectionRange(start, end);
        return;
    }
    if (notesEditor.active) {
        finishActiveNotes();
    }
    const blocks = notesBlocks(source.value);
    let block = preferredStart === null ? null : blocks.find(item => item.start === preferredStart);
    block = block || blocks.find(item => start >= item.start && start < item.end);
    if (!block) {
        block = blocks.find(item => item.end === start);
    }
    if (!block && start === source.value.length && blocks.at(-1)?.end === start && !source.value.endsWith('\n\n')) {
        block = blocks.at(-1);
    }
    if (!block) {
        const next = blocks.find(item => item.start >= start);
        block = { start, end: next?.start ?? source.value.length };
    }
    const surface = document.getElementById('notes-preview');
    if (wholeDocument) {
        block = { start: 0, end: source.value.length };
        surface.replaceChildren();
    }
    let element = [...surface.children].find(item => Number(item.dataset.start) === block.start && Number(item.dataset.end) === block.end);
    if (!element) {
        element = document.createElement('div');
        const next = [...surface.children].find(item => Number(item.dataset.start) >= block.end);
        surface.insertBefore(element, next || null);
    }
    element.className = 'notes-active';
    element.removeAttribute('role');
    element.removeAttribute('tabindex');
    const area = document.createElement('textarea');
    area.id = 'notes-active-block';
    area.className = 'notes-active-source';
    area.setAttribute('aria-label', 'Edit notes');
    area.dataset.start = block.start;
    area.dataset.end = block.end;
    area.spellcheck = true;
    area.value = source.value.slice(block.start, block.end);
    element.replaceChildren(area);
    notesEditor.active = { area, start: block.start, end: block.end, originalEnd: block.end, prefix: source.value.slice(0, block.start), suffix: source.value.slice(block.end) };
    area.addEventListener('input', () => {
        syncActiveNotes();
        resizeActiveNotes();
    });
    area.addEventListener('compositionstart', () => { notesEditor.composing = true; });
    area.addEventListener('compositionend', () => {
        notesEditor.composing = false;
        syncActiveNotes();
        resizeActiveNotes();
    });
    area.addEventListener('blur', () => {
        if (!notesEditor.rendering && notesEditor.active?.area === area) {
            finishActiveNotes();
        }
    });
    area.addEventListener('keydown', activeNotesKeydown);
    area.focus({ preventScroll: true });
    area.setSelectionRange(Math.min(area.value.length, start - block.start), Math.min(area.value.length, end - block.start));
    resizeActiveNotes();
}

function activeNotesKeydown(event) {
    const active = notesEditor.active;
    if (!active || event.isComposing || notesEditor.composing) {
        return;
    }
    const area = active.area;
    const cursor = area.selectionStart;
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'a') {
        event.preventDefault();
        focusNotesAtOffset(0, document.getElementById('field-notes').value.length, null, true);
        return;
    }
    if (['ArrowUp', 'ArrowDown'].includes(event.key) && !event.shiftKey && !event.ctrlKey && !event.metaKey && !event.altKey && area.selectionStart === area.selectionEnd) {
        const blocks = notesBlocks(document.getElementById('field-notes').value);
        const previous = blocks.filter(block => block.end <= active.start).at(-1);
        const next = blocks.find(block => block.start >= active.end);
        const atEnd = cursor >= area.value.replace(/\n+$/, '').length;
        if (event.key === 'ArrowUp' && cursor === 0 && previous) {
            event.preventDefault();
            finishActiveNotes();
            focusNotesAtOffset(previous.end, previous.end, previous.start);
            return;
        }
        if (event.key === 'ArrowDown' && atEnd && next) {
            event.preventDefault();
            finishActiveNotes();
            focusNotesAtOffset(next.start, next.start, next.start);
            return;
        }
    }
    if ((event.ctrlKey || event.metaKey) && !event.shiftKey && !event.altKey && ['Home', 'End'].includes(event.key)) {
        event.preventDefault();
        const target = event.key === 'Home' ? 0 : document.getElementById('field-notes').value.length;
        finishActiveNotes();
        focusNotesAtOffset(target);
        return;
    }
    if (event.key !== 'Enter' || event.shiftKey || area.selectionStart !== area.selectionEnd) {
        return;
    }
    const before = area.value.slice(0, cursor);
    const after = area.value.slice(cursor);
    const fenced = /^\s*(```|~~~)/.test(area.value);
    const heading = /^#{1,6}\s+[^\n]*$/.test(before);
    const equation = mathToken(area.value.trim(), true);
    const completeEquation = equation && equation.raw === area.value.trim();
    if (!after.trim() && !fenced && (before.endsWith('\n') || heading || completeEquation)) {
        event.preventDefault();
        const separator = before.endsWith('\n') ? '\n' : '\n\n';
        area.setRangeText(separator, cursor, cursor, 'end');
        const target = active.start + area.selectionStart;
        syncActiveNotes();
        finishActiveNotes();
        focusNotesAtOffset(target);
    }
}

function updateNotesPreview() {
    if (!notesMarkdown) {
        return;
    }
    const source = document.getElementById('field-notes');
    const live = notesPreviewEnabled();
    source.hidden = live;
    document.getElementById('notes-preview').hidden = !live;
    const sameNode = notesEditor.nodeId === selectedNodeId;
    if (!sameNode || notesEditor.source !== source.value) {
        const selection = sameNode ? getNotesSelection() : null;
        const focused = document.activeElement === notesEditor.active?.area;
        const preferredStart = notesEditor.active?.start;
        renderNotesBlocks();
        if (live && focused && selection) {
            focusNotesAtOffset(...selection, preferredStart);
        }
    } else if (!notesEditor.active && live && !document.getElementById('notes-preview').children.length) {
        renderNotesBlocks();
    }
}

function bindNotesEditor() {
    const toggle = document.getElementById('notes-preview-toggle');
    const source = document.getElementById('field-notes');
    const surface = document.getElementById('notes-preview');
    const preferenceKey = `${STORAGE_KEY}:notes-preview`;
    try {
        toggle.checked = localStorage.getItem(preferenceKey) !== 'false';
    } catch (error) {
        // Notes editing does not depend on browser preferences being available.
    }
    toggle.addEventListener('change', () => {
        const selection = getNotesSelection();
        const preferredStart = notesEditor.active?.start;
        finishActiveNotes();
        updateNotesPreview();
        if (!toggle.checked && selection) {
            focusNotesAtOffset(...selection, preferredStart);
        }
        try {
            localStorage.setItem(preferenceKey, String(toggle.checked));
        } catch (error) {
            // Toggling remains usable without persistent preferences.
        }
    });
    source.addEventListener('input', updateNotesPreview);
    const editBlock = event => {
        if (source.disabled) {
            return;
        }
        const block = event.target.closest('.notes-rendered-block');
        if (!block && event.target !== surface) {
            return;
        }
        event.preventDefault();
        let start = block ? Number(block.dataset.start) : source.value.length;
        let end = block ? Number(block.dataset.end) : start;
        if (block && notesEditor.active && start >= notesEditor.active.originalEnd) {
            const delta = notesEditor.active.area.value.length - (notesEditor.active.originalEnd - notesEditor.active.start);
            start += delta;
            end += delta;
        }
        finishActiveNotes();
        const content = source.value.slice(start, end);
        const cursor = start + content.replace(/\n+$/, '').length;
        focusNotesAtOffset(cursor, cursor, start);
    };
    surface.addEventListener('pointerdown', editBlock);
    surface.addEventListener('click', event => {
        if (!event.isTrusted || event.detail === 0) {
            editBlock(event);
        }
    });
    surface.addEventListener('keydown', event => {
        if (event.target === surface && event.key === 'Enter') {
            event.preventDefault();
            focusNotesAtOffset(source.value.length);
        } else if (event.target.classList.contains('notes-rendered-block') && ['Enter', ' '].includes(event.key)) {
            editBlock(event);
        }
    });
    updateNotesPreview();
}
