/**
 * Citation Highlight Utilities
 *
 * Functions for navigating to and highlighting cited content in TipTap
 * documents and canvas elements when the user clicks a source citation
 * in the Blair AI sidebar.
 */

import type { Editor } from '@tiptap/core'
import { toast } from 'sonner'

// ============================================================================
// TipTap Document Helpers
// ============================================================================

/**
 * Find the position of a heading node whose text content matches `headingText`.
 * Returns the position of the heading node, or null if not found.
 */
export function findHeadingPosition(editor: Editor, headingText: string): number | null {
  const doc = editor.state.doc
  const normalizedTarget = headingText.trim().toLowerCase()
  let foundPos: number | null = null

  doc.descendants((node, pos) => {
    if (foundPos !== null) return false // stop traversal
    if (node.type.name === 'heading') {
      const nodeText = node.textContent.trim().toLowerCase()
      if (nodeText === normalizedTarget) {
        foundPos = pos
        return false
      }
    }
    return true
  })

  return foundPos
}

/**
 * Search the document content for a text string, returning the position range
 * of the first occurrence. Returns null if the text is not found.
 */
export function findTextInDocument(
  editor: Editor,
  text: string
): { from: number; to: number } | null {
  const doc = editor.state.doc
  const normalizedTarget = text.trim().toLowerCase()
  if (!normalizedTarget) return null

  let result: { from: number; to: number } | null = null

  doc.descendants((node, pos) => {
    if (result !== null) return false // stop traversal
    if (node.isText && node.text) {
      const nodeText = node.text.toLowerCase()
      const index = nodeText.indexOf(normalizedTarget)
      if (index !== -1) {
        result = {
          from: pos + index,
          to: pos + index + normalizedTarget.length,
        }
        return false
      }
    }
    return true
  })

  // If exact substring not found in a single text node, try across the full document text
  if (!result) {
    const fullText = doc.textContent.toLowerCase()
    const index = fullText.indexOf(normalizedTarget)
    if (index !== -1) {
      // Map text offset to document position
      let charsSeen = 0
      doc.descendants((node, pos) => {
        if (result !== null) return false
        if (node.isText && node.text) {
          const nodeLen = node.text.length
          if (charsSeen + nodeLen > index && charsSeen <= index) {
            const startOffset = index - charsSeen
            result = {
              from: pos + startOffset,
              to: pos + startOffset + Math.min(normalizedTarget.length, nodeLen - startOffset),
            }
            return false
          }
          charsSeen += nodeLen
        }
        return true
      })
    }
  }

  return result
}

/**
 * Apply a temporary highlight decoration to a range in the TipTap editor.
 * The highlight fades out after `duration` ms (default 4000ms).
 *
 * Uses a <mark> element with the specified className. After 3s the "fading"
 * class is added, and the mark is removed after `duration`.
 */
export function applyTemporaryHighlight(
  editor: Editor,
  from: number,
  to: number,
  options: { className?: string; duration?: number } = {}
): void {
  const { className = 'blair-citation-highlight', duration = 4000 } = options

  // Scroll the target position into view
  editor.commands.setTextSelection({ from, to })
  editor.commands.scrollIntoView()

  // Create a temporary <mark> by wrapping the selection
  const domRange = editor.view.domAtPos(from)
  if (!domRange) return

  // Use a decoration approach: insert a temporary CSS class via a mark
  // We'll use the editor's view to find the DOM elements and add classes directly
  const coords = editor.view.coordsAtPos(from)
  if (!coords) return

  // Find and highlight the DOM elements in the range
  const domSelection = window.getSelection()
  if (domSelection) {
    const range = document.createRange()
    try {
      const startDom = editor.view.domAtPos(from)
      const endDom = editor.view.domAtPos(to)
      range.setStart(startDom.node, startDom.offset)
      range.setEnd(endDom.node, endDom.offset)

      const mark = document.createElement('mark')
      mark.className = className

      range.surroundContents(mark)

      // After 3s, add fading class
      const fadeTimer = setTimeout(() => {
        mark.classList.add('fading')
      }, Math.max(duration - 1000, 0))

      // After duration, remove the mark
      const removeTimer = setTimeout(() => {
        const parent = mark.parentNode
        if (parent) {
          while (mark.firstChild) {
            parent.insertBefore(mark.firstChild, mark)
          }
          parent.removeChild(mark)
        }
      }, duration)

      // If the editor is destroyed before timeouts fire, clean up
      const cleanup = () => {
        clearTimeout(fadeTimer)
        clearTimeout(removeTimer)
      }
      editor.on('destroy', cleanup)
    } catch {
      // Range manipulation can fail with complex node structures
      // Fall back to just scrolling into view (already done above)
    }
  }
}

