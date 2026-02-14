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
  CheckSquare,
  History,
} from 'lucide-react'
import { isTaskDone, type Task, type TaskType, type TaskPriority } from '@/hooks/use-queries'
import { TaskViewerDots } from './TaskViewerDots'
import type { TaskViewer } from '@/hooks/use-task-viewers'

// ============================================================================
// Types
// ============================================================================

export interface TaskCardProps {
  task: Task
  onClick?: (task: Task) => void
  onEdit?: (task: Task) => void
  onDelete?: (task: Task) => void
  onStatusChange?: (task: Task, status: string) => void
  viewers?: TaskViewer[]
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
  // Parse the date string as a local date to avoid timezone issues
  // ISO date strings like "2026-01-26" or "2026-01-26T00:00:00" are parsed as UTC,
  // which can shift to the previous day in negative UTC offset timezones
  const datePart = dateString.split('T')[0]
  const [year, month, day] = datePart.split('-').map(Number)

  // Validate parsed values
  if (isNaN(year) || isNaN(month) || isNaN(day)) {
    return { text: 'Invalid', isOverdue: false, isSoon: false }
  }

  const dueDate = new Date(year, month - 1, day) // month is 0-indexed

  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  // Use Math.round for robustness against floating point edge cases
  const diffDays = Math.round((dueDate.getTime() - today.getTime()) / (1000 * 60 * 60 * 24))

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
    text: dueDate.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
    isOverdue: false,
    isSoon: false,
  }
}

/**
 * Format completed date for done tasks
 */
