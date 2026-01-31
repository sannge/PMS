# Phase 3: Rich Text Editor Core - Research

**Researched:** 2026-01-31
**Domain:** TipTap rich text editor extensions and toolbar UI
**Confidence:** HIGH

## Summary

Phase 3 builds a full-featured rich text editor for the knowledge base document system. The project already has TipTap v2.27.2 installed with 18 extension packages, and two existing editor components (`RichTextEditor.tsx` for task descriptions, `NoteEditor.tsx` for the old notes system). The existing `RichTextEditor.tsx` already implements approximately 80% of the required functionality (bold, italic, underline, strikethrough, text color, font family, font size, tables with resize, links, lists, indentation). The key gaps are: (1) headings H4-H6 (currently only H1-H3), (2) interactive checklists/task lists, (3) code blocks with syntax highlighting (requires new `@tiptap/extension-code-block-lowlight` + `lowlight` packages), and (4) word count display (requires new `@tiptap/extension-character-count` package).

The new knowledge base editor should be a **new component** (not a modification of the existing `RichTextEditor.tsx` which serves task descriptions) because it will later integrate with auto-save (Phase 4), locking (Phase 5), tabs (Phase 6), and images (Phase 7). However, it should reuse the same extension configuration patterns and toolbar UI approach from the existing components.

**Primary recommendation:** Build the new `DocumentEditor` component by extracting and extending patterns from the existing `RichTextEditor.tsx`, adding the three missing capabilities (task lists, syntax-highlighted code blocks, word count), expanding headings to H1-H6, and structuring for future extensibility.

## Standard Stack

The established libraries/tools for this domain:

### Core (Already Installed)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `@tiptap/react` | 2.27.2 | React bindings for TipTap | Already in project |
| `@tiptap/starter-kit` | 2.27.2 | Bold, italic, strike, code, headings, lists, code blocks, blockquote, history | Bundles all basics |
| `@tiptap/extension-underline` | 2.27.2 | Underline mark | Not in StarterKit |
| `@tiptap/extension-text-style` | 2.27.2 | Base for font family, font size, color | Required by Color/FontFamily |
| `@tiptap/extension-color` | 2.27.2 | Text foreground color | Requirement EDIT-09 |
| `@tiptap/extension-font-family` | 2.27.2 | Font family selection | Requirement EDIT-08 |
| `@tiptap/extension-link` | 2.27.2 | Clickable links | Requirement EDIT-07 |
| `@tiptap/extension-table` | 2.27.2 | Tables with resizable columns | Requirement EDIT-05 |
| `@tiptap/extension-table-row` | 2.27.2 | Table row node | Required by Table |
| `@tiptap/extension-table-cell` | 2.27.2 | Table cell node | Required by Table |
| `@tiptap/extension-table-header` | 2.27.2 | Table header cell node | Required by Table |
| `@tiptap/extension-task-list` | 2.27.2 | Interactive checklist container | Requirement EDIT-04 |
| `@tiptap/extension-task-item` | 2.27.2 | Toggleable checkbox items | Requirement EDIT-04 |
| `@tiptap/extension-text-align` | 2.27.2 | Text alignment | Nice-to-have in toolbar |
| `@tiptap/extension-highlight` | 2.27.2 | Text highlighting | Nice-to-have in toolbar |
| `@tiptap/extension-placeholder` | 2.27.2 | Placeholder text | UX polish |

### New Packages Required
| Library | Version | Purpose | Why Needed |
|---------|---------|---------|------------|
| `@tiptap/extension-code-block-lowlight` | ^2.27.2 | Code blocks with syntax highlighting | EDIT-06: syntax highlighting |
| `lowlight` | ^3.3.0 | Syntax highlighting engine (highlight.js AST) | Required by code-block-lowlight |
| `@tiptap/extension-character-count` | ^2.27.2 | Word and character counting | EDIT-14: word count display |

### Supporting (Already Installed)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `lucide-react` | installed | Toolbar icons | All toolbar buttons |
| `@radix-ui/react-popover` | installed | Color picker, font picker dropdowns | Toolbar popovers |
| `tailwindcss` | installed | Styling editor and toolbar | All component styling |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| lowlight (highlight.js) | Shiki | Shiki has better themes but is heavier; lowlight is the TipTap-blessed option |
| Custom word count | `@tiptap/extension-character-count` | Extension is official, reactive, and handles edge cases |
| Custom FontSize extension | No official TipTap extension | Must keep the existing custom `FontSize` extension from RichTextEditor.tsx -- there is no official `@tiptap/extension-font-size` |

