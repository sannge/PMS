/**
 * CanvasEditor
 *
 * Top-level canvas component. Manages canvas state via useCanvasState,
 * composes CanvasToolbar + CanvasViewport + CanvasContainer[].
 * Manages the single activeEditor state for the toolbar.
 */

import { useState, useCallback, useRef, useEffect, useReducer, useMemo } from 'react'
import type { Editor } from '@tiptap/core'
import { cn } from '@/lib/utils'
import { useAuthToken } from '@/contexts/auth-context'
import type { CanvasDocument } from './canvas-types'
import type { SetImageAttrs } from './editor-extensions'
import { useCanvasState } from './use-canvas-state'
import { computeCanvasBounds } from './canvas-utils'
import { CanvasToolbar } from './canvas-toolbar'
import { CanvasViewport } from './canvas-viewport'
import { CanvasContainer } from './canvas-container'
import { DocumentTimestamp } from './document-header'
import { useImageUpload } from './use-image-upload'
import './canvas-styles.css'

interface CanvasEditorProps {
  canvasData: CanvasDocument
  onChange?: (canvasJson: object) => void
  editable: boolean
  className?: string
  documentId?: string
  title?: string
  updatedAt?: string
  onBaselineSync?: (json: object) => void
  /** Backend-managed embedding status */
  embeddingStatus?: 'none' | 'stale' | 'syncing' | 'synced'
}

