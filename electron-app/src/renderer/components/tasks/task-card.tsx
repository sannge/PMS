/**
 * Task Card Component
 *
 * Ultra-compact row-based task display optimized for dense lists.
 * Features:
 * - Single-row layout with all information inline
 * - Task type icon and key
 * - Status badge with quick-change dropdown
 * - Priority indicator
 * - Due date with overdue highlighting
 * - Story points and subtask count
 * - Assignee avatar
 * - Hover-reveal actions
 */

import { useState, useCallback, useRef, useEffect } from 'react'
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
  ArrowRight,
  Layers,
  MoreHorizontal,
} from 'lucide-react'
import type { Task, TaskType, TaskPriority, TaskStatus } from '@/stores/tasks-store'
import { TaskStatusBadge } from './task-status-badge'

// ============================================================================
// Types
// ============================================================================

export interface TaskCardProps {
  task: Task
  onClick?: (task: Task) => void
  onEdit?: (task: Task) => void
  onDelete?: (task: Task) => void
  onStatusChange?: (task: Task, status: TaskStatus) => void
  disabled?: boolean
  showDragHandle?: boolean
  variant?: 'default' | 'compact'
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
    icon: <Flag className="h-3 w-3" />,
    color: 'text-red-500',
    label: 'Highest',
  },
  high: {
    icon: <Flag className="h-3 w-3" />,
    color: 'text-orange-500',
    label: 'High',
  },
  medium: {
    icon: <Flag className="h-3 w-3" />,
    color: 'text-yellow-500',
    label: 'Medium',
  },
  low: {
    icon: <Flag className="h-3 w-3" />,
    color: 'text-blue-500',
    label: 'Low',
  },
  lowest: {
    icon: <Flag className="h-3 w-3" />,
    color: 'text-slate-400',
    label: 'Lowest',
  },
}

// ============================================================================
// Helper Functions
// ============================================================================

function getTaskTypeIcon(taskType: TaskType): JSX.Element {
  switch (taskType) {
    case 'bug':
      return <Bug className="h-3.5 w-3.5 text-red-500" />
    case 'epic':
      return <Bookmark className="h-3.5 w-3.5 text-purple-500" />
    case 'story':
      return <Bookmark className="h-3.5 w-3.5 text-green-500" />
    case 'subtask':
      return <Layers className="h-3.5 w-3.5 text-blue-400" />
    case 'task':
    default:
      return <CheckCircle2 className="h-3.5 w-3.5 text-blue-500" />
  }
}

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
// Actions Dropdown Component
// ============================================================================

interface ActionsDropdownProps {
  onEdit?: () => void
  onDelete?: () => void
  disabled?: boolean
}

