/**
 * Kanban Column Component
 *
 * A reusable column component for Kanban-style task boards.
 * Features:
 * - Status-based column with configurable styling
 * - Column header with icon, title, and task count
 * - Add task button (optional)
 * - Drag-and-drop task reordering and moving between columns
 * - Drop zone indicators during drag operations
 * - Loading skeleton state
 * - Empty state with icon
 * - Sorted task display by task_rank
 */

import { useCallback, useMemo, useRef } from 'react'
import { cn } from '@/lib/utils'
import {
  Plus,
  Circle,
  Timer,
  Eye,
  CheckCircle2,
  XCircle,
  GripVertical,
} from 'lucide-react'
import type { Task } from '@/hooks/use-queries'
import { TaskCard } from './task-card'
import { SkeletonTaskCard } from '@/components/ui/skeleton'

// ============================================================================
// Types
// ============================================================================

/**
 * Column configuration for Kanban board
 */
export interface KanbanColumnConfig {
  id: string
  title: string
  icon: JSX.Element
  color: string
  bgColor: string
}

export interface KanbanColumnProps {
  /**
   * Column configuration (id, title, icon, colors)
   */
  column: KanbanColumnConfig
  /**
   * Tasks to display in this column
   */
  tasks: Task[]
  /**
   * Callback when a task is clicked
   */
  onTaskClick?: (task: Task) => void
  /**
   * Callback when add task button is clicked
   */
  onAddTask?: (status: string) => void
  /**
   * Callback when task drag starts
   */
  onDragStart?: (e: React.DragEvent, task: Task) => void
  /**
   * Callback when task drag ends
   */
  onDragEnd?: (e: React.DragEvent) => void
  /**
   * Callback when dragging over this column
   */
  onDragOver?: (e: React.DragEvent) => void
  /**
   * Callback when drag leaves this column
   */
  onDragLeave?: (e: React.DragEvent) => void
  /**
   * Callback when a task is dropped on this column
   */
  onDrop?: (e: React.DragEvent, status: string) => void
  /**
   * ID of the currently dragging task (if any)
   */
  draggingTaskId?: string | null
  /**
   * Whether a drag operation is currently over this column
   */
  isDragOver?: boolean
  /**
   * Whether the column is in loading state
   */
  isLoading?: boolean
  /**
   * Whether task editing is disabled
   */
  disabled?: boolean
  /**
   * Whether to show the add task button
   */
  showAddButton?: boolean
  /**
   * Additional CSS classes
   */
  className?: string
}

// ============================================================================
// Constants
// ============================================================================

/**
 * Default column configurations for standard 5-status Kanban board
 */
export const DEFAULT_COLUMNS: KanbanColumnConfig[] = [
  {
    id: 'Todo',
    title: 'To Do',
    icon: <Circle className="h-4 w-4" />,
    color: 'bg-slate-500',
    bgColor: 'bg-slate-500/10',
  },
  {
    id: 'In Progress',
    title: 'In Progress',
    icon: <Timer className="h-4 w-4" />,
    color: 'bg-blue-500',
    bgColor: 'bg-blue-500/10',
  },
  {
    id: 'In Review',
    title: 'In Review',
    icon: <Eye className="h-4 w-4" />,
    color: 'bg-purple-500',
    bgColor: 'bg-purple-500/10',
  },
  {
    id: 'Issue',
    title: 'Issue',
    icon: <XCircle className="h-4 w-4" />,
    color: 'bg-red-500',
    bgColor: 'bg-red-500/10',
  },
  {
    id: 'Done',
    title: 'Done',
    icon: <CheckCircle2 className="h-4 w-4" />,
    color: 'bg-green-500',
    bgColor: 'bg-green-500/10',
  },
]

/**
 * Get column configuration by status ID
 */
export function getColumnConfig(status: string): KanbanColumnConfig {
  const config = DEFAULT_COLUMNS.find((col) => col.id === status)
  if (config) return config
  // Fallback for unknown status
  return {
    id: status,
    title: status.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
    icon: <Circle className="h-4 w-4" />,
    color: 'bg-slate-500',
    bgColor: 'bg-slate-500/10',
  }
}

// ============================================================================
// Draggable Task Card Component
// ============================================================================

interface DraggableTaskCardProps {
  task: Task
  onClick?: (task: Task) => void
  onDragStart?: (e: React.DragEvent, task: Task) => void
  onDragEnd?: (e: React.DragEvent) => void
  isDragging: boolean
  disabled?: boolean
}