export function CanvasEditor({
  canvasData,
  onChange,
  editable,
  className,
  documentId,
  title,
  updatedAt,
  onBaselineSync,
  embeddingStatus,
}: CanvasEditorProps) {
  const [activeEditor, setActiveEditor] = useState<Editor | null>(null)
  const measuredHeights = useRef<Map<string, number>>(new Map()).current
  const measuredWidths = useRef<Map<string, number>>(new Map()).current
  // Counter to force canvas bounds recalculation when measured sizes change
  const [boundsVersion, forceCanvasBoundsUpdate] = useReducer((v: number) => v + 1, 0)
  const token = useAuthToken()
  const canvasRootRef = useRef<HTMLDivElement>(null)

  const state = useCanvasState(canvasData, onChange, editable)

  // Initialize canvas title from document title when not set in canvas data
  const hasInitializedTitle = useRef(false)
  useEffect(() => {
    if (!hasInitializedTitle.current && title && state.canvasTitle === undefined) {
      state.setCanvasTitle(title)
      hasInitializedTitle.current = true
    }
  }, [title, state.canvasTitle, state.setCanvasTitle])

  // Refs for stable access inside callbacks (avoids stale closures / dep churn)
  const containersRef = useRef(state.containers)
  containersRef.current = state.containers
  const moveContainersBatchRef = useRef(state.moveContainersBatch)
  moveContainersBatchRef.current = state.moveContainersBatch
  const resizeAndPushRef = useRef(state.resizeAndPush)
  resizeAndPushRef.current = state.resizeAndPush

  // H2 fix: Ref for editable to avoid stale closure in ResizeObserver callbacks
  const editableRef = useRef(editable)
  useEffect(() => { editableRef.current = editable }, [editable])

  // Sync baseline on mount for dirty detection
  const onBaselineSyncRef = useRef(onBaselineSync)
  useEffect(() => { onBaselineSyncRef.current = onBaselineSync }, [onBaselineSync])
  // eslint-disable-next-line react-hooks/exhaustive-deps -- mount-only: sync baseline once on initial render
  useEffect(() => {
    if (onBaselineSyncRef.current && canvasData) {
      onBaselineSyncRef.current(canvasData)
    }
  }, [])

  const { width: canvasWidth, height: canvasHeight } = useMemo(
    () => computeCanvasBounds(state.containers, measuredHeights, measuredWidths),
    // boundsVersion changes when measured sizes change (via forceCanvasBoundsUpdate)
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [state.containers, boundsVersion],
  )

  const handleEditorMount = useCallback((_containerId: string, editor: Editor | null) => {
    setActiveEditor(editor)
  }, [])

  const handleAddContainer = useCallback((x: number, y: number) => {
    if (!editable) return
    state.addContainer(x, y)
  }, [editable, state.addContainer])

  const handleAddContainerFromToolbar = useCallback(() => {
    // Stagger toolbar-created containers so they don't stack on top of each other
    const offset = (state.containers.length % 10) * 30
    state.addContainer(100 + offset, 100 + offset)
    // Scroll viewport to top-left so the new container is visible
    requestAnimationFrame(() => {
      const viewport = canvasRootRef.current?.querySelector('[role="region"]')
      if (viewport) viewport.scrollTo({ left: 0, top: 0, behavior: 'smooth' })
    })
  }, [state.addContainer, state.containers.length])

  // Use ref for viewport to avoid stale closure on rapid zoom changes
  const viewportRef = useRef(state.viewport)
  viewportRef.current = state.viewport

  const handleZoomChange = useCallback((zoom: number) => {
    state.setViewport({ ...viewportRef.current, zoom })
  }, [state.setViewport])

  const handleHeightChange = useCallback((id: string, height: number) => {
    const prev = measuredHeights.get(id)
    measuredHeights.set(id, height)
    if (prev === undefined || Math.abs(prev - height) > 5) {
      forceCanvasBoundsUpdate()
    }
  }, [measuredHeights])

  const handleWidthChange = useCallback((id: string, width: number) => {
    const prev = measuredWidths.get(id)
    measuredWidths.set(id, width)
    if (prev === undefined || Math.abs(prev - width) > 5) {
      forceCanvasBoundsUpdate()

      // Auto-push overlapping containers to the right when content expands
      if (!editableRef.current) return
      const containers = containersRef.current
      const expanded = containers.find((c) => c.id === id)
      if (!expanded) return
      // Only push when measured width increased from previous measurement
      // (skip first measurement to avoid spurious pushes on mount)
      if (prev === undefined || width <= prev + 5) return

      const effectiveRight = expanded.x + Math.max(width, expanded.width)
      const expandedTop = expanded.y
      const expandedHeight = measuredHeights.get(id) ?? expanded.height ?? 200
      const expandedBottom = expandedTop + expandedHeight
      const gap = 20

      // Collect ALL containers to the right that vertically overlap, sorted by x.
      // The cascade loop checks each against a running boundary so containers
      // pushed by earlier pushes are also moved (indirect overlap).
      const overlapping = containers
        .filter((c) => {
          if (c.id === id || c.x <= expanded.x) return false
          const h = measuredHeights.get(c.id) ?? c.height ?? 200
          return c.y + h > expandedTop && c.y < expandedBottom
        })
        .sort((a, b) => a.x - b.x)

      if (overlapping.length === 0) return

      // Push cascading: each pushed container shifts the boundary for the next
      const moves: Array<{ id: string; x: number; y: number }> = []
      let boundary = effectiveRight + gap
      for (const other of overlapping) {
        if (other.x < boundary) {
          moves.push({ id: other.id, x: boundary, y: other.y })
          const otherW = Math.max(other.width, measuredWidths.get(other.id) ?? other.width)
          boundary += otherW + gap
        }
      }

      if (moves.length > 0) {
        moveContainersBatchRef.current(moves)
      }
    }
  }, [measuredWidths, measuredHeights])

  // Atomically resize + push overlapping containers in one state update
  // (bypasses ResizeObserver → RAF chain for immediate response)
  const handleAutoExpand = useCallback((id: string, newWidth: number) => {
    if (!editable) return
    resizeAndPushRef.current(id, newWidth, measuredHeights, measuredWidths)
  }, [measuredHeights, measuredWidths, editable])

  // Delete container + clear activeEditor and orphaned measurements
  const handleDeleteContainer = useCallback((id: string) => {
    if (state.activeContainerId === id) {
      setActiveEditor(null)
    }
    measuredHeights.delete(id)
    measuredWidths.delete(id)
    state.deleteContainer(id)
  }, [state.activeContainerId, state.deleteContainer, measuredHeights, measuredWidths])

  // Click on canvas background deselects active container
  const handleDeselect = useCallback(() => {
    state.setActiveContainer(null)
    setActiveEditor(null)
  }, [state.setActiveContainer])

  // Escape key deselects active container (scoped to canvas DOM tree)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || !state.activeContainerId) return
      if (canvasRootRef.current && !canvasRootRef.current.contains(e.target as Node)) return
      // Don't deselect if Escape is targeting a popover/dropdown
      if ((e.target as HTMLElement).closest('[role="listbox"], [role="menu"], [role="dialog"], [data-radix-popper-content-wrapper]')) return
      state.setActiveContainer(null)
      setActiveEditor(null)
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [state.activeContainerId, state.setActiveContainer])

  // Shared image upload hook (M4: extracted to eliminate duplication with DocumentEditor)
  const uploadImageFile = useImageUpload(token, documentId)

  // Toolbar image upload: uploads and inserts into active editor
  const uploadImage = useCallback(async (file: File) => {
    const editorAtInvocation = activeEditor
    if (!editorAtInvocation || editorAtInvocation.isDestroyed) return
    const result = await uploadImageFile(file)
    if (!result || editorAtInvocation.isDestroyed) return
    editorAtInvocation.chain().focus().setImage({
      src: result.url,
      attachmentId: result.attachmentId,
    } as SetImageAttrs).run()
  }, [activeEditor, uploadImageFile])

  return (
    <div ref={canvasRootRef} className={cn('flex flex-col min-h-0 overflow-hidden bg-background', className)}>
      <CanvasToolbar
        activeEditor={activeEditor}
        editable={editable}
        onImageUpload={editable ? uploadImage : undefined}
        zoom={state.viewport.zoom}
        onZoomChange={handleZoomChange}
        onAddContainer={handleAddContainerFromToolbar}
      />

      {/* Title section — mirrors normal document's h1 heading + timestamp */}
      <div className="px-6 pt-4 pb-2 border-b shrink-0">
        {updatedAt && <DocumentTimestamp updatedAt={updatedAt} documentId={documentId} embeddingStatus={embeddingStatus} />}
        {editable ? (
          <input
            type="text"
            value={state.canvasTitle ?? title ?? ''}
            onChange={(e) => state.setCanvasTitle(e.target.value)}
            maxLength={255}
            className="w-full text-2xl font-bold leading-tight bg-transparent border-none outline-none p-0 placeholder:text-muted-foreground/50"
            placeholder="Untitled"
          />
        ) : (
          <h1 className="text-2xl font-bold leading-tight">
            {state.canvasTitle || title || 'Untitled'}
          </h1>
        )}
        <hr className="mt-2 border-border" />
      </div>

      <CanvasViewport
        viewport={state.viewport}
        onViewportChange={state.setViewport}
        onAddContainer={handleAddContainer}
        onDeselect={handleDeselect}
        editable={editable}
        canvasWidth={canvasWidth}
        canvasHeight={canvasHeight}
        zoom={state.viewport.zoom}
        containerCount={state.containers.length}
      >
        {state.containers.map((container) => (
          <CanvasContainer
            key={container.id}
            container={container}
            isActive={state.activeContainerId === container.id}
            editable={editable}
            zoom={state.viewport.zoom}
            onActivate={state.setActiveContainer}
            onMove={state.moveContainer}
            onResize={state.resizeContainer}
            onContentChange={state.updateContainerContent}
            onDelete={handleDeleteContainer}
            onBringToFront={state.bringToFront}
            onEditorMount={handleEditorMount}
            onHeightChange={handleHeightChange}
            onWidthChange={handleWidthChange}
            onAutoExpand={handleAutoExpand}
            onImageUpload={editable ? uploadImageFile : undefined}
            documentId={documentId}
          />
        ))}
      </CanvasViewport>
    </div>
  )
}