**Installation:**
```bash
cd electron-app
npm install @tiptap/extension-code-block-lowlight lowlight @tiptap/extension-character-count
```

## Architecture Patterns

### Recommended Project Structure
```
electron-app/src/renderer/
├── components/
│   └── knowledge/              # New directory for knowledge base components
│       ├── document-editor.tsx  # Main DocumentEditor component
│       ├── editor-toolbar.tsx   # Extracted toolbar component
│       ├── editor-extensions.ts # Extension configuration factory
│       ├── editor-types.ts      # TypeScript interfaces
│       └── editor-styles.css    # TipTap/ProseMirror CSS overrides
```

### Pattern 1: Extension Configuration Factory
**What:** Centralize TipTap extension setup in a single factory function.
**When to use:** When the extension list is long and may grow across phases.
**Example:**
```typescript
// editor-extensions.ts
import StarterKit from '@tiptap/starter-kit'
import Underline from '@tiptap/extension-underline'
import TextStyle from '@tiptap/extension-text-style'
import Color from '@tiptap/extension-color'
import FontFamily from '@tiptap/extension-font-family'
import Link from '@tiptap/extension-link'
import Table from '@tiptap/extension-table'
import TableRow from '@tiptap/extension-table-row'
import TableCell from '@tiptap/extension-table-cell'
import TableHeader from '@tiptap/extension-table-header'
import TaskList from '@tiptap/extension-task-list'
import TaskItem from '@tiptap/extension-task-item'
import TextAlign from '@tiptap/extension-text-align'
import Highlight from '@tiptap/extension-highlight'
import Placeholder from '@tiptap/extension-placeholder'
import CharacterCount from '@tiptap/extension-character-count'
import CodeBlockLowlight from '@tiptap/extension-code-block-lowlight'
import { common, createLowlight } from 'lowlight'

// Create lowlight instance with common languages (37 languages)
const lowlight = createLowlight(common)

// Custom FontSize extension (no official package exists)
const FontSize = Extension.create({ /* ... same as existing RichTextEditor.tsx ... */ })

export function createDocumentExtensions(options?: { placeholder?: string }) {
  return [
    StarterKit.configure({
      heading: { levels: [1, 2, 3, 4, 5, 6] },  // H1-H6 per EDIT-02
      codeBlock: false,  // Replaced by CodeBlockLowlight
    }),
    Underline,
    TextStyle,
    FontFamily,
    FontSize,
    Color,
    Highlight.configure({ multicolor: true }),
    TextAlign.configure({ types: ['heading', 'paragraph'] }),
    Link.configure({
      openOnClick: false,
      HTMLAttributes: { class: 'text-primary underline cursor-pointer' },
    }),
    Table.configure({
      resizable: true,
      HTMLAttributes: { class: 'border-collapse border border-border w-full' },
    }),
    TableRow,
    TableCell.configure({
      HTMLAttributes: { class: 'border border-border p-2' },
    }),
    TableHeader.configure({
      HTMLAttributes: { class: 'border border-border p-2 bg-muted font-semibold' },
    }),
    TaskList.configure({
      HTMLAttributes: { class: 'not-prose' },
    }),
    TaskItem.configure({
      HTMLAttributes: { class: 'flex items-start gap-2' },
      nested: true,
    }),
    CodeBlockLowlight.configure({
      lowlight,
      HTMLAttributes: { class: 'rounded-md bg-muted p-4 font-mono text-sm' },
    }),
    CharacterCount,
    Placeholder.configure({
      placeholder: options?.placeholder || 'Start writing...',
    }),
  ]
}
```

### Pattern 2: Toolbar as Separate Component with Editor Prop
**What:** Extract the toolbar into its own component that receives the TipTap `Editor` instance.
**When to use:** Always -- keeps the main editor component clean and toolbar testable.
**Example:**
```typescript
// editor-toolbar.tsx
interface EditorToolbarProps {
  editor: Editor
}

export function EditorToolbar({ editor }: EditorToolbarProps) {
  // Group toolbar buttons into logical sections with dividers
  return (
    <div className="flex flex-wrap items-center gap-1 p-2 border-b bg-muted/30">
      {/* Text formatting group */}
      {/* Heading dropdown */}
      {/* List group */}
      {/* Table controls (conditional) */}
      {/* Insert group (link, code block) */}
      {/* Font controls */}
      {/* Color controls */}
    </div>
  )
}
```

