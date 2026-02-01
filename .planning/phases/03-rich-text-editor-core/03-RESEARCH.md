# Phase 3: Rich Text Editor Core - Research

**Researched:** 2026-01-31 (re-verified)
**Domain:** TipTap rich text editor extensions and toolbar UI
**Confidence:** HIGH

## Summary

Phase 3 builds a full-featured rich text editor for the knowledge base document system. The project already has TipTap v2.27.2 installed with 16 extension packages (verified in `package.json`), and one existing editor component (`RichTextEditor.tsx` for task descriptions). The existing `RichTextEditor.tsx` already implements approximately 80% of the required functionality (bold, italic, underline, strikethrough, text color, font family, font size, tables with resize, links, lists, indentation). The key gaps are: (1) headings H4-H6 (currently only H1-H3), (2) interactive checklists/task lists (packages installed but not used in RichTextEditor), (3) code blocks with syntax highlighting (requires new `@tiptap/extension-code-block-lowlight` + `lowlight` packages), and (4) word count display (requires new `@tiptap/extension-character-count` package).

The new knowledge base editor should be a **new component** (not a modification of the existing `RichTextEditor.tsx` which serves task descriptions) because it will later integrate with auto-save (Phase 4), locking (Phase 5), tabs (Phase 6), and images (Phase 7). However, it should reuse the same extension configuration patterns and toolbar UI approach from the existing component. The `knowledge/` directory does not yet exist and will be created in this phase.

**Primary recommendation:** Build the new `DocumentEditor` component by extracting and extending patterns from the existing `RichTextEditor.tsx`, adding the three missing capabilities (task lists, syntax-highlighted code blocks, word count), expanding headings to H1-H6, and structuring for future extensibility. Use TipTap JSON as the content format from the start (not HTML).

## Standard Stack

The established libraries/tools for this domain:

### Core (Already Installed -- verified in node_modules at v2.27.2)
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

**Verified not installed:** `npm ls @tiptap/extension-code-block-lowlight lowlight @tiptap/extension-character-count` returns `(empty)`.

### Supporting (Already Installed)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `lucide-react` | ^0.400.0 | Toolbar icons | All toolbar buttons |
| `@radix-ui/react-popover` | installed | Color picker, font picker dropdowns | Toolbar popovers (via `@/components/ui/popover`) |
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
│   ├── editor/                    # EXISTING - task description editor (DO NOT MODIFY)
│   │   └── RichTextEditor.tsx
│   └── knowledge/                 # NEW directory (does not exist yet)
│       ├── document-editor.tsx    # Main DocumentEditor component
│       ├── editor-toolbar.tsx     # Extracted toolbar component
│       ├── editor-extensions.ts   # Extension configuration factory + constants
│       ├── editor-types.ts        # TypeScript interfaces
│       └── editor-styles.css      # TipTap/ProseMirror CSS overrides + highlight.js theme
```

### Pattern 1: Extension Configuration Factory
**What:** Centralize TipTap extension setup in a single factory function.
**When to use:** When the extension list is long and may grow across phases.
**Example:**
```typescript
// editor-extensions.ts
import { Extension } from '@tiptap/core'
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

// Custom FontSize extension -- copy from RichTextEditor.tsx lines 34-64
const FontSize = Extension.create({ /* ... exact copy ... */ })

// Custom Indent extension -- copy from RichTextEditor.tsx lines 67-141
const Indent = Extension.create({ /* ... exact copy ... */ })

