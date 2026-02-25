# Component Architecture

## Component Tree

```
EditorPanel (existing, modified — format detection)
├── DocumentActionBar (existing, unchanged)
├── DocumentEditor (existing, unchanged — for legacy docs)
└── CanvasEditor (NEW — for canvas docs)
    ├── CanvasToolbar (NEW — wraps EditorToolbar + canvas controls)
    └── CanvasViewport (NEW — scrollable infinite surface)
        └── CanvasContainer[] (NEW — draggable/resizable boxes)
            └── ContainerEditor (NEW — lazy TipTap / static HTML)
```

All new components live in `electron-app/src/renderer/components/knowledge/`.

---

## CanvasEditor (`canvas-editor.tsx`)

Top-level canvas component. Manages canvas state, owns the single TipTap toolbar, handles save serialization.

### Props

```typescript
interface CanvasEditorProps {
  canvasData: CanvasDocument
  onChange?: (canvasJson: object) => void
  editable: boolean
  className?: string
  documentId?: string
  updatedAt?: string
  onBaselineSync?: (json: object) => void
}
```

### State

```typescript
const [containers, setContainers] = useState<CanvasContainerData[]>([])
const [activeContainerId, setActiveContainerId] = useState<string | null>(null)
const [viewport, setViewport] = useState<Viewport>({ scrollX: 0, scrollY: 0, zoom: 1 })
const [activeEditor, setActiveEditor] = useState<Editor | null>(null)
```

### Behavior

- Initializes containers from `canvasData` prop
- Tracks which container is "active" — only the active one mounts a real TipTap instance
- Passes `activeEditor` to `CanvasToolbar`; toolbar commands apply to the focused container's editor
- Serializes all containers back to `CanvasDocument` JSON on every change → calls `onChange`
- Click on empty canvas area creates a new container at that position (edit mode only)
- Image upload reused from `document-editor.tsx` patterns

### Toolbar Switching (Critical Pattern)

1. `CanvasEditor` holds `useState<Editor | null>(null)` for the active editor
2. Each `ContainerEditor` calls `onEditorReady(editor)` when TipTap mounts, `onEditorReady(null)` when it unmounts
3. `CanvasEditor.handleEditorMount(containerId, editor)` calls `setActiveEditor(editor)`
4. `CanvasToolbar` receives `activeEditor={activeEditor}` and passes it to `EditorToolbar`
5. On container switch: old editor unmounts → `onEditorReady(null)` → new editor mounts → `onEditorReady(newEditor)` → toolbar re-renders

Using React state (not ref) ensures the toolbar re-renders when the editor changes. The performance cost is negligible since container switching is user-initiated.

---

## CanvasViewport (`canvas-viewport.tsx`)

Infinite scrollable canvas surface with dot grid background.

### Props

```typescript
interface CanvasViewportProps {
  children: React.ReactNode
  viewport: Viewport
  onViewportChange: (v: Viewport) => void
  onCanvasClick: (canvasX: number, canvasY: number) => void
  editable: boolean
  className?: string
}
```

### Implementation

- **Outer div**: `overflow: auto`, fills available space, captures scroll events to update viewport
- **Inner div**: dynamically sized from `computeCanvasBounds()`:
  ```typescript
  maxRight = Math.max(maxRight, container.x + container.width + 500)
  maxBottom = Math.max(maxBottom, container.y + measuredHeight + 500)
  // minimums: 3000 x 2000
  ```
- **Dot grid background** via CSS:
  ```css
  background-image: radial-gradient(circle, hsl(var(--border)) 1px, transparent 1px);
  background-size: 20px 20px;
  ```
- **Click-to-create**: `onClick` on inner div checks `event.target === event.currentTarget` (direct click on canvas, not on a container), then calls `onCanvasClick(canvasX, canvasY)`. Disabled in view mode.

---

## CanvasContainer (`canvas-container.tsx`)

A single absolutely-positioned container on the canvas. Handles drag-to-move and resize-to-width.

### Props

```typescript
interface CanvasContainerProps {
  container: CanvasContainerData
  isActive: boolean
  editable: boolean
  onActivate: (id: string) => void
  onMove: (id: string, x: number, y: number) => void
  onResize: (id: string, width: number) => void
  onContentChange: (id: string, content: object) => void
  onDelete: (id: string) => void
  onBringToFront: (id: string) => void
  onEditorMount: (id: string, editor: Editor | null) => void
  documentId?: string
}
```

### Implementation

- **Positioning**: `position: absolute; left: ${x}px; top: ${y}px; width: ${width}px`
- **Drag-to-move**: Reuses the `drawio-node.tsx` resize pattern (mousedown → document-level mousemove/mouseup)
  - Drag handle: 8px strip or grip icon at top of container
  - mousedown: record start position and container x,y
  - mousemove: direct DOM manipulation for 60fps smoothness
  - mouseup: commit final position via `onMove`
