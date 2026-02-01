---
phase: 03-rich-text-editor-core
plan: 02
subsystem: frontend-editor
tags: [tiptap, toolbar, headings, lists, code-block, indent]
depends_on: ["03-01"]
provides:
  - Heading dropdown (Paragraph + H1-H6) with Popover UI
  - Bullet list, numbered list, and checklist toolbar buttons
  - Code block toggle button
  - Indent/outdent controls
affects:
  - 03-03 (table toolbar controls -- placeholder preserved)
  - 03-04 (link/font/color toolbar -- placeholder preserved)
tech-stack:
  added: []
  patterns:
    - "Popover-based heading dropdown with font-size preview per level"
    - "as any cast for custom Indent extension commands (not in TipTap type system)"
key-files:
  created: []
  modified:
    - electron-app/src/renderer/components/knowledge/editor-toolbar.tsx
decisions:
  - "Heading dropdown uses Radix Popover (not Select) for richer preview rendering"
  - "HeadingOption data-driven pattern with level + className for DRY heading list"
metrics:
  duration: "~2 min"
  completed: "2026-02-01"
---

# Phase 3 Plan 2: Heading, List, Code Block & Indent Toolbar Summary

Heading dropdown (Paragraph + H1-H6) with Popover, list/checklist buttons, code block toggle, and indent/outdent controls added to editor toolbar.

## What Was Done

### Task 1: Add heading dropdown, list buttons, code block, and indent controls

- Added `HeadingDropdown` component using Radix Popover with controlled open state
- `getCurrentHeadingLabel()` helper checks `editor.isActive('heading', { level })` for H1-H6, falls back to "Paragraph"
- `HEADING_OPTIONS` data array with 7 entries (Paragraph + H1-H6), each with label, level, and Tailwind class for font-size preview
- Popover trigger shows dynamic icon (Heading or Pilcrow) + current label + chevron
- Active heading option highlighted with `bg-primary/10`
- Popover closes on selection via `setOpen(false)`
- Bullet list button: `toggleBulletList()` with `isActive('bulletList')`
- Numbered list button: `toggleOrderedList()` with `isActive('orderedList')`
- Checklist button: `toggleTaskList()` with `isActive('taskList')`
- Code block button: `toggleCodeBlock()` with `isActive('codeBlock')`
- Indent/outdent buttons use `(editor.chain().focus() as any).indent().run()` pattern per research pitfall 7
- All existing toolbar sections (undo/redo, basic formatting) preserved
- Placeholder comments for Plan 03-03 (table) and Plan 03-04 (link/font/color) preserved

## Deviations from Plan

None - plan executed exactly as written.

## Commits

| # | Hash | Message |
|---|------|---------|
| 1 | 8b5ae67 | feat(03-02): add heading dropdown, list buttons, code block, and indent controls to toolbar |

## Verification

- `npx tsc --noEmit` passes (zero new errors; all errors are pre-existing in other files)
- Toolbar contains all required command calls: toggleHeading, toggleBulletList, toggleOrderedList, toggleTaskList, toggleCodeBlock
- Heading dropdown uses Popover with 7 options (Paragraph + H1-H6)
- Indent/outdent use `as any` pattern for custom extension commands
- Placeholder comments preserved for plans 03-03 and 03-04

## Next Phase Readiness

Plans 03-03 and 03-04 can proceed immediately. Placeholder comments mark insertion points for table controls and link/font/color controls.
