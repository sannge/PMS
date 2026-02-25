/**
 * Canvas Utilities
 *
 * Pure functions for canvas bounds computation, coordinate math,
 * static HTML generation, and z-index management.
 */

import { generateHTML } from '@tiptap/html'
import DOMPurify from 'dompurify'
import type { JSONContent, Extensions } from '@tiptap/core'
import type { CanvasContainerData } from './canvas-types'

/** Escape HTML special characters for safe insertion into innerHTML */
export function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

const MAX_COORD = 50000

export function computeCanvasBounds(
  containers: CanvasContainerData[],
  measuredHeights: Map<string, number>,
  measuredWidths?: Map<string, number>,
): { width: number; height: number } {
  // When no containers exist, return 0 — the viewport will fill via CSS (100%)
  if (containers.length === 0) {
    return { width: 0, height: 0 }
  }

  // Minimum canvas size when containers exist — enough padding to scroll around
  let maxRight = 1200
  let maxBottom = 800

  for (const c of containers) {
    const h = c.height ?? measuredHeights.get(c.id) ?? 200
    // Use measured width (accounts for content-expanded containers) or stored width
    const w = Math.max(c.width, measuredWidths?.get(c.id) ?? c.width)
    maxRight = Math.max(maxRight, c.x + w + 300)
    maxBottom = Math.max(maxBottom, c.y + h + 300)
  }

  return { width: maxRight, height: maxBottom }
}

export function generateStaticHTML(content: object, extensions: Extensions): string {
  try {
    const raw = generateHTML(content as JSONContent, extensions)
    return DOMPurify.sanitize(raw, {
      ADD_ATTR: ['data-type', 'data-drawio-xml', 'data-attachment-id', 'contenteditable', 'draggable', 'colspan', 'rowspan', 'colwidth', 'style'],
      ADD_TAGS: ['colgroup', 'col'],
      FORBID_TAGS: ['script', 'iframe', 'object', 'embed', 'form'],
    })
  } catch {
    return '<p></p>'
  }
}

export function bringToFront(
  containers: CanvasContainerData[],
  id: string,
): CanvasContainerData[] {
  const maxZ = containers.reduce((max, c) => Math.max(max, c.zIndex), 0)
  if (maxZ > 10000) {
    return normalizeZIndices(containers, id)
  }
  return containers.map((c) =>
    c.id === id ? { ...c, zIndex: maxZ + 1 } : c,
  )
}

/**
 * Normalize z-indices to prevent unbounded growth.
 * Preserves relative ordering and places the target container on top.
 */
function normalizeZIndices(
  containers: CanvasContainerData[],
  frontId: string,
): CanvasContainerData[] {
  const sorted = [...containers]
    .filter((c) => c.id !== frontId)
    .sort((a, b) => a.zIndex - b.zIndex)
  const frontContainer = containers.find((c) => c.id === frontId)
  if (frontContainer) sorted.push(frontContainer)
  const idToZ = new Map<string, number>()
  sorted.forEach((c, i) => idToZ.set(c.id, i + 1))
  return containers.map((c) => ({ ...c, zIndex: idToZ.get(c.id) ?? c.zIndex }))
}

export { MAX_COORD }
