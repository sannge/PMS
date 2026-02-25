/**
 * Canvas Types
 *
 * TypeScript interfaces for the infinite canvas editor.
 * Canvas documents are stored in the existing content_json column
 * and distinguished by the "format": "canvas" discriminator.
 */

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
  /** Explicit height set by user resize. When undefined, container auto-sizes to content. */
  height?: number
  minWidth: number
  zIndex: number
  content: object
}

export interface CanvasDocument {
  format: 'canvas'
  version: 1
  /** Editable display title (independent of sidebar document name) */
  title?: string
  viewport: Viewport
  containers: CanvasContainerData[]
}

export function isCanvasDocument(doc: unknown): doc is CanvasDocument {
  if (typeof doc !== 'object' || doc === null) return false
  const obj = doc as Record<string, unknown>
  if (obj.format !== 'canvas') return false
  if (obj.version !== 1) return false
  if (!Array.isArray(obj.containers)) return false
  if (typeof obj.viewport !== 'object' || obj.viewport === null) return false
  const vp = obj.viewport as Record<string, unknown>
  if (!Number.isFinite(vp.zoom)) return false
  if (!Number.isFinite(vp.scrollX)) return false
  if (!Number.isFinite(vp.scrollY)) return false
  // Validate containers have required fields with finite numbers
  for (const c of obj.containers as Array<Record<string, unknown>>) {
    if (typeof c !== 'object' || c === null) return false
    if (typeof c.id !== 'string') return false
    if (!Number.isFinite(c.x) || !Number.isFinite(c.y)) return false
    if (!Number.isFinite(c.width) || !Number.isFinite(c.zIndex)) return false
    if (!Number.isFinite(c.minWidth)) return false
    if (typeof c.content !== 'object' || c.content === null) return false
  }
  return true
}

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

export function convertToCanvas(legacyContent: object): CanvasDocument {
  return {
    format: 'canvas',
    version: 1,
    viewport: { scrollX: 0, scrollY: 0, zoom: 1 },
    containers: [
      {
        id: crypto.randomUUID(),
        x: 50,
        y: 50,
        width: 600,
        minWidth: 200,
        zIndex: 1,
        content: legacyContent,
      },
    ],
  }
}