### Pattern 3: Word Count via useEditorState
**What:** Use TipTap's reactive `useEditorState` hook or access `editor.storage.characterCount` to display word count.
**When to use:** EDIT-14 -- word count at bottom of editor.
**Example:**
```typescript
// In the status bar at the bottom of the editor
function EditorStatusBar({ editor }: { editor: Editor }) {
  const wordCount = editor.storage.characterCount?.words() ?? 0
  const charCount = editor.storage.characterCount?.characters() ?? 0

  return (
    <div className="flex items-center justify-between px-3 py-1.5 border-t text-xs text-muted-foreground">
      <span>{wordCount} words</span>
      <span>{charCount} characters</span>
    </div>
  )
}
```

### Pattern 4: Heading Dropdown Instead of Individual Buttons
**What:** Use a dropdown/select for H1-H6 + Paragraph instead of individual heading buttons.
**When to use:** When supporting H1-H6 (six heading levels would consume too much toolbar space).
**Example:**
```typescript
<Popover>
  <PopoverTrigger asChild>
    <button className="flex items-center gap-1 px-2 py-1.5 rounded hover:bg-muted text-xs">
      <Heading className="h-4 w-4" />
      <span>{getCurrentHeadingLabel(editor)}</span>
      <ChevronDown className="h-3 w-3" />
    </button>
  </PopoverTrigger>
  <PopoverContent>
    <button onClick={() => editor.chain().focus().setParagraph().run()}>Paragraph</button>
    {[1, 2, 3, 4, 5, 6].map(level => (
      <button
        key={level}
        onClick={() => editor.chain().focus().toggleHeading({ level }).run()}
        className={cn(editor.isActive('heading', { level }) && 'bg-primary/10')}
      >
        Heading {level}
      </button>
    ))}
  </PopoverContent>
</Popover>
```

### Anti-Patterns to Avoid
- **Modifying the existing `RichTextEditor.tsx`:** That component serves task descriptions with its own debounce, image upload, and max-length logic. The knowledge base editor has different lifecycle needs (auto-save Phase 4, locking Phase 5). Build a new component.
- **Importing from `lowlight/lib/core`:** This is the lowlight v2 import path. With lowlight v3, use `import { common, createLowlight } from 'lowlight'`.
- **Using StarterKit's built-in codeBlock alongside CodeBlockLowlight:** They conflict. Disable codeBlock in StarterKit when using CodeBlockLowlight: `StarterKit.configure({ codeBlock: false })`.
- **Inline CSS for syntax highlighting:** Use highlight.js CSS themes via an import. Lowlight generates classes like `hljs-keyword`, `hljs-string`, etc. that need a theme stylesheet.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Syntax highlighting in code blocks | Custom regex highlighter | `@tiptap/extension-code-block-lowlight` + `lowlight` | 190+ language grammars, battle-tested parsing |
| Word/character counting | Manual text splitting | `@tiptap/extension-character-count` | Handles ProseMirror node structure correctly, reactive |
| Font size extension | -- | Keep existing custom `FontSize` extension | No official package exists; the existing custom extension in RichTextEditor.tsx works correctly |
| Table resize handles | Custom drag implementation | `Table.configure({ resizable: true })` | Built-in ProseMirror table resize, handles column width persistence |
| Checklist/task lists | Custom checkbox nodes | `@tiptap/extension-task-list` + `@tiptap/extension-task-item` | Already installed, handles nesting, toggling, keyboard navigation |

**Key insight:** TipTap's extension ecosystem covers every requirement in this phase. The only custom code needed is the `FontSize` extension (already written) and the `Indent` extension (already written). Everything else has an official or well-maintained package.

## Common Pitfalls

### Pitfall 1: StarterKit + CodeBlockLowlight Conflict
**What goes wrong:** Both StarterKit (which includes `codeBlock`) and `CodeBlockLowlight` register a `codeBlock` node type, causing a ProseMirror schema error.
**Why it happens:** StarterKit bundles a basic `codeBlock` by default.
**How to avoid:** Explicitly disable codeBlock in StarterKit: `StarterKit.configure({ codeBlock: false })`.
**Warning signs:** Runtime error: "Duplicate node type: codeBlock".

