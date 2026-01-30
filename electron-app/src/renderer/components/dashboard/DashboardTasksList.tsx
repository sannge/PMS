import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { cn } from '@/lib/utils'
import { useMyPendingTasks, useMyTasksCrossApp } from '@/hooks/use-queries'
import type { Task, MyTasksParams } from '@/hooks/use-queries'
import {
  ListTodo,
  Calendar,
  Loader2,
  Search,
  ChevronUp,
  ChevronDown,
  X,
} from 'lucide-react'

// ============================================================================
// Types
// ============================================================================

type TaskSortField = 'due_date' | 'title' | 'updated_at'
type SortOrder = 'asc' | 'desc'

interface DashboardTasksListProps {
  applicationId?: string
  onTaskClick?: (task: Task) => void
  className?: string
}

const TASK_SORT_OPTIONS: { value: TaskSortField; label: string }[] = [
  { value: 'updated_at', label: 'Updated' },
  { value: 'due_date', label: 'Due date' },
  { value: 'title', label: 'Title' },
]

const TASK_STATUS_OPTIONS = [
  { value: 'todo', label: 'Todo', className: 'bg-slate-500/10 text-slate-600 dark:text-slate-400 hover:bg-slate-500/20 border-slate-500/20' },
  { value: 'in_progress', label: 'In Progress', className: 'bg-blue-500/10 text-blue-600 dark:text-blue-400 hover:bg-blue-500/20 border-blue-500/20' },
  { value: 'in_review', label: 'Review', className: 'bg-violet-500/10 text-violet-600 dark:text-violet-400 hover:bg-violet-500/20 border-violet-500/20' },
  { value: 'issue', label: 'Issue', className: 'bg-red-500/10 text-red-600 dark:text-red-400 hover:bg-red-500/20 border-red-500/20' },
  { value: 'done', label: 'Done', className: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-500/20 border-emerald-500/20' },
] as const

// ============================================================================
// Helpers
// ============================================================================

function getStatusConfig(status: string) {
  switch (status) {
    case 'todo':
      return { label: 'Todo', className: 'bg-slate-500/10 text-slate-600 dark:text-slate-400' }
    case 'in_progress':
      return { label: 'In Progress', className: 'bg-blue-500/10 text-blue-600 dark:text-blue-400' }
    case 'in_review':
      return { label: 'In Review', className: 'bg-violet-500/10 text-violet-600 dark:text-violet-400' }
    case 'issue':
      return { label: 'Issue', className: 'bg-red-500/10 text-red-600 dark:text-red-400' }
    case 'done':
      return { label: 'Done', className: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' }
    default:
      return { label: status, className: 'bg-slate-500/10 text-slate-500' }
  }
}

function getPriorityDot(priority: string) {
  switch (priority) {
    case 'highest':
      return 'bg-red-500'
    case 'high':
      return 'bg-orange-500'
    case 'medium':
      return 'bg-yellow-500'
    case 'low':
      return 'bg-blue-500'
    case 'lowest':
      return 'bg-slate-400'
    default:
      return 'bg-slate-400'
  }
}

function getDueDateInfo(dueDateStr: string | null) {
  if (!dueDateStr) return null
  const dueDate = new Date(dueDateStr + 'T00:00:00')
  const now = new Date()
  now.setHours(0, 0, 0, 0)
  const diffMs = dueDate.getTime() - now.getTime()
  const diffDays = Math.round(diffMs / (1000 * 60 * 60 * 24))

  if (diffDays < 0) {
    return { label: `${Math.abs(diffDays)}d overdue`, className: 'text-red-500' }
  } else if (diffDays === 0) {
    return { label: 'Today', className: 'text-amber-500' }
  } else if (diffDays <= 3) {
    return { label: `${diffDays}d`, className: 'text-amber-500' }
  } else {
    return { label: `${diffDays}d`, className: 'text-muted-foreground' }
  }
}

// ============================================================================
// Skeleton
// ============================================================================

function TaskRowSkeleton() {
  return (
    <div className="flex items-center gap-3 px-3 py-2 animate-pulse">
      <div className="h-2 w-2 rounded-full bg-muted" />
      <div className="h-3.5 w-14 rounded bg-muted" />
      <div className="h-3.5 w-40 rounded bg-muted flex-1" />
      <div className="h-4 w-16 rounded-full bg-muted" />
    </div>
  )
}

// ============================================================================
// Component
// ============================================================================

export function DashboardTasksList({
  applicationId,
  onTaskClick,
  className,
}: DashboardTasksListProps) {
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState<TaskSortField>('updated_at')
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc')
  const [statusFilter, setStatusFilter] = useState<string | undefined>()
  const [sortDropdownOpen, setSortDropdownOpen] = useState(false)

  const taskParams = useMemo<MyTasksParams>(
    () => ({
      search: search || undefined,
      sortBy,
      sortOrder,
      status: statusFilter,
    }),
    [search, sortBy, sortOrder, statusFilter]
  )

  // Use per-app hook when applicationId is provided, cross-app otherwise
  const perAppQuery = useMyPendingTasks(applicationId || undefined, applicationId ? search : undefined)
  const crossAppQuery = useMyTasksCrossApp(applicationId ? undefined : taskParams)

  const { data, isLoading, isFetchingNextPage, hasNextPage, fetchNextPage } =
    applicationId ? perAppQuery : crossAppQuery

  const tasks = useMemo(
    () => data?.pages.flatMap((p) => p.items) ?? [],
    [data]
  )

  // Infinite scroll observer
  const loadMoreRef = useRef<HTMLDivElement>(null)

  const handleObserver = useCallback(
    (entries: IntersectionObserverEntry[]) => {
      const [target] = entries
      if (target.isIntersecting && hasNextPage && !isFetchingNextPage) {
        fetchNextPage()
      }
    },
    [hasNextPage, isFetchingNextPage, fetchNextPage]
  )

  useEffect(() => {
    const el = loadMoreRef.current
    if (!el) return

    const observer = new IntersectionObserver(handleObserver, {
      rootMargin: '100px',
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [handleObserver])

  const hasActiveFilters = !!statusFilter || !!search

  return (
    <div className={cn('flex flex-col h-full', className)}>
      {/* ── Panel Header ── */}
      <div className="flex-shrink-0 pb-3 space-y-2.5">
        {/* Title row */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-violet-500/10">
              <ListTodo className="h-4 w-4 text-violet-500" />
            </div>
            <h3 className="text-sm font-semibold text-foreground tracking-tight">My Tasks</h3>
            {!isLoading && (
              <span className="rounded-md bg-muted px-1.5 py-0.5 text-[10px] font-semibold tabular-nums text-muted-foreground">
                {tasks.length}
              </span>
            )}
          </div>
          {hasActiveFilters && (
            <button
              onClick={() => { setSearch(''); setStatusFilter(undefined) }}
              className="text-[10px] font-medium text-muted-foreground hover:text-foreground transition-colors"
            >
              Clear
            </button>
          )}
        </div>

        {/* Search + Sort row */}
        <div className="flex items-center gap-1.5">
          <div className="relative flex-1 min-w-0">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground/60" />
            <input
              type="text"
              placeholder="Search..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className={cn(
                'w-full rounded-md border border-border/60 bg-muted/30 pl-7 pr-6 py-1',
                'text-xs placeholder:text-muted-foreground/50',
                'focus:outline-none focus:ring-1 focus:ring-ring/50 focus:border-ring/30 focus:bg-background',
                'transition-all duration-150'
              )}
            />
            {search && (
              <button
                onClick={() => setSearch('')}
                className="absolute right-1.5 top-1/2 -translate-y-1/2 p-0.5 rounded text-muted-foreground/50 hover:text-foreground"
              >
                <X className="h-3 w-3" />
              </button>
            )}
          </div>

          {/* Sort control */}
          <div className="flex items-center">
            <div className="relative">
              <button
                onClick={() => setSortDropdownOpen((o) => !o)}
                className={cn(
                  'h-[26px] rounded-l-md border border-border/60 bg-muted/30 pl-2 pr-5',
                  'text-[10px] font-medium text-muted-foreground',
                  'hover:text-foreground hover:bg-muted/50',
                  'focus:outline-none focus:ring-1 focus:ring-ring/50',
                  'cursor-pointer transition-colors duration-150'
                )}
                title="Sort by"
              >
                {TASK_SORT_OPTIONS.find((o) => o.value === sortBy)?.label}
                <ChevronDown className="absolute right-1 top-1/2 -translate-y-1/2 h-2.5 w-2.5 opacity-50" />
              </button>
              {sortDropdownOpen && (
                <>
                  <div className="fixed inset-0 z-40" onClick={() => setSortDropdownOpen(false)} />
                  <div className={cn(
                    'absolute right-0 top-full mt-1 z-50 min-w-[100px]',
                    'rounded-md border border-border bg-popover p-0.5 shadow-md'
                  )}>
                    {TASK_SORT_OPTIONS.map((opt) => (
                      <button
                        key={opt.value}
                        onClick={() => { setSortBy(opt.value); setSortDropdownOpen(false) }}
                        className={cn(
                          'w-full text-left rounded-sm px-2 py-1 text-[11px]',
                          'transition-colors duration-100',
                          opt.value === sortBy
                            ? 'bg-accent text-accent-foreground font-medium'
                            : 'text-popover-foreground hover:bg-accent/50'
                        )}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
            <button
              onClick={() => setSortOrder((o) => o === 'asc' ? 'desc' : 'asc')}
              className={cn(
                'h-[26px] w-[26px] flex items-center justify-center',
                'rounded-r-md border border-l-0 border-border/60 bg-muted/30',
                'text-muted-foreground hover:text-foreground hover:bg-muted/50',
                'transition-colors duration-150'
              )}
              title={sortOrder === 'asc' ? 'Ascending' : 'Descending'}
            >
              {sortOrder === 'asc' ? (
                <ChevronUp className="h-3 w-3" />
              ) : (
                <ChevronDown className="h-3 w-3" />
              )}
            </button>
          </div>
        </div>

        {/* Status filter chips */}
        <div className="flex items-center gap-1">
          {TASK_STATUS_OPTIONS.map((opt) => {
            const isActive = statusFilter === opt.value
            return (
              <button
                key={opt.value}
                onClick={() => setStatusFilter(isActive ? undefined : opt.value)}
                className={cn(
                  'rounded-md px-2 py-0.5 text-[10px] font-medium transition-all duration-150',
                  'border',
                  isActive
                    ? cn(opt.className, 'border-current/20 shadow-sm')
                    : 'border-transparent text-muted-foreground/60 hover:text-muted-foreground hover:bg-muted/50'
                )}
              >
                {opt.label}
              </button>
            )
          })}
        </div>
      </div>

      {/* ── Scrollable Content ── */}
      <div className="flex-1 min-h-0 overflow-y-auto -mx-1 px-1">
        {isLoading ? (
          <div className="rounded-xl border border-border/50 bg-card/40 overflow-hidden">
            <TaskRowSkeleton />
            <TaskRowSkeleton />
            <TaskRowSkeleton />
            <TaskRowSkeleton />
            <TaskRowSkeleton />
          </div>
        ) : tasks.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-muted/40 mb-3">
              <ListTodo className="h-6 w-6 text-muted-foreground/30" />
            </div>
            <p className="text-xs font-medium text-muted-foreground/70">No tasks found</p>
            {hasActiveFilters && (
              <p className="mt-1 text-[10px] text-muted-foreground/50">
                Try adjusting your filters
              </p>
            )}
          </div>
        ) : (
          <div className="rounded-xl border border-border/50 bg-card/40 overflow-hidden divide-y divide-border/30">
            {tasks.map((task) => {
              const statusConfig = getStatusConfig(task.status)
              const priorityDot = getPriorityDot(task.priority)
              const dueDateInfo = task.due_date ? getDueDateInfo(task.due_date) : null

              return (
                <button
                  key={task.id}
                  onClick={() => onTaskClick?.(task)}
                  className={cn(
                    'group w-full text-left flex items-center gap-2.5 px-3 py-2',
                    'transition-colors duration-100',
                    'hover:bg-accent/5',
                    'focus:outline-none focus:bg-accent/5'
                  )}
                >
                  {/* Priority dot */}
                  <div className={cn('h-1.5 w-1.5 rounded-full flex-shrink-0', priorityDot)} />

                  {/* Task key */}
                  <span className="flex-shrink-0 text-[10px] font-mono font-medium text-muted-foreground/60">
                    {task.task_key}
                  </span>

                  {/* Title */}
                  <span className="flex-1 text-xs text-foreground truncate group-hover:text-foreground/80 transition-colors">
                    {task.title}
                  </span>

                  {/* Status pill */}
                  <span
                    className={cn(
                      'flex-shrink-0 rounded-md px-1.5 py-px text-[10px] font-medium',
                      statusConfig.className
                    )}
                  >
                    {statusConfig.label}
                  </span>

                  {/* Due date */}
                  {dueDateInfo && (
                    <span className={cn('flex items-center gap-1 text-[10px] flex-shrink-0', dueDateInfo.className)}>
                      <Calendar className="h-2.5 w-2.5" />
                      {dueDateInfo.label}
                    </span>
                  )}
                </button>
              )
            })}

            {/* Infinite scroll sentinel */}
            <div ref={loadMoreRef} className="h-1" />
            {isFetchingNextPage && (
              <div className="flex items-center justify-center py-3">
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground/40" />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
