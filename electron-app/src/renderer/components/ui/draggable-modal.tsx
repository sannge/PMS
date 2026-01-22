/**
 * DraggableModal Component
 *
 * A wrapper that makes any modal content draggable and resizable.
 * Built with vanilla React for maximum control and performance.
 *
 * Features:
 * - Drag to move by header
 * - Resize from corners and edges
 * - Stays within viewport bounds
 * - Smooth animations
 * - Keyboard accessible
 * - Memory of last position (optional)
 */

import { useState, useCallback, useRef, useEffect, type ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { GripHorizontal } from 'lucide-react'

// ============================================================================
// Types
// ============================================================================

export interface DraggableModalProps {
  /** Content to render inside the modal */
  children: ReactNode
  /** Whether the modal is open */
  open: boolean
  /** Callback when modal should close */
  onClose: () => void
  /** Initial width in pixels */
  initialWidth?: number
  /** Initial height in pixels (auto if not specified) */
  initialHeight?: number
  /** Minimum width in pixels */
  minWidth?: number
  /** Minimum height in pixels */
  minHeight?: number
  /** Maximum width in pixels */
  maxWidth?: number
  /** Maximum height in pixels */
  maxHeight?: number
  /** Whether the modal can be resized */
  resizable?: boolean
  /** Custom class name for the modal container */
  className?: string
  /** ID for persisting position (uses localStorage) */
  persistId?: string
  /** Custom header content (if not provided, uses default grip handle) */
  header?: ReactNode
  /** Whether to show the default drag handle */
  showDragHandle?: boolean
}

interface Position {
  x: number
  y: number
}

interface Size {
  width: number
  height: number
}

type ResizeDirection = 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw' | null

// ============================================================================
// Helper Functions
// ============================================================================

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
}

function getPersistedState(id: string): { position?: Position; size?: Size } | null {
  try {
    const stored = localStorage.getItem(`draggable-modal-${id}`)
    return stored ? JSON.parse(stored) : null
  } catch {
    return null
  }
}

function setPersistedState(id: string, state: { position: Position; size: Size }): void {
  try {
    localStorage.setItem(`draggable-modal-${id}`, JSON.stringify(state))
  } catch {
    // Ignore storage errors
  }
}

// ============================================================================
// Component
// ============================================================================

