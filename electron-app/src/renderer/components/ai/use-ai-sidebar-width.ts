/**
 * AI Sidebar Width Hook
 *
 * Manages the resizable sidebar width with pointer-capture drag,
 * clamped between 300-600px, persisted to localStorage.
 */

import { useState, useCallback, useRef } from 'react'

// ============================================================================
// Constants
// ============================================================================

const WIDTH_STORAGE_KEY = 'ai-sidebar-width'
const DEFAULT_WIDTH = 400
const MIN_WIDTH = 300
const MAX_WIDTH = 600

// ============================================================================
// localStorage helpers
// ============================================================================

function loadWidth(): number {
  try {
    const val = localStorage.getItem(WIDTH_STORAGE_KEY)
    if (val) {
      const n = parseInt(val, 10)
      if (!isNaN(n) && n >= MIN_WIDTH && n <= MAX_WIDTH) return n
    }
  } catch {
    // ignore
  }
  return DEFAULT_WIDTH
}

function persistWidth(w: number): void {
  try {
    localStorage.setItem(WIDTH_STORAGE_KEY, String(w))
  } catch {
    // ignore
  }
}

// ============================================================================
// Hook
// ============================================================================

export function useAiSidebarWidth() {
  const [width, setWidth] = useState(loadWidth)
  const widthRef = useRef(width)

  const onResizeStart = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault()
    const target = e.currentTarget
    target.setPointerCapture(e.pointerId)

    const onPointerMove = (ev: PointerEvent) => {
      const viewportWidth = window.innerWidth
      const newWidth = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, viewportWidth - ev.clientX))
      widthRef.current = newWidth
      setWidth(newWidth)
    }

    const onPointerUp = () => {
      target.releasePointerCapture(e.pointerId)
      target.removeEventListener('pointermove', onPointerMove)
      target.removeEventListener('pointerup', onPointerUp)
      persistWidth(widthRef.current)
    }

    target.addEventListener('pointermove', onPointerMove)
    target.addEventListener('pointerup', onPointerUp)
  }, [])

  return { width, onResizeStart }
}
