/**
 * KanbanBoard Component
 *
 * Enhanced Kanban board with @dnd-kit for smooth drag-and-drop.
 * Supports cross-column movement and within-column reordering.
 *
 * Features:
 * - 5 status columns (To Do, In Progress, In Review, Done, Blocked)
 * - Smooth drag animations with DragOverlay
 * - Within-column reordering
 * - Optimistic UI updates with rollback
 * - Real-time WebSocket sync
 * - Keyboard accessibility
 */

import { useState, useCallback, useEffect, useMemo, useRef } from 'react'
import {
  DndContext,
  DragOverlay,
  closestCenter,
  pointerWithin,
  rectIntersection,
  type CollisionDetection,
} from '@dnd-kit/core'
import { cn } from '@/lib/utils'
import { useAuthStore, getAuthHeaders } from '@/stores/auth-store'
import { useMoveTask, useArchivedTasksCount, type Task, type TaskStatusValue as TaskStatus } from '@/hooks/use-queries'
import {
  LayoutGrid,
  Plus,
  AlertCircle,
  Wifi,
  WifiOff,
  Eye,
  Archive,
  Columns,
} from 'lucide-react'
import { ProgressBar } from '@/components/ui/skeleton'
import {
  useTaskUpdates,
  useTaskMoved,
  useWebSocket,
  type TaskUpdateEventData,
  type TaskMovedEventData,
} from '@/hooks/use-websocket'
import { useDragAndDrop } from '@/hooks/use-drag-and-drop'
import { DroppableColumn, DEFAULT_COLUMNS } from './DroppableColumn'
import { TaskCard } from '../tasks/task-card'
import { ArchivedTasksList } from '../archive/ArchivedTasksList'

// ============================================================================
// Types
// ============================================================================

export interface KanbanBoardProps {
  /**
   * Project ID to display tasks for
   */
  projectId: string
  /**
   * Project key for task keys display
   */
  projectKey: string
  /**
   * Callback when a task is clicked
   */
  onTaskClick?: (task: Task) => void
  /**
   * Callback when add task is clicked
   */
  onAddTask?: (status?: TaskStatus) => void
  /**
   * Callback when task status changes via drag-drop
   */
  onTaskStatusChange?: (task: Task, newStatus: TaskStatus) => void
  /**
   * Additional CSS classes
   */
  className?: string
  /**
   * Whether to enable real-time updates
   */
  enableRealtime?: boolean
  /**
   * Callback to receive the refresh function
   */
  onRefresh?: (refreshFn: () => void) => void
  /**
   * Whether the current user can edit tasks (drag-and-drop)
   * When false, tasks are view-only and cannot be dragged
   */
  canEdit?: boolean
}

// ============================================================================
// Custom Collision Detection
// ============================================================================

/**
 * Custom collision detection that prefers columns over tasks when dragging
 */
const customCollisionDetection: CollisionDetection = (args) => {
  // First, use pointerWithin for column detection
  const pointerCollisions = pointerWithin(args)

  // If we're over a column, prefer that
  const columnCollision = pointerCollisions.find(
    (c) =>
      typeof c.id === 'string' &&
      ['todo', 'in_progress', 'in_review', 'issue', 'done'].includes(c.id)
  )

  if (columnCollision) {
    return [columnCollision]
  }

  // Fall back to rectIntersection for more precise task-to-task detection
  const rectCollisions = rectIntersection(args)
  if (rectCollisions.length > 0) {
    return rectCollisions
  }

  // Finally, try closestCenter as a fallback
  return closestCenter(args)
}

// ============================================================================
// Component
// ============================================================================

