/**
 * useCanvasState Hook
 *
 * Manages all canvas state mutations. onChange is fired via useEffect
 * after state updates (NOT inside state updaters) to avoid double-firing
 * in React 18 StrictMode.
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import { toast } from 'sonner'
import type { CanvasDocument, CanvasContainerData, Viewport } from './canvas-types'
import { createContainer } from './canvas-types'
import { bringToFront as bringToFrontUtil, MAX_COORD } from './canvas-utils'

const MAX_CONTAINERS = 100

/** Sanitize a number: replace NaN/Infinity with fallback */
function sanitizeNum(n: number, fallback: number): number {
  return Number.isFinite(n) ? n : fallback
}

function serialize(
  containers: CanvasContainerData[],
  viewport: Viewport,
  title?: string,
): CanvasDocument {
  return {
    format: 'canvas',
    version: 1,
    ...(title !== undefined ? { title } : {}),
    viewport,
    containers,
  }
}

export function useCanvasState(
  initialData: CanvasDocument,
  onChange?: (doc: CanvasDocument) => void,
  editable?: boolean,
) {
  const [containers, setContainers] = useState<CanvasContainerData[]>(initialData.containers)
  const [viewport, setViewportState] = useState<Viewport>(initialData.viewport)
  const [canvasTitle, setCanvasTitle] = useState<string | undefined>(initialData.title)
  const [activeContainerId, setActiveContainerId] = useState<string | null>(null)

  // Track mount state for cleanup guards (viewport flush, etc.)
  const isUnmountRef = useRef(false)
  useEffect(() => () => { isUnmountRef.current = true }, [])

  // Resync state when parent provides new initialData (e.g., after cancel/discard refetch)
  const prevInitialDataObjRef = useRef(initialData)
  const prevInitialDataRef = useRef<string>(JSON.stringify(initialData))
  useEffect(() => {
    if (initialData === prevInitialDataObjRef.current) return  // same reference, skip stringify
    prevInitialDataObjRef.current = initialData
    const serialized = JSON.stringify(initialData)
    if (serialized !== prevInitialDataRef.current) {
      prevInitialDataRef.current = serialized
      setContainers(initialData.containers)
      setViewportState(initialData.viewport)
      setCanvasTitle(initialData.title)
      setActiveContainerId(null)
    }
  }, [initialData])

  // Reset to initial data when transitioning from edit to view mode (cancel/discard)
  const prevEditableRef = useRef(editable)
  useEffect(() => {
    if (prevEditableRef.current === true && editable === false) {
      setContainers(initialData.containers)
      setViewportState(initialData.viewport)
      setCanvasTitle(initialData.title)
      setActiveContainerId(null)
    }
    prevEditableRef.current = editable
  }, [editable, initialData])

  const onChangeRef = useRef(onChange)
  useEffect(() => { onChangeRef.current = onChange }, [onChange])

  const viewportRef = useRef(viewport)
  viewportRef.current = viewport

  const canvasTitleRef = useRef(canvasTitle)
  canvasTitleRef.current = canvasTitle

  // Fire onChange whenever containers state changes (referential equality check
  // skips initial mount and StrictMode remount without data change)
  const prevContainersRef = useRef(containers)
  useEffect(() => {
    if (containers === prevContainersRef.current) return
    prevContainersRef.current = containers
    onChangeRef.current?.(serialize(containers, viewportRef.current, canvasTitleRef.current))
  }, [containers])

  // Fire onChange when canvas title changes
  const prevCanvasTitleRef = useRef(canvasTitle)
  useEffect(() => {
    if (canvasTitle === prevCanvasTitleRef.current) return
    prevCanvasTitleRef.current = canvasTitle
    onChangeRef.current?.(serialize(prevContainersRef.current, viewportRef.current, canvasTitle))
  }, [canvasTitle])

  // Persist viewport-only changes (scroll/zoom) with debounce.
  // On unmount, flush any pending viewport save to prevent lost scroll/zoom state.
  const viewportTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const prevViewportRef = useRef(viewport)
  useEffect(() => {
    if (viewport === prevViewportRef.current) return
    prevViewportRef.current = viewport
    if (viewportTimerRef.current) clearTimeout(viewportTimerRef.current)
    viewportTimerRef.current = setTimeout(() => {
      onChangeRef.current?.(serialize(prevContainersRef.current, viewport, canvasTitleRef.current))
      viewportTimerRef.current = null
    }, 500)
    return () => {
      if (viewportTimerRef.current) {
        clearTimeout(viewportTimerRef.current)
        // Only flush on actual unmount to preserve debounce on re-runs
        if (isUnmountRef.current) {
          onChangeRef.current?.(serialize(prevContainersRef.current, viewport, canvasTitleRef.current))
        }
        viewportTimerRef.current = null
      }
    }
  }, [viewport])

  const addContainer = useCallback((x: number, y: number) => {
    setContainers((prev) => {
      if (prev.length >= MAX_CONTAINERS) {
        // Toast must be deferred to avoid setState-during-render warnings
        queueMicrotask(() => toast.info(`Maximum of ${MAX_CONTAINERS} containers reached`))
        return prev
      }
      const maxZ = prev.reduce((max, c) => Math.max(max, c.zIndex), 0)
      const c = createContainer(
        Math.max(0, Math.min(sanitizeNum(x, 0), MAX_COORD)),
        Math.max(0, Math.min(sanitizeNum(y, 0), MAX_COORD)),
      )
      c.zIndex = maxZ + 1
      // Defer setActiveContainerId to avoid nested setState
      queueMicrotask(() => setActiveContainerId(c.id))
      return [...prev, c]
    })
  }, [])

  const moveContainer = useCallback((id: string, x: number, y: number) => {
    const clampedX = Math.max(0, Math.min(sanitizeNum(x, 0), MAX_COORD))
    const clampedY = Math.max(0, Math.min(sanitizeNum(y, 0), MAX_COORD))
    setContainers((prev) =>
      prev.map((c) => (c.id === id ? { ...c, x: clampedX, y: clampedY } : c)),
    )
  }, [])

  const moveContainersBatch = useCallback((moves: Array<{ id: string; x: number; y: number }>) => {
    if (moves.length === 0) return
    setContainers((prev) => {
      const moveMap = new Map(moves.map((m) => [m.id, m]))
      let changed = false
      const result = prev.map((c) => {
        const move = moveMap.get(c.id)
        if (!move) return c
        const clampedX = Math.max(0, Math.min(sanitizeNum(move.x, 0), MAX_COORD))
        const clampedY = Math.max(0, Math.min(sanitizeNum(move.y, 0), MAX_COORD))
        if (c.x === clampedX && c.y === clampedY) return c
        changed = true
        return { ...c, x: clampedX, y: clampedY }
      })
      return changed ? result : prev
    })
  }, [])

  const resizeContainer = useCallback((id: string, width: number, height?: number) => {
    setContainers((prev) => {
      const target = prev.find((c) => c.id === id)
      const minW = target?.minWidth ?? 200
      const clampedWidth = Math.max(minW, Math.min(sanitizeNum(width, minW), MAX_COORD))
      const updates: Partial<CanvasContainerData> = { width: clampedWidth }
      if (height !== undefined) {
        updates.height = Math.max(50, Math.min(sanitizeNum(height, 50), MAX_COORD))
      }
      return prev.map((c) => (c.id === id ? { ...c, ...updates } : c))
    })
  }, [])

  /** Resize a container AND push overlapping containers in one atomic state update */
  const resizeAndPush = useCallback((
    id: string,
    width: number,
    measuredHeights: Map<string, number>,
    measuredWidths: Map<string, number>,
  ) => {
    setContainers((prev) => {
      // 1. Resize the container
      const target = prev.find((c) => c.id === id)
      const minW = target?.minWidth ?? 200
      const clampedWidth = Math.max(minW, Math.min(sanitizeNum(width, minW), MAX_COORD))
      let result = prev.map((c) => (c.id === id ? { ...c, width: clampedWidth } : c))

      // 2. Find and push overlapping containers to the right
      const expanded = result.find((c) => c.id === id)
      if (!expanded) return result

      const effectiveRight = expanded.x + clampedWidth
      const expandedTop = expanded.y
      const expandedHeight = measuredHeights.get(id) ?? expanded.height ?? 200
      const expandedBottom = expandedTop + expandedHeight
      const gap = 20

      // Collect ALL containers to the right that vertically overlap, sorted by x.
      // The cascade loop checks each against a running boundary so containers
      // pushed by earlier pushes are also moved (indirect overlap).
      const rightward = result
        .filter((c) => {
          if (c.id === id || c.x <= expanded.x) return false
          const h = measuredHeights.get(c.id) ?? c.height ?? 200
          return c.y + h > expandedTop && c.y < expandedBottom
        })
        .sort((a, b) => a.x - b.x)

      if (rightward.length === 0) return result

      // Cascade: each pushed container shifts the boundary for the next
      const moveMap = new Map<string, number>()
      let boundary = effectiveRight + gap
      for (const other of rightward) {
        if (other.x < boundary) {
          moveMap.set(other.id, boundary)
          const otherW = Math.max(other.width, measuredWidths.get(other.id) ?? other.width)
          boundary += otherW + gap
        }
      }

      if (moveMap.size === 0) return result

      return result.map((c) => {
        const newX = moveMap.get(c.id)
        if (newX === undefined) return c
        return { ...c, x: Math.max(0, Math.min(sanitizeNum(newX, 0), MAX_COORD)) }
      })
    })
  }, [])

  const deleteContainer = useCallback((id: string) => {
    setContainers((prev) => prev.filter((c) => c.id !== id))
    setActiveContainerId((prev) => (prev === id ? null : prev))
  }, [])

  const updateContainerContent = useCallback((id: string, content: object) => {
    setContainers((prev) =>
      prev.map((c) => (c.id === id ? { ...c, content } : c)),
    )
  }, [])

  const setActiveContainer = useCallback((id: string | null) => {
    setActiveContainerId(id)
  }, [])

  const bringToFront = useCallback((id: string) => {
    setContainers((prev) => {
      const target = prev.find((c) => c.id === id)
      if (!target) return prev
      const maxZ = prev.reduce((max, c) => Math.max(max, c.zIndex), 0)
      if (target.zIndex === maxZ) return prev  // Already at front, skip
      return bringToFrontUtil(prev, id)
    })
  }, [])

  const setViewport = useCallback((v: Viewport) => {
    const sanitized: Viewport = {
      scrollX: sanitizeNum(v.scrollX, 0),
      scrollY: sanitizeNum(v.scrollY, 0),
      zoom: Math.max(0.1, Math.min(sanitizeNum(v.zoom, 1), 10)),
    }
    setViewportState(sanitized)
    viewportRef.current = sanitized
  }, [])

  return {
    containers,
    viewport,
    canvasTitle,
    setCanvasTitle,
    activeContainerId,
    addContainer,
    moveContainer,
    moveContainersBatch,
    resizeContainer,
    resizeAndPush,
    deleteContainer,
    updateContainerContent,
    setActiveContainer,
    bringToFront,
    setViewport,
  }
}
