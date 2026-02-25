# Implementation Tasks

Step-by-step task breakdown for the infinite canvas editor. Tasks are ordered by dependency — each phase builds on the previous one.

---

## Phase 1: Foundation — Types + Detection

### Task 1.1: Create `canvas-types.ts`

**File**: `electron-app/src/renderer/components/knowledge/canvas-types.ts`

Create all TypeScript interfaces and utility functions:
- `Viewport` interface (`scrollX`, `scrollY`, `zoom`)
- `CanvasContainerData` interface (`id`, `x`, `y`, `width`, `minWidth`, `zIndex`, `content`)
- `CanvasDocument` interface (`format`, `version`, `viewport`, `containers`)
- `isCanvasDocument(doc: unknown): doc is CanvasDocument` type guard
- `createEmptyCanvas(): CanvasDocument` factory
- `createContainer(x: number, y: number): CanvasContainerData` factory

**Acceptance**: Types compile with strict mode. Type guard correctly identifies canvas vs legacy documents.

---

### Task 1.2: Update `content-utils.ts`

**File**: `electron-app/src/renderer/components/knowledge/content-utils.ts`

- Add `isCanvasFormat(content: object | null): boolean` helper
- Modify `ensureContentHeading()` (if it exists) to return canvas documents unchanged — canvas docs don't have a single heading structure

**Acceptance**: `isCanvasFormat` returns `true` for `{ format: "canvas", ... }` and `false` for `{ type: "doc", ... }` or `null`.

---

### Task 1.3: Update `editor-panel.tsx` — Format Detection

**File**: `electron-app/src/renderer/components/knowledge/editor-panel.tsx`

- Parse `content_json` into object
- Branch on `isCanvasDocument()`:
  - Canvas → render `<CanvasEditor>`
  - Legacy → render existing `<DocumentEditor>`
- Pass through all existing props (`editable`, `onChange`, `documentId`, etc.)

**Acceptance**: Legacy documents render identically to before. Canvas documents render `CanvasEditor` (stub is fine for this task).

---

## Phase 2: Canvas Infrastructure

### Task 2.1: Create `canvas-utils.ts`

**File**: `electron-app/src/renderer/components/knowledge/canvas-utils.ts`

Implement utility functions:
- `computeCanvasBounds(containers, measuredHeights: Map<string, number>)` → `{ width: number, height: number }`
  - Width: `Math.max(3000, max(container.x + container.width) + 500)`
  - Height: `Math.max(2000, max(container.y + measuredHeight) + 500)`
