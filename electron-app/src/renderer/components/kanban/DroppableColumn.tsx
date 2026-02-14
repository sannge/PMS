/**
 * DroppableColumn Component
 *
 * A Kanban column with @dnd-kit droppable support.
 * Handles task drops and provides visual feedback during drag operations.
 */

import { useDroppable } from '@dnd-kit/core'
import {
  SortableContext,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { cn } from '@/lib/utils'
import { Plus, Circle, Timer, Eye, CheckCircle2, XCircle } from 'lucide-react'
import { DraggableTaskCard } from './DraggableTaskCard'
import { SkeletonTaskCard } from '@/components/ui/skeleton'
import type { Task } from '@/hooks/use-queries'
import { createSortableId } from '@/hooks/use-drag-and-drop'

// ============================================================================
// Types
// ============================================================================

export interface ColumnConfig {
  id: string
  title: string
  icon: JSX.Element
  color: string
  bgColor: string
}

export interface DroppableColumnProps {
  /**
   * Column configuration
   */
  column: ColumnConfig
  /**
   * Tasks in this column
   */
  tasks: Task[]
  /**
   * Whether the column is being hovered during drag
   */
  isOver?: boolean
  /**
   * Whether loading
   */
  isLoading?: boolean
  /**
   * Callback when task is clicked
   */
  onTaskClick?: (task: Task) => void
  /**
   * Callback when add task button is clicked
   */
  onAddTask?: (status: string) => void
  /**
   * Additional class names
   */
  className?: string
}

// ============================================================================
// Constants
// ============================================================================

const COLUMN_ICONS: Record<string, JSX.Element> = {
  Todo: <Circle className="h-4 w-4" />,
  'In Progress': <Timer className="h-4 w-4" />,
  'In Review': <Eye className="h-4 w-4" />,
  Issue: <XCircle className="h-4 w-4" />,
  Done: <CheckCircle2 className="h-4 w-4" />,
}

/**
 * Default column configurations.
 * Column IDs match TaskStatus.name values from the backend.
 */
export const DEFAULT_COLUMNS: ColumnConfig[] = [
  {
    id: 'Todo',
    title: 'To Do',
    icon: COLUMN_ICONS.Todo,
    color: 'bg-slate-500',
    bgColor: 'bg-slate-500/10',
  },
  {
    id: 'In Progress',
    title: 'In Progress',
    icon: COLUMN_ICONS['In Progress'],
    color: 'bg-blue-500',
    bgColor: 'bg-blue-500/10',
  },
  {
    id: 'In Review',
    title: 'In Review',
    icon: COLUMN_ICONS['In Review'],
    color: 'bg-purple-500',
    bgColor: 'bg-purple-500/10',
  },
  {
    id: 'Issue',
    title: 'Issue',
    icon: COLUMN_ICONS.Issue,
    color: 'bg-red-500',
    bgColor: 'bg-red-500/10',
  },
  {
    id: 'Done',
    title: 'Done',
    icon: COLUMN_ICONS.Done,
    color: 'bg-green-500',
    bgColor: 'bg-green-500/10',
  },
]

/**
 * Get column config by status
 */
export function getColumnConfig(status: string): ColumnConfig | undefined {
  return DEFAULT_COLUMNS.find((c) => c.id === status)
}

// ============================================================================
// Component
// ============================================================================

export function DroppableColumn({
  column,
  tasks,
  isOver = false,
  isLoading = false,
  onTaskClick,
  onAddTask,
  className,
}: DroppableColumnProps): JSX.Element {
  // Set up droppable
  const { setNodeRef, isOver: isDroppableOver } = useDroppable({
    id: column.id,
    data: {
      type: 'column',
      status: column.id,
    },
  })

  // Track whether we're being dragged over
  const isDragOver = isOver || isDroppableOver

  // Create sortable IDs for tasks
  const sortableIds = tasks.map((task) => createSortableId(task.id))

  return (
    <div
      ref={setNodeRef}
      className={cn(
        'flex h-full w-72 flex-shrink-0 flex-col rounded-lg bg-muted/30 transition-all duration-200',
        isDragOver && 'ring-2 ring-primary/50 bg-primary/5',
        className
      )}
    >
      {/* Column Header */}
      <div className="flex items-center justify-between p-3 border-b border-border">
        <div className="flex items-center gap-2">
          <div
            className={cn(
              'flex h-6 w-6 items-center justify-center rounded text-white',
              column.color
            )}
          >
            {column.icon}
          </div>
          <h3 className="font-medium text-foreground">{column.title}</h3>
          <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
            {tasks.length}
          </span>
        </div>
        {onAddTask && (
          <button
            onClick={() => onAddTask(column.id)}
            className={cn(
              'rounded p-1 text-muted-foreground transition-colors',
              'hover:bg-accent hover:text-accent-foreground',
              'focus:outline-none focus:ring-2 focus:ring-ring'
            )}
            title={`Add task to ${column.title}`}
          >
            <Plus className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Column Content with Sortable Context */}
      <div className="flex-1 overflow-y-auto p-2">
        <SortableContext
          items={sortableIds}
          strategy={verticalListSortingStrategy}
        >
          <div className="space-y-2">
            {isLoading ? (
              <>
                <SkeletonTaskCard />
                <SkeletonTaskCard />
              </>
            ) : tasks.length === 0 ? (
              <EmptyState column={column} isDragOver={isDragOver} />
            ) : (
              <>
                {tasks.map((task) => (
                  <DraggableTaskCard
                    key={task.id}
                    task={task}
                    onClick={onTaskClick}
                    disabled={!!task.archived_at}
                  />
                ))}
                {/* Drop zone indicator when dragging */}
                {isDragOver && (
                  <DropZoneIndicator />
                )}
              </>
            )}
          </div>
        </SortableContext>
      </div>
    </div>
  )
}

// ============================================================================
// Sub-components
// ============================================================================

interface EmptyStateProps {
  column: ColumnConfig
  isDragOver: boolean
}

function EmptyState({ column, isDragOver }: EmptyStateProps): JSX.Element {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center py-8 text-center transition-all',
        isDragOver &&
          'bg-primary/10 rounded-lg border-2 border-dashed border-primary/50'
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

function DropZoneIndicator(): JSX.Element {
  return (
    <div className="h-12 rounded-lg border-2 border-dashed border-primary/50 bg-primary/10 flex items-center justify-center animate-pulse">
      <span className="text-xs text-primary">Drop here</span>
    </div>
  )
}

export default DroppableColumn