export function KanbanBoard({
  projectId,
  projectKey: _projectKey,
  onTaskClick,
  onAddTask,
  onTaskStatusChange,
  className,
  enableRealtime = true,
  onRefresh,
  canEdit = true,
}: KanbanBoardProps): JSX.Element {
  // State
  const [tasks, setTasks] = useState<Task[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [realtimeNotice, setRealtimeNotice] = useState<string | null>(null)
  const [showArchive, setShowArchive] = useState(false)

  // Ref to always have access to latest tasks (avoids stale closure issues)
  const tasksRef = useRef<Task[]>([])
  useEffect(() => {
    tasksRef.current = tasks
  }, [tasks])

  // Auth
  const token = useAuthStore((state) => state.token)

  // Task move mutation
  const moveTaskMutation = useMoveTask(projectId)
  const isMoving = moveTaskMutation.isPending

  // Archived tasks count for tab badge
  const { data: archivedCount } = useArchivedTasksCount(projectId)

  // WebSocket status
  const { status } = useWebSocket()

  // ============================================================================
  // Task Move Handler
  // ============================================================================

  const handleTaskMove = useCallback(
    async (
      taskId: string,
      targetStatus: TaskStatus,
      beforeTaskId: string | null,
      afterTaskId: string | null
    ): Promise<boolean> => {
      // Use ref to get latest task data (avoids stale closure issues)
      const currentTasks = tasksRef.current
      const task = currentTasks.find((t) => t.id === taskId)
      if (!task) {
        return false
      }

      // Skip if already at target status and no reordering needed
      if (task.status === targetStatus && !beforeTaskId && !afterTaskId) {
        return true
      }

      // Optimistic update
      const originalTasks = [...currentTasks]
      const now = new Date().toISOString()
      setTasks((prevTasks) =>
        prevTasks.map((t) => {
          if (t.id !== taskId) return t
          // Set completed_at when moving to done, clear when moving away
          const completed_at = targetStatus === 'done'
            ? (t.completed_at || now) // Keep existing or set new
            : (t.status === 'done' ? null : t.completed_at) // Clear if was done
          return { ...t, status: targetStatus, completed_at }
        })
      )

      // Notify callback
      if (onTaskStatusChange && task.status !== targetStatus) {
        onTaskStatusChange(task, targetStatus)
      }

      try {
        // Make API call using TanStack Query mutation
        const result = await moveTaskMutation.mutateAsync({
          taskId,
          targetStatus,
          beforeTaskId: beforeTaskId || undefined,
          afterTaskId: afterTaskId || undefined,
        })

        // Update local state with the returned task (includes new row_version)
        setTasks((prevTasks) =>
          prevTasks.map((t) => (t.id === taskId ? result : t))
        )

        return true
      } catch (err) {
        // Revert on failure and show error notice
        setTasks(originalTasks)
        const errorMessage = err instanceof Error ? err.message : 'Failed to move task'
        setRealtimeNotice(errorMessage)
        setTimeout(() => setRealtimeNotice(null), 5000)
        return false
      }
    },
    [moveTaskMutation, onTaskStatusChange]
  )

  // ============================================================================
  // Drag and Drop Hook
  // ============================================================================

  const {
    sensors,
    activeTask,
    activeId: _activeId,
    overColumnId,
    handleDragStart,
    handleDragEnd,
    handleDragOver,
    handleDragCancel,
    isDragging: _isDragging,
  } = useDragAndDrop({
    tasks,
    onTaskMove: handleTaskMove,
    disabled: isLoading || !canEdit,
  })

  // ============================================================================
  // WebSocket Handler
  // ============================================================================

  const handleTaskUpdate = useCallback(
    (data: TaskUpdateEventData) => {
      if (data.project_id !== projectId) return

      setTasks((currentTasks) => {
        if (data.action === 'created' && data.task) {
          const exists = currentTasks.some((t) => t.id === data.task_id)
          if (!exists) {
            setRealtimeNotice('New task added')
            setTimeout(() => setRealtimeNotice(null), 3000)
            return [...currentTasks, data.task as unknown as Task]
          }
          return currentTasks
        } else if (data.action === 'updated' && data.task) {
          const index = currentTasks.findIndex((t) => t.id === data.task_id)
          if (index !== -1) {
            setRealtimeNotice('Task updated')
            setTimeout(() => setRealtimeNotice(null), 3000)
            const newTasks = [...currentTasks]
            newTasks[index] = data.task as unknown as Task
            return newTasks
          }
          return currentTasks
        } else if (data.action === 'deleted') {
          const index = currentTasks.findIndex((t) => t.id === data.task_id)
          if (index !== -1) {
            setRealtimeNotice('Task removed')
            setTimeout(() => setRealtimeNotice(null), 3000)
            return currentTasks.filter((t) => t.id !== data.task_id)
          }
          return currentTasks
        } else if (data.action === 'status_changed' && data.task) {
          const index = currentTasks.findIndex((t) => t.id === data.task_id)
          if (index !== -1) {
            setRealtimeNotice('Task status changed')
            setTimeout(() => setRealtimeNotice(null), 3000)
            const newTasks = [...currentTasks]
            newTasks[index] = data.task as unknown as Task
            return newTasks
          }
          return currentTasks
        }
        return currentTasks
      })
    },
    [projectId]
  )

  // Subscribe to task updates
  useTaskUpdates(enableRealtime ? projectId : null, handleTaskUpdate)

  // ============================================================================
  // WebSocket Handler for Task Moved (drag-drop by other users)
  // ============================================================================

  const handleTaskMoved = useCallback(
    (data: TaskMovedEventData) => {
      console.log('[KanbanBoard] handleTaskMoved called:', data)
      if (data.project_id !== projectId) {
        console.log('[KanbanBoard] Ignoring - different project:', data.project_id, '!==', projectId)
        return
      }

      setTasks((currentTasks) => {
        const taskIndex = currentTasks.findIndex((t) => t.id === data.task_id)
        if (taskIndex === -1) {
          // Task not found, might have been added - add it if we have the task data
          if (data.task) {
            setRealtimeNotice('Task moved')
            setTimeout(() => setRealtimeNotice(null), 3000)
            return [...currentTasks, data.task as unknown as Task]
          }
          return currentTasks
        }

        // Update the task's status and rank
        setRealtimeNotice('Task moved')
        setTimeout(() => setRealtimeNotice(null), 3000)

        const newTasks = [...currentTasks]
        const existingTask = newTasks[taskIndex]

        // Determine the new status from the task data or status_id
        let newStatus = existingTask.status
        if (data.task && (data.task as unknown as Task).status) {
          newStatus = (data.task as unknown as Task).status
        }

        newTasks[taskIndex] = {
          ...existingTask,
          status: newStatus,
          task_rank: data.new_rank,
          updated_at: data.timestamp,
        }

        return newTasks
      })
    },
    [projectId]
  )

  // Subscribe to task moved events
  useTaskMoved(enableRealtime ? projectId : null, handleTaskMoved)

  // ============================================================================
  // Fetch Tasks
  // ============================================================================

  const fetchTasks = useCallback(async () => {
    setIsLoading(true)
    setError(null)

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.get<Task[]>(
        `/api/projects/${projectId}/tasks`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error('Failed to fetch tasks')
      }

      setTasks(response.data || [])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch tasks')
    } finally {
      setIsLoading(false)
    }
  }, [projectId, token])

  // Initial fetch - clear stale data when projectId changes
  useEffect(() => {
    setTasks([])
    setError(null)
    fetchTasks()
  }, [fetchTasks])

  // Register refresh callback with parent
  useEffect(() => {
    if (onRefresh) {
      onRefresh(fetchTasks)
    }
  }, [fetchTasks, onRefresh])

  // ============================================================================
  // Group Tasks by Status
  // ============================================================================

  const tasksByStatus = useMemo(() => {
    return DEFAULT_COLUMNS.reduce(
      (acc, column) => {
        acc[column.id] = tasks
          .filter((t) => t.status === column.id)
          .sort((a, b) => {
            if (!a.task_rank && !b.task_rank) return 0
            if (!a.task_rank) return 1
            if (!b.task_rank) return -1
            return a.task_rank.localeCompare(b.task_rank)
          })
        return acc
      },
      {} as Record<TaskStatus, Task[]>
    )
  }, [tasks])

  // ============================================================================
  // Render
  // ============================================================================

  // Error state
  if (error && !isLoading && tasks.length === 0) {
    return (
      <div
        className={cn(
          'flex flex-col items-center justify-center py-12',
          className
        )}
      >
        <div className="flex h-16 w-16 items-center justify-center rounded-full bg-destructive/10">
          <AlertCircle className="h-8 w-8 text-destructive" />
        </div>
        <h3 className="mt-4 text-lg font-semibold text-foreground">
          Failed to load tasks
        </h3>
        <p className="mt-2 text-muted-foreground">{error}</p>
      </div>
    )
  }

  return (
    <div className={cn('flex flex-col h-full', className)}>
      {/* Toolbar */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          {/* Real-time connection indicator */}
          {enableRealtime && (
            <div
              className={cn(
                'flex items-center gap-1.5 px-2 py-1 rounded-md text-xs',
                status.isConnected
                  ? 'bg-green-500/10 text-green-600 dark:text-green-400'
                  : 'bg-muted text-muted-foreground'
              )}
              title={
                status.isConnected
                  ? 'Real-time updates active'
                  : 'Not connected to real-time updates'
              }
            >
              {status.isConnected ? (
                <Wifi className="h-3.5 w-3.5" />
              ) : (
                <WifiOff className="h-3.5 w-3.5" />
              )}
              <span className="hidden sm:inline">
                {status.isConnected ? 'Live' : 'Offline'}
              </span>
            </div>
          )}

          {/* Real-time update notice */}
          {realtimeNotice && (
            <div
              className={cn(
                'flex items-center gap-1.5 px-2 py-1 rounded-md text-xs animate-in fade-in slide-in-from-left-2 duration-200',
                realtimeNotice.toLowerCase().includes('failed')
                  ? 'bg-red-500/10 text-red-600 dark:text-red-400'
                  : 'bg-blue-500/10 text-blue-600 dark:text-blue-400'
              )}
            >
              {realtimeNotice.toLowerCase().includes('failed') ? (
                <AlertCircle className="h-3.5 w-3.5" />
              ) : (
                <Wifi className="h-3.5 w-3.5" />
              )}
              <span>{realtimeNotice}</span>
            </div>
          )}

          {/* Moving indicator */}
          {isMoving && (
            <div className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-amber-500/10 text-amber-600 dark:text-amber-400 text-xs animate-pulse">
              <span>Moving task...</span>
            </div>
          )}

          {/* View-only indicator when canEdit is false */}
          {!canEdit && (
            <div
              className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-muted text-muted-foreground text-xs"
              title="You can view tasks but cannot edit or move them"
            >
              <Eye className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">View only</span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* Add Task Button - only show when user can edit and not in archive view */}
          {onAddTask && canEdit && !showArchive && (
            <button
              onClick={() => onAddTask()}
              className={cn(
                'inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground',
                'hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
                'transition-colors duration-200'
              )}
            >
              <Plus className="h-4 w-4" />
              Add Task
            </button>
          )}
        </div>
      </div>

      {/* Tab Navigation - Proper underline style tabs */}
      <div className="flex border-b px-1">
        <button
          onClick={() => setShowArchive(false)}
          className={cn(
            'flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm font-medium transition-colors',
            !showArchive
              ? 'border-primary text-foreground'
              : 'border-transparent text-muted-foreground hover:border-muted hover:text-foreground'
          )}
        >
          <Columns className="h-4 w-4" />
          <span>Board</span>
        </button>
        <button
          onClick={() => setShowArchive(true)}
          className={cn(
            'flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm font-medium transition-colors',
            showArchive
              ? 'border-primary text-foreground'
              : 'border-transparent text-muted-foreground hover:border-muted hover:text-foreground'
          )}
        >
          <Archive className="h-4 w-4" />
          <span>Archive</span>
          {archivedCount != null && archivedCount > 0 && (
            <span
              className={cn(
                'ml-0.5 inline-flex items-center justify-center rounded-full px-1.5 py-0.5 text-xs font-medium tabular-nums',
                showArchive
                  ? 'bg-primary/15 text-primary'
                  : 'bg-muted text-muted-foreground'
              )}
            >
              {archivedCount}
            </span>
          )}
        </button>
      </div>

      {/* Progress bar - only show for board view */}
      {!showArchive && <ProgressBar isActive={isLoading && tasks.length > 0} />}

      {/* Archive View */}
      {showArchive ? (
        <ArchivedTasksList
          projectId={projectId}
          onTaskClick={onTaskClick}
          onTaskRestored={(task) => {
            // Add restored task to local state (task is now in Done status)
            setTasks((prev) => {
              const exists = prev.some((t) => t.id === task.id)
              return exists ? prev : [...prev, task]
            })
          }}
          className="flex-1"
        />
      ) : (
        <>
          {/* Board with DnD Context */}
          <DndContext
            sensors={sensors}
            collisionDetection={customCollisionDetection}
            onDragStart={handleDragStart}
            onDragOver={handleDragOver}
            onDragEnd={handleDragEnd}
            onDragCancel={handleDragCancel}
          >
            <div className="flex-1 overflow-x-auto">
              <div className="flex gap-4 pb-4 min-w-max">
                {DEFAULT_COLUMNS.map((column) => (
                  <DroppableColumn
                    key={column.id}
                    column={column}
                    tasks={tasksByStatus[column.id] || []}
                    isOver={overColumnId === column.id}
                    isLoading={isLoading && tasks.length === 0}
                    onTaskClick={onTaskClick}
                    onAddTask={onAddTask}
                  />
                ))}
              </div>
            </div>

            {/* Drag Overlay - shows the dragging card */}
            <DragOverlay dropAnimation={null}>
              {activeTask ? (
                <div className="shadow-xl ring-2 ring-primary/50 rounded-lg opacity-90">
                  <TaskCard task={activeTask} variant="default" />
                </div>
              ) : null}
            </DragOverlay>
          </DndContext>
        </>
      )}

      {/* Empty State - only show for board view */}
      {!showArchive && !isLoading && tasks.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12">
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-muted">
            <LayoutGrid className="h-8 w-8 text-muted-foreground" />
          </div>
          <h3 className="mt-4 text-lg font-semibold text-foreground">
            No tasks yet
          </h3>
          <p className="mt-2 text-center text-muted-foreground">
            Create your first task to get started with this project.
          </p>
          {onAddTask && (
            <button
              onClick={() => onAddTask()}
              className={cn(
                'mt-4 inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground',
                'hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
                'transition-colors duration-200'
              )}
            >
              <Plus className="h-4 w-4" />
              Create Task
            </button>
          )}
        </div>
      )}
    </div>
  )
}

export default KanbanBoard
