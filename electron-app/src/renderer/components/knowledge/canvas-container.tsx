/**
 * CanvasContainer
 *
 * Absolutely positioned container on the canvas. Supports drag-to-move
 * via the drag handle and right-edge resize. Uses mousedown/mousemove/mouseup
 * pattern from drawio-node.tsx for smooth 60fps interaction.
 */

import { useCallback, useRef, useEffect } from 'react'
import type { Editor } from '@tiptap/core'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { CanvasContainerData } from './canvas-types'
import { ContainerEditor } from './container-editor'
import './canvas-styles.css'

interface CanvasContainerProps {
  container: CanvasContainerData
  isActive: boolean
  editable: boolean
  zoom: number
  onActivate: (id: string) => void
  onMove: (id: string, x: number, y: number) => void
  onResize: (id: string, width: number, height?: number) => void
  onContentChange: (id: string, content: object) => void
  onDelete: (id: string) => void
  onBringToFront: (id: string) => void
  onEditorMount: (id: string, editor: Editor | null) => void
  onHeightChange?: (id: string, height: number) => void
  onWidthChange?: (id: string, width: number) => void
  onAutoExpand?: (id: string, newWidth: number) => void
  onImageUpload?: (file: File) => Promise<{ url: string; attachmentId: string } | null>
  documentId?: string
}