function DraggableTaskCard({
  task,
  onClick,
  onDragStart,
  onDragEnd,
  isDragging,
  disabled,
}: DraggableTaskCardProps): JSX.Element {
  // Track whether a drag actually started to differentiate click vs drag
  const didDragRef = useRef(false)

  const handleDragStart = useCallback(
    (e: React.DragEvent) => {
      if (disabled) {
        e.preventDefault()
        return
      }
      didDragRef.current = true
      e.dataTransfer.effectAllowed = 'move'
      e.dataTransfer.setData('text/plain', task.id)
      e.dataTransfer.setData('application/json', JSON.stringify({
        taskId: task.id,
        sourceStatus: task.task_status?.name || 'Todo',
        sourceRank: task.task_rank,
      }))
      onDragStart?.(e, task)
    },
    [task, disabled, onDragStart]
  )

  const handleDragEnd = useCallback(
    (e: React.DragEvent) => {
      onDragEnd?.(e)
      // Reset after a short delay to allow click event to check the flag
      setTimeout(() => {
        didDragRef.current = false
      }, 0)
    },
    [onDragEnd]
  )

  const handleMouseDown = useCallback(() => {
    // Reset the drag flag on mousedown
    didDragRef.current = false
  }, [])

  const handleClickWrapper = useCallback(
    (e: React.MouseEvent) => {
      // Ignore clicks on buttons inside the card
      if ((e.target as HTMLElement).closest('button')) {
        return
      }
      // Only trigger click if no drag occurred
      if (!didDragRef.current && onClick) {
        onClick(task)
      }
    },
    [onClick, task]
  )

  return (
    <div
      draggable={!disabled ? 'true' : 'false'}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
      onMouseDown={handleMouseDown}
      onClick={handleClickWrapper}
      style={{
        WebkitUserDrag: disabled ? 'none' : 'element',
        userSelect: 'none',
      } as React.CSSProperties}
      className={cn(
        'group relative transition-all duration-150 app-no-drag',
        isDragging && 'opacity-50 scale-95',
        disabled ? 'cursor-not-allowed' : 'cursor-grab active:cursor-grabbing'
      )}
    >
      {/* Drag handle indicator */}
      {!disabled && (
        <div
          className={cn(
            'absolute left-0 top-1/2 -translate-y-1/2 -translate-x-1 opacity-0 transition-opacity',
            'group-hover:opacity-50'
          )}
        >
          <GripVertical className="h-4 w-4 text-muted-foreground" />
        </div>
      )}
      {/* TaskCard - pointer events disabled so drag works from anywhere */}
      <div style={{ pointerEvents: 'none' }}>
        <TaskCard task={task} variant="default" disabled={disabled} />
      </div>
    </div>
  )
}

// ============================================================================
// Column Header Component
// ============================================================================

interface ColumnHeaderProps {
  column: KanbanColumnConfig
  taskCount: number
  onAddTask?: (status: string) => void
  showAddButton?: boolean
  disabled?: boolean
}

function ColumnHeader({
  column,
  taskCount,
  onAddTask,
  showAddButton = true,
  disabled,
}: ColumnHeaderProps): JSX.Element {
  return (
    <div className="flex items-center justify-between p-3 border-b border-border">
      <div className="flex items-center gap-2">
        {/* Status icon */}
        <div
          className={cn(
            'flex h-6 w-6 items-center justify-center rounded text-white',
            column.color
          )}
        >
          {column.icon}
        </div>
        {/* Column title */}
        <h3 className="font-medium text-foreground">{column.title}</h3>
        {/* Task count badge */}
        <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
          {taskCount}
        </span>
      </div>
      {/* Add task button */}
      {showAddButton && onAddTask && (
        <button
          onClick={() => onAddTask(column.id)}
          disabled={disabled}
          className={cn(
            'rounded p-1 text-muted-foreground transition-colors',
            'hover:bg-accent hover:text-accent-foreground',
            'focus:outline-none focus:ring-2 focus:ring-ring',
            'disabled:pointer-events-none disabled:opacity-50'
          )}
          title={`Add task to ${column.title}`}
        >
          <Plus className="h-4 w-4" />
        </button>
      )}
    </div>
  )
}

// ============================================================================
// Empty State Component
// ============================================================================