- **Resize**: Right-edge resize handle, 4px wide, `cursor: ew-resize`. Same pattern as `ResizableImageView` in `editor-extensions.tsx`. Only width is resizable.
- **Active state**: `ring-2 ring-primary` border when selected
- **Delete**: X button on hover, top-right corner, edit mode only
- **Height reporting**: `ResizeObserver` on container div reports measured height to parent for bounds calculation

### Why NOT @dnd-kit

@dnd-kit's sortable/droppable model is slot-based and doesn't support arbitrary pixel coordinate positioning. The `drawio-node.tsx` mouse event pattern is simpler and more appropriate for free-form canvas positioning.

---

## ContainerEditor (`container-editor.tsx`)

Lazy-loaded TipTap editor inside each container. Renders static HTML when inactive, mounts full TipTap when active.

### Props

```typescript
interface ContainerEditorProps {
  content: object           // TipTap JSON
  isActive: boolean
  editable: boolean
  onChange: (json: object) => void
  onEditorReady: (editor: Editor | null) => void
  documentId?: string
}
```

### Implementation

- **Inactive** (`isActive=false`): Render via `generateHTML()` from `@tiptap/html` inside a div with `dangerouslySetInnerHTML`, styled with `prose prose-sm` + `editor-styles.css` selectors
- **Active** (`isActive=true`): Mount TipTap via `useEditor` with `createDocumentExtensions()`; wire `onUpdate` → `onChange`; call `onEditorReady(editor)` on mount, `onEditorReady(null)` on unmount
- **Transition safety**: Cleanup effect captures `editor.getJSON()` and calls `onChange` before the editor is destroyed, preventing content loss on container switch
- **Single instance**: Only 1 TipTap instance is mounted at any time across the entire canvas

### Static Extension List

`@tiptap/html`'s `generateHTML()` needs a schema-compatible extension list. Custom extensions (`ResizableImage`, `DrawioNode`) use `ReactNodeViewRenderer` only for the interactive editor — their `renderHTML`/`parseHTML` methods work standalone. A static extension list (without `Placeholder`, `CharacterCount`, without `ReactNodeViewRenderer`) must be exported from `editor-extensions.tsx` for use with `generateStaticHTML()`.

---

## CanvasToolbar (`canvas-toolbar.tsx`)

Wraps the existing `EditorToolbar` and adds canvas-specific controls.

### Props

```typescript
interface CanvasToolbarProps {
  activeEditor: Editor | null
  editable: boolean
  onImageUpload?: (file: File) => void
  zoom: number
  onZoomChange: (zoom: number) => void
}
```

### Implementation

- When `activeEditor` is null: shows disabled state with message "Click a container to edit"
- When `activeEditor` is set: renders existing `EditorToolbar` with that editor instance
- Right side: zoom controls (`ZoomIn`, `ZoomOut`, `RotateCcw` from lucide-react), "New Container" button (`PlusSquare` icon)
- Fixed at top of `CanvasEditor`, does NOT scroll with canvas

---

## Custom Hook: `use-canvas-state.ts`

Encapsulates all canvas state mutations.

```typescript
function useCanvasState(
  initialData: CanvasDocument,
  onChange?: (doc: CanvasDocument) => void
) {
  // Returns:
  // containers: CanvasContainerData[]
  // viewport: Viewport
  // activeContainerId: string | null
  //
  // addContainer(x: number, y: number): void
  // moveContainer(id: string, x: number, y: number): void
  // resizeContainer(id: string, width: number): void
  // deleteContainer(id: string): void
  // updateContainerContent(id: string, json: object): void
  // setActiveContainer(id: string | null): void
  // bringToFront(id: string): void
  // setViewport(v: Viewport): void
}
```

Every mutation serializes the full `CanvasDocument` and calls `onChange`.

---

## Utility: `canvas-utils.ts`

| Function | Purpose |
|----------|---------|
| `computeCanvasBounds(containers, measuredHeights)` | Returns `{ width, height }` for the inner canvas div |
| `canvasCoordFromEvent(event, viewportRef)` | Converts mouse event to canvas coordinates |
| `generateStaticHTML(content, extensions)` | Wraps `@tiptap/html`'s `generateHTML` |
| `bringToFront(containers, id)` | Returns new containers array with target `zIndex = max + 1` |

---

## Patterns Reused from Existing Codebase

| Pattern | Source File | Usage |
|---------|-------------|-------|
| Drag/resize via mousedown→mousemove→mouseup | `drawio-node.tsx:67-96` | Container drag-to-move and width resize |
| TipTap extension factory | `editor-extensions.tsx:503-578` | Container editor instances + static HTML |
| Image upload flow | `document-editor.tsx:94-152` | Canvas editor image handling |
| Ref-based callback stability | `document-editor.tsx:75-91` | Canvas state callbacks |
| Toolbar receives editor instance | `document-editor.tsx:466` | Active container's editor → toolbar |
| NodeView editable/readonly check | `drawio-node.tsx:33-196` | ContainerEditor active/inactive states |
