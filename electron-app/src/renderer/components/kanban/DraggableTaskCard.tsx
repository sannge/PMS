/**
 * DraggableTaskCard Component
 *
 * A task card wrapped with @dnd-kit's sortable functionality.
 * Provides smooth drag animations and accessibility support.
 *
 * Drag can be initiated from anywhere on the card:
 * - Quick click (< 5px movement): triggers onClick
 * - Click and drag (>= 5px movement): initiates drag
 */

import { useRef, useCallback } from 'react'
import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { cn } from '@/lib/utils'
import { TaskCard } from '../tasks/task-card'
import type { Task } from '@/hooks/use-queries'
import { createSortableId } from '@/hooks/use-drag-and-drop'

// ============================================================================
// Types
// ============================================================================

export interface DraggableTaskCardProps {
  /**
   * Task data to display
   */
  task: Task
  /**
   * Callback when task is clicked (quick click without drag)
   */
  onClick?: (task: Task) => void
  /**
   * Whether drag is disabled
   */
  disabled?: boolean
  /**
   * Additional class names
   */
  className?: string
}

// ============================================================================
// Component
// ============================================================================

export function DraggableTaskCard({
  task,
  onClick,
  disabled = false,
  className,
}: DraggableTaskCardProps): JSX.Element {
  const sortableId = createSortableId(task.id)
  const didDragRef = useRef(false)

  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({
    id: sortableId,
    disabled,
    data: {
      type: 'task',
      task,
    },
  })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  }

  // Track drag start via transform
  if (isDragging && !didDragRef.current) {
    didDragRef.current = true
  }

  // Merged pointer down handler - must call dnd-kit's handler
  const handlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      didDragRef.current = false
      // Call dnd-kit's handler
      if (listeners?.onPointerDown) {
        listeners.onPointerDown(e as any)
      }
    },
    [listeners]
  )

  // Handle click - only trigger if we didn't drag
  const handleClick = useCallback(() => {
    // Use setTimeout to ensure drag state is updated
    setTimeout(() => {
      if (!didDragRef.current && onClick && !isDragging) {
        onClick(task)
      }
      didDragRef.current = false
    }, 10)
  }, [onClick, task, isDragging])

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn(
        'group relative transition-shadow cursor-grab active:cursor-grabbing',
        isDragging && 'opacity-50 shadow-lg ring-2 ring-primary/50 z-50',
        disabled && 'cursor-default',
        className
      )}
      {...attributes}
      onPointerDown={handlePointerDown}
      onClick={handleClick}
    >
      {/* Task card content - pointer-events-none ensures drag works from anywhere */}
      <div className="pointer-events-none">
        <TaskCard
          task={task}
          variant="default"
        />
      </div>
    </div>
  )
}

export default DraggableTaskCard
