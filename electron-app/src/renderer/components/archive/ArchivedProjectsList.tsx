/**
 * ArchivedProjectsList Component
 *
 * Displays archived projects for an application with infinite scroll.
 * Features:
 * - Cursor-based pagination with IntersectionObserver
 * - Skeleton loading states
 * - Project click to navigate (where users can add tasks or restore archived tasks)
 *
 * Note: Projects are automatically restored when a task is added or an archived
 * task is restored within the project.
 */

import { useMemo, useCallback, useRef, useEffect, useState, memo } from 'react'
import {
  Archive,
  Loader2,
  Inbox,
  Search,
  X,
  FolderKanban,
  Calendar,
  ListTodo,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  useArchivedProjects,
  Project,
} from '@/hooks/use-queries'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Button } from '@/components/ui/button'

// ============================================================================
// Skeleton Component
// ============================================================================

function ArchivedProjectSkeleton() {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-border/50 bg-card px-3 py-2.5 animate-pulse">
      {/* Project icon skeleton */}
      <div className="h-8 w-8 rounded-lg bg-muted flex-shrink-0" />

      {/* Main content */}
      <div className="flex-1 min-w-0 space-y-1.5">
        {/* Name skeleton */}
        <div className="h-4 bg-muted rounded w-3/4" />

        {/* Meta row skeleton */}
        <div className="flex items-center gap-3">
          <div className="h-4 bg-muted rounded w-12" />
          <div className="h-3 w-3 bg-muted rounded" />
          <div className="h-4 bg-muted rounded w-16" />
        </div>
      </div>
    </div>
  )
}

function ArchivedProjectsListSkeleton({ count = 5 }: { count?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: count }).map((_, i) => (
        <ArchivedProjectSkeleton key={i} />
      ))}
    </div>
  )
}

// ============================================================================
// Hooks
// ============================================================================

/**
 * Simple debounce hook for search input
 */
function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value)

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedValue(value)
    }, delay)

    return () => clearTimeout(timer)
  }, [value, delay])

  return debouncedValue
}

// ============================================================================
// Types
// ============================================================================

export interface ArchivedProjectsListProps {
  applicationId: string
  onProjectClick?: (project: Project) => void
  className?: string
}

// ============================================================================
// Helper Functions
// ============================================================================