export function CanvasContainer({
  container,
  isActive,
  editable,
  zoom,
  onActivate,
  onMove,
  onResize,
  onContentChange,
  onDelete,
  onBringToFront,
  onEditorMount,
  onHeightChange,
  onWidthChange,
  onAutoExpand,
  onImageUpload,
  documentId,
}: CanvasContainerProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const dragStartRef = useRef({ mouseX: 0, mouseY: 0, containerX: 0, containerY: 0 })
  const resizeStartRef = useRef({ mouseX: 0, mouseY: 0, containerWidth: 0, containerHeight: 0 })
  // Separate cleanup refs per interaction type to prevent listener leaks
  const dragCleanupRef = useRef<(() => void) | null>(null)
  const resizeCleanupRef = useRef<(() => void) | null>(null)
  const cornerResizeCleanupRef = useRef<(() => void) | null>(null)

  // Stable refs for callbacks/values used in mouse handlers to avoid stale closures
  const onMoveRef = useRef(onMove)
  useEffect(() => { onMoveRef.current = onMove }, [onMove])

  const onResizeRef = useRef(onResize)
  useEffect(() => { onResizeRef.current = onResize }, [onResize])

  const onDeleteRef = useRef(onDelete)
  useEffect(() => { onDeleteRef.current = onDelete }, [onDelete])

  const zoomRef = useRef(zoom)
  useEffect(() => { zoomRef.current = zoom }, [zoom])

  const onAutoExpandRef = useRef(onAutoExpand)
  useEffect(() => { onAutoExpandRef.current = onAutoExpand }, [onAutoExpand])

  // Track mount state to guard async callbacks (ResizeObserver RAF, etc.)
  const isMountedRef = useRef(true)
  // Guard against double-click on delete button
  const isDeletingRef = useRef(false)

  // Cleanup document-level mouse listeners on unmount (prevents leaks during mid-drag unmount)
  useEffect(() => {
    return () => {
      isMountedRef.current = false
      isDeletingRef.current = false
      dragCleanupRef.current?.()
      resizeCleanupRef.current?.()
      cornerResizeCleanupRef.current?.()
    }
  }, [])

  // ResizeObserver for size reporting (debounced)
  useEffect(() => {
    const el = containerRef.current
    if (!el || (!onHeightChange && !onWidthChange)) return

    let rafId: number | null = null
    const observer = new ResizeObserver((entries) => {
      if (rafId !== null) cancelAnimationFrame(rafId)
      rafId = requestAnimationFrame(() => {
        if (!isMountedRef.current) return
        for (const entry of entries) {
          onHeightChange?.(container.id, entry.contentRect.height)
          onWidthChange?.(container.id, entry.contentRect.width)
        }
        rafId = null
      })
    })
    observer.observe(el)
    return () => {
      observer.disconnect()
      if (rafId !== null) cancelAnimationFrame(rafId)
    }
  }, [container.id, onHeightChange, onWidthChange])


  const handleClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    if (!editable) return
    onActivate(container.id)
    onBringToFront(container.id)
  }, [container.id, editable, onActivate, onBringToFront])

  // Guard: prevent starting a new interaction while one is in progress
  const isInteracting = useCallback(() =>
    !!(dragCleanupRef.current || resizeCleanupRef.current || cornerResizeCleanupRef.current),
  [])

  // Drag-to-move via drag handle
  const handleDragMouseDown = useCallback((e: React.MouseEvent) => {
    if (!editable || isInteracting()) return
    e.preventDefault()
    e.stopPropagation()

    dragStartRef.current = {
      mouseX: e.clientX,
      mouseY: e.clientY,
      containerX: container.x,
      containerY: container.y,
    }

    const el = containerRef.current

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const dx = (moveEvent.clientX - dragStartRef.current.mouseX) / zoomRef.current
      const dy = (moveEvent.clientY - dragStartRef.current.mouseY) / zoomRef.current
      const newX = Math.max(0, dragStartRef.current.containerX + dx)
      const newY = Math.max(0, dragStartRef.current.containerY + dy)
      if (el) {
        el.style.left = `${newX}px`
        el.style.top = `${newY}px`
      }
    }

    const cleanup = () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
      dragCleanupRef.current = null
    }

    const handleMouseUp = (upEvent: MouseEvent) => {
      const dx = (upEvent.clientX - dragStartRef.current.mouseX) / zoomRef.current
      const dy = (upEvent.clientY - dragStartRef.current.mouseY) / zoomRef.current
      const finalX = Math.max(0, dragStartRef.current.containerX + dx)
      const finalY = Math.max(0, dragStartRef.current.containerY + dy)
      onMoveRef.current(container.id, finalX, finalY)
      // Clear manual positioning so React-managed styles resume
      if (el) {
        el.style.left = ''
        el.style.top = ''
      }
      cleanup()
    }

    dragCleanupRef.current = cleanup
    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
  }, [editable, isInteracting, container.id, container.x, container.y])

  // Right-edge resize (width only)
  const handleResizeMouseDown = useCallback((e: React.MouseEvent) => {
    if (!editable || isInteracting()) return
    e.preventDefault()
    e.stopPropagation()

    resizeStartRef.current = {
      mouseX: e.clientX,
      mouseY: e.clientY,
      containerWidth: container.width,
      containerHeight: containerRef.current?.offsetHeight ?? 100,
    }

    const el = containerRef.current
    const minWidth = container.minWidth

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const dx = (moveEvent.clientX - resizeStartRef.current.mouseX) / zoomRef.current
      const newWidth = Math.max(minWidth, resizeStartRef.current.containerWidth + dx)
      if (el) {
        el.style.width = `${newWidth}px`
        el.style.minWidth = `${newWidth}px`
      }
    }

    const cleanup = () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
      resizeCleanupRef.current = null
    }

    const handleMouseUp = (upEvent: MouseEvent) => {
      const dx = (upEvent.clientX - resizeStartRef.current.mouseX) / zoomRef.current
      const finalWidth = Math.max(minWidth, resizeStartRef.current.containerWidth + dx)
      onResizeRef.current(container.id, finalWidth)
      // Clear manual dimensions so React-managed styles resume
      if (el) {
        el.style.width = ''
        el.style.minWidth = ''
      }
      cleanup()
    }

    resizeCleanupRef.current = cleanup
    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
  }, [editable, isInteracting, container.id, container.width, container.minWidth])

  // Bottom-right corner resize (width + height)
  const handleCornerResizeMouseDown = useCallback((e: React.MouseEvent) => {
    if (!editable || isInteracting()) return
    e.preventDefault()
    e.stopPropagation()

    resizeStartRef.current = {
      mouseX: e.clientX,
      mouseY: e.clientY,
      containerWidth: container.width,
      containerHeight: container.height ?? containerRef.current?.offsetHeight ?? 100,
    }

    const el = containerRef.current
    const minWidth = container.minWidth
    const minHeight = 50

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const dx = (moveEvent.clientX - resizeStartRef.current.mouseX) / zoomRef.current
      const dy = (moveEvent.clientY - resizeStartRef.current.mouseY) / zoomRef.current
      const newWidth = Math.max(minWidth, resizeStartRef.current.containerWidth + dx)
      const newHeight = Math.max(minHeight, resizeStartRef.current.containerHeight + dy)
      if (el) {
        el.style.width = `${newWidth}px`
        el.style.minWidth = `${newWidth}px`
        el.style.height = `${newHeight}px`
      }
    }

    const cleanup = () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
      cornerResizeCleanupRef.current = null
    }

    const handleMouseUp = (upEvent: MouseEvent) => {
      const dx = (upEvent.clientX - resizeStartRef.current.mouseX) / zoomRef.current
      const dy = (upEvent.clientY - resizeStartRef.current.mouseY) / zoomRef.current
      const finalWidth = Math.max(minWidth, resizeStartRef.current.containerWidth + dx)
      const finalHeight = Math.max(minHeight, resizeStartRef.current.containerHeight + dy)
      onResizeRef.current(container.id, finalWidth, finalHeight)
      // Clear manual dimensions so React-managed styles resume
      if (el) {
        el.style.width = ''
        el.style.minWidth = ''
        el.style.height = ''
      }
      cleanup()
    }

    cornerResizeCleanupRef.current = cleanup
    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
  }, [editable, isInteracting, container.id, container.width, container.height, container.minWidth])

  const handleContentChange = useCallback((json: object) => {
    onContentChange(container.id, json)
  }, [container.id, onContentChange])

  const handleEditorReady = useCallback((editor: Editor | null) => {
    onEditorMount(container.id, editor)
  }, [container.id, onEditorMount])

  /** Auto-expand container when content overflows (e.g., wide table pasted) */
  const handleOverflow = useCallback((contentWidth: number) => {
    // contentWidth is scrollWidth of .canvas-editor-content/.canvas-static-preview.
    // Add margin for borders/padding to get the container's minWidth.
    const needed = contentWidth + 10
    if (needed <= container.width) return  // already wide enough, suppress resize loop
    // Use atomic resize+push if available (single state update), else plain resize
    if (onAutoExpandRef.current) {
      onAutoExpandRef.current(container.id, needed)
    } else {
      onResizeRef.current(container.id, needed)
    }
  }, [container.id, container.width])

  const handleDelete = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (isDeletingRef.current) return
    isDeletingRef.current = true
    onDeleteRef.current(container.id)
  }, [container.id])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (!editable) return
    if (e.target !== e.currentTarget) return
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      onActivate(container.id)
      onBringToFront(container.id)
    } else if (e.key === 'Delete' || e.key === 'Backspace') {
      e.preventDefault()
      if (isDeletingRef.current) return
      isDeletingRef.current = true
      onDeleteRef.current(container.id)
    }
  }, [container.id, editable, onActivate, onBringToFront])

  return (
    <div
      ref={containerRef}
      role="article"
      aria-label={`Text container at position ${Math.round(container.x)}, ${Math.round(container.y)}`}
      tabIndex={editable ? 0 : undefined}
      className={cn(
        'canvas-container absolute',
        isActive && 'canvas-container--active',
        editable && !isActive && 'canvas-container--editable',
      )}
      style={{
        left: container.x,
        top: container.y,
        minWidth: container.width,
        height: container.height,
        zIndex: container.zIndex,
      }}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
    >
      {/* Drag handle */}
      {editable && (
        <div
          className="canvas-drag-handle"
          onMouseDown={handleDragMouseDown}
          role="presentation"
          aria-hidden="true"
        >
          <div className="canvas-drag-handle-dots" aria-hidden="true" />
        </div>
      )}

      {/* Content */}
      <ContainerEditor
        content={container.content}
        isActive={isActive}
        editable={editable}
        onChange={handleContentChange}
        onEditorReady={handleEditorReady}
        onOverflow={handleOverflow}
        onImageUpload={onImageUpload}
        documentId={documentId}
      />

      {/* Right-edge resize handle (width only) */}
      {editable && (
        <div
          className="canvas-resize-handle"
          onMouseDown={handleResizeMouseDown}
          role="presentation"
          aria-hidden="true"
        />
      )}

      {/* Corner resize handle (width + height) */}
      {editable && (
        <div
          className="canvas-corner-resize-handle"
          onMouseDown={handleCornerResizeMouseDown}
          role="presentation"
          aria-hidden="true"
        />
      )}

      {/* Delete button */}
      {editable && (
        <button
          type="button"
          className="canvas-delete-btn"
          onClick={handleDelete}
          title="Delete container"
          aria-label="Delete container"
        >
          <X className="h-3 w-3" aria-hidden="true" />
        </button>
      )}
    </div>
  )
}
