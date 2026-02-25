/**
 * Overdue and upcoming tasks list for the dashboard.
 */

import { cn } from '@/lib/utils'
import { AlertTriangle, Calendar } from 'lucide-react'
import type { UpcomingTaskItem } from '@/hooks/use-queries'
import { getLocalToday } from '@/lib/time-utils'

interface OverdueTasksListProps {
  overdueTasks: UpcomingTaskItem[]
  upcomingTasks: UpcomingTaskItem[]
  onTaskClick?: (task: UpcomingTaskItem) => void
  className?: string
}

function getPriorityDot(priority: string): string {
  switch (priority) {
    case 'highest': return 'bg-red-500'
    case 'high': return 'bg-orange-500'
    case 'medium': return 'bg-yellow-500'
    case 'low': return 'bg-blue-500'
    case 'lowest': return 'bg-slate-400'
    default: return 'bg-slate-400'
  }
}

function getStatusPill(statusName: string): string {
  switch (statusName) {
    case 'Todo': return 'bg-slate-500/10 text-slate-600 dark:text-slate-400'
    case 'In Progress': return 'bg-blue-500/10 text-blue-600 dark:text-blue-400'
    case 'In Review': return 'bg-violet-500/10 text-violet-600 dark:text-violet-400'
    case 'Issue': return 'bg-red-500/10 text-red-600 dark:text-red-400'
    case 'Done': return 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
    default: return 'bg-slate-500/10 text-slate-500'
  }
}

function getDaysLabel(dateStr: string | null): { label: string; isOverdue: boolean } {
  if (!dateStr) return { label: '', isOverdue: false }
  // Use local time for "today" comparison
  const localToday = getLocalToday() // "YYYY-MM-DD"
  const today = new Date(localToday + 'T00:00:00Z')
  const due = new Date(dateStr + 'T00:00:00Z')
  const diffDays = Math.round((due.getTime() - today.getTime()) / (1000 * 60 * 60 * 24))

  if (diffDays < 0) return { label: `${Math.abs(diffDays)}d overdue`, isOverdue: true }
  if (diffDays === 0) return { label: 'Due today', isOverdue: false }
  if (diffDays === 1) return { label: 'Due tomorrow', isOverdue: false }
  return { label: `Due in ${diffDays}d`, isOverdue: false }
}

function TaskRow({ task, onTaskClick }: { task: UpcomingTaskItem; onTaskClick?: (t: UpcomingTaskItem) => void }) {
  const { label, isOverdue } = getDaysLabel(task.due_date)

  return (
    <button
      aria-label={`Open task ${task.task_key}: ${task.title}`}
      onClick={() => onTaskClick?.(task)}
      className={cn(
        'flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm',
        'transition-colors hover:bg-muted/50',
        'focus:outline-none focus:ring-1 focus:ring-ring'
      )}
    >
      <div
        className={cn('h-2 w-2 flex-shrink-0 rounded-full', getPriorityDot(task.priority))}
        aria-label={`Priority: ${task.priority}`}
        role="img"
      />
      <span className="flex-shrink-0 text-xs font-mono text-muted-foreground">{task.task_key}</span>
      <span className="flex-1 truncate text-foreground">{task.title}</span>
      <span className={cn('flex-shrink-0 rounded-full px-2 py-0.5 text-xs font-medium', getStatusPill(task.status_name))}>
        {task.status_name}
      </span>
      {label && (
        <span className={cn(
          'flex-shrink-0 text-xs font-medium',
          isOverdue ? 'text-red-500' : 'text-muted-foreground'
        )}>
          {label}
        </span>
      )}
    </button>
  )
}

export function OverdueTasksList({ overdueTasks, upcomingTasks, onTaskClick, className }: OverdueTasksListProps): JSX.Element {
  const hasOverdue = overdueTasks.length > 0
  const hasUpcoming = upcomingTasks.length > 0

  if (!hasOverdue && !hasUpcoming) {
    return (
      <div className={cn('rounded-2xl border border-border bg-card p-5', className)}>
        <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
          <Calendar className="h-4 w-4 text-muted-foreground" />
          Upcoming & Overdue
        </h3>
        <div className="flex h-32 items-center justify-center">
          <p className="text-sm text-muted-foreground">No upcoming or overdue tasks</p>
        </div>
      </div>
    )
  }

  return (
    <div className={cn('rounded-2xl border border-border bg-card p-5', className)}>
      <h3 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
        <Calendar className="h-4 w-4 text-muted-foreground" />
        Upcoming & Overdue
        {hasOverdue && (
          <span className="flex items-center gap-1 rounded-full bg-red-500/10 px-2 py-0.5 text-xs font-medium text-red-600 dark:text-red-400">
            <AlertTriangle className="h-3 w-3" />
            {overdueTasks.length}
          </span>
        )}
      </h3>
      <div className="space-y-0.5 max-h-[280px] overflow-y-auto" tabIndex={0} role="region" aria-label="Overdue and upcoming tasks">
        {overdueTasks.map(task => (
          <TaskRow key={`overdue-${task.id}`} task={task} onTaskClick={onTaskClick} />
        ))}
        {hasOverdue && hasUpcoming && (
          <div className="my-2 border-t border-border" />
        )}
        {upcomingTasks.map(task => (
          <TaskRow key={`upcoming-${task.id}`} task={task} onTaskClick={onTaskClick} />
        ))}
      </div>
    </div>
  )
}