function formatArchivedDate(dateString: string): string {
  // Backend sends UTC dates without timezone indicator, so append 'Z' if missing
  const utcDateString = dateString.endsWith('Z') || dateString.includes('+') || dateString.includes('-', 10)
    ? dateString
    : dateString + 'Z'

  const date = new Date(utcDateString)
  if (isNaN(date.getTime())) return 'Archived'

  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

  // Handle edge case where date might be slightly in the future due to clock skew
  if (diffDays < 0) return 'Just now'
  if (diffDays === 0) return 'Today'
  if (diffDays === 1) return 'Yesterday'
  if (diffDays < 7) return `${diffDays} days ago`
  if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`

  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

// ============================================================================
// Archived Project Item Component
// ============================================================================

interface ArchivedProjectItemProps {
  project: Project
  onProjectClick?: (project: Project) => void
}

const ArchivedProjectItem = memo(function ArchivedProjectItem({
  project,
  onProjectClick,
}: ArchivedProjectItemProps) {
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (onProjectClick && (e.key === 'Enter' || e.key === ' ')) {
        e.preventDefault()
        onProjectClick(project)
      }
    },
    [onProjectClick, project]
  )

  return (
    <div
      onClick={() => onProjectClick?.(project)}
      onKeyDown={handleKeyDown}
      role={onProjectClick ? 'button' : undefined}
      tabIndex={onProjectClick ? 0 : undefined}
      className={cn(
        'group flex items-center gap-3 rounded-lg border border-border/60 bg-card px-3 py-2.5',
        'transition-all duration-200 ease-out',
        onProjectClick && 'cursor-pointer hover:border-primary/30 hover:bg-accent/30'
      )}
    >
      {/* Project Icon */}
      <div className="flex-shrink-0 flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10">
        <FolderKanban className="h-4 w-4 text-primary" />
      </div>

      {/* Main Content */}
      <div className="flex-1 min-w-0 space-y-1">
        {/* Name Row */}
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-foreground truncate">
            {project.name}
          </span>
        </div>

        {/* Meta Row */}
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          {/* Project Key */}
          <span className="font-mono text-[10px] bg-muted/50 px-1.5 py-0.5 rounded">
            {project.key}
          </span>

          {/* Tasks Count */}
          <span className="flex items-center gap-1" title="Tasks">
            <ListTodo className="h-3 w-3" />
            <span>{project.tasks_count}</span>
          </span>

          {/* Archived Date */}
          {project.archived_at && (
            <span
              className="flex items-center gap-1 text-amber-600 dark:text-amber-500"
              title={`Archived: ${new Date(project.archived_at).toLocaleString()}`}
            >
              <Calendar className="h-3 w-3" />
              <span>{formatArchivedDate(project.archived_at)}</span>
            </span>
          )}
        </div>
      </div>

      {/* Hint text for how to restore */}
      {onProjectClick && (
        <span className="text-[10px] text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity">
          Click to view
        </span>
      )}
    </div>
  )
})

// ============================================================================
// Main Component
// ============================================================================

export function ArchivedProjectsList({
  applicationId,
  onProjectClick,
  className,
}: ArchivedProjectsListProps) {
  const loadMoreRef = useRef<HTMLDivElement>(null)
  const searchInputRef = useRef<HTMLInputElement>(null)
  const [searchInput, setSearchInput] = useState('')
  const debouncedSearch = useDebounce(searchInput, 300)

  // Track if user is actively searching (input is focused)
  const [isSearchFocused, setIsSearchFocused] = useState(false)

  // Query hooks
  const { data, isLoading, isFetching, isFetchingNextPage, hasNextPage, fetchNextPage } =
    useArchivedProjects(applicationId, debouncedSearch || undefined)

  // Refocus search input after search completes (only if user was actively searching)
  useEffect(() => {
    if (!isFetching && isSearchFocused && searchInputRef.current) {
      searchInputRef.current.focus()
    }
  }, [isFetching, isSearchFocused])

  // Flatten paginated data
  const projects = useMemo(() => {
    return data?.pages.flatMap((page) => page.items) ?? []
  }, [data])

  // IntersectionObserver for infinite scroll
  const handleObserver = useCallback(
    (entries: IntersectionObserverEntry[]) => {
      const target = entries[0]
      if (target.isIntersecting && hasNextPage && !isFetchingNextPage) {
        fetchNextPage()
      }
    },
    [hasNextPage, isFetchingNextPage, fetchNextPage]
  )

  useEffect(() => {
    const element = loadMoreRef.current
    if (!element) return

    const observer = new IntersectionObserver(handleObserver, {
      threshold: 0.1,
      rootMargin: '100px',
    })

    observer.observe(element)
    return () => observer.disconnect()
  }, [handleObserver])

  // Header component (reused across states)
  const header = (
    <div className="px-4 py-3 border-b space-y-3">
      <div className="flex items-center gap-2">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-muted/80">
          <Archive className="h-4 w-4 text-muted-foreground" />
        </div>
        <div>
          <h3 className="font-semibold text-sm">Archived Projects</h3>
          <p className="text-xs text-muted-foreground">
            Add a task or restore an archived task to bring a project back
          </p>
        </div>
      </div>
      {/* Search input */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <input
          ref={searchInputRef}
          type="text"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          onFocus={() => setIsSearchFocused(true)}
          onBlur={() => setIsSearchFocused(false)}
          placeholder="Search archived projects..."
          className={cn(
            'w-full pl-9 pr-8 py-2 text-sm rounded-md',
            'bg-muted/50 border border-input',
            'placeholder:text-muted-foreground',
            'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1'
          )}
        />
        {searchInput && (
          <button
            onClick={() => {
              setSearchInput('')
              searchInputRef.current?.focus()
            }}
            className="absolute right-2 top-1/2 -translate-y-1/2 p-1 hover:bg-muted rounded"
            title="Clear search"
          >
            <X className="h-3 w-3 text-muted-foreground" />
          </button>
        )}
      </div>
    </div>
  )

  // Loading state with skeleton
  if (isLoading && projects.length === 0) {
    return (
      <div className={cn('flex flex-col h-full', className)}>
        {/* Header skeleton */}
        <div className="px-4 py-3 border-b space-y-3">
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-lg bg-muted animate-pulse" />
            <div className="space-y-1">
              <div className="h-4 w-32 bg-muted rounded animate-pulse" />
              <div className="h-3 w-44 bg-muted rounded animate-pulse" />
            </div>
          </div>
          <div className="h-10 bg-muted/50 rounded-md animate-pulse" />
        </div>
        {/* Skeleton list */}
        <div className="p-4">
          <ArchivedProjectsListSkeleton count={6} />
        </div>
      </div>
    )
  }

  // Empty state (with search context)
  const emptyStateContent = (
    <div className="flex flex-col items-center justify-center py-12 px-4">
      <div className="flex h-14 w-14 items-center justify-center rounded-full bg-muted/80">
        {debouncedSearch ? (
          <Search className="h-6 w-6 text-muted-foreground" />
        ) : (
          <Inbox className="h-6 w-6 text-muted-foreground" />
        )}
      </div>
      <h3 className="mt-4 text-base font-semibold text-foreground">
        {debouncedSearch ? 'No matching projects' : 'No archived projects'}
      </h3>
      <p className="mt-2 text-center text-sm text-muted-foreground max-w-xs">
        {debouncedSearch
          ? `No archived projects match "${debouncedSearch}"`
          : 'Projects with all tasks archived will appear here.'}
      </p>
      {debouncedSearch && (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setSearchInput('')}
          className="mt-4"
        >
          Clear search
        </Button>
      )}
    </div>
  )

  // Empty state
  if (!isLoading && projects.length === 0) {
    return (
      <div className={cn('flex flex-col h-full', className)}>
        {header}
        {emptyStateContent}
      </div>
    )
  }

  return (
    <div className={cn('flex flex-col h-full', className)}>
      {header}

      {/* Project List */}
      <ScrollArea className="flex-1">
        <div className="p-4 space-y-2">
          {projects.map((project) => (
            <ArchivedProjectItem
              key={project.id}
              project={project}
              onProjectClick={onProjectClick}
            />
          ))}

          {/* Load more trigger */}
          <div ref={loadMoreRef} className="h-4" />

          {/* Loading more indicator */}
          {isFetchingNextPage && (
            <div className="flex items-center justify-center py-4">
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              <span className="ml-2 text-sm text-muted-foreground">
                Loading more...
              </span>
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  )
}
