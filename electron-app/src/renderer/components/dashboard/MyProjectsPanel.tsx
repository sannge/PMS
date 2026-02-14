import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { cn } from '@/lib/utils'
import { useMyProjects, useMyProjectsCrossApp } from '@/hooks/use-queries'
import type { Project } from '@/hooks/use-queries'
import {
  FolderKanban,
  Calendar,
  ArrowUpRight,
  Loader2,
  Building2,
  Search,
  ChevronUp,
  ChevronDown,
  X,
} from 'lucide-react'

// ============================================================================
// Types
// ============================================================================

type ProjectSortField = 'due_date' | 'name' | 'updated_at'
type SortOrder = 'asc' | 'desc'

interface MyProjectsPanelProps {
  applicationId?: string
  onProjectClick?: (project: Project) => void
  className?: string
}

const PROJECT_SORT_OPTIONS: { value: ProjectSortField; label: string }[] = [
  { value: 'due_date', label: 'Due date' },
  { value: 'name', label: 'Name' },
  { value: 'updated_at', label: 'Updated' },
]

const PROJECT_STATUS_OPTIONS = [
  { value: 'Todo', className: 'bg-slate-500/10 text-slate-600 dark:text-slate-400 hover:bg-slate-500/20 border-slate-500/20' },
  { value: 'In Progress', className: 'bg-blue-500/10 text-blue-600 dark:text-blue-400 hover:bg-blue-500/20 border-blue-500/20' },
  { value: 'Issue', className: 'bg-red-500/10 text-red-600 dark:text-red-400 hover:bg-red-500/20 border-red-500/20' },
  { value: 'Done', className: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-500/20 border-emerald-500/20' },
] as const

// ============================================================================
// Helpers
// ============================================================================

function getDueDateInfo(dueDateStr: string) {
  const dueDate = new Date(dueDateStr + 'T00:00:00')
  const now = new Date()
  now.setHours(0, 0, 0, 0)
  const diffMs = dueDate.getTime() - now.getTime()
  const diffDays = Math.round(diffMs / (1000 * 60 * 60 * 24))

  if (diffDays < 0) {
    return { label: `${Math.abs(diffDays)}d overdue`, className: 'text-red-500' }
  } else if (diffDays === 0) {
    return { label: 'Due today', className: 'text-amber-500' }
  } else if (diffDays <= 3) {
    return { label: `Due in ${diffDays}d`, className: 'text-amber-500' }
  } else {
    return { label: `Due in ${diffDays}d`, className: 'text-muted-foreground' }
  }
}

function getStatusPill(status: string | null) {
  switch (status) {
    case 'Todo':
      return { label: 'Todo', className: 'bg-slate-500/10 text-slate-600 dark:text-slate-400' }
    case 'In Progress':
      return { label: 'In Progress', className: 'bg-blue-500/10 text-blue-600 dark:text-blue-400' }
    case 'Issue':
      return { label: 'Issue', className: 'bg-red-500/10 text-red-600 dark:text-red-400' }
    case 'Done':
      return { label: 'Done', className: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' }
    default:
      return null
  }
}

// ============================================================================
// Skeleton
// ============================================================================

function ProjectCardSkeleton() {
  return (
    <div className="rounded-lg border border-border bg-card/50 p-3.5 animate-pulse">
      <div className="flex items-start justify-between">
        <div className="space-y-2 flex-1">
          <div className="flex items-center gap-2">
            <div className="h-4 w-10 rounded bg-muted" />
            <div className="h-4 w-36 rounded bg-muted" />
          </div>
          <div className="flex items-center gap-3">
            <div className="h-3.5 w-16 rounded bg-muted" />
            <div className="h-3.5 w-14 rounded bg-muted" />
          </div>
        </div>
      </div>
    </div>
  )
}

// ============================================================================
// Component
// ============================================================================

export function MyProjectsPanel({
  applicationId,
  onProjectClick,
  className,
}: MyProjectsPanelProps) {
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState<ProjectSortField>('due_date')
  const [sortOrder, setSortOrder] = useState<SortOrder>('asc')
  const [statusFilter, setStatusFilter] = useState<string | undefined>()
  const [sortDropdownOpen, setSortDropdownOpen] = useState(false)

  const params = useMemo(
    () => ({
      search: search || undefined,
      sortBy,
      sortOrder,
      status: statusFilter,
    }),
    [search, sortBy, sortOrder, statusFilter]
  )

  // Use per-app hook when applicationId is provided, cross-app otherwise
  const perAppQuery = useMyProjects(applicationId || undefined, applicationId ? params : undefined)
  const crossAppQuery = useMyProjectsCrossApp(applicationId ? undefined : params)

  const { data, isLoading, isFetchingNextPage, hasNextPage, fetchNextPage } =
    applicationId ? perAppQuery : crossAppQuery

  const projects = useMemo(
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
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-amber-500/10">
              <FolderKanban className="h-4 w-4 text-amber-500" />
            </div>
            <h3 className="text-sm font-semibold text-foreground tracking-tight">Projects</h3>
            {!isLoading && (
              <span className="rounded-md bg-muted px-1.5 py-0.5 text-[10px] font-semibold tabular-nums text-muted-foreground">
                {projects.length}
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
                {PROJECT_SORT_OPTIONS.find((o) => o.value === sortBy)?.label}
                <ChevronDown className="absolute right-1 top-1/2 -translate-y-1/2 h-2.5 w-2.5 opacity-50" />
              </button>
              {sortDropdownOpen && (
                <>
                  <div className="fixed inset-0 z-40" onClick={() => setSortDropdownOpen(false)} />
                  <div className={cn(
                    'absolute right-0 top-full mt-1 z-50 min-w-[100px]',
                    'rounded-md border border-border bg-popover p-0.5 shadow-md'
                  )}>
                    {PROJECT_SORT_OPTIONS.map((opt) => (
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
          {PROJECT_STATUS_OPTIONS.map((opt) => {
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
                {opt.value}
              </button>
            )
          })}
        </div>
      </div>

      {/* ── Scrollable Content ── */}
      <div className="flex-1 min-h-0 overflow-y-auto -mx-1 px-1">
        {isLoading ? (
          <div className="space-y-2">
            <ProjectCardSkeleton />
            <ProjectCardSkeleton />
            <ProjectCardSkeleton />
          </div>
        ) : projects.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-muted/40 mb-3">
              <FolderKanban className="h-6 w-6 text-muted-foreground/30" />
            </div>
            <p className="text-xs font-medium text-muted-foreground/70">No projects found</p>
            {hasActiveFilters && (
              <p className="mt-1 text-[10px] text-muted-foreground/50">
                Try adjusting your filters
              </p>
            )}
          </div>
        ) : (
          <div className="space-y-1.5">
            {projects.map((project) => {
              const dueDateInfo = getDueDateInfo(project.due_date)
              const statusPill = getStatusPill(project.derived_status)

              return (
                <button
                  key={project.id}
                  onClick={() => onProjectClick?.(project)}
                  className={cn(
                    'group w-full text-left rounded-lg border border-border/50 bg-card/60 p-3',
                    'transition-all duration-150 ease-out',
                    'hover:bg-card hover:border-border hover:shadow-sm',
                    'focus:outline-none focus:ring-1 focus:ring-ring/50'
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0 space-y-1">
                      {/* Title row */}
                      <div className="flex items-center gap-1.5">
                        <span className="flex-shrink-0 rounded bg-muted/80 px-1 py-px text-[10px] font-mono font-semibold text-muted-foreground">
                          {project.key}
                        </span>
                        <span className="text-sm font-medium text-foreground truncate leading-tight">
                          {project.name}
                        </span>
                      </div>

                      {/* Meta row */}
                      <div className="flex items-center gap-2 flex-wrap">
                        {statusPill && (
                          <span
                            className={cn(
                              'rounded-md px-1.5 py-px text-[10px] font-medium',
                              statusPill.className
                            )}
                          >
                            {statusPill.label}
                          </span>
                        )}

                        <span className={cn('flex items-center gap-1 text-[11px]', dueDateInfo.className)}>
                          <Calendar className="h-2.5 w-2.5" />
                          {dueDateInfo.label}
                        </span>

                        <span className="text-[11px] text-muted-foreground/60">
                          {project.tasks_count} task{project.tasks_count !== 1 ? 's' : ''}
                        </span>

                        {project.application_name && (
                          <span className="flex items-center gap-1 text-[11px] text-muted-foreground/50">
                            <Building2 className="h-2.5 w-2.5" />
                            {project.application_name}
                          </span>
                        )}
                      </div>
                    </div>

                    <ArrowUpRight
                      className={cn(
                        'h-3.5 w-3.5 flex-shrink-0 text-muted-foreground/20 mt-0.5',
                        'transition-all duration-150',
                        'group-hover:text-muted-foreground/60'
                      )}
                    />
                  </div>
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