function ActionsDropdown({ onEdit, onDelete, disabled }: ActionsDropdownProps): JSX.Element {
  const [isOpen, setIsOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleToggle = (e: React.MouseEvent) => {
    e.stopPropagation()
    setIsOpen(!isOpen)
  }

  return (
    <div ref={dropdownRef} className="relative">
      <button
        onClick={handleToggle}
        disabled={disabled}
        className={cn(
          'flex h-6 w-6 items-center justify-center rounded-md',
          'text-muted-foreground transition-colors',
          'hover:bg-muted hover:text-foreground',
          'focus:outline-none focus:ring-1 focus:ring-ring',
          'disabled:pointer-events-none disabled:opacity-50'
        )}
        title="Actions"
      >
        <MoreHorizontal className="h-3.5 w-3.5" />
      </button>

      {isOpen && (
        <div
          className={cn(
            'absolute right-0 top-full z-50 mt-1 min-w-[120px]',
            'rounded-md border border-border bg-popover shadow-lg',
            'animate-in fade-in-0 zoom-in-95 duration-100'
          )}
        >
          {onEdit && (
            <button
              onClick={(e) => {
                e.stopPropagation()
                onEdit()
                setIsOpen(false)
              }}
              className={cn(
                'flex w-full items-center gap-2 px-3 py-1.5 text-xs',
                'text-foreground hover:bg-accent',
                'transition-colors first:rounded-t-md'
              )}
            >
              <Edit2 className="h-3 w-3" />
              Edit
            </button>
          )}
          {onDelete && (
            <button
              onClick={(e) => {
                e.stopPropagation()
                onDelete()
                setIsOpen(false)
              }}
              className={cn(
                'flex w-full items-center gap-2 px-3 py-1.5 text-xs',
                'text-destructive hover:bg-destructive/10',
                'transition-colors last:rounded-b-md'
              )}
            >
              <Trash2 className="h-3 w-3" />
              Delete
            </button>
          )}
        </div>
      )}
    </div>
  )
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
  variant = 'default',
  className,
}: TaskCardProps): JSX.Element {
  const handleClick = useCallback(
    (e: React.MouseEvent) => {
      if ((e.target as HTMLElement).closest('button')) {
        return
      }
      if (!disabled && onClick) {
        onClick(task)
      }
    },
    [task, disabled, onClick]
  )

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

  // Compact variant - minimal single row
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
          'group flex h-9 items-center gap-2 rounded-md border border-border/50 bg-card px-2',
          'transition-all duration-100',
          onClick && !disabled && 'cursor-pointer hover:border-primary/40 hover:bg-accent/30',
          disabled && 'opacity-50 cursor-not-allowed',
          'focus:outline-none focus:ring-1 focus:ring-ring',
          className
        )}
      >
        {/* Task Type Icon */}
        <div className="flex-shrink-0">{getTaskTypeIcon(task.task_type)}</div>

        {/* Task Key */}
        <span className="flex-shrink-0 text-[10px] font-medium text-muted-foreground font-mono">
          {task.task_key}
        </span>

        {/* Title */}
        <span className="flex-1 min-w-0 text-xs text-foreground truncate">{task.title}</span>

        {/* Priority */}
        <span className={cn('flex-shrink-0', priorityConfig.color)} title={priorityConfig.label}>
          {priorityConfig.icon}
        </span>

        {/* Assignee */}
        {task.assignee_id && (
          <div className="flex-shrink-0 flex h-5 w-5 items-center justify-center rounded-full bg-primary/10 text-primary">
            <User className="h-2.5 w-2.5" />
          </div>
        )}

        {/* View indicator */}
        {onClick && !disabled && (
          <ArrowRight className="h-3 w-3 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
        )}
      </div>
    )
  }

  // Default variant - compact row with more details
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
        'group relative flex h-11 items-center gap-2.5 rounded-lg border border-border/60 bg-card px-3',
        'transition-all duration-150 ease-out',
        onClick && !disabled && [
          'cursor-pointer',
          'hover:border-primary/30 hover:bg-primary/[0.02]',
          'hover:shadow-sm',
        ],
        disabled && 'opacity-50 cursor-not-allowed',
        'focus:outline-none focus:ring-1 focus:ring-ring',
        className
      )}
    >
      {/* Task Type Icon */}
      <div className="flex-shrink-0" title={getTaskTypeLabel(task.task_type)}>
        {getTaskTypeIcon(task.task_type)}
      </div>

      {/* Task Key */}
      <span className="flex-shrink-0 text-[10px] font-medium text-muted-foreground font-mono min-w-[60px]">
        {task.task_key}
      </span>

      {/* Title */}
      <span className="flex-1 min-w-0 text-sm text-foreground truncate group-hover:text-primary transition-colors">
        {task.title}
      </span>

      {/* Status Badge */}
      <div className="flex-shrink-0" onClick={(e) => e.stopPropagation()}>
        <TaskStatusBadge
          status={task.status}
          onStatusChange={onStatusChange ? handleStatusChange : undefined}
          disabled={disabled}
          size="sm"
        />
      </div>

      {/* Priority */}
      <span className={cn('flex-shrink-0', priorityConfig.color)} title={priorityConfig.label}>
        {priorityConfig.icon}
      </span>

      {/* Story Points */}
      {task.story_points != null && (
        <span className="flex-shrink-0 flex h-5 min-w-5 items-center justify-center rounded bg-muted px-1 text-[10px] font-medium text-muted-foreground">
          {task.story_points}
        </span>
      )}

      {/* Due Date */}
      {dueInfo && (
        <span
          className={cn(
            'flex-shrink-0 flex items-center gap-0.5 text-[10px]',
            dueInfo.isOverdue
              ? 'text-red-500 font-medium'
              : dueInfo.isSoon
                ? 'text-yellow-600 dark:text-yellow-500'
                : 'text-muted-foreground'
          )}
          title={new Date(task.due_date!).toLocaleDateString()}
        >
          <Clock className="h-2.5 w-2.5" />
          {dueInfo.text}
        </span>
      )}

      {/* Subtasks indicator */}
      {task.subtasks_count != null && task.subtasks_count > 0 && (
        <span className="flex-shrink-0 flex items-center gap-0.5 text-[10px] text-muted-foreground">
          <Layers className="h-2.5 w-2.5" />
          {task.subtasks_count}
        </span>
      )}

      {/* Assignee */}
      {task.assignee_id && (
        <div className="flex-shrink-0 flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 text-primary">
          <User className="h-3 w-3" />
        </div>
      )}

      {/* Actions */}
      <div
        className={cn(
          'flex-shrink-0 opacity-0 transition-opacity duration-100',
          'group-hover:opacity-100'
        )}
      >
        {(onEdit || onDelete) && (
          <ActionsDropdown
            onEdit={onEdit ? () => onEdit(task) : undefined}
            onDelete={onDelete ? () => onDelete(task) : undefined}
            disabled={disabled}
          />
        )}
      </div>

      {/* Arrow indicator */}
      {onClick && !disabled && (
        <ArrowRight
          className={cn(
            'h-3.5 w-3.5 flex-shrink-0 text-muted-foreground/50',
            'opacity-0 -translate-x-1 transition-all duration-150',
            'group-hover:opacity-100 group-hover:translate-x-0',
            'group-hover:text-primary'
          )}
        />
      )}
    </div>
  )
}

// ============================================================================
// Exports
// ============================================================================

export { getTaskTypeIcon, getTaskTypeLabel, PRIORITY_CONFIG }
export default TaskCard