export function DraggableModal({
  children,
  open,
  onClose,
  initialWidth = 400,
  initialHeight,
  minWidth = 200,
  minHeight = 150,
  maxWidth = 1200,
  maxHeight = 900,
  resizable = true,
  className,
  persistId,
  header,
  showDragHandle = true,
}: DraggableModalProps): JSX.Element | null {
  const containerRef = useRef<HTMLDivElement>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [isResizing, setIsResizing] = useState(false)
  const [resizeDirection, setResizeDirection] = useState<ResizeDirection>(null)

  // Initialize position and size
  const [position, setPosition] = useState<Position>(() => {
    if (persistId) {
      const persisted = getPersistedState(persistId)
      if (persisted?.position) return persisted.position
    }
    // Center in viewport
    return {
      x: Math.max(0, (window.innerWidth - initialWidth) / 2),
      y: Math.max(0, (window.innerHeight - (initialHeight || 300)) / 2),
    }
  })

  const [size, setSize] = useState<Size>(() => {
    if (persistId) {
      const persisted = getPersistedState(persistId)
      if (persisted?.size) return persisted.size
    }
    return {
      width: initialWidth,
      height: initialHeight || 0, // 0 means auto
    }
  })

  // Drag state refs
  const dragStartRef = useRef<{ mouseX: number; mouseY: number; posX: number; posY: number } | null>(null)
  const resizeStartRef = useRef<{ mouseX: number; mouseY: number; width: number; height: number; posX: number; posY: number } | null>(null)

  // Persist state when it changes
  useEffect(() => {
    if (persistId && !isDragging && !isResizing) {
      setPersistedState(persistId, { position, size })
    }
  }, [persistId, position, size, isDragging, isResizing])

  // Handle mouse move for dragging
  const handleMouseMove = useCallback(
    (e: MouseEvent) => {
      if (isDragging && dragStartRef.current) {
        const deltaX = e.clientX - dragStartRef.current.mouseX
        const deltaY = e.clientY - dragStartRef.current.mouseY

        const newX = clamp(
          dragStartRef.current.posX + deltaX,
          0,
          window.innerWidth - (containerRef.current?.offsetWidth || 100)
        )
        const newY = clamp(
          dragStartRef.current.posY + deltaY,
          0,
          window.innerHeight - 50 // Keep at least 50px visible
        )

        setPosition({ x: newX, y: newY })
      }

      if (isResizing && resizeStartRef.current && resizeDirection) {
        const deltaX = e.clientX - resizeStartRef.current.mouseX
        const deltaY = e.clientY - resizeStartRef.current.mouseY

        let newWidth = resizeStartRef.current.width
        let newHeight = resizeStartRef.current.height
        let newX = resizeStartRef.current.posX
        let newY = resizeStartRef.current.posY

        // Handle horizontal resize
        if (resizeDirection.includes('e')) {
          newWidth = clamp(resizeStartRef.current.width + deltaX, minWidth, maxWidth)
        }
        if (resizeDirection.includes('w')) {
          const widthChange = clamp(resizeStartRef.current.width - deltaX, minWidth, maxWidth) - resizeStartRef.current.width
          newWidth = resizeStartRef.current.width + widthChange
          newX = resizeStartRef.current.posX - widthChange
        }

        // Handle vertical resize
        if (resizeDirection.includes('s')) {
          newHeight = clamp(resizeStartRef.current.height + deltaY, minHeight, maxHeight)
        }
        if (resizeDirection.includes('n')) {
          const heightChange = clamp(resizeStartRef.current.height - deltaY, minHeight, maxHeight) - resizeStartRef.current.height
          newHeight = resizeStartRef.current.height + heightChange
          newY = resizeStartRef.current.posY - heightChange
        }

        // Ensure modal stays in viewport
        newX = Math.max(0, newX)
        newY = Math.max(0, newY)

        setSize({ width: newWidth, height: newHeight })
        setPosition({ x: newX, y: newY })
      }
    },
    [isDragging, isResizing, resizeDirection, minWidth, minHeight, maxWidth, maxHeight]
  )

  // Handle mouse up
  const handleMouseUp = useCallback(() => {
    setIsDragging(false)
    setIsResizing(false)
    setResizeDirection(null)
    dragStartRef.current = null
    resizeStartRef.current = null
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  }, [])

  // Add/remove global event listeners
  useEffect(() => {
    if (isDragging || isResizing) {
      document.addEventListener('mousemove', handleMouseMove)
      document.addEventListener('mouseup', handleMouseUp)
      document.body.style.userSelect = 'none'
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }
  }, [isDragging, isResizing, handleMouseMove, handleMouseUp])

  // Start dragging
  const handleDragStart = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault()
      setIsDragging(true)
      dragStartRef.current = {
        mouseX: e.clientX,
        mouseY: e.clientY,
        posX: position.x,
        posY: position.y,
      }
      document.body.style.cursor = 'grabbing'
    },
    [position]
  )

  // Start resizing
  const handleResizeStart = useCallback(
    (e: React.MouseEvent, direction: ResizeDirection) => {
      e.preventDefault()
      e.stopPropagation()
      setIsResizing(true)
      setResizeDirection(direction)
      resizeStartRef.current = {
        mouseX: e.clientX,
        mouseY: e.clientY,
        width: containerRef.current?.offsetWidth || size.width,
        height: containerRef.current?.offsetHeight || size.height,
        posX: position.x,
        posY: position.y,
      }
    },
    [position, size]
  )

  // Handle escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && open) {
        onClose()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [open, onClose])

  if (!open) return null

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm animate-in fade-in-0"
        onClick={onClose}
      />

      {/* Modal */}
      <div
        ref={containerRef}
        className={cn(
          'fixed z-50 bg-card border border-border rounded-xl shadow-2xl',
          'animate-in fade-in-0 zoom-in-95',
          'flex flex-col overflow-hidden',
          isDragging && 'transition-none',
          !isDragging && 'transition-shadow',
          className
        )}
        style={{
          left: position.x,
          top: position.y,
          width: size.width,
          height: size.height || 'auto',
        }}
      >
        {/* Drag Handle / Header */}
        {(showDragHandle || header) && (
          <div
            onMouseDown={handleDragStart}
            className={cn(
              'flex items-center justify-center px-4 py-2',
              'border-b border-border/50 bg-muted/30',
              'cursor-grab active:cursor-grabbing',
              'select-none'
            )}
          >
            {header || (
              <div className="flex items-center gap-1 text-muted-foreground/50">
                <GripHorizontal className="h-4 w-4" />
              </div>
            )}
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-auto">{children}</div>

        {/* Resize Handles */}
        {resizable && (
          <>
            {/* Corner handles */}
            <div
              onMouseDown={(e) => handleResizeStart(e, 'se')}
              className="absolute bottom-0 right-0 h-4 w-4 cursor-se-resize"
            />
            <div
              onMouseDown={(e) => handleResizeStart(e, 'sw')}
              className="absolute bottom-0 left-0 h-4 w-4 cursor-sw-resize"
            />
            <div
              onMouseDown={(e) => handleResizeStart(e, 'ne')}
              className="absolute top-0 right-0 h-4 w-4 cursor-ne-resize"
            />
            <div
              onMouseDown={(e) => handleResizeStart(e, 'nw')}
              className="absolute top-0 left-0 h-4 w-4 cursor-nw-resize"
            />

            {/* Edge handles */}
            <div
              onMouseDown={(e) => handleResizeStart(e, 'e')}
              className="absolute top-4 bottom-4 right-0 w-2 cursor-e-resize"
            />
            <div
              onMouseDown={(e) => handleResizeStart(e, 'w')}
              className="absolute top-4 bottom-4 left-0 w-2 cursor-w-resize"
            />
            <div
              onMouseDown={(e) => handleResizeStart(e, 's')}
              className="absolute bottom-0 left-4 right-4 h-2 cursor-s-resize"
            />
            <div
              onMouseDown={(e) => handleResizeStart(e, 'n')}
              className="absolute top-0 left-4 right-4 h-2 cursor-n-resize"
            />
          </>
        )}
      </div>
    </>
  )
}

export default DraggableModal
