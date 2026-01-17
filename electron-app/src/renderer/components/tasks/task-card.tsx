/**
 * Task Card Component
 *
 * Displays a task in a card format with title, status, priority,
 * assignee, and other metadata.
 *
 * Features:
 * - Task type icon
 * - Status badge with transitions
 * - Priority indicator
 * - Assignee avatar
 * - Due date display
 * - Story points badge
 * - Edit and delete actions
 * - Hover effects and accessibility
 * - Drag handle ready for future DnD
 */

import { useCallback } from 'react'
import { cn } from '@/lib/utils'
import {
  Bug,
  Bookmark,
  CheckCircle2,
  Clock,
  User,
  Flag,
  Edit2,
  Trash2,
  GripVertical,
  ArrowRight,
  Layers,
} from 'lucide-react'
import type { Task, TaskType, TaskPriority, TaskStatus } from '@/stores/tasks-store'
import { TaskStatusBadge } from './task-status-badge'

// ============================================================================
// Types
// ============================================================================

export interface TaskCardProps {
  /**
   * Task data to display
   */
  task: Task
  /**
   * Callback when the card is clicked
   */
  onClick?: (task: Task) => void
  /**
   * Callback when edit is clicked
   */
  onEdit?: (task: Task) => void
  /**
   * Callback when delete is clicked
   */
  onDelete?: (task: Task) => void
  /**
   * Callback when status changes
   */
  onStatusChange?: (task: Task, status: TaskStatus) => void
  /**
   * Whether actions are disabled
   */
  disabled?: boolean
  /**
   * Whether to show the drag handle
   */
  showDragHandle?: boolean
  /**
   * Display variant
   */
  variant?: 'default' | 'compact'
  /**
   * Additional CSS classes
   */
  className?: string
}

interface PriorityConfig {
  icon: JSX.Element
  color: string
  label: string
}

// ============================================================================
// Constants
// ============================================================================

