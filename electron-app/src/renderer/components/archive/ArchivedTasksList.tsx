/**
 * ArchivedTasksList Component
 *
 * Displays archived tasks for a project with infinite scroll.
 * Features:
 * - Cursor-based pagination with IntersectionObserver
 * - Skeleton loading states
 * - Confirmation dialog before restore
 * - Smooth exit animation when restoring
 * - Task click to view details
 */

import { useMemo, useCallback, useRef, useEffect, useState, memo } from 'react'
import {
  Archive,
  Loader2,
  RotateCcw,
  Inbox,
  Search,
  X,
  CheckCircle2,
  AlertCircle,
  Bug,
  Bookmark,
  Layers,
  Flag,
  Calendar,
  User,
  Undo2,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  useArchivedTasks,
  useUnarchiveTask,
  Task,
  TaskType,
  TaskPriority,
} from '@/hooks/use-queries'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Button } from '@/components/ui/button'

// ============================================================================
// Toast Notification Component (inline, lightweight)
// ============================================================================

interface ToastMessage {
  id: string
  type: 'success' | 'error'
  message: string
}

function ToastNotification({
  toast,
  onDismiss,
}: {
  toast: ToastMessage
  onDismiss: (id: string) => void
}) {
  useEffect(() => {
    const timer = setTimeout(() => {
      onDismiss(toast.id)
    }, 3000)
    return () => clearTimeout(timer)
  }, [toast.id, onDismiss])

  return (
    <div
      className={cn(
        'flex items-center gap-2 px-4 py-3 rounded-lg shadow-lg',
        'animate-in slide-in-from-top-2 fade-in duration-200',
        'border backdrop-blur-sm',
        toast.type === 'success'
          ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400'
          : 'bg-red-500/10 border-red-500/30 text-red-600 dark:text-red-400'
      )}
    >
      {toast.type === 'success' ? (
        <CheckCircle2 className="h-4 w-4 flex-shrink-0" />
      ) : (
        <AlertCircle className="h-4 w-4 flex-shrink-0" />
      )}
      <span className="text-sm font-medium">{toast.message}</span>
      <button
        onClick={() => onDismiss(toast.id)}
        className="ml-2 p-0.5 rounded hover:bg-black/10 dark:hover:bg-white/10"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  )
}

function ToastContainer({
  toasts,
  onDismiss,
}: {
  toasts: ToastMessage[]
  onDismiss: (id: string) => void
}) {
  if (toasts.length === 0) return null

  return (
    <div className="fixed top-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map((toast) => (
        <ToastNotification key={toast.id} toast={toast} onDismiss={onDismiss} />
      ))}
    </div>
  )
}

// ============================================================================
// Restore Confirmation Dialog
// ============================================================================

interface RestoreConfirmDialogProps {
  task: Task | null
  isOpen: boolean
  isRestoring: boolean
  onConfirm: () => void
  onCancel: () => void
}

function RestoreConfirmDialog({
  task,
  isOpen,
  isRestoring,
  onConfirm,
  onCancel,
}: RestoreConfirmDialogProps) {
  // Handle escape key
  useEffect(() => {
    if (!isOpen) return
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !isRestoring) {
        onCancel()
      }
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [isOpen, isRestoring, onCancel])

  if (!isOpen || !task) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-[2px] animate-in fade-in duration-200"
        onClick={isRestoring ? undefined : onCancel}
      />

      {/* Dialog */}
      <div
        className={cn(
          'relative z-10 w-full max-w-sm mx-4',
          'bg-card border border-border/80 rounded-xl shadow-2xl',
          'animate-in fade-in zoom-in-95 slide-in-from-bottom-2 duration-200'
        )}
      >
        {/* Header */}
        <div className="px-5 pt-5 pb-4">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
              <Undo2 className="h-5 w-5 text-primary" />
            </div>
            <div className="flex-1 min-w-0">
              <h3 className="text-base font-semibold text-foreground">
                Restore this task?
              </h3>
              <p className="mt-1 text-sm text-muted-foreground">
                This will move the task back to Done and restart the 7-day archive timer.
              </p>
            </div>
          </div>

          {/* Task preview */}
          <div className="mt-4 p-3 rounded-lg bg-muted/50 border border-border/50">
            <div className="flex items-center gap-2">
              <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                {task.task_key}
              </span>
            </div>
            <p className="mt-1.5 text-sm font-medium text-foreground line-clamp-2">
              {task.title}
            </p>
          </div>
        </div>

        {/* Actions */}
        <div className="px-5 pb-5 flex gap-3">
          <Button
            variant="outline"
            onClick={onCancel}
            disabled={isRestoring}
            className="flex-1 h-9"
          >
            Cancel
          </Button>
          <Button
            onClick={onConfirm}
            disabled={isRestoring}
            className={cn(
              'flex-1 h-9 gap-2',
              'bg-primary hover:bg-primary/90'
            )}
          >
            {isRestoring ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                <span>Restoring...</span>
              </>
            ) : (
              <>
                <RotateCcw className="h-3.5 w-3.5" />
                <span>Restore</span>
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  )
}