export function createDocumentExtensions(options?: { placeholder?: string }) {
  return [
    StarterKit.configure({
      heading: { levels: [1, 2, 3, 4, 5, 6] },  // H1-H6 per EDIT-02
      codeBlock: false,  // CRITICAL: disable to avoid conflict with CodeBlockLowlight
    }),
    Underline,
    TextStyle,
    FontFamily,
    FontSize,
    Indent,
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
      defaultLanguage: 'plaintext',
      HTMLAttributes: { class: 'rounded-md bg-muted p-4 font-mono text-sm overflow-x-auto' },
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
import { Editor } from '@tiptap/react'

interface EditorToolbarProps {
  editor: Editor
}

export function EditorToolbar({ editor }: EditorToolbarProps) {
  // Group toolbar buttons into logical sections with dividers
  return (
    <div className="flex flex-wrap items-center gap-1 p-2 border-b bg-muted/30">
      {/* Undo/Redo group */}
      {/* Text formatting group */}
      {/* Heading dropdown */}
      {/* List group */}
      {/* Table controls (conditional -- only when cursor is in table) */}
      {/* Insert group (link, code block) */}
      {/* Font controls */}
      {/* Color controls */}
    </div>
  )
}
```

### Pattern 3: Reactive Word Count via useEditorState
**What:** Use TipTap's `useEditorState` hook (confirmed available in v2.27.2) for reactive word count that updates on every document change without causing full component re-renders.
**When to use:** EDIT-14 -- word count at bottom of editor.
**Example:**
```typescript
// In the status bar at the bottom of the editor
import { useEditorState } from '@tiptap/react'

function EditorStatusBar({ editor }: { editor: Editor }) {
  const { wordCount, charCount } = useEditorState({
    editor,
    selector: (ctx) => ({
      wordCount: ctx.editor.storage.characterCount?.words() ?? 0,
      charCount: ctx.editor.storage.characterCount?.characters() ?? 0,
    }),
  })

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

### Pattern 5: JSON Content Format
**What:** Use TipTap JSON (`editor.getJSON()` / `editor.commands.setContent(json)`) as the content format, not HTML.
**When to use:** Always for the knowledge base editor. Phase 4 stores content as JSON (primary) + Markdown + plain text.
**Why:** JSON preserves full document structure fidelity, is more efficient to diff, and is the native ProseMirror format. HTML round-tripping can lose information.

### Anti-Patterns to Avoid
- **Modifying the existing `RichTextEditor.tsx`:** That component serves task descriptions with its own debounce, image upload, and max-length logic. The knowledge base editor has different lifecycle needs (auto-save Phase 4, locking Phase 5). Build a new component.
- **Importing from `lowlight/lib/core`:** This is the lowlight v2 import path. With lowlight v3, use `import { common, createLowlight } from 'lowlight'`.
- **Using StarterKit's built-in codeBlock alongside CodeBlockLowlight:** They conflict. Disable codeBlock in StarterKit when using CodeBlockLowlight: `StarterKit.configure({ codeBlock: false })`.
- **Inline CSS for syntax highlighting:** Use highlight.js CSS themes via an import. Lowlight generates classes like `hljs-keyword`, `hljs-string`, etc. that need a theme stylesheet.
- **Using `editor.getHTML()` as the content format:** Use JSON. HTML is lossy for round-tripping.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Syntax highlighting in code blocks | Custom regex highlighter | `@tiptap/extension-code-block-lowlight` + `lowlight` | 190+ language grammars, battle-tested parsing |
| Word/character counting | Manual text splitting | `@tiptap/extension-character-count` | Handles ProseMirror node structure correctly, reactive via `editor.storage` |
| Font size extension | -- | Keep existing custom `FontSize` extension | No official package exists; the custom extension in RichTextEditor.tsx works correctly |
| Indent extension | -- | Keep existing custom `Indent` extension | No official package exists; the custom extension in RichTextEditor.tsx works correctly |
| Table resize handles | Custom drag implementation | `Table.configure({ resizable: true })` | Built-in ProseMirror table resize, handles column width persistence |
| Checklist/task lists | Custom checkbox nodes | `@tiptap/extension-task-list` + `@tiptap/extension-task-item` | Already installed, handles nesting, toggling, keyboard navigation |
| Reactive editor state in toolbar | Manual `editor.on('transaction')` listener | `useEditorState` hook from `@tiptap/react` | Built into TipTap 2.27.2, efficient selector-based reactivity |

**Key insight:** TipTap's extension ecosystem covers every requirement in this phase. The only custom code needed is the `FontSize` extension (already written in RichTextEditor.tsx) and the `Indent` extension (already written in RichTextEditor.tsx). Everything else has an official package.

## Common Pitfalls

### Pitfall 1: StarterKit + CodeBlockLowlight Conflict
**What goes wrong:** Both StarterKit (which includes `codeBlock`) and `CodeBlockLowlight` register a `codeBlock` node type, causing a ProseMirror schema error.
**Why it happens:** StarterKit bundles a basic `codeBlock` by default.
**How to avoid:** Explicitly disable codeBlock in StarterKit: `StarterKit.configure({ codeBlock: false })`.
**Warning signs:** Runtime error: "Duplicate node type: codeBlock".

### Pitfall 2: lowlight v2 vs v3 Import Syntax
**What goes wrong:** Code uses `import { lowlight } from 'lowlight/lib/core'` (v2 syntax) but installs lowlight v3.
**Why it happens:** Most online tutorials and even some TipTap docs reference v2 syntax. There is an open GitHub issue (#4874) about updating TipTap docs for lowlight v3.
**How to avoid:** With lowlight v3 (current), use: `import { common, createLowlight } from 'lowlight'` then `const lowlight = createLowlight(common)`.
**Warning signs:** Module not found error on `lowlight/lib/core`.

### Pitfall 3: Missing highlight.js CSS Theme
**What goes wrong:** Code blocks render but have no syntax coloring (all text is same color).
**Why it happens:** lowlight generates HTML with `hljs-*` classes but no CSS defines their colors.
**How to avoid:** Import a highlight.js theme CSS file: `import 'highlight.js/styles/github-dark.css'` (or any theme). highlight.js is a dependency of lowlight so no additional install needed.
**Warning signs:** Code block content has `<span class="hljs-keyword">` but no visual difference.

### Pitfall 4: Table Resize CSS Missing
**What goes wrong:** Table resize handles are invisible or don't show the resize cursor.
**Why it happens:** TipTap's table resize creates `.column-resize-handle` and `.resize-cursor` elements that need CSS.
**How to avoid:** The existing `RichTextEditor.tsx` already has the correct CSS in editorProps (lines 1018-1026). Copy these styles into `editor-styles.css` as proper CSS rules.
**Warning signs:** Can't see or grab column resize handles.

### Pitfall 5: Task List Checkbox Styling
**What goes wrong:** Task list checkboxes render as native browser checkboxes with no styling, or the layout is broken.
**Why it happens:** ProseMirror renders task items as `<li data-type="taskItem">` with an `<input type="checkbox">` that needs explicit styling.
**How to avoid:** Add CSS for `ul[data-type=taskList]` to remove default list styling and flex-align the checkbox with text. Write these styles in `editor-styles.css`:
```css
ul[data-type="taskList"] { list-style: none; padding-left: 0; }
ul[data-type="taskList"] li { display: flex; align-items: flex-start; gap: 0.5rem; }
ul[data-type="taskList"] input[type="checkbox"] { margin-top: 0.25rem; height: 1rem; width: 1rem; accent-color: hsl(var(--primary)); }
```
**Warning signs:** Checkboxes overlap text, or list bullets appear alongside checkboxes.

### Pitfall 6: Editor Re-renders on Every Keystroke
**What goes wrong:** The entire component re-renders on every keystroke, causing lag.
**Why it happens:** Using `editor.getJSON()` in the `onUpdate` callback and passing it to parent state causes React re-renders.
**How to avoid:** Debounce the `onUpdate` callback. The existing `RichTextEditor.tsx` uses a 500ms debounce. For the knowledge base editor, use 300ms debounce during Phase 3 (will be replaced by the auto-save pipeline in Phase 4).
**Warning signs:** Typing feels sluggish, especially in large documents.

### Pitfall 7: Custom Extensions Missing `addCommands` Type Declarations
**What goes wrong:** TypeScript errors when using `editor.chain().focus().indent().run()` because the custom Indent extension commands aren't in the type system.
**Why it happens:** Custom extensions need module augmentation to extend TipTap's `Commands` interface.
**How to avoid:** Add TypeScript module declarations for custom commands, or use type assertion `(editor.chain().focus() as any).indent().run()` (the existing RichTextEditor.tsx uses the `as any` approach at lines 653/662).
**Warning signs:** TypeScript error "Property 'indent' does not exist on type 'ChainedCommands'".

## Code Examples

### Setting Up CodeBlockLowlight with lowlight v3
```typescript
// Source: TipTap CodeBlockLowlight docs + lowlight v3 npm README
import CodeBlockLowlight from '@tiptap/extension-code-block-lowlight'
import { common, createLowlight } from 'lowlight'

// Create lowlight with common languages (37 languages: js, ts, python, css, html, json, etc.)
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

### CharacterCount for Reactive Word Count Display
```typescript
// Source: TipTap CharacterCount docs (https://tiptap.dev/docs/editor/extensions/functionality/character-count)
import CharacterCount from '@tiptap/extension-character-count'
import { useEditorState } from '@tiptap/react'

// In extension array (no configuration needed for basic word count):
CharacterCount

// In component, use useEditorState for reactive updates:
const { wordCount, charCount } = useEditorState({
  editor,
  selector: (ctx) => ({
    wordCount: ctx.editor.storage.characterCount?.words() ?? 0,
    charCount: ctx.editor.storage.characterCount?.characters() ?? 0,
  }),
})

// Custom word counter is available if needed:
CharacterCount.configure({
  wordCounter: (text) => text.split(/\s+/).filter((word) => word !== '').length,
})
```

### Task List / Checklist Setup
```typescript
// Source: TipTap TaskList/TaskItem extension docs + verified package installed at 2.27.2
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

// Required CSS in editor-styles.css:
// ul[data-type="taskList"] { list-style: none; padding-left: 0; }
// ul[data-type="taskList"] li { display: flex; align-items: flex-start; gap: 0.5rem; }
// ul[data-type="taskList"] input[type="checkbox"] { margin-top: 0.25rem; height: 1rem; width: 1rem; }
```

### Heading Levels H1-H6 Configuration
```typescript
// Override StarterKit default (which only supports H1-H3 in existing RichTextEditor):
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
  },
})

// Add click handler for links in read-only mode via editorProps:
editorProps: {
  handleClick: (view, pos, event) => {
    const target = event.target as HTMLElement
    const link = target.closest('a')
    if (link && !editor?.isEditable) {
      event.preventDefault()
      window.open(link.href, '_blank')
      return true
    }
    return false
  },
}
```

### Custom FontSize Extension (from existing codebase)
```typescript
// Source: RichTextEditor.tsx lines 34-64 (verified in codebase)
const FontSize = Extension.create({
  name: 'fontSize',
  addOptions() {
    return { types: ['textStyle'] }
  },
  addGlobalAttributes() {
    return [{
      types: this.options.types,
      attributes: {
        fontSize: {
          default: null,
          parseHTML: element => element.style.fontSize?.replace(/['"]+/g, '') || null,
          renderHTML: attributes => {
            if (!attributes.fontSize) return {}
            return { style: `font-size: ${attributes.fontSize}` }
          },
        },
      },
    }]
  },
})

// Usage: editor.chain().focus().setMark('textStyle', { fontSize: '1.25rem' }).run()
```

### Existing Constants to Copy from RichTextEditor.tsx
```typescript
// Font sizes (lines 351-356):
const FONT_SIZES = [
  { label: 'Small', value: '0.875rem' },
  { label: 'Normal', value: '1rem' },
  { label: 'Large', value: '1.25rem' },
  { label: 'Heading', value: '1.5rem' },
]

// Font families (lines 358-369):
const FONT_FAMILIES = [
  { label: 'Arial (Default)', value: 'Arial, sans-serif' },
  { label: 'Sans Serif', value: 'ui-sans-serif, system-ui, sans-serif' },
  { label: 'Serif', value: 'ui-serif, Georgia, serif' },
  { label: 'Mono', value: 'ui-monospace, monospace' },
  { label: 'Times New Roman', value: 'Times New Roman, serif' },
  { label: 'Georgia', value: 'Georgia, serif' },
  { label: 'Verdana', value: 'Verdana, sans-serif' },
  { label: 'Tahoma', value: 'Tahoma, sans-serif' },
  { label: 'Trebuchet MS', value: 'Trebuchet MS, sans-serif' },
  { label: 'Courier New', value: 'Courier New, monospace' },
]

const DEFAULT_FONT_FAMILY = 'Arial, sans-serif'

// COLORS array (60 colors, lines 305-326) and HIGHLIGHT_COLORS array (40 colors, lines 328-349)
// Both arrays are in RichTextEditor.tsx -- copy exactly as-is
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| lowlight v2 singleton import | lowlight v3 `createLowlight()` factory | lowlight 3.0 (2023) | Must use new import syntax |
| Manual editor state tracking | `useEditorState` hook with selector | TipTap 2.x (verified in 2.27.2) | Efficient reactive state without full re-renders |
| `editor.storage.characterCount.words()` only | `useEditorState` + `words()` with custom `wordCounter` option | TipTap 2.8+ | Customizable word counting, reactive UI |
| Individual `@tiptap/extension-*` installs | `@tiptap/extensions` bundle available | TipTap 2.6+ | Can install individually or as bundle; project uses individual |

**Deprecated/outdated:**
- `import { lowlight } from 'lowlight/lib/core'`: This is lowlight v2 syntax. With v3, use `import { createLowlight, common } from 'lowlight'`.

## Existing Codebase Reference

### RichTextEditor.tsx Key Details (verified)
- **Location:** `electron-app/src/renderer/components/editor/RichTextEditor.tsx` (1206 lines)
- **Uses HTML format:** `editor.getHTML()` with 500ms debounce (knowledge base editor will use JSON)
- **Heading levels:** Only H1-H3 configured
- **Has image support:** ResizableImage custom extension with upload, paste, drop (NOT needed for Phase 3)
- **Has max-length:** 512KB content size limit (NOT needed for knowledge base)
- **Custom extensions:** FontSize (lines 34-64), Indent (lines 67-141) -- both must be copied
- **Toolbar pattern:** ToolbarButton component (lines 377-398), grouped sections with border-r dividers
- **Table resize CSS:** Tailwind arbitrary variants in editorProps (lines 1018-1026)
- **Constants:** COLORS (60 colors), HIGHLIGHT_COLORS (40 colors), FONT_SIZES (4 options), FONT_FAMILIES (10 options)

### Available UI Components (verified in components/ui/)
- `popover.tsx` -- for color pickers, font dropdowns, heading dropdown
- `dialog.tsx` -- available if needed for link insertion
- `dropdown-menu.tsx` -- alternative for heading/font selection
- `input.tsx` -- for link URL input
- `tooltip.tsx` -- for toolbar button tooltips
- `separator.tsx` -- for toolbar group dividers
- `skeleton.tsx` -- for editor loading state

### No NoteEditor Exists
The previous research incorrectly referenced `electron-app/src/renderer/components/notes/note-editor.tsx`. This file does NOT exist in the codebase. The only existing editor component is `RichTextEditor.tsx`.

## Open Questions

1. **highlight.js Theme for Dark/Light Mode**
   - What we know: The app supports dark mode via Tailwind's `dark:` prefix. highlight.js has separate light and dark themes.
   - What's unclear: Whether to use a single theme that works in both modes or dynamically switch themes.
   - Recommendation: Use `github-dark` theme for code blocks with a dark background (matches the `bg-muted` pattern used throughout the app). Code blocks typically look better on dark backgrounds regardless of app theme.

2. **Editor Content Format for Phase 4 Compatibility**
   - What we know: Phase 4 will store content in three formats (JSON, Markdown, plain text). TipTap can output JSON via `editor.getJSON()` and HTML via `editor.getHTML()`.
   - Resolution: Use TipTap JSON (`editor.getJSON()`) as the primary format from the start. It preserves full fidelity and is what Phase 4 will need for server-side Markdown conversion.

3. **Font Size Values**
   - What we know: The existing `RichTextEditor.tsx` uses rem values (0.875rem, 1rem, 1.25rem, 1.5rem) with only 4 options.
   - Resolution: Keep the same 4-option approach for consistency with the task description editor.

## Sources

### Primary (HIGH confidence)
- Existing codebase: `electron-app/src/renderer/components/editor/RichTextEditor.tsx` -- verified TipTap v2.27.2 configuration, custom FontSize/Indent extensions, toolbar patterns, table resize CSS, all constants
- Existing codebase: `electron-app/package.json` -- verified 16 TipTap packages at ^2.6.0+, installed at 2.27.2
- Existing codebase: `node_modules/@tiptap/react/dist/index.d.ts` -- verified `useEditorState` export exists in 2.27.2
- [TipTap CharacterCount Docs](https://tiptap.dev/docs/editor/extensions/functionality/character-count) -- `words()` API, `wordCounter` config, `useEditorState` usage pattern
- [TipTap CodeBlockLowlight Docs](https://tiptap.dev/docs/editor/extensions/nodes/code-block-lowlight) -- setup with lowlight v3

### Secondary (MEDIUM confidence)
- [lowlight npm README](https://www.npmjs.com/package/lowlight) -- v3 exports `all`, `common`, `createLowlight`; `common` = 37 languages
- [TipTap GitHub Issue #4874](https://github.com/ueberdosis/tiptap/issues/4874) -- confirms lowlight v3 API change, docs update pending

### Tertiary (LOW confidence)
- None -- all findings verified against official sources or existing codebase

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all packages verified in existing `package.json` and `node_modules`; new packages verified against npm registry
- Architecture: HIGH -- patterns derived from working code in `RichTextEditor.tsx` (1206 lines verified); `useEditorState` confirmed in installed dist
- Pitfalls: HIGH -- pitfalls 1-3 verified against official docs/GitHub issues; pitfalls 4-7 derived from actual codebase inspection

**Research date:** 2026-01-31 (re-verified)
**Valid until:** 2026-03-31 (TipTap v2 is stable; no v3 migration planned per STATE.md)