function formatCompletedDate(dateString: string): string {
  const date = new Date(dateString)
  if (isNaN(date.getTime())) {
    return 'Completed'
  }
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

/**
 * Format a timestamp into a compact relative time string
 * e.g., "2m", "1h", "3d", "1w", "2mo"
 */
/**
 * Get initials from a name or email
 */
function getInitials(displayName: string | null, email: string): string {
  if (displayName) {
    const parts = displayName.trim().split(/\s+/)
    if (parts.length >= 2) {
      return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
    }
    return displayName.slice(0, 2).toUpperCase()
  }
  // Fallback to email
  return email.slice(0, 2).toUpperCase()
}

/**
 * Get display name from assignee info
 */
function getAssigneeDisplayName(assignee: { display_name: string | null; email: string }): string {
  return assignee.display_name || assignee.email.split('@')[0]
}

function formatRelativeTime(dateString: string): string {
  // Ensure UTC parsing - append 'Z' if no timezone indicator
  let dateStr = dateString
  if (!dateStr.endsWith('Z') && !dateStr.includes('+') && !dateStr.includes('-', 10)) {
    dateStr = dateStr + 'Z'
  }

  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()

  // Handle invalid dates or future dates
  if (isNaN(diffMs) || diffMs < 0) {
    return 'now'
  }

  const diffSec = Math.floor(diffMs / 1000)
  const diffMin = Math.floor(diffSec / 60)
  const diffHr = Math.floor(diffMin / 60)
  const diffDay = Math.floor(diffHr / 24)
  const diffWeek = Math.floor(diffDay / 7)
  const diffMonth = Math.floor(diffDay / 30)

  if (diffSec < 60) return 'now'
  if (diffMin < 60) return `${diffMin}m`
  if (diffHr < 24) return `${diffHr}h`
  if (diffDay < 7) return `${diffDay}d`
  if (diffWeek < 4) return `${diffWeek}w`
  if (diffMonth < 12) return `${diffMonth}mo`
  return `${Math.floor(diffMonth / 12)}y`
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
  onStatusChange: _onStatusChange,
  viewers = [],
  disabled = false,
  showDragHandle: _showDragHandle,
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

  const priorityConfig = PRIORITY_CONFIG[task.priority]
  const isDone = isTaskDone(task)
  // For done tasks, show completed date instead of due date
  const dueInfo = isDone ? null : (task.due_date ? formatDueDate(task.due_date) : null)
  const completedInfo = isDone && task.completed_at ? formatCompletedDate(task.completed_at) : null

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

        {/* Title */}
        <span className="flex-1 min-w-0 text-xs font-medium text-foreground truncate">{task.title}</span>

        {/* Priority */}
        <span className={cn('flex-shrink-0', priorityConfig.color)} title={priorityConfig.label}>
          {priorityConfig.icon}
        </span>

        {/* Assignee */}
        {task.assignee ? (
          <div className="flex-shrink-0 relative group/assignee">
            <div
              className="flex h-5 w-5 items-center justify-center rounded-full bg-primary/10 text-primary text-[9px] font-semibold"
            >
              {getInitials(task.assignee.display_name, task.assignee.email)}
            </div>
            {/* Hover tooltip */}
            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 px-2 py-1 rounded bg-popover border border-border shadow-md text-xs whitespace-nowrap opacity-0 invisible group-hover/assignee:opacity-100 group-hover/assignee:visible transition-opacity z-50">
              <div className="font-medium text-foreground">{getAssigneeDisplayName(task.assignee)}</div>
              <div className="text-muted-foreground text-[10px]">{task.assignee.email}</div>
              {/* Arrow */}
              <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-border" />
              <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-popover -mt-[1px]" />
            </div>
          </div>
        ) : (
          <div className="flex-shrink-0 relative group/assignee">
            <div
              className="flex h-5 w-5 items-center justify-center rounded-full bg-muted/50 border border-dashed border-muted-foreground/30"
            >
              <User className="h-2.5 w-2.5 text-muted-foreground/50" />
            </div>
            {/* Hover tooltip */}
            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 px-2 py-1 rounded bg-popover border border-border shadow-md text-xs whitespace-nowrap opacity-0 invisible group-hover/assignee:opacity-100 group-hover/assignee:visible transition-opacity z-50">
              <div className="text-muted-foreground">Unassigned</div>
              {/* Arrow */}
              <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-border" />
              <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-popover -mt-[1px]" />
            </div>
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

      {/* Viewer indicators */}
      {viewers.length > 0 && (
        <TaskViewerDots viewers={viewers} maxDots={3} className="flex-shrink-0" />
      )}

      {/* Title */}
      <span className="flex-1 min-w-0 text-sm font-medium text-foreground truncate group-hover:text-primary transition-colors">
        {task.title}
      </span>

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

      {/* Due Date (only for non-done tasks) */}
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

      {/* Completed Date (only for done tasks) */}
      {completedInfo && (
        <span
          className="flex-shrink-0 flex items-center gap-0.5 text-[10px] text-green-600 dark:text-green-500"
          title={`Completed: ${new Date(task.completed_at!).toLocaleString()}`}
        >
          <CheckCircle2 className="h-2.5 w-2.5" />
          {completedInfo}
        </span>
      )}

      {/* Subtasks indicator */}
      {task.subtasks_count != null && task.subtasks_count > 0 && (
        <span className="flex-shrink-0 flex items-center gap-0.5 text-[10px] text-muted-foreground">
          <Layers className="h-2.5 w-2.5" />
          {task.subtasks_count}
        </span>
      )}

      {/* Checklist progress indicator */}
      {task.checklist_total != null && task.checklist_total > 0 && (
        <span
          className={cn(
            'flex-shrink-0 flex items-center gap-1 text-[10px]',
            task.checklist_done === task.checklist_total
              ? 'text-green-600 dark:text-green-500'
              : 'text-muted-foreground'
          )}
          title={`${task.checklist_done}/${task.checklist_total} checklist items done`}
        >
          <CheckSquare className="h-2.5 w-2.5" />
          <span className="tabular-nums">
            {task.checklist_done}/{task.checklist_total}
          </span>
        </span>
      )}

      {/* Last updated indicator - always visible */}
      {task.updated_at && (
        <span
          className="flex-shrink-0 flex items-center gap-0.5 text-[9px] text-muted-foreground/70"
          title={`Updated ${new Date(task.updated_at).toLocaleString()}`}
        >
          <History className="h-2.5 w-2.5" />
          {formatRelativeTime(task.updated_at)}
        </span>
      )}

      {/* Assignee */}
      {task.assignee ? (
        <div className="flex-shrink-0 relative group/assignee">
          <div
            className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 text-primary text-[10px] font-semibold"
          >
            {getInitials(task.assignee.display_name, task.assignee.email)}
          </div>
          {/* Hover tooltip */}
          <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 px-2 py-1 rounded bg-popover border border-border shadow-md text-xs whitespace-nowrap opacity-0 invisible group-hover/assignee:opacity-100 group-hover/assignee:visible transition-opacity z-50">
            <div className="font-medium text-foreground">{getAssigneeDisplayName(task.assignee)}</div>
            <div className="text-muted-foreground text-[10px]">{task.assignee.email}</div>
            {/* Arrow */}
            <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-border" />
            <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-popover -mt-[1px]" />
          </div>
        </div>
      ) : (
        <div className="flex-shrink-0 relative group/assignee">
          <div
            className="flex h-6 w-6 items-center justify-center rounded-full bg-muted/50 border border-dashed border-muted-foreground/30"
          >
            <User className="h-3 w-3 text-muted-foreground/50" />
          </div>
          {/* Hover tooltip */}
          <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 px-2 py-1 rounded bg-popover border border-border shadow-md text-xs whitespace-nowrap opacity-0 invisible group-hover/assignee:opacity-100 group-hover/assignee:visible transition-opacity z-50">
            <div className="text-muted-foreground">Unassigned</div>
            {/* Arrow */}
            <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-border" />
            <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-popover -mt-[1px]" />
          </div>
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
