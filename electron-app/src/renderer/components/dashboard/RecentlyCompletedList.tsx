/**
 * Recently completed tasks list for the dashboard.
 */

import { cn } from '@/lib/utils'
import { CheckCircle2 } from 'lucide-react'
import type { UpcomingTaskItem } from '@/hooks/use-queries'

interface RecentlyCompletedListProps {
  tasks: UpcomingTaskItem[]
  onTaskClick?: (task: UpcomingTaskItem) => void
  className?: string
}

export function RecentlyCompletedList({ tasks, onTaskClick, className }: RecentlyCompletedListProps): JSX.Element {
  if (tasks.length === 0) {
    return (
      <div className={cn('rounded-2xl border border-border bg-card p-5', className)}>
        <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4 text-emerald-500" />
          Recently Completed
        </h3>
        <div className="flex h-32 items-center justify-center">
          <p className="text-sm text-muted-foreground">No tasks completed recently</p>
        </div>
      </div>
    )
  }

  return (
    <div className={cn('rounded-2xl border border-border bg-card p-5', className)}>
      <h3 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
        <CheckCircle2 className="h-4 w-4 text-emerald-500" />
        Recently Completed
        <span className="text-xs font-normal text-muted-foreground">Last 7 days</span>
      </h3>
      <div className="space-y-0.5 max-h-[280px] overflow-y-auto" tabIndex={0} role="region" aria-label="Recently completed tasks">
        {tasks.map(task => (
          <button
            key={task.id}
            aria-label={`Open task ${task.task_key}: ${task.title}`}
            onClick={() => onTaskClick?.(task)}
            className={cn(
              'flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm',
              'transition-colors hover:bg-muted/50',
              'focus:outline-none focus:ring-1 focus:ring-ring'
            )}
          >
            <CheckCircle2 className="h-4 w-4 flex-shrink-0 text-emerald-500" />
            <span className="flex-shrink-0 text-xs font-mono text-muted-foreground">{task.task_key}</span>
            <span className="flex-1 truncate text-foreground">{task.title}</span>
            <span className="flex-shrink-0 text-xs text-muted-foreground">
              {task.project_key}
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}