### Pitfall 2: lowlight v2 vs v3 Import Syntax
**What goes wrong:** Code uses `import { lowlight } from 'lowlight/lib/core'` (v2 syntax) but installs lowlight v3.
**Why it happens:** Most online tutorials and even some TipTap docs reference v2 syntax.
**How to avoid:** With lowlight v3 (current), use: `import { common, createLowlight } from 'lowlight'` then `const lowlight = createLowlight(common)`.
**Warning signs:** Module not found error on `lowlight/lib/core`.

### Pitfall 3: Missing highlight.js CSS Theme
**What goes wrong:** Code blocks render but have no syntax coloring (all text is same color).
**Why it happens:** lowlight generates HTML with `hljs-*` classes but no CSS defines their colors.
**How to avoid:** Import a highlight.js theme CSS file: `import 'highlight.js/styles/github-dark.css'` (or any theme). Choose a theme that works with both light and dark modes, or conditionally load themes.
**Warning signs:** Code block content has `<span class="hljs-keyword">` but no visual difference.

### Pitfall 4: Table Resize CSS Missing
**What goes wrong:** Table resize handles are invisible or don't show the resize cursor.
**Why it happens:** TipTap's table resize creates `.column-resize-handle` and `.resize-cursor` elements that need CSS.
**How to avoid:** The existing `RichTextEditor.tsx` already has the correct CSS classes in editorProps. Copy these styles.
**Warning signs:** Can't see or grab column resize handles.

### Pitfall 5: Task List Checkbox Styling
**What goes wrong:** Task list checkboxes render as native browser checkboxes with no styling, or the layout is broken.
**Why it happens:** ProseMirror renders task items as `<li data-type="taskItem">` with an `<input type="checkbox">` that needs explicit styling.
**How to avoid:** Add CSS for `ul[data-type=taskList]` to remove default list styling and flex-align the checkbox with text. The existing `NoteEditor.tsx` already has working CSS for this.
**Warning signs:** Checkboxes overlap text, or list bullets appear alongside checkboxes.

### Pitfall 6: Editor Re-renders on Every Keystroke
**What goes wrong:** The entire component re-renders on every keystroke, causing lag.
**Why it happens:** Using `editor.getHTML()` in the `onUpdate` callback and passing it to parent state causes React re-renders.
**How to avoid:** Debounce the `onUpdate` callback. The existing `RichTextEditor.tsx` uses a 500ms debounce. For the knowledge base editor, this will be replaced by the auto-save pipeline in Phase 4, but during Phase 3 a simple debounce is sufficient.
**Warning signs:** Typing feels sluggish, especially in large documents.

## Code Examples

### Setting Up CodeBlockLowlight with lowlight v3
```typescript
// Source: Official TipTap docs + lowlight v3 README
import CodeBlockLowlight from '@tiptap/extension-code-block-lowlight'
import { common, createLowlight } from 'lowlight'

// Create lowlight with common languages (js, ts, python, css, html, json, etc.)
const lowlight = createLowlight(common)

// In extension array:
CodeBlockLowlight.configure({
  lowlight,
  defaultLanguage: 'plaintext',
  HTMLAttributes: {
    class: 'rounded-md bg-muted p-4 font-mono text-sm overflow-x-auto',
  },
})
```

### CharacterCount for Word Count Display
```typescript
// Source: Official TipTap CharacterCount docs
import CharacterCount from '@tiptap/extension-character-count'

// In extension array (no configuration needed for basic word count):
CharacterCount

// In component, read word count:
const wordCount = editor.storage.characterCount?.words() ?? 0
```

### Task List / Checklist Setup
```typescript
// Source: Existing NoteEditor.tsx in codebase
import TaskList from '@tiptap/extension-task-list'
import TaskItem from '@tiptap/extension-task-item'

// In extension array:
TaskList.configure({
  HTMLAttributes: { class: 'not-prose' },
}),
TaskItem.configure({
  HTMLAttributes: { class: 'flex items-start gap-2' },
  nested: true,  // Allow nested task items
}),

// CSS needed on EditorContent wrapper:
// '[&_ul[data-type=taskList]]:list-none [&_ul[data-type=taskList]]:pl-0',
// '[&_ul[data-type=taskList]_li]:flex [&_ul[data-type=taskList]_li]:items-start',
// '[&_ul[data-type=taskList]_input]:mt-1 [&_ul[data-type=taskList]_input]:h-4 [&_ul[data-type=taskList]_input]:w-4',
// '[&_ul[data-type=taskList]_input]:accent-primary'
```