// ============================================================================
// Skeleton Component
// ============================================================================

function ArchivedTaskSkeleton() {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-border/50 bg-card px-3 py-2.5 animate-pulse">
      {/* Task type icon skeleton */}
      <div className="h-4 w-4 rounded bg-muted flex-shrink-0" />

      {/* Main content */}
      <div className="flex-1 min-w-0 space-y-1.5">
        {/* Title skeleton */}
        <div className="h-4 bg-muted rounded w-3/4" />

        {/* Meta row skeleton */}
        <div className="flex items-center gap-3">
          <div className="h-4 bg-muted rounded w-16" />
          <div className="h-3 w-3 bg-muted rounded" />
          <div className="h-4 bg-muted rounded w-20" />
        </div>
      </div>

      {/* Assignee skeleton */}
      <div className="h-7 w-7 rounded-full bg-muted flex-shrink-0" />

      {/* Restore button skeleton */}
      <div className="h-8 w-20 bg-muted rounded flex-shrink-0" />
    </div>
  )
}

function ArchivedTasksListSkeleton({ count = 5 }: { count?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: count }).map((_, i) => (
        <ArchivedTaskSkeleton key={i} />
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

export interface ArchivedTasksListProps {
  projectId: string
  onTaskClick?: (task: Task) => void
  onTaskRestored?: (task: Task) => void
  className?: string
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

const PRIORITY_CONFIG: Record<TaskPriority, { color: string; label: string }> = {
  highest: { color: 'text-red-500', label: 'Highest' },
  high: { color: 'text-orange-500', label: 'High' },
  medium: { color: 'text-yellow-500', label: 'Medium' },
  low: { color: 'text-blue-500', label: 'Low' },
  lowest: { color: 'text-slate-400', label: 'Lowest' },
}

function formatCompletedDate(dateString: string): string {
  const date = new Date(dateString)
  if (isNaN(date.getTime())) return 'Completed'

  const now = new Date()
  const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24))

  if (diffDays === 0) return 'Today'
  if (diffDays === 1) return 'Yesterday'
  if (diffDays < 7) return `${diffDays} days ago`
  if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`

  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function getInitials(displayName: string | null, email: string): string {
  if (displayName) {
    const parts = displayName.trim().split(/\s+/)
    if (parts.length >= 2) {
      return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
    }
    return displayName.slice(0, 2).toUpperCase()
  }
  return email.slice(0, 2).toUpperCase()
}

// ============================================================================
// Archived Task Item Component
// ============================================================================

interface ArchivedTaskItemProps {
  task: Task
  onTaskClick?: (task: Task) => void
  onRestore: (task: Task) => void
  isExiting: boolean
  canRestore: boolean
}

const ArchivedTaskItem = memo(function ArchivedTaskItem({
  task,
  onTaskClick,
  onRestore,
  isExiting,
  canRestore,
}: ArchivedTaskItemProps) {
  const priorityConfig = PRIORITY_CONFIG[task.priority]

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (onTaskClick && (e.key === 'Enter' || e.key === ' ')) {
        e.preventDefault()
        onTaskClick(task)
      }
    },
    [onTaskClick, task]
  )

  return (
    <div
      onClick={() => onTaskClick?.(task)}
      onKeyDown={handleKeyDown}
      role={onTaskClick ? 'button' : undefined}
      tabIndex={onTaskClick ? 0 : undefined}
      className={cn(
        'group flex items-center gap-3 rounded-lg border border-border/60 bg-card px-3 py-2.5',
        'transition-all duration-300 ease-out',
        onTaskClick && 'cursor-pointer hover:border-primary/30 hover:bg-accent/30',
        // Exit animation - fade out, slide right, and scale down
        isExiting && [
          'opacity-0 translate-x-4 scale-95',
          'border-green-500/30 bg-green-500/5',
        ]
      )}
    >
      {/* Task Type Icon */}
      <div className="flex-shrink-0">
        {getTaskTypeIcon(task.task_type)}
      </div>

      {/* Main Content */}
      <div className="flex-1 min-w-0 space-y-1">
        {/* Title Row */}
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-foreground truncate">
            {task.title}
          </span>
        </div>

        {/* Meta Row */}
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          {/* Task Key */}
          <span className="font-mono text-[10px] bg-muted/50 px-1.5 py-0.5 rounded">
            {task.task_key}
          </span>

          {/* Priority */}
          <span className={cn('flex items-center gap-1', priorityConfig.color)} title={priorityConfig.label}>
            <Flag className="h-3 w-3" />
          </span>

          {/* Story Points */}
          {task.story_points != null && (
            <span className="flex items-center gap-1" title="Story points">
              <span className="bg-muted px-1.5 py-0.5 rounded text-[10px] font-medium">
                {task.story_points}
              </span>
            </span>
          )}

          {/* Completed Date */}
          {task.completed_at && (
            <span
              className="flex items-center gap-1 text-green-600 dark:text-green-500"
              title={`Completed: ${new Date(task.completed_at).toLocaleString()}`}
            >
              <Calendar className="h-3 w-3" />
              <span>{formatCompletedDate(task.completed_at)}</span>
            </span>
          )}
        </div>
      </div>

      {/* Assignee */}
      {task.assignee ? (
        <div
          className="flex-shrink-0 flex h-7 w-7 items-center justify-center rounded-full bg-primary/10 text-primary text-[10px] font-semibold"
          title={task.assignee.display_name || task.assignee.email}
        >
          {getInitials(task.assignee.display_name, task.assignee.email)}
        </div>
      ) : (
        <div
          className="flex-shrink-0 flex h-7 w-7 items-center justify-center rounded-full bg-muted/50 border border-dashed border-muted-foreground/30"
          title="Unassigned"
        >
          <User className="h-3 w-3 text-muted-foreground/50" />
        </div>
      )}

      {/* Restore Button - Only shown if user has permission */}
      {canRestore && !isExiting && (
        <Button
          variant="outline"
          size="sm"
          onClick={(e) => {
            e.stopPropagation()
            onRestore(task)
          }}
          className={cn(
            'flex-shrink-0 h-8 gap-1.5 text-xs font-medium',
            'border-border/60',
            'hover:bg-primary hover:text-primary-foreground hover:border-primary',
            'transition-all duration-150'
          )}
        >
          <RotateCcw className="h-3 w-3" />
          <span>Restore</span>
        </Button>
      )}
    </div>
  )
})

// ============================================================================
// Main Component
// ============================================================================

export function ArchivedTasksList({
  projectId,
  onTaskClick,
  onTaskRestored,
  className,
}: ArchivedTasksListProps) {
  const loadMoreRef = useRef<HTMLDivElement>(null)
  const searchInputRef = useRef<HTMLInputElement>(null)
  const [searchInput, setSearchInput] = useState('')
  const debouncedSearch = useDebounce(searchInput, 300)
  const [toasts, setToasts] = useState<ToastMessage[]>([])

  // Confirmation dialog state
  const [taskToRestore, setTaskToRestore] = useState<Task | null>(null)
  const [isRestoring, setIsRestoring] = useState(false)

  // Track tasks that are animating out (being restored)
  const [exitingTaskIds, setExitingTaskIds] = useState<Set<string>>(new Set())

  // Track if user is actively searching (input is focused)
  const [isSearchFocused, setIsSearchFocused] = useState(false)

  // Query hooks
  const { data, isLoading, isFetching, isFetchingNextPage, hasNextPage, fetchNextPage } =
    useArchivedTasks(projectId, debouncedSearch || undefined)

  const unarchiveMutation = useUnarchiveTask(projectId)

  // Refocus search input after search completes (only if user was actively searching)
  useEffect(() => {
    if (!isFetching && isSearchFocused && searchInputRef.current) {
      searchInputRef.current.focus()
    }
  }, [isFetching, isSearchFocused])

  // Toast helpers
  const addToast = useCallback(
    (type: 'success' | 'error', message: string) => {
      const id = Math.random().toString(36).substring(7)
      setToasts((prev) => [...prev, { id, type, message }])
    },
    []
  )

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  // Flatten paginated data and get can_restore flag from first page
  const tasks = useMemo(() => {
    return data?.pages.flatMap((page) => page.items) ?? []
  }, [data])

  // Permission flag from backend (check first page for can_restore)
  const canRestore = useMemo(() => {
    return data?.pages[0]?.can_restore ?? false
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

  // Open confirmation dialog
  const handleRestoreClick = useCallback((task: Task) => {
    setTaskToRestore(task)
  }, [])

  // Cancel restore
  const handleCancelRestore = useCallback(() => {
    if (!isRestoring) {
      setTaskToRestore(null)
    }
  }, [isRestoring])

  // Confirm and execute restore with animation
  const handleConfirmRestore = useCallback(async () => {
    if (!taskToRestore) return

    const task = taskToRestore
    setIsRestoring(true)

    try {
      // Start exit animation
      setExitingTaskIds((prev) => new Set(prev).add(task.id))

      // Close dialog after a brief moment
      setTimeout(() => {
        setTaskToRestore(null)
      }, 150)

      // Wait for animation to play
      await new Promise((resolve) => setTimeout(resolve, 300))

      // Execute the actual restore
      const restoredTask = await unarchiveMutation.mutateAsync(task.id)
      addToast('success', `"${task.title}" restored to Done`)

      // Notify parent to add task back to the board
      onTaskRestored?.(restoredTask)
    } catch (err) {
      console.error('Failed to unarchive task:', err)
      addToast(
        'error',
        err instanceof Error ? err.message : 'Failed to restore task'
      )
      // Remove from exiting set on error
      setExitingTaskIds((prev) => {
        const next = new Set(prev)
        next.delete(task.id)
        return next
      })
    } finally {
      setIsRestoring(false)
    }
  }, [taskToRestore, unarchiveMutation, addToast, onTaskRestored])

  // Header component (reused across states)
  const header = (
    <div className="px-4 py-3 border-b space-y-3">
      <div className="flex items-center gap-2">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-muted/80">
          <Archive className="h-4 w-4 text-muted-foreground" />
        </div>
        <div>
          <h3 className="font-semibold text-sm">Archived Tasks</h3>
          <p className="text-xs text-muted-foreground">
            Completed more than 7 days ago
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
          placeholder="Search archived tasks..."
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
  if (isLoading && tasks.length === 0) {
    return (
      <div className={cn('flex flex-col h-full', className)}>
        {/* Header skeleton */}
        <div className="px-4 py-3 border-b space-y-3">
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-lg bg-muted animate-pulse" />
            <div className="space-y-1">
              <div className="h-4 w-28 bg-muted rounded animate-pulse" />
              <div className="h-3 w-40 bg-muted rounded animate-pulse" />
            </div>
          </div>
          <div className="h-10 bg-muted/50 rounded-md animate-pulse" />
        </div>
        {/* Skeleton list */}
        <div className="p-4">
          <ArchivedTasksListSkeleton count={6} />
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
        {debouncedSearch ? 'No matching tasks' : 'No archived tasks'}
      </h3>
      <p className="mt-2 text-center text-sm text-muted-foreground max-w-xs">
        {debouncedSearch
          ? `No archived tasks match "${debouncedSearch}"`
          : 'Tasks in Done status for more than 7 days will appear here.'}
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
  if (!isLoading && tasks.length === 0) {
    return (
      <div className={cn('flex flex-col h-full', className)}>
        {header}
        {emptyStateContent}
        <ToastContainer toasts={toasts} onDismiss={dismissToast} />
      </div>
    )
  }

  return (
    <div className={cn('flex flex-col h-full', className)}>
      {header}

      {/* Task List */}
      <ScrollArea className="flex-1">
        <div className="p-4 space-y-2">
          {tasks.map((task) => (
            <ArchivedTaskItem
              key={task.id}
              task={task}
              onTaskClick={onTaskClick}
              onRestore={handleRestoreClick}
              isExiting={exitingTaskIds.has(task.id)}
              canRestore={canRestore}
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

      {/* Toast notifications */}
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />

      {/* Restore confirmation dialog */}
      <RestoreConfirmDialog
        task={taskToRestore}
        isOpen={taskToRestore !== null}
        isRestoring={isRestoring}
        onConfirm={handleConfirmRestore}
        onCancel={handleCancelRestore}
      />
    </div>
  )
}
