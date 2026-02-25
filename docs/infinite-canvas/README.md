# Infinite Canvas Editor

**Status**: Planned
**Feature**: Free-form infinite canvas for knowledge base documents
**Dependencies**: TipTap, existing knowledge base infrastructure (019-knowledge-base)

## Problem

The existing knowledge base editor uses a single TipTap instance in a traditional document-flow layout. Long unbroken text and wide tables (e.g., pasted Excel data) cause horizontal overflow that breaks the tab bar and sidebar. Users need a OneNote-style free-form editing surface where content blocks can be positioned freely.

## Solution

A free-form pixel-positioned infinite canvas where users drag text containers to any (x, y) coordinate. Each container holds its own TipTap rich-text editor instance, but only the focused container mounts a live TipTap editor — inactive containers render static HTML for performance.

## Architecture Overview

### Rendering Path

The canvas introduces a **new rendering path inside the existing `EditorPanel`**. When a document's `content_json` contains `"format": "canvas"`, `EditorPanel` renders `CanvasEditor` instead of `DocumentEditor`. Old documents (`content.type === 'doc'`) continue to render in `DocumentEditor` — full backward compatibility.

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Canvas layer | Pure frontend concern | Backend API unchanged — still `PUT /api/documents/{id}/content` with `{ content_json, row_version }` |
| Collaboration | Lock-based exclusive editing | Reuses existing lock system; no Yjs/CRDT needed for canvas |
| TipTap instances | 1 active at a time | Inactive containers use `generateHTML()` for static preview; prevents memory/DOM bloat |
| Canvas bounds | Dynamically computed | No fixed 10000x10000 div; bounds grow from container positions + padding |
| Scrolling | Native `overflow: auto` | Simpler than CSS transform-based panning; works with accessibility |
| Container dragging | mousedown/mousemove/mouseup | @dnd-kit's sortable/droppable model doesn't support free-form pixel positioning |
| Container height | Auto-grow from content | Never stored; like OneNote, containers expand to fit their content |
| Zoom | CSS `transform: scale()` | 75%, 100%, 125% levels for MVP |

### Integration Points

- **EditorPanel** — single integration point; format detection → conditional render
- **Save/lock system** — unchanged; `CanvasEditor` calls `onChange` on every mutation
- **Both surfaces** — works identically in Notes page sidebar and embedded KnowledgePanel
- **Meilisearch** — updated `content_converter.py` extracts plain text from all containers
- **Attachment tracking** — updated `extract_attachment_ids` walks canvas containers

## File Overview

### New Files (9)

| File | Purpose |
|------|---------|
| `canvas-types.ts` | TypeScript interfaces, type guard, factory functions |
| `canvas-editor.tsx` | Top-level canvas component, state management |
| `canvas-viewport.tsx` | Infinite scrollable surface with dot grid |
| `canvas-container.tsx` | Draggable/resizable container box |
| `container-editor.tsx` | Lazy TipTap mount / static HTML preview |
| `canvas-toolbar.tsx` | Toolbar wrapper + canvas-specific controls |
| `canvas-styles.css` | Dot grid, container styling, drag/resize handles |
| `use-canvas-state.ts` | Canvas state management hook |
| `canvas-utils.ts` | Bounds calculation, coordinate math, HTML generation |

All files live in `electron-app/src/renderer/components/knowledge/`.

### Modified Files (4)

| File | Change |
|------|--------|
| `editor-panel.tsx` | Format detection, conditional `CanvasEditor` vs `DocumentEditor` |
| `content-utils.ts` | `isCanvasFormat()` helper; skip canvas docs in `ensureContentHeading` |
| `content_converter.py` | Canvas format → markdown/plain text extraction |
| `document_service.py` | `extract_attachment_ids` walks canvas containers |

## Related Documentation

- [Data Model](./data-model.md) — Canvas JSON format and backward compatibility
- [Components](./components.md) — Component architecture with props and state
- [Backend Changes](./backend-changes.md) — Content converter and service updates
- [Tasks](./tasks.md) — Step-by-step implementation task breakdown