### Heading Levels H1-H6 Configuration
```typescript
// Override StarterKit default (which only supports H1-H3):
StarterKit.configure({
  heading: {
    levels: [1, 2, 3, 4, 5, 6],
  },
  codeBlock: false,  // Replaced by CodeBlockLowlight
})
```

### Link Click Handling in Electron
```typescript
// Links should open in external browser, not in Electron window
Link.configure({
  openOnClick: false,  // Prevent default click behavior in editor
  HTMLAttributes: {
    class: 'text-primary underline cursor-pointer',
    // In read-only mode, add click handler to open external browser
  },
})

// Add click handler for links in read-only mode:
// editor.on('click', ...) or use editorProps.handleClick
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| lowlight v2 singleton import | lowlight v3 `createLowlight()` factory | lowlight 3.0 (2023) | Must use new import syntax |
| `@tiptap/extension-character-count` basic | Rewritten with `words()` + `wordCounter` config | TipTap 2.8+ | Customizable word counting |
| Individual `@tiptap/extension-*` installs | `@tiptap/extensions` bundle available | TipTap 2.6+ | Can install individually or as bundle; project uses individual |

**Deprecated/outdated:**
- `import { lowlight } from 'lowlight/lib/core'`: This is lowlight v2 syntax. With v3, use `import { createLowlight, common } from 'lowlight'`.

## Open Questions

1. **highlight.js Theme for Dark/Light Mode**
   - What we know: The app supports dark mode via Tailwind's `dark:` prefix. highlight.js has separate light and dark themes.
   - What's unclear: Whether to use a single theme that works in both modes (like `github-dark-dimmed`) or dynamically switch themes.
   - Recommendation: Use `github-dark` theme for code blocks with a dark background (matches the `bg-muted` pattern used throughout the app). Code blocks typically look better on dark backgrounds regardless of app theme.

2. **Editor Content Format for Phase 4 Compatibility**
   - What we know: Phase 4 will store content in three formats (JSON, Markdown, plain text). TipTap can output JSON via `editor.getJSON()` and HTML via `editor.getHTML()`.
   - What's unclear: Whether to use JSON or HTML as the primary content format during Phase 3.
   - Recommendation: Use TipTap JSON (`editor.getJSON()`) as the primary format from the start. It preserves full fidelity and is what Phase 4 will need for server-side Markdown conversion. Store as JSON, render from JSON.

3. **Font Size Values**
   - What we know: The existing `RichTextEditor.tsx` uses rem values (0.875rem, 1rem, 1.25rem, 1.5rem) with only 4 options.
   - What's unclear: Whether knowledge base documents need more granular font size control.
   - Recommendation: Keep the same 4-option approach for consistency. More granular control adds complexity without clear user benefit.

## Sources

### Primary (HIGH confidence)
- Existing codebase: `electron-app/src/renderer/components/editor/RichTextEditor.tsx` -- verified installed TipTap v2.27.2 configuration, custom FontSize extension, table resize CSS
- Existing codebase: `electron-app/src/renderer/components/notes/note-editor.tsx` -- verified TaskList/TaskItem configuration and CSS
- Existing codebase: `electron-app/package.json` -- verified all 18 TipTap packages at ^2.6.0+, installed at 2.27.2
- [TipTap Table Extension Docs](https://tiptap.dev/docs/editor/extensions/nodes/table) -- resizable configuration, commands
- [TipTap CodeBlockLowlight Docs](https://tiptap.dev/docs/editor/extensions/nodes/code-block-lowlight) -- setup with lowlight
- [TipTap CharacterCount Docs](https://tiptap.dev/docs/editor/extensions/functionality/character-count) -- words() API

### Secondary (MEDIUM confidence)
- [lowlight GitHub README](https://github.com/wooorm/lowlight) -- v3 import syntax: `createLowlight(common)`
- [npm @tiptap/extension-character-count](https://www.npmjs.com/package/@tiptap/extension-character-count) -- standalone package confirmed

### Tertiary (LOW confidence)
- None -- all findings verified against official sources or existing codebase

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all packages verified in existing `package.json` or official TipTap docs
- Architecture: HIGH -- patterns derived from working code already in the codebase
- Pitfalls: HIGH -- pitfalls 1-2 verified against official docs; pitfalls 3-6 derived from existing codebase patterns

**Research date:** 2026-01-31
**Valid until:** 2026-03-31 (TipTap v2 is stable; no v3 migration planned per STATE.md)