- `canvasCoordFromEvent(event: MouseEvent, viewportRef: HTMLDivElement)` → `{ x: number, y: number }` (canvas-space coordinates accounting for scroll offset)
- `generateStaticHTML(content: object, extensions: Extension[])` → `string` (wraps `@tiptap/html`'s `generateHTML`)
- `bringToFront(containers: CanvasContainerData[], id: string)` → new array with target container's `zIndex` set to `max(allZIndexes) + 1`

**Acceptance**: Each function unit-testable in isolation.

---

### Task 2.2: Create `use-canvas-state.ts`

**File**: `electron-app/src/renderer/components/knowledge/use-canvas-state.ts`

Custom hook managing all canvas mutations:
- State: `containers`, `viewport`, `activeContainerId`
- Actions: `addContainer(x, y)`, `moveContainer(id, x, y)`, `resizeContainer(id, width)`, `deleteContainer(id)`, `updateContainerContent(id, json)`, `setActiveContainer(id | null)`, `bringToFront(id)`, `setViewport(v)`
- Every mutation serializes the full `CanvasDocument` and calls `onChange` callback

**Acceptance**: Hook initializes from `CanvasDocument` prop. All mutations produce valid `CanvasDocument` JSON. `onChange` fires on every mutation.

---

### Task 2.3: Create `canvas-styles.css`

**File**: `electron-app/src/renderer/components/knowledge/canvas-styles.css`

CSS for canvas-specific styling:
- Dot grid background: `radial-gradient(circle, hsl(var(--border)) 1px, transparent 1px)` with `background-size: 20px 20px`
- Container styling: white background, subtle border, rounded corners, drop shadow
- Active container: `ring-2 ring-primary`
- Drag handle: 8px strip at top with grip dots pattern, `cursor: grab` / `cursor: grabbing`
- Resize handle: 4px strip on right edge, `cursor: ew-resize`
- Delete button: positioned top-right, visible on hover
- Static preview styling: inherits from `editor-styles.css` prose classes

**Acceptance**: Styles render correctly in both light and dark themes. Uses CSS variables from the design system.

---

## Phase 3: Canvas Components (bottom-up)

### Task 3.1: Create `container-editor.tsx`

**File**: `electron-app/src/renderer/components/knowledge/container-editor.tsx`

Lazy TipTap editor / static HTML preview:
- **Inactive** (`isActive=false`): render `generateHTML()` output via `dangerouslySetInnerHTML`, styled with `prose prose-sm` + editor-styles.css
- **Active** (`isActive=true`): mount TipTap via `useEditor` with `createDocumentExtensions()`; wire `onUpdate` → `onChange`; call `onEditorReady(editor)` on mount, `onEditorReady(null)` on unmount
- Cleanup effect: captures `editor.getJSON()` and calls `onChange` before editor is destroyed (prevents content loss on container switch)

**Prerequisite**: Export a schema-only extension list (without `ReactNodeViewRenderer`, `Placeholder`, `CharacterCount`) from `editor-extensions.tsx` for use with `generateHTML()`.

**Acceptance**: Switching between active/inactive preserves content. Only 1 TipTap instance exists at any time. Static preview visually matches the active editor appearance.

---

### Task 3.2: Create `canvas-container.tsx`

**File**: `electron-app/src/renderer/components/knowledge/canvas-container.tsx`

Draggable/resizable container box:
- Absolute positioning from `container.x`, `container.y`, `container.width`
- **Drag**: mousedown on drag handle → document-level mousemove/mouseup (reuse `drawio-node.tsx:67-96` pattern). Direct DOM manipulation during drag for 60fps, commit via `onMove` on mouseup
- **Resize**: Right-edge handle, same mouse pattern, only adjusts width. Enforce `minWidth`
- **Click**: calls `onActivate(id)` and `onBringToFront(id)`
- **Delete**: X button on hover (top-right), edit mode only, calls `onDelete(id)`
- **Height reporting**: `ResizeObserver` on the container div, reports measured height to parent

**Acceptance**: Drag is smooth (no jank). Resize respects minWidth. Delete removes container. Height correctly reported as content changes.

---

### Task 3.3: Create `canvas-viewport.tsx`

**File**: `electron-app/src/renderer/components/knowledge/canvas-viewport.tsx`

Infinite scrollable surface:
- Outer div: `overflow: auto`, fills available space
- Inner div: dynamically sized via `computeCanvasBounds()` (min 3000x2000)
- Dot grid background on inner div
- Scroll events update `viewport.scrollX/scrollY` via `onViewportChange`
- Click on inner div (not on a child container): `event.target === event.currentTarget` check, then `onCanvasClick(canvasX, canvasY)`. Disabled in read-only mode

**Acceptance**: Canvas scrolls smoothly in all directions. Inner div grows when containers are near edges. Click-to-create fires only on empty canvas area.

---

### Task 3.4: Create `canvas-toolbar.tsx`

**File**: `electron-app/src/renderer/components/knowledge/canvas-toolbar.tsx`

Toolbar wrapper:
- When `activeEditor` is null: disabled state with "Click a container to edit" message
- When `activeEditor` is set: renders existing `EditorToolbar` with that editor instance
- Right side: zoom controls (`ZoomIn`, `ZoomOut`, `RotateCcw` icons), "New Container" button (`PlusSquare` icon)
- Fixed at top of `CanvasEditor`, does NOT scroll with canvas

**Acceptance**: Toolbar reflects the formatting state of the currently active container. Zoom buttons update zoom level. "New Container" creates a container in the viewport center.

---

### Task 3.5: Create `canvas-editor.tsx`

**File**: `electron-app/src/renderer/components/knowledge/canvas-editor.tsx`

Top-level composition:
- Uses `useCanvasState` hook for state management
- Composes `CanvasToolbar` + `CanvasViewport` + `CanvasContainer[]`
- Manages `activeEditor` state via `handleEditorMount(containerId, editor)`
- Handles image upload (reuse pattern from `document-editor.tsx:94-152`)
- Passes `onBaselineSync` through for save system integration

**Acceptance**: Full canvas workflow works: create containers by clicking canvas, type in containers, drag/resize containers, switch between containers (toolbar updates), delete containers.

---

## Phase 4: Backend Updates

### Task 4.1: Update `content_converter.py`

**File**: `fastapi-backend/app/services/content_converter.py`

- Add canvas format guard to `tiptap_json_to_markdown()` — check `format == "canvas"` before `type == "doc"`
- Add `_canvas_to_markdown(canvas)` — extracts markdown from containers with `## Section N` headers
- Add canvas format guard to `tiptap_json_to_plain_text()`
- Add `_canvas_to_plain_text(canvas)` — extracts plain text, double-newline separated

**Acceptance**: Canvas documents produce meaningful markdown and plain text. Legacy documents produce identical output to before. Unit tests pass.

---

### Task 4.2: Update `document_service.py`

**File**: `fastapi-backend/app/services/document_service.py`

- Extend `extract_attachment_ids` to check `format == "canvas"` and iterate through each container's `content`, applying the same recursive `walk` function

**Acceptance**: Image attachments inside canvas containers are correctly tracked. Legacy document attachment extraction unchanged. Unit tests pass.

---

## Phase 5: Integration and Polish

### Task 5.1: Wire up `EditorPanel`

**File**: `electron-app/src/renderer/components/knowledge/editor-panel.tsx`

Full integration of `CanvasEditor` into `EditorPanel`:
- All `editMode` props pass through correctly
- Save/lock system works with canvas documents
- Dirty detection works (canvas mutations trigger onChange → dirty state)
- Read-only mode disables all canvas editing features

**Acceptance**: Canvas documents save and reload correctly (positions, content preserved). Lock system works. Read-only users see static canvas (no drag, no create, no edit).

---

### Task 5.2: Add "Convert to Canvas" action

**Location**: `DocumentActionBar` or document context menu

- Button/menu item to convert a legacy document to canvas format
- Wraps existing TipTap content in a single container at position (50, 50) with width 600
- One-way conversion (no back-conversion for MVP)
- Confirmation dialog recommended since it's irreversible

**Acceptance**: Conversion preserves all existing content. Document renders in canvas mode after conversion. Undo is not supported (confirm dialog warns user).

---

### Task 5.3: "New Canvas Document" creation flow

**Location**: Document creation dialog/menu

- Add toggle or dropdown in document creation UI to choose between "Document" and "Canvas"
- Canvas option creates document with `content_json = JSON.stringify(createEmptyCanvas())`
- Opens directly into canvas editor with empty dot grid

**Acceptance**: New canvas documents are created and immediately editable. The creation flow is intuitive alongside the existing document creation.

---

## Verification Checklist

### Backend
- [ ] Unit tests for `_canvas_to_markdown()` with multi-container canvas
- [ ] Unit tests for `_canvas_to_plain_text()` with multi-container canvas
- [ ] Unit tests for `extract_attachment_ids()` with canvas format
- [ ] All existing tests pass unchanged (backward compatibility)

### Frontend Manual Testing
- [ ] Create new canvas document → empty canvas with dot grid
- [ ] Click canvas → container appears at click position
- [ ] Type in container → TipTap editor works with full formatting
- [ ] Drag container → repositions smoothly at 60fps
- [ ] Resize container → width changes, content reflows
- [ ] Click different container → previous deactivates (static HTML), new activates (TipTap)
- [ ] Toolbar reflects active container's formatting state
- [ ] Save → reload → containers at same positions with same content
- [ ] Open legacy document → renders in DocumentEditor (no regression)
- [ ] Paste Excel table inside container → contained within container bounds
- [ ] Long text in container → wraps within container width (no page overflow)
- [ ] Read-only mode → no drag, no create, no edit, no delete
- [ ] Convert to Canvas → content preserved in single container

---

## Known Challenges and Mitigations

| Challenge | Mitigation |
|-----------|------------|
| `generateHTML` extension compatibility | Custom extensions have standalone `renderHTML`/`parseHTML`; export a schema-only extension list from `editor-extensions.tsx` |
| Measuring container height for bounds | `ResizeObserver` on each container div; store measured heights in a `Map` in `CanvasEditor` (debounced) |
| Click-to-create vs container-click interference | Check `event.target === event.currentTarget` on canvas inner div |
| Editor focus management on container switch | Cleanup effect in `ContainerEditor` captures `editor.getJSON()` before unmount |
| Large number of containers (50+) | MVP is fine for 20-30; future optimization via `IntersectionObserver` virtualization |
