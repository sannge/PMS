/**
 * CanvasViewport
 *
 * Infinite scrollable canvas surface with dot grid background.
 * Uses native overflow:auto scrolling. Inner div is dynamically
 * sized from computeCanvasBounds().
 *
 * Right-click on the canvas background opens a context menu
 * with "Add Container" (instead of click-to-create).
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import { FileText, PlusSquare } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Viewport } from './canvas-types'
import './canvas-styles.css'

interface ContextMenuState {
  visible: boolean
  /** Screen position for the menu */
  screenX: number
  screenY: number
  /** Canvas-space position for the new container */
  canvasX: number
  canvasY: number
}

interface CanvasViewportProps {
  children: React.ReactNode
  viewport: Viewport
  onViewportChange: (v: Viewport) => void
  onAddContainer: (canvasX: number, canvasY: number) => void
  onDeselect?: () => void
  editable: boolean
  canvasWidth: number
  canvasHeight: number
  zoom: number
  containerCount: number
  className?: string
}

export function CanvasViewport({
  children,
  viewport,
  onViewportChange,
  onAddContainer,
  onDeselect,
  editable,
  canvasWidth,
  canvasHeight,
  zoom,
  containerCount,
  className,
}: CanvasViewportProps) {
  const outerRef = useRef<HTMLDivElement>(null)
  const hasRestoredScroll = useRef(false)

  const [ctxMenu, setCtxMenu] = useState<ContextMenuState>({
    visible: false, screenX: 0, screenY: 0, canvasX: 0, canvasY: 0,
  })

  // Restore viewport scroll position on mount
  useEffect(() => {
    if (outerRef.current && !hasRestoredScroll.current) {
      outerRef.current.scrollLeft = viewport.scrollX
      outerRef.current.scrollTop = viewport.scrollY
      hasRestoredScroll.current = true
    }
  }, [viewport.scrollX, viewport.scrollY])

  const handleScroll = useCallback(() => {
    if (!outerRef.current) return
    onViewportChange({
      scrollX: outerRef.current.scrollLeft,
      scrollY: outerRef.current.scrollTop,
      zoom,
    })
  }, [onViewportChange, zoom])

  // Right-click opens context menu
  const handleContextMenu = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    // Only on the canvas background, not on containers
    if ((e.target as HTMLElement).closest('.canvas-container')) return
    if (!editable) return
    e.preventDefault()

    const rect = (e.currentTarget as HTMLDivElement).getBoundingClientRect()
    const canvasX = (e.clientX - rect.left) / zoom
    const canvasY = (e.clientY - rect.top) / zoom

    setCtxMenu({
      visible: true,
      screenX: e.clientX,
      screenY: e.clientY,
      canvasX,
      canvasY,
    })
  }, [editable, zoom])

  // Close context menu
  const closeMenu = useCallback(() => {
    setCtxMenu((prev) => prev.visible ? { ...prev, visible: false } : prev)
  }, [])

  // Ref for auto-focusing the first menu item
  const menuItemRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!ctxMenu.visible) return
    const rafId = requestAnimationFrame(() => menuItemRef.current?.focus())
    const handleClose = () => closeMenu()
    document.addEventListener('click', handleClose)
    document.addEventListener('scroll', handleClose, true)
    return () => {
      cancelAnimationFrame(rafId)
      document.removeEventListener('click', handleClose)
      document.removeEventListener('scroll', handleClose, true)
    }
  }, [ctxMenu.visible, closeMenu])

  const handleMenuKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Escape' || e.key === 'Tab') {
      e.preventDefault()
      closeMenu()
    } else if (e.key === 'Enter' || e.key === ' ') {
      // Let the button's onClick handle it
    }
  }, [closeMenu])

  const ctxMenuRef = useRef(ctxMenu)
  ctxMenuRef.current = ctxMenu

  const handleAddFromMenu = useCallback((e: React.MouseEvent | React.KeyboardEvent) => {
    e.stopPropagation()
    onAddContainer(ctxMenuRef.current.canvasX, ctxMenuRef.current.canvasY)
    setCtxMenu((prev) => ({ ...prev, visible: false }))
  }, [onAddContainer])

  // Click on canvas background deselects active container (no creation)
  const handleCanvasClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if ((e.target as HTMLElement).closest('.canvas-container')) return
    onDeselect?.()
  }, [onDeselect])

  // When canvas has no containers, fill the viewport (no scrollbar)
  const isEmpty = canvasWidth === 0 && canvasHeight === 0

  return (
    <div
      ref={outerRef}
      role="region"
      aria-label="Canvas editor"
      className={cn(
        'flex-1 relative min-w-0',
        isEmpty ? 'overflow-hidden' : 'overflow-auto',
        className,
      )}
      onScroll={handleScroll}
    >
      {/* Spacer div — provides scroll area AND dot grid background.
           minWidth/minHeight ensure the dot grid always fills the viewport. */}
      <div
        className="canvas-dot-grid"
        style={isEmpty ? { width: '100%', height: '100%' } : {
          width: canvasWidth * zoom,
          height: canvasHeight * zoom,
          minWidth: '100%',
          minHeight: '100%',
          position: 'relative',
          backgroundSize: `${20 * zoom}px ${20 * zoom}px`,
        }}
        onClick={handleCanvasClick}
        onContextMenu={handleContextMenu}
      >
        {/* Transform div provides zoom via CSS scale */}
        <div
          style={isEmpty ? { width: '100%', height: '100%', position: 'relative' } : {
            width: canvasWidth,
            height: canvasHeight,
            transformOrigin: '0 0',
            transform: zoom !== 1 ? `scale(${zoom})` : undefined,
            position: 'absolute',
            top: 0,
            left: 0,
          }}
        >
          {children}
        </div>

        {/* Empty canvas message for read-only users */}
        {containerCount === 0 && !editable && (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-muted-foreground gap-3 pointer-events-none">
            <FileText className="h-12 w-12 text-muted-foreground/30" aria-hidden="true" />
            <p className="text-sm">This canvas is empty</p>
          </div>
        )}

        {/* Empty canvas hint for editors */}
        {containerCount === 0 && editable && (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-muted-foreground gap-3 pointer-events-none">
            <p className="text-sm">Right-click to add a text container</p>
          </div>
        )}
      </div>

      {/* Context menu — clamped to viewport bounds */}
      {ctxMenu.visible && (() => {
        const outerRect = outerRef.current?.getBoundingClientRect()
        const menuW = 170 // approximate menu width
        const menuH = 40  // approximate menu height
        let left = ctxMenu.screenX - (outerRect?.left ?? 0) + (outerRef.current?.scrollLeft ?? 0)
        let top = ctxMenu.screenY - (outerRect?.top ?? 0) + (outerRef.current?.scrollTop ?? 0)
        // Clamp so menu stays inside the visible viewport (account for scroll offset)
        if (outerRect) {
          const scrollL = outerRef.current?.scrollLeft ?? 0
          const scrollT = outerRef.current?.scrollTop ?? 0
          const maxLeft = scrollL + outerRect.width - menuW
          const maxTop = scrollT + outerRect.height - menuH
          left = Math.max(scrollL, Math.min(left, maxLeft))
          top = Math.max(scrollT, Math.min(top, maxTop))
        }
        return (
          <div
            className="canvas-context-menu"
            style={{ left, top }}
            role="menu"
            onKeyDown={handleMenuKeyDown}
          >
            <button
              ref={menuItemRef}
              type="button"
              role="menuitem"
              className="canvas-context-menu-item"
              onClick={handleAddFromMenu}
            >
              <PlusSquare className="h-4 w-4" aria-hidden="true" />
              Add Container
            </button>
          </div>
        )
      })()}
    </div>
  )
}