const PRIORITY_CONFIG: Record<TaskPriority, PriorityConfig> = {
  highest: {
    icon: <Flag className="h-3.5 w-3.5" />,
    color: 'text-red-600 dark:text-red-400',
    label: 'Highest',
  },
  high: {
    icon: <Flag className="h-3.5 w-3.5" />,
    color: 'text-orange-600 dark:text-orange-400',
    label: 'High',
  },
  medium: {
    icon: <Flag className="h-3.5 w-3.5" />,
    color: 'text-yellow-600 dark:text-yellow-400',
    label: 'Medium',
  },
  low: {
    icon: <Flag className="h-3.5 w-3.5" />,
    color: 'text-blue-600 dark:text-blue-400',
    label: 'Low',
  },
  lowest: {
    icon: <Flag className="h-3.5 w-3.5" />,
    color: 'text-slate-400 dark:text-slate-500',
    label: 'Lowest',
  },
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Get task type icon
 */
function getTaskTypeIcon(taskType: TaskType): JSX.Element {
  switch (taskType) {
    case 'bug':
      return <Bug className="h-4 w-4 text-red-500" />
    case 'epic':
      return <Bookmark className="h-4 w-4 text-purple-500" />
    case 'story':
      return <Bookmark className="h-4 w-4 text-green-500" />
    case 'subtask':
      return <Layers className="h-4 w-4 text-blue-400" />
    case 'task':
    default:
      return <CheckCircle2 className="h-4 w-4 text-blue-500" />
  }
}

/**
 * Get task type label
 */
function getTaskTypeLabel(taskType: TaskType): string {
  switch (taskType) {
    case 'bug':
      return 'Bug'
    case 'epic':
      return 'Epic'
    case 'story':
      return 'Story'
    case 'subtask':
      return 'Subtask'
    case 'task':
    default:
      return 'Task'
  }
}

/**
 * Format due date with relative display
 */
function formatDueDate(dateString: string): { text: string; isOverdue: boolean; isSoon: boolean } {
  const date = new Date(dateString)
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const dueDate = new Date(date.getFullYear(), date.getMonth(), date.getDate())
  const diffDays = Math.ceil((dueDate.getTime() - today.getTime()) / (1000 * 60 * 60 * 24))

  if (diffDays < 0) {
    return { text: 'Overdue', isOverdue: true, isSoon: false }
  }
  if (diffDays === 0) {
    return { text: 'Today', isOverdue: false, isSoon: true }
  }
  if (diffDays === 1) {
    return { text: 'Tomorrow', isOverdue: false, isSoon: true }
  }
  if (diffDays <= 7) {
    return { text: `${diffDays}d`, isOverdue: false, isSoon: true }
  }

  return {
    text: date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
    isOverdue: false,
    isSoon: false,
  }
}

// ============================================================================
// Component
// ============================================================================

export function TaskCard({
  task,
  onClick,
  onEdit,
  onDelete,
  onStatusChange,
  disabled = false,
  showDragHandle = false,
  variant = 'default',
  className,
}: TaskCardProps): JSX.Element {
  // Handle card click
  const handleClick = useCallback(
    (e: React.MouseEvent) => {
      // Don't trigger click if clicking on buttons or dropdown
      if ((e.target as HTMLElement).closest('button')) {
        return
      }
      if (!disabled && onClick) {
        onClick(task)
      }
    },
    [task, disabled, onClick]
  )

  // Handle edit click
  const handleEdit = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation()
      if (!disabled && onEdit) {
        onEdit(task)
      }
    },
    [task, disabled, onEdit]
  )

  // Handle delete click
  const handleDelete = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation()
      if (!disabled && onDelete) {
        onDelete(task)
      }
    },
    [task, disabled, onDelete]
  )

  // Handle status change
  const handleStatusChange = useCallback(
    (status: TaskStatus) => {
      if (!disabled && onStatusChange) {
        onStatusChange(task, status)
      }
    },
    [task, disabled, onStatusChange]
  )

  const priorityConfig = PRIORITY_CONFIG[task.priority]
  const dueInfo = task.due_date ? formatDueDate(task.due_date) : null

  // Compact variant
  if (variant === 'compact') {
    return (
      <div
        onClick={handleClick}
        role={onClick ? 'button' : undefined}
        tabIndex={onClick ? 0 : undefined}
        onKeyDown={(e) => {
          if (onClick && (e.key === 'Enter' || e.key === ' ')) {
            e.preventDefault()
            onClick(task)
          }
        }}
        className={cn(
          'group flex items-center gap-3 rounded-lg border border-border bg-card p-2 transition-all',
          onClick && !disabled && 'cursor-pointer hover:border-primary/50 hover:bg-accent/50',
          disabled && 'opacity-50 cursor-not-allowed',
          'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1',
          className
        )}
      >
        {/* Task Type Icon */}
        <div className="flex-shrink-0">{getTaskTypeIcon(task.task_type)}</div>

        {/* Task Key */}
        <span className="flex-shrink-0 text-xs font-medium text-muted-foreground font-mono">
          {task.task_key}
        </span>

        {/* Title */}
        <span className="flex-1 text-sm text-foreground truncate">{task.title}</span>

        {/* Priority */}
        <span className={cn('flex-shrink-0', priorityConfig.color)} title={priorityConfig.label}>
          {priorityConfig.icon}
        </span>

        {/* Assignee */}
        {task.assignee_id && (
          <div className="flex-shrink-0 flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 text-primary">
            <User className="h-3 w-3" />
          </div>
        )}

        {/* View indicator */}
        {onClick && !disabled && (
          <ArrowRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
        )}
      </div>
    )
  }

  // Default variant
  return (
    <div
      onClick={handleClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={(e) => {
        if (onClick && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault()
          onClick(task)
        }
      }}
      className={cn(
        'group relative rounded-lg border border-border bg-card p-3 transition-all',
        onClick && !disabled && 'cursor-pointer hover:border-primary/50 hover:shadow-md',
        disabled && 'opacity-50 cursor-not-allowed',
        'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1',
        className
      )}
    >
      {/* Drag Handle (optional) */}
      {showDragHandle && (
        <div className="absolute left-0 top-0 bottom-0 flex items-center px-1 opacity-0 group-hover:opacity-100 transition-opacity cursor-grab">
          <GripVertical className="h-4 w-4 text-muted-foreground" />
        </div>
      )}

      {/* Header Row */}
      <div className="flex items-start justify-between gap-2">
        {/* Task Key and Type */}
        <div className="flex items-center gap-2">
          {getTaskTypeIcon(task.task_type)}
          <span className="text-xs font-medium text-muted-foreground font-mono">
            {task.task_key}
          </span>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          {onEdit && (
            <button
              onClick={handleEdit}
              disabled={disabled}
              className={cn(
                'rounded-md p-1 text-muted-foreground transition-colors',
                'hover:bg-accent hover:text-accent-foreground',
                'focus:outline-none focus:ring-2 focus:ring-ring',
                'disabled:pointer-events-none disabled:opacity-50'
              )}
              title="Edit task"
            >
              <Edit2 className="h-3.5 w-3.5" />
            </button>
          )}
          {onDelete && (
            <button
              onClick={handleDelete}
              disabled={disabled}
              className={cn(
                'rounded-md p-1 text-muted-foreground transition-colors',
                'hover:bg-destructive/10 hover:text-destructive',
                'focus:outline-none focus:ring-2 focus:ring-ring',
                'disabled:pointer-events-none disabled:opacity-50'
              )}
              title="Delete task"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Title */}
      <h4 className="mt-2 text-sm font-medium text-foreground line-clamp-2">
        {task.title}
      </h4>

      {/* Description (if present) */}
      {task.description && (
        <p className="mt-1 text-xs text-muted-foreground line-clamp-2">
          {task.description}
        </p>
      )}

      {/* Footer */}
      <div className="mt-3 flex items-center justify-between gap-2">
        {/* Left side: Status + Priority */}
        <div className="flex items-center gap-2">
          {/* Status Badge */}
          <TaskStatusBadge
            status={task.status}
            onStatusChange={onStatusChange ? handleStatusChange : undefined}
            disabled={disabled}
            size="sm"
          />

          {/* Priority */}
          <span
            className={cn('flex items-center', priorityConfig.color)}
            title={priorityConfig.label}
          >
            {priorityConfig.icon}
          </span>

          {/* Story Points */}
          {task.story_points != null && (
            <span className="rounded-full bg-muted px-1.5 py-0.5 text-xs font-medium text-muted-foreground">
              {task.story_points}
            </span>
          )}
        </div>

        {/* Right side: Due date + Assignee */}
        <div className="flex items-center gap-2">
          {/* Due Date */}
          {dueInfo && (
            <span
              className={cn(
                'flex items-center gap-1 text-xs',
                dueInfo.isOverdue
                  ? 'text-red-600 dark:text-red-400'
                  : dueInfo.isSoon
                    ? 'text-yellow-600 dark:text-yellow-400'
                    : 'text-muted-foreground'
              )}
              title={new Date(task.due_date!).toLocaleDateString()}
            >
              <Clock className="h-3 w-3" />
              {dueInfo.text}
            </span>
          )}

          {/* Subtasks indicator */}
          {task.subtasks_count != null && task.subtasks_count > 0 && (
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              <Layers className="h-3 w-3" />
              {task.subtasks_count}
            </span>
          )}

          {/* Assignee */}
          {task.assignee_id && (
            <div className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 text-primary">
              <User className="h-3 w-3" />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ============================================================================
// Exports
// ============================================================================

export { getTaskTypeIcon, getTaskTypeLabel, PRIORITY_CONFIG }
export default TaskCard
