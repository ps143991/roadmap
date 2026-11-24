'use strict';

const notesEditor = { view: null, nodeId: null, syncing: false, focused: false };
const notesCM = RoadmapNotesCM;
const refreshNotes = notesCM.StateEffect.define();
const notesAccess = new notesCM.Compartment();

function notesPreviewEnabled() {
    return document.getElementById('notes-preview-toggle').checked;
}

function notesMarkdownExtensions() {
    const displayStart = line => {
        const text = line.text.slice(line.pos);
        if (!text.startsWith('$$') && !text.startsWith('\\[')) return false;
        const token = mathToken(text, true);
        return !token || !text.slice(token.raw.length).trim();
    };
    return {
        defineNodes: ['NotesMath', { name: 'NotesMathBlock', block: true }],
        parseInline: [{
            name: 'NotesMath',
            before: 'Escape',
            parse(context, next, position) {
                if (next !== 36 && next !== 92) return -1;
                const token = mathToken(context.slice(position, context.end), false);
                return token ? context.addElement(context.elt('NotesMath', position, position + token.raw.length)) : -1;
            }
        }],
        parseBlock: [{
            name: 'NotesMathBlock',
            before: 'FencedCode',
            endLeaf(context, line) { return displayStart(line); },
            parse(context, line) {
                if (!displayStart(line)) return false;
                const from = context.lineStart + line.pos;
                const depth = context.depth;
                let text = line.text.slice(line.pos);
                let to = context.lineStart + line.text.length;
                let advance = true;
                while (!mathToken(text, true)) {
                    if (!context.nextLine() || line.depth < depth) {
                        advance = false;
                        break;
                    }
                    text += '\n' + line.text;
                    to = context.lineStart + line.text.length;
                }
                context.addElement(context.elt('NotesMathBlock', from, to));
                if (advance) context.nextLine();
                return true;
            }
        }]
    };
}

function notesSelectionTouches(state, from, to) {
    return notesEditor.focused && state.selection.ranges.some(range => range.empty ? range.head >= from && range.head <= to : range.from < to && range.to > from);
}

function notesEscaped(source, offset) {
    let backslashes = 0;
    while (offset > 0 && source[--offset] === '\\') backslashes++;
    return backslashes % 2 === 1;
}

