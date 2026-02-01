---
phase: 03-rich-text-editor-core
plan: 01
subsystem: frontend-editor
tags: [tiptap, prosemirror, rich-text, lowlight, code-block]
depends_on: []
provides:
  - DocumentEditor component with TipTap editor and basic formatting toolbar
  - Extension factory with 18+ extensions configured upfront
  - ProseMirror CSS for tables, task lists, code blocks, headings, highlights
  - TypeScript interfaces for editor props
affects:
  - 03-02 (heading/list toolbar sections)
  - 03-03 (table toolbar controls)
  - 03-04 (font/color/link toolbar + status bar)
tech-stack:
  added:
    - "@tiptap/extension-code-block-lowlight@2.27.2"
    - "lowlight@3.3.0"
    - "@tiptap/extension-character-count@2.27.2"
  patterns:
    - "Extension factory pattern (createDocumentExtensions) -- configure all extensions once, toolbar plans only add UI"
    - "useRef-based debounce for editor onChange (300ms)"
    - "JSON-first content model (editor.getJSON() not getHTML())"
key-files:
  created:
    - electron-app/src/renderer/components/knowledge/editor-types.ts
    - electron-app/src/renderer/components/knowledge/editor-extensions.ts
    - electron-app/src/renderer/components/knowledge/editor-styles.css
    - electron-app/src/renderer/components/knowledge/editor-toolbar.tsx
    - electron-app/src/renderer/components/knowledge/document-editor.tsx
  modified: []
decisions:
  - "Extension factory pattern: all extensions configured in createDocumentExtensions(), toolbar plans only add UI sections"
  - "JSON content format: onChange emits editor.getJSON() for three-format storage strategy"
  - "lowlight v3 syntax: import { common, createLowlight } from 'lowlight' (not v2 hljs)"
  - "Added proper ProseMirror TypeScript types to Indent extension (fixing implicit any from original RichTextEditor)"
metrics:
  duration: "~6 min"
  completed: "2026-02-01"
---

# Phase 3 Plan 1: Editor Foundation & Extension Factory Summary

TipTap editor foundation with extension factory pattern, basic formatting toolbar, and ProseMirror CSS.

## What Was Done

### Task 1: Install packages, create types, extension factory, and CSS
- Installed 3 new npm packages: `@tiptap/extension-code-block-lowlight`, `lowlight`, `@tiptap/extension-character-count` (all pinned to TipTap v2 compatible versions)
- Created `editor-types.ts` with `DocumentEditorProps`, `EditorToolbarProps`, and `ToolbarSection` type
- Created `editor-extensions.ts` with `createDocumentExtensions()` factory configuring 18+ extensions:
  - StarterKit (headings H1-H6, codeBlock disabled), Underline, TextStyle, FontFamily, FontSize (custom), Indent (custom)
  - Color, Highlight (multicolor), TextAlign, Link
  - Table (resizable), TableRow, TableCell, TableHeader
  - TaskList, TaskItem (nested), CodeBlockLowlight (lowlight v3 + common languages), CharacterCount, Placeholder
- Exported all constants: COLORS (60), HIGHLIGHT_COLORS (40), FONT_SIZES (4), FONT_FAMILIES (10), DEFAULT_FONT_FAMILY
- Created `editor-styles.css` with highlight.js github-dark theme import and ProseMirror styles for headings, tables, task lists, code blocks, lists, blockquotes, links, and placeholder

### Task 2: Create EditorToolbar and DocumentEditor components
- Created `editor-toolbar.tsx` with ToolbarButton helper, ToolbarSeparator, and EditorToolbar component
- Toolbar sections: Undo/Redo | Bold/Italic/Underline/Strikethrough | placeholder comments for plans 03-02 through 03-04
- Created `document-editor.tsx` composing EditorToolbar + EditorContent
- Debounced onChange (300ms) using useRef + setTimeout pattern (no lodash dependency)
- Content sync only applies when editor is not focused (prevents cursor jump during typing)
- Editable prop sync via useEffect

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed implicit any types in Indent extension**
- **Found during:** Task 1
- **Issue:** The Indent extension copied from RichTextEditor.tsx had implicit `any` types on `tr`, `state`, `dispatch`, `node`, `pos` parameters causing TS7031/TS7006 errors
- **Fix:** Added ProseMirror type imports (`Transaction`, `EditorState`, `Node`) and explicit type annotations. Cast return as `Partial<RawCommands>` to satisfy TS2322
- **Files modified:** editor-extensions.ts
- **Commit:** dee16a9

**2. [Rule 1 - Bug] Removed unused Editor import in toolbar**
- **Found during:** Task 2
- **Issue:** `Editor` was imported from `@tiptap/react` but only used via the `EditorToolbarProps` type import
- **Fix:** Removed the direct `Editor` import (type comes through EditorToolbarProps)
- **Files modified:** editor-toolbar.tsx
- **Commit:** 495c187

## Commits

| # | Hash | Message |
|---|------|---------|
| 1 | dee16a9 | feat(03-01): add editor types, extension factory, and ProseMirror CSS |
| 2 | 495c187 | feat(03-01): add EditorToolbar and DocumentEditor components |

## Verification

- All 5 files exist in `electron-app/src/renderer/components/knowledge/`
- `npx tsc --noEmit` passes with zero errors in knowledge/ files (52 pre-existing errors in other files unchanged)
- npm packages installed: @tiptap/extension-code-block-lowlight@2.27.2, lowlight@3.3.0, @tiptap/extension-character-count@2.27.2
- Extension factory configures StarterKit with `codeBlock: false` (no conflict with CodeBlockLowlight)
- CSS imports `highlight.js/styles/github-dark.css`

## Next Phase Readiness

Plans 03-02 through 03-04 can proceed immediately. They only need to:
1. Import the editor instance from EditorToolbarProps
2. Add toolbar UI sections where the placeholder comments are
3. No new extensions needed -- all are already configured in `createDocumentExtensions()`
