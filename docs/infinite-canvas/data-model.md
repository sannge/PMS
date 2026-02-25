# Canvas Data Model

## Canvas Document Format

Canvas documents are stored in the existing `content_json` column as opaque JSON. The presence of `"format": "canvas"` distinguishes them from legacy TipTap documents.

### Schema

```json
{
  "format": "canvas",
  "version": 1,
  "viewport": { "scrollX": 0, "scrollY": 0, "zoom": 1 },
  "containers": [
    {
      "id": "uuid-string",
      "x": 50,
      "y": 50,
      "width": 600,
      "minWidth": 200,
      "zIndex": 1,
      "content": { "type": "doc", "content": [{ "type": "paragraph" }] }
    }
  ]
}
```

### Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `format` | `"canvas"` | Discriminator — distinguishes from legacy `{ "type": "doc" }` documents |
| `version` | `number` | Schema version for future migrations (always `1` for now) |
| `viewport` | `Viewport` | Persisted scroll position and zoom level, restored on load |
| `viewport.scrollX` | `number` | Horizontal scroll offset in pixels |
| `viewport.scrollY` | `number` | Vertical scroll offset in pixels |
| `viewport.zoom` | `number` | Zoom level (0.75, 1.0, or 1.25 for MVP) |
| `containers` | `CanvasContainerData[]` | Ordered array of content containers |
| `containers[].id` | `string` | UUID, generated via `crypto.randomUUID()` |
| `containers[].x` | `number` | Left position in canvas pixels |
| `containers[].y` | `number` | Top position in canvas pixels |
| `containers[].width` | `number` | Container width in pixels (user-resizable) |
| `containers[].minWidth` | `number` | Minimum width constraint (default 200px) |
| `containers[].zIndex` | `number` | Stacking order; click-to-front assigns `max(allZIndexes) + 1` |
| `containers[].content` | `object` | Standard TipTap JSON (`{ "type": "doc", "content": [...] }`) |

### Design Rules

- **Height is never stored.** Each container auto-grows from its TipTap content height (OneNote behavior).
- **Width is user-resizable.** Minimum 200px. Content reflows within the container width.
- **zIndex** determines visual stacking. Clicking a container brings it to front.
- **Viewport** is persisted per document — users return to their last scroll position and zoom level.
- **Container order** in the array determines iteration order for text extraction (Meilisearch indexing, markdown export). Order matches creation time.

## TypeScript Types

```typescript
// canvas-types.ts

export interface Viewport {
  scrollX: number
  scrollY: number
  zoom: number
}

export interface CanvasContainerData {
  id: string
  x: number
  y: number
  width: number
  minWidth: number
  zIndex: number
  content: object  // TipTap JSON
}

export interface CanvasDocument {
  format: 'canvas'
  version: 1
  viewport: Viewport
  containers: CanvasContainerData[]
}
```

## Format Detection

```typescript
export function isCanvasDocument(doc: unknown): doc is CanvasDocument {
  return typeof doc === 'object' && doc !== null && (doc as any).format === 'canvas'
}
```

## Factory Functions

```typescript
export function createEmptyCanvas(): CanvasDocument {
  return {
    format: 'canvas',
    version: 1,
    viewport: { scrollX: 0, scrollY: 0, zoom: 1 },
    containers: [],
  }
}

export function createContainer(x: number, y: number): CanvasContainerData {
  return {
    id: crypto.randomUUID(),
    x,
    y,
    width: 600,
    minWidth: 200,
    zIndex: 1,
    content: { type: 'doc', content: [{ type: 'paragraph' }] },
  }
}
```

## Backward Compatibility

### Legacy Documents

Legacy documents have `{ "type": "doc", "content": [...] }` at the top level — no `format` key. `EditorPanel` detects this and renders the existing `DocumentEditor`. Zero changes to legacy document rendering.

### Detection Logic (in EditorPanel)

```
content_json parsed → object
  ├── has "format": "canvas"  → CanvasEditor
  └── has "type": "doc"       → DocumentEditor (existing)
```

### Convert to Canvas (One-Way)

A "Convert to Canvas" action wraps existing TipTap content in a single container at position (50, 50):

```typescript
function convertToCanvas(legacyContent: object): CanvasDocument {
  return {
    format: 'canvas',
    version: 1,
    viewport: { scrollX: 0, scrollY: 0, zoom: 1 },
    containers: [{
      id: crypto.randomUUID(),
      x: 50,
      y: 50,
      width: 600,
      minWidth: 200,
      zIndex: 1,
      content: legacyContent,
    }],
  }
}
```

This is a one-way conversion for MVP — no back-conversion from canvas to document.

### Version Migration

The `version` field enables future schema changes. When loading, if `version < CURRENT_VERSION`, run migration functions in sequence. For `version: 1` (the only version), no migration is needed.