function notesMathRanges(source, excluded) {
    const ranges = [];
    const starts = /\$|\\[([]/g;
    let match;
    while ((match = starts.exec(source))) {
        const from = match.index;
        const blocked = excluded.find(range => from >= range.from && from < range.to);
        if (blocked) {
            starts.lastIndex = blocked.to;
            continue;
        }
        if (notesEscaped(source, from)) continue;
        const token = mathToken(source.slice(from), false);
        if (!token || excluded.some(range => range.from < from + token.raw.length && range.to > from)) continue;
        const delimiter = token.raw.startsWith('$$') || token.raw.startsWith('\\') ? 2 : 1;
        ranges.push({ from, to: from + token.raw.length, text: token.text, display: token.display, delimiter });
        starts.lastIndex = from + token.raw.length;
    }
    return ranges;
}

class NotesMathWidget extends notesCM.WidgetType {
    constructor(math, block) {
        super();
        this.math = math;
        this.block = block;
    }
    eq(other) {
        return this.math.text === other.math.text && this.math.from === other.math.from && this.math.to === other.math.to && this.block === other.block && this.math.display === other.math.display;
    }
    updateDOM(element) {
        if (element.tagName !== (this.block ? 'DIV' : 'SPAN') || element.dataset.tex !== this.math.text || element.dataset.display !== String(this.block)) return false;
        this.setOffsets(element);
        return true;
    }
    setOffsets(element) {
        element.dataset.from = this.math.from;
        element.dataset.to = this.math.to;
        element.dataset.delimiter = this.math.delimiter;
    }
    toDOM() {
        const element = document.createElement(this.block ? 'div' : 'span');
        element.className = 'notes-math-widget';
        element.dataset.tex = this.math.text;
        element.dataset.display = this.block;
        this.setOffsets(element);
        element.innerHTML = katex.renderToString(this.math.text, { displayMode: this.block, throwOnError: false, trust: false, strict: 'ignore', maxExpand: 1000 });
        element.setAttribute('aria-label', `Edit equation: ${this.math.text}`);
        element.addEventListener('pointerdown', event => {
            event.preventDefault();
            focusNotesAtOffset(Number(element.dataset.from) + Number(element.dataset.delimiter));
        });
        return element;
    }
    ignoreEvent() { return true; }
}

class NotesListWidget extends notesCM.WidgetType {
    constructor(label) {
        super();
        this.label = label;
    }
    eq(other) { return this.label === other.label; }
    toDOM() {
        const element = document.createElement('span');
        element.className = 'notes-list-marker';
        element.textContent = this.label;
        return element;
    }
    ignoreEvent() { return false; }
}

function notesDecorations(state) {
    if (!notesPreviewEnabled()) return notesCM.Decoration.none;
    const source = state.doc.toString();
    const tree = notesCM.ensureSyntaxTree(state, state.doc.length, 50) || notesCM.syntaxTree(state);
    const nodes = [];
    const excluded = [];
    tree.iterate({ enter(node) {
        const entry = { name: node.name, from: node.from, to: node.to, parent: node.node.parent };
        nodes.push(entry);
        if (['InlineCode', 'FencedCode', 'CodeBlock'].includes(node.name)) excluded.push(entry);
    } });
    const maths = notesMathRanges(source, excluded);
    const decorations = [];
    const hidden = [];
    const inMath = node => maths.some(math => node.from >= math.from && node.to <= math.to);
    const hide = (from, to, widget = null, block = false) => {
        if (to <= from || hidden.some(range => from < range.to && to > range.from)) return;
        hidden.push({ from, to });
        decorations.push(notesCM.Decoration.replace({ widget, block }).range(from, to));
    };
    const mark = (from, to, className) => {
        if (to > from) decorations.push(notesCM.Decoration.mark({ class: className }).range(from, to));
    };
    for (const math of maths) {
        if (notesSelectionTouches(state, math.from, math.to)) {
            mark(math.from, math.to, 'notes-source-token');
        } else {
            const first = state.doc.lineAt(math.from);
            const last = state.doc.lineAt(math.to);
            const block = math.display && !source.slice(first.from, math.from).trim() && !source.slice(math.to, last.to).trim();
            hide(math.from, math.to, new NotesMathWidget(math, block), block);
        }
    }
    const lineClasses = new Map();
    const addLine = (from, className, style = '') => {
        const line = state.doc.lineAt(from);
        const current = lineClasses.get(line.from) || { classes: [], style: '' };
        current.classes.push(className);
        current.style += style;
        lineClasses.set(line.from, current);
    };
    for (const node of nodes) {
        if (inMath(node) && !['Document', 'Paragraph', 'ListItem', 'BulletList', 'OrderedList', 'Blockquote'].includes(node.name)) continue;
        const parent = node.parent;
        if (/^(ATX|Setext)Heading[1-6]$/.test(node.name)) {
            addLine(node.from, `notes-heading notes-heading-${node.name.at(-1)}`);
        } else if (node.name === 'StrongEmphasis') {
            mark(node.from, node.to, 'notes-strong');
        } else if (node.name === 'Emphasis') {
            mark(node.from, node.to, 'notes-emphasis');
        } else if (node.name === 'Strikethrough') {
            mark(node.from, node.to, 'notes-strikethrough');
        } else if (node.name === 'InlineCode') {
            mark(node.from, node.to, 'notes-inline-code');
        } else if (node.name === 'Link' || node.name === 'Autolink') {
            mark(node.from, node.to, 'notes-link');
            if (node.name === 'Link' && !notesSelectionTouches(state, node.from, node.to)) {
                const target = nodes.find(child => child.name === 'LinkMark' && child.parent?.from === node.from && child.parent?.to === node.to && source.slice(child.from, child.to) === '(');
                if (target) hide(target.from, node.to);
            }
        } else if (node.name === 'LinkReference' && !notesSelectionTouches(state, node.from, node.to)) {
            hide(node.from, node.to);
        } else if (node.name === 'FencedCode' || node.name === 'CodeBlock') {
            for (let number = state.doc.lineAt(node.from).number; number <= state.doc.lineAt(node.to).number; number++) addLine(state.doc.line(number).from, 'notes-code-line');
        } else if (node.name === 'QuoteMark') {
            addLine(node.from, 'notes-quote-line');
        }
        if (['EmphasisMark', 'StrikethroughMark', 'CodeMark', 'LinkMark', 'URL', 'LinkTitle', 'LinkLabel', 'HeaderMark'].includes(node.name) && parent) {
            if (node.name === 'CodeMark' && parent.name !== 'InlineCode') continue;
            if (node.name === 'URL' && parent.name === 'Autolink') continue;
            if (node.name === 'LinkLabel' && parent.name !== 'Link') continue;
            const active = notesSelectionTouches(state, parent.from, parent.to);
            if (!active) {
                let end = node.to;
                if (node.name === 'HeaderMark' && source[end] === ' ') end++;
                hide(node.from, end);
            } else {
                mark(node.from, node.to, 'notes-source-token');
            }
        }
        if (node.name === 'ListMark') {
            const line = state.doc.lineAt(node.from);
            const prefix = source.slice(line.from, node.from);
            const indent = prefix.replace(/\t/g, '    ').length;
            addLine(node.from, 'notes-list-line', `--notes-indent:${Math.floor(indent / 2) * 1.4}em;`);
            if (!notesSelectionTouches(state, line.from, node.to)) {
                if (!prefix.trim()) hide(line.from, node.from);
                const raw = source.slice(node.from, node.to);
                hide(node.from, node.to, new NotesListWidget(/^\d/.test(raw) ? raw : '•'));
            }
        }
    }
    for (const [from, line] of lineClasses) decorations.push(notesCM.Decoration.line({ attributes: { class: line.classes.join(' '), style: line.style } }).range(from));
    return notesCM.Decoration.set(decorations, true);
}

const notesDecorationField = notesCM.StateField.define({
    create: notesDecorations,
    update(value, transaction) {
        return transaction.docChanged || transaction.selection || transaction.effects.some(effect => effect.is(refreshNotes)) || notesCM.syntaxTree(transaction.startState) !== notesCM.syntaxTree(transaction.state) ? notesDecorations(transaction.state) : value;
    },
    provide: field => notesCM.EditorView.decorations.from(field)
});

function getNotesSelection() {
    const view = notesEditor.view;
    return view?.hasFocus ? [view.state.selection.main.from, view.state.selection.main.to] : null;
}

function syncActiveNotes() {
    const view = notesEditor.view;
    if (!view || notesEditor.syncing || notesEditor.nodeId !== selectedNodeId) return;
    const source = document.getElementById('field-notes');
    const value = view.state.doc.toString();
    if (source.value !== value) {
        source.value = value;
        source.dispatchEvent(new Event('input', { bubbles: true }));
    }
}

function focusNotesAtOffset(start, end = start) {
    const view = notesEditor.view;
    if (!view || document.getElementById('field-notes').disabled) return;
    const anchor = Math.max(0, Math.min(view.state.doc.length, start));
    const head = Math.max(0, Math.min(view.state.doc.length, end));
    notesEditor.focused = true;
    view.dispatch({ selection: { anchor, head }, effects: refreshNotes.of(null), scrollIntoView: true });
    view.focus();
}

function updateNotesPreview() {
    const view = notesEditor.view;
    if (!view || notesEditor.syncing) return;
    const source = document.getElementById('field-notes');
    source.hidden = true;
    document.getElementById('notes-preview').hidden = false;
    const changedNode = notesEditor.nodeId !== selectedNodeId;
    const changedSource = view.state.doc.toString() !== source.value;
    const accessChanged = view.state.readOnly !== source.disabled;
    if (!changedNode && !changedSource && !accessChanged) return;
    notesEditor.syncing = true;
    notesEditor.nodeId = selectedNodeId;
    const selection = changedNode ? { anchor: 0 } : { anchor: Math.min(source.value.length, view.state.selection.main.anchor), head: Math.min(source.value.length, view.state.selection.main.head) };
    const effects = [refreshNotes.of(null)];
    if (accessChanged) effects.push(notesAccess.reconfigure([notesCM.EditorState.readOnly.of(source.disabled), notesCM.EditorView.editable.of(!source.disabled)]));
    view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: source.value }, selection, effects });
    notesEditor.syncing = false;
}

