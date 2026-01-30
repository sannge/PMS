/**
 * TaskList Component
 *
 * Reusable infinite scroll task list component.
 * Features:
 * - IntersectionObserver for auto-loading more tasks
 * - Skeleton loading states
 * - Loading and empty states
 * - Click to view task details
 */

import { useEffect, useRef, useCallback } from 'react'
import { Loader2, CheckCircle2, Archive, AlertCircle } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Task } from '@/hooks/use-queries'
import { TaskCard } from './task-card'

// ============================================================================
// Skeleton Component
// ============================================================================

function TaskCardSkeleton() {
  return (
    <div className="rounded-lg border border-border/50 bg-card p-3 animate-pulse">
      <div className="flex items-start gap-3">
        {/* Task type icon skeleton */}
        <div className="h-5 w-5 rounded bg-muted" />

        <div className="flex-1 space-y-2">
          {/* Title skeleton */}
          <div className="h-4 bg-muted rounded w-3/4" />

          {/* Task key and meta skeleton */}
          <div className="flex items-center gap-2">
            <div className="h-3 bg-muted rounded w-16" />
            <div className="h-3 bg-muted rounded w-12" />
          </div>
        </div>

        {/* Status badge skeleton */}
        <div className="h-6 w-16 bg-muted rounded-full" />
      </div>
    </div>
  )
}

export function TaskListSkeleton({ count = 5 }: { count?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: count }).map((_, i) => (
        <TaskCardSkeleton key={i} />
      ))}
    </div>
  )
}

// ============================================================================
// Types
// ============================================================================

export interface TaskListProps {
  tasks: Task[]
  isLoading: boolean
  isFetchingNextPage: boolean
  hasNextPage: boolean
  fetchNextPage: () => void
  onTaskClick?: (task: Task) => void
  emptyMessage?: string
  emptyIcon?: React.ReactNode
  className?: string
}

// ============================================================================
// Component
// ============================================================================

export function TaskList({
  tasks,
  isLoading,
  isFetchingNextPage,
  hasNextPage,
  fetchNextPage,
  onTaskClick,
  emptyMessage = 'No tasks found',
  emptyIcon,
  className,
}: TaskListProps) {
  const loadMoreRef = useRef<HTMLDivElement>(null)

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

  // Loading state with skeleton
  if (isLoading && tasks.length === 0) {
    return <TaskListSkeleton count={6} />
  }

  // Empty state
  if (!isLoading && tasks.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        {emptyIcon || <CheckCircle2 className="h-12 w-12 text-muted-foreground/40" />}
        <p className="mt-4 text-sm text-muted-foreground">{emptyMessage}</p>
      </div>
    )
  }

  return (
    <div className={cn('space-y-1', className)}>
      {tasks.map((task) => (
        <TaskCard
          key={task.id}
          task={task}
          onClick={onTaskClick}
          variant="compact"
        />
      ))}

      {/* Load more trigger */}
      <div ref={loadMoreRef} className="h-4" />

      {/* Loading more indicator */}
      {isFetchingNextPage && (
        <div className="flex items-center justify-center py-4">
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          <span className="ml-2 text-sm text-muted-foreground">Loading more...</span>
        </div>
      )}
    </div>
  )
}