// ============================================================================
// Canvas Document Helpers
// ============================================================================

/**
 * Highlight an element on a canvas-style document by ID.
 * Centers the viewport on the element and applies a glow ring.
 *
 * @param canvasRef - Ref to the canvas container element
 * @param elementId - The DOM id of the element to highlight
 * @param options - Highlight options (color, duration)
 */
export function highlightCanvasElement(
  canvasRef: { current: HTMLElement | null } | HTMLElement | null,
  elementId: string,
  options: { color?: string; duration?: number } = {}
): void {
  const { color = 'rgba(250, 204, 21, 0.6)', duration = 4000 } = options

  const container =
    canvasRef && 'current' in canvasRef ? canvasRef.current : (canvasRef as HTMLElement | null)
  if (!container) {
    toast('Could not find canvas element', {
      description: 'The referenced element could not be located.',
    })
    return
  }

  const element = container.querySelector(`[id="${CSS.escape(elementId)}"]`) as HTMLElement | null
  if (!element) {
    toast('Element not found', {
      description: 'The referenced element could not be located in the document.',
    })
    return
  }

  // Scroll element into view
  element.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' })

  // Apply glow ring
  const prevOutline = element.style.outline
  const prevOutlineOffset = element.style.outlineOffset
  const prevTransition = element.style.transition

  element.style.transition = 'outline-color 1s ease-out'
  element.style.outline = `3px solid ${color}`
  element.style.outlineOffset = '2px'

  // Fade out after duration - 1s
  const fadeTimer = setTimeout(() => {
    element.style.outlineColor = 'transparent'
  }, Math.max(duration - 1000, 0))

  // Remove styles after duration
  const removeTimer = setTimeout(() => {
    element.style.outline = prevOutline
    element.style.outlineOffset = prevOutlineOffset
    element.style.transition = prevTransition
  }, duration)

  // Clean up if element is removed from DOM
  const observer = new MutationObserver(() => {
    if (!document.contains(element)) {
      clearTimeout(fadeTimer)
      clearTimeout(removeTimer)
      observer.disconnect()
    }
  })
  observer.observe(container, { childList: true, subtree: true })
  setTimeout(() => observer.disconnect(), duration + 100)
}

// ============================================================================
// High-level Navigation
// ============================================================================

/**
 * Navigate to a citation target in a TipTap editor. Tries heading first,
 * then falls back to full-text search of the chunk text.
 *
 * Shows a toast if the cited content cannot be found.
 */
export function navigateToCitation(
  editor: Editor,
  params: { headingContext?: string; chunkText?: string }
): void {
  const { headingContext, chunkText } = params

  // Try heading first
  if (headingContext) {
    const headingPos = findHeadingPosition(editor, headingContext)
    if (headingPos !== null) {
      applyTemporaryHighlight(editor, headingPos, headingPos + headingContext.length)
      return
    }
  }

  // Try chunk text
  if (chunkText) {
    // Use first 100 chars for search to improve match likelihood
    const searchText = chunkText.slice(0, 100)
    const range = findTextInDocument(editor, searchText)
    if (range) {
      applyTemporaryHighlight(editor, range.from, range.to)
      return
    }
  }

  toast('Citation not found', {
    description: 'The referenced content could not be located in this document.',
  })
}