function bindNotesEditor() {
    const toggle = document.getElementById('notes-preview-toggle');
    const source = document.getElementById('field-notes');
    const surface = document.getElementById('notes-preview');
    const preferenceKey = `${STORAGE_KEY}:notes-preview`;
    try { toggle.checked = localStorage.getItem(preferenceKey) !== 'false'; } catch (error) { /* Editing remains available without browser preferences. */ }
    source.hidden = true;
    const focusChanged = () => {
        requestAnimationFrame(() => {
            const view = notesEditor.view;
            notesEditor.focused = view.hasFocus;
            view.dispatch({ effects: refreshNotes.of(null) });
        });
        return false;
    };
    notesEditor.view = new notesCM.EditorView({
        parent: surface,
        state: notesCM.EditorState.create({
            doc: source.value,
            extensions: [
                notesCM.EditorState.lineSeparator.of('\n'),
                notesCM.markdown({ extensions: notesMarkdownExtensions() }),
                notesCM.EditorView.lineWrapping,
                notesCM.drawSelection(),
                notesCM.highlightSpecialChars(),
                notesCM.keymap.of([...notesCM.defaultKeymap, notesCM.indentWithTab]),
                notesAccess.of([notesCM.EditorState.readOnly.of(source.disabled), notesCM.EditorView.editable.of(!source.disabled)]),
                notesDecorationField,
                notesCM.EditorView.contentAttributes.of({ id: 'notes-live-input', 'aria-label': 'Notes', spellcheck: 'true' }),
                notesCM.EditorView.domEventHandlers({ focus: focusChanged, blur: focusChanged }),
                notesCM.EditorView.updateListener.of(update => { if (update.docChanged) syncActiveNotes(); })
            ]
        })
    });
    toggle.addEventListener('change', () => {
        notesEditor.view.dispatch({ effects: refreshNotes.of(null) });
        try { localStorage.setItem(preferenceKey, String(toggle.checked)); } catch (error) { /* Toggling remains usable without persistent preferences. */ }
    });
    source.addEventListener('input', updateNotesPreview);
    updateNotesPreview();
}