interface EmptyStateProps {
  column: KanbanColumnConfig
  isDragOver: boolean
}

function EmptyState({ column, isDragOver }: EmptyStateProps): JSX.Element {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center py-8 text-center transition-all',
        isDragOver && 'bg-primary/10 rounded-lg border-2 border-dashed border-primary/50'
      )}
    >
      <div
        className={cn(
          'flex h-10 w-10 items-center justify-center rounded-lg text-muted-foreground',
          column.bgColor
        )}
      >
        {column.icon}
      </div>
      <p className="mt-2 text-sm text-muted-foreground">
        {isDragOver ? 'Drop task here' : 'No tasks'}
      </p>
    </div>
  )
}

// ============================================================================
// Loading State Component
// ============================================================================

function LoadingState(): JSX.Element {
  return (
    <>
      <SkeletonTaskCard />
      <SkeletonTaskCard />
    </>
  )
}

// ============================================================================
// Drop Zone Indicator Component
// ============================================================================

interface DropZoneIndicatorProps {
  isVisible: boolean
}

function DropZoneIndicator({ isVisible }: DropZoneIndicatorProps): JSX.Element | null {
  if (!isVisible) return null

  return (
    <div className="h-12 rounded-lg border-2 border-dashed border-primary/50 bg-primary/10 flex items-center justify-center">
      <span className="text-xs text-primary">Drop here</span>
    </div>
  )
}

// ============================================================================
// Main Component
// ============================================================================

export function KanbanColumn({
  column,
  tasks,
  onTaskClick,
  onAddTask,
  onDragStart,
  onDragEnd,
  onDragOver,
  onDragLeave,
  onDrop,
  draggingTaskId,
  isDragOver = false,
  isLoading = false,
  disabled = false,
  showAddButton = true,
  className,
}: KanbanColumnProps): JSX.Element {
  // Sort tasks by task_rank
  const sortedTasks = useMemo(() => {
    return [...tasks].sort((a, b) => {
      // Tasks without rank go to the end
      if (!a.task_rank && !b.task_rank) return 0
      if (!a.task_rank) return 1
      if (!b.task_rank) return -1
      return a.task_rank.localeCompare(b.task_rank)
    })
  }, [tasks])

  // Handle drag over
  const handleDragOver = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      e.dataTransfer.dropEffect = 'move'
      onDragOver?.(e)
    },
    [onDragOver]
  )

  // Handle drag leave - only trigger when leaving the column entirely
  const handleDragLeave = useCallback(
    (e: React.DragEvent) => {
      const relatedTarget = e.relatedTarget as HTMLElement
      const currentTarget = e.currentTarget as HTMLElement
      if (!currentTarget.contains(relatedTarget)) {
        onDragLeave?.(e)
      }
    },
    [onDragLeave]
  )

  // Handle drop
  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      onDrop?.(e, column.id)
    },
    [column.id, onDrop]
  )

  return (
    <div
      className={cn(
        'flex h-full w-72 flex-shrink-0 flex-col rounded-lg bg-muted/30 transition-all duration-200',
        isDragOver && 'ring-2 ring-primary/50 bg-primary/5',
        className
      )}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Column Header */}
      <ColumnHeader
        column={column}
        taskCount={tasks.length}
        onAddTask={onAddTask}
        showAddButton={showAddButton}
        disabled={disabled}
      />

      {/* Column Content */}
      <div className="flex-1 overflow-y-auto p-2 space-y-2">
        {isLoading ? (
          <LoadingState />
        ) : sortedTasks.length === 0 ? (
          <EmptyState column={column} isDragOver={isDragOver} />
        ) : (
          <>
            {sortedTasks.map((task) => (
              <DraggableTaskCard
                key={task.id}
                task={task}
                onClick={onTaskClick}
                onDragStart={onDragStart}
                onDragEnd={onDragEnd}
                isDragging={draggingTaskId === task.id}
                disabled={disabled || !!task.archived_at}
              />
            ))}
            {/* Drop zone indicator at the bottom when dragging */}
            <DropZoneIndicator isVisible={isDragOver && !!draggingTaskId} />
          </>
        )}
      </div>
    </div>
  )
}

// ============================================================================
// Exports
// ============================================================================

export { DraggableTaskCard, ColumnHeader, EmptyState, LoadingState, DropZoneIndicator }
export default KanbanColumn
