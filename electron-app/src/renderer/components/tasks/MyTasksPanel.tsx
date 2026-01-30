/**
 * MyTasksPanel Component
 *
 * Application-level view of tasks assigned to the current user.
 * Features:
 * - Three tabs: Pending, Completed (last 7 days), Archived (7+ days old)
 * - Infinite scroll with cursor-based pagination
 * - Task click to open detail view
 */

import { useState, useMemo, useCallback, useEffect } from 'react'
import { ListTodo, CheckCircle2, Archive, Inbox, Search, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  useMyPendingTasks,
  useMyCompletedTasks,
  useMyArchivedTasks,
  Task,
} from '@/hooks/use-queries'
import { TaskList } from './TaskList'
import { ScrollArea } from '@/components/ui/scroll-area'

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

type TabId = 'pending' | 'completed' | 'archived'

interface Tab {
  id: TabId
  label: string
  icon: React.ReactNode
}

export interface MyTasksPanelProps {
  applicationId: string
  onTaskClick?: (task: Task) => void
  className?: string
}

// ============================================================================
// Constants
// ============================================================================

const TABS: Tab[] = [
  { id: 'pending', label: 'Pending', icon: <ListTodo className="h-4 w-4" /> },
  { id: 'completed', label: 'Completed', icon: <CheckCircle2 className="h-4 w-4" /> },
  { id: 'archived', label: 'Archived', icon: <Archive className="h-4 w-4" /> },
]

// ============================================================================
// Component
// ============================================================================

export function MyTasksPanel({
  applicationId,
  onTaskClick,
  className,
}: MyTasksPanelProps) {
  const [activeTab, setActiveTab] = useState<TabId>('pending')
  const [searchInput, setSearchInput] = useState('')
  const debouncedSearch = useDebounce(searchInput, 300)

  // Fetch tasks for each tab with search
  const pendingQuery = useMyPendingTasks(applicationId, debouncedSearch || undefined)
  const completedQuery = useMyCompletedTasks(applicationId, debouncedSearch || undefined)
  const archivedQuery = useMyArchivedTasks(applicationId, debouncedSearch || undefined)

  // Get current query based on active tab
  const currentQuery = useMemo(() => {
    switch (activeTab) {
      case 'pending':
        return pendingQuery
      case 'completed':
        return completedQuery
      case 'archived':
        return archivedQuery
    }
  }, [activeTab, pendingQuery, completedQuery, archivedQuery])

  // Flatten paginated data into task array
  const tasks = useMemo(() => {
    return currentQuery.data?.pages.flatMap((page) => page.items) ?? []
  }, [currentQuery.data])

  // Get task counts for tab badges
  const pendingCount = pendingQuery.data?.pages[0]?.items.length ?? 0
  const completedCount = completedQuery.data?.pages[0]?.items.length ?? 0
  const archivedCount = archivedQuery.data?.pages[0]?.items.length ?? 0

  const getTabCount = useCallback(
    (tabId: TabId): number | undefined => {
      switch (tabId) {
        case 'pending':
          return pendingCount > 0 ? pendingCount : undefined
        case 'completed':
          return completedCount > 0 ? completedCount : undefined
        case 'archived':
          return archivedCount > 0 ? archivedCount : undefined
      }
    },
    [pendingCount, completedCount, archivedCount]
  )

  const getEmptyMessage = useCallback((tabId: TabId): string => {
    if (debouncedSearch) {
      return `No ${tabId} tasks matching "${debouncedSearch}"`
    }
    switch (tabId) {
      case 'pending':
        return "You're all caught up! No pending tasks."
      case 'completed':
        return 'No recently completed tasks.'
      case 'archived':
        return 'No archived tasks.'
    }
  }, [debouncedSearch])

  const getEmptyIcon = useCallback((tabId: TabId) => {
    if (debouncedSearch) {
      return <Search className="h-12 w-12 text-muted-foreground/40" />
    }
    switch (tabId) {
      case 'pending':
        return <Inbox className="h-12 w-12 text-emerald-500/40" />
      case 'completed':
        return <CheckCircle2 className="h-12 w-12 text-muted-foreground/40" />
      case 'archived':
        return <Archive className="h-12 w-12 text-muted-foreground/40" />
    }
  }, [debouncedSearch])

  return (
    <div className={cn('flex h-full flex-col', className)}>
      {/* Header */}
      <div className="border-b px-4 py-3 space-y-3">
        <div>
          <h2 className="text-lg font-semibold">My Tasks</h2>
          <p className="text-sm text-muted-foreground">
            Tasks assigned to you across all projects
          </p>
        </div>
        {/* Search input */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search tasks..."
            className={cn(
              'w-full pl-9 pr-8 py-2 text-sm rounded-md',
              'bg-muted/50 border border-input',
              'placeholder:text-muted-foreground',
              'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1'
            )}
          />
          {searchInput && (
            <button
              onClick={() => setSearchInput('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-1 hover:bg-muted rounded"
              title="Clear search"
            >
              <X className="h-3 w-3 text-muted-foreground" />
            </button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b px-4">
        {TABS.map((tab) => {
          const count = getTabCount(tab.id)
          const isActive = activeTab === tab.id

          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                'flex items-center gap-2 border-b-2 px-4 py-3 text-sm font-medium transition-colors',
                isActive
                  ? 'border-primary text-foreground'
                  : 'border-transparent text-muted-foreground hover:border-muted hover:text-foreground'
              )}
            >
              {tab.icon}
              <span>{tab.label}</span>
              {count !== undefined && (
                <span
                  className={cn(
                    'ml-1 rounded-full px-2 py-0.5 text-xs font-medium',
                    isActive
                      ? 'bg-primary/10 text-primary'
                      : 'bg-muted text-muted-foreground'
                  )}
                >
                  {count > 99 ? '99+' : count}
                </span>
              )}
            </button>
          )
        })}
      </div>

      {/* Task List */}
      <ScrollArea className="flex-1">
        <div className="p-4">
          <TaskList
            tasks={tasks}
            isLoading={currentQuery.isLoading}
            isFetchingNextPage={currentQuery.isFetchingNextPage}
            hasNextPage={currentQuery.hasNextPage ?? false}
            fetchNextPage={currentQuery.fetchNextPage}
            onTaskClick={onTaskClick}
            emptyMessage={getEmptyMessage(activeTab)}
            emptyIcon={getEmptyIcon(activeTab)}
          />
        </div>
      </ScrollArea>
    </div>
  )
}
