/**
 * Task Kanban Board Component
 *
 * Kanban-style board view for managing tasks within a project.
 * Displays tasks organized by 5 status columns with drag-and-drop support.
 *
 * Features:
 * - 5 status columns (To Do, In Progress, In Review, Done, Blocked)
 * - Drag-and-drop task movement between columns
 * - Task cards with status badges
 * - Column task counts
 * - Add task button per column
 * - Empty state handling
 * - Real-time updates via WebSocket
 * - Optimistic UI updates during drag operations
 */

import { useState, useCallback, useEffect, useMemo } from 'react'
import { cn } from '@/lib/utils'
import { useAuthStore, getAuthHeaders } from '@/stores/auth-store'
import {
  useTasksStore,
  type Task,
  type TaskStatus,
  type TaskMove,
} from '@/stores/tasks-store'
import {
  LayoutGrid,
  Plus,
  AlertCircle,
  Circle,
  Timer,
  Eye,
  CheckCircle2,
  XCircle,
  Wifi,
  WifiOff,
  GripVertical,
} from 'lucide-react'
import { SkeletonTaskCard, ProgressBar } from '@/components/ui/skeleton'
import {
  useTaskUpdates,
  useWebSocket,
  type TaskUpdateEventData,
} from '@/hooks/use-websocket'
import { TaskCard } from './task-card'

// ============================================================================
// Types
// ============================================================================

/**
 * Board column definition
 */
interface BoardColumn {
  id: TaskStatus
  title: string
  icon: JSX.Element
  color: string
  bgColor: string
}

export interface TaskKanbanBoardProps {
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
}

// ============================================================================
// Constants
// ============================================================================

const BOARD_COLUMNS: BoardColumn[] = [
  {
    id: 'todo',
    title: 'To Do',
    icon: <Circle className="h-4 w-4" />,
    color: 'bg-slate-500',
    bgColor: 'bg-slate-500/10',
  },
  {
    id: 'in_progress',
    title: 'In Progress',
    icon: <Timer className="h-4 w-4" />,
    color: 'bg-blue-500',
    bgColor: 'bg-blue-500/10',
  },
  {
    id: 'in_review',
    title: 'In Review',
    icon: <Eye className="h-4 w-4" />,
    color: 'bg-purple-500',
    bgColor: 'bg-purple-500/10',
  },
  {
    id: 'done',
    title: 'Done',
    icon: <CheckCircle2 className="h-4 w-4" />,
    color: 'bg-green-500',
    bgColor: 'bg-green-500/10',
  },
  {
    id: 'blocked',
    title: 'Blocked',
    icon: <XCircle className="h-4 w-4" />,
    color: 'bg-red-500',
    bgColor: 'bg-red-500/10',
  },
]

// ============================================================================
// Draggable Task Card Component
// ============================================================================

interface DraggableTaskCardProps {
  task: Task
  onClick?: (task: Task) => void
  onDragStart: (e: React.DragEvent, task: Task) => void
  onDragEnd: (e: React.DragEvent) => void
  isDragging: boolean
}

function DraggableTaskCard({
  task,
  onClick,
  onDragStart,
  onDragEnd,
  isDragging,
}: DraggableTaskCardProps): JSX.Element {
  return (
    <div
      draggable
      onDragStart={(e) => onDragStart(e, task)}
      onDragEnd={onDragEnd}
      className={cn(
        'group relative transition-all duration-150',
        isDragging && 'opacity-50 scale-95'
      )}
    >
      {/* Drag handle indicator */}
      <div
        className={cn(
          'absolute left-0 top-1/2 -translate-y-1/2 -translate-x-1 opacity-0 transition-opacity',
          'group-hover:opacity-50 cursor-grab active:cursor-grabbing'
        )}
      >
        <GripVertical className="h-4 w-4 text-muted-foreground" />
      </div>
      <TaskCard task={task} onClick={onClick} variant="default" />
    </div>
  )
}

// ============================================================================
// Board Column Component
// ============================================================================

interface BoardColumnProps {
  column: BoardColumn
  tasks: Task[]
  onTaskClick?: (task: Task) => void
  onAddTask?: (status: TaskStatus) => void
  onDragStart: (e: React.DragEvent, task: Task) => void
  onDragEnd: (e: React.DragEvent) => void
  onDragOver: (e: React.DragEvent) => void
  onDragLeave: (e: React.DragEvent) => void
  onDrop: (e: React.DragEvent, status: TaskStatus) => void
  draggingTaskId: string | null
  isDragOver: boolean
  isLoading?: boolean
}

function BoardColumnComponent({
  column,
  tasks,
  onTaskClick,
  onAddTask,
  onDragStart,
  onDragEnd,
  onDragOver,
  onDragLeave,
  onDrop,
  draggingTaskId,
  isDragOver,
  isLoading,
}: BoardColumnProps): JSX.Element {
  return (
    <div
      className={cn(
        'flex h-full w-72 flex-shrink-0 flex-col rounded-lg bg-muted/30 transition-all duration-200',
        isDragOver && 'ring-2 ring-primary/50 bg-primary/5'
      )}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={(e) => onDrop(e, column.id)}
    >
      {/* Column Header */}
      <div className="flex items-center justify-between p-3 border-b border-border">
        <div className="flex items-center gap-2">
          <div
            className={cn(
              'flex h-6 w-6 items-center justify-center rounded text-white',
              column.color
            )}
          >
            {column.icon}
          </div>
          <h3 className="font-medium text-foreground">{column.title}</h3>
          <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
            {tasks.length}
          </span>
        </div>
        {onAddTask && (
          <button
            onClick={() => onAddTask(column.id)}
            className={cn(
              'rounded p-1 text-muted-foreground transition-colors',
              'hover:bg-accent hover:text-accent-foreground',
              'focus:outline-none focus:ring-2 focus:ring-ring'
            )}
            title={`Add task to ${column.title}`}
          >
            <Plus className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Column Content */}
      <div className="flex-1 overflow-y-auto p-2 space-y-2">
        {isLoading ? (
          <>
            <SkeletonTaskCard />
            <SkeletonTaskCard />
          </>
        ) : tasks.length === 0 ? (
          <div
            className={cn(
              'flex flex-col items-center justify-center py-8 text-center transition-all',
              isDragOver && 'bg-primary/10 rounded-lg border-2 border-dashed border-primary/50'
            )}
          >
            <div
              className={cn(
                'flex h-10 w-10 items-center justify-center rounded-lg text-muted-foreground',
                column.bgColor
              )}
            >
              {column.icon}
            </div>
            <p className="mt-2 text-sm text-muted-foreground">
              {isDragOver ? 'Drop task here' : 'No tasks'}
            </p>
          </div>
        ) : (
          <>
            {tasks.map((task) => (
              <DraggableTaskCard
                key={task.id}
                task={task}
                onClick={onTaskClick}
                onDragStart={onDragStart}
                onDragEnd={onDragEnd}
                isDragging={draggingTaskId === task.id}
              />
            ))}
            {/* Drop zone indicator at the bottom when dragging */}
            {isDragOver && draggingTaskId && (
              <div className="h-12 rounded-lg border-2 border-dashed border-primary/50 bg-primary/10 flex items-center justify-center">
                <span className="text-xs text-primary">Drop here</span>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

// ============================================================================
// Main Component
// ============================================================================

export function TaskKanbanBoard({
  projectId,
  projectKey,
  onTaskClick,
  onAddTask,
  onTaskStatusChange,
  className,
  enableRealtime = true,
}: TaskKanbanBoardProps): JSX.Element {
  // State
  const [tasks, setTasks] = useState<Task[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [realtimeNotice, setRealtimeNotice] = useState<string | null>(null)

  // Drag state
  const [draggingTaskId, setDraggingTaskId] = useState<string | null>(null)
  const [dragOverColumn, setDragOverColumn] = useState<TaskStatus | null>(null)

  // Auth
  const token = useAuthStore((state) => state.token)

  // Store actions
  const { moveTask, isMoving } = useTasksStore()

  // WebSocket status
  const { status } = useWebSocket()

  // Handle real-time task updates
  const handleTaskUpdate = useCallback(
    (data: TaskUpdateEventData) => {
      if (data.project_id !== projectId) return

      setTasks((currentTasks) => {
        if (data.action === 'created' && data.task) {
          // Add new task if not already present
          const exists = currentTasks.some((t) => t.id === data.task_id)
          if (!exists) {
            setRealtimeNotice('New task added')
            setTimeout(() => setRealtimeNotice(null), 3000)
            return [...currentTasks, data.task as Task]
          }
          return currentTasks
        } else if (data.action === 'updated' && data.task) {
          // Update existing task
          const index = currentTasks.findIndex((t) => t.id === data.task_id)
          if (index !== -1) {
            setRealtimeNotice('Task updated')
            setTimeout(() => setRealtimeNotice(null), 3000)
            const newTasks = [...currentTasks]
            newTasks[index] = data.task as Task
            return newTasks
          }
          return currentTasks
        } else if (data.action === 'deleted') {
          // Remove deleted task
          const index = currentTasks.findIndex((t) => t.id === data.task_id)
          if (index !== -1) {
            setRealtimeNotice('Task removed')
            setTimeout(() => setRealtimeNotice(null), 3000)
            return currentTasks.filter((t) => t.id !== data.task_id)
          }
          return currentTasks
        } else if (data.action === 'status_changed' && data.task) {
          // Update task status
          const index = currentTasks.findIndex((t) => t.id === data.task_id)
          if (index !== -1) {
            setRealtimeNotice('Task status changed')
            setTimeout(() => setRealtimeNotice(null), 3000)
            const newTasks = [...currentTasks]
            newTasks[index] = data.task as Task
            return newTasks
          }
          return currentTasks
        }
        return currentTasks
      })
    },
    [projectId]
  )

  // Subscribe to task updates via WebSocket
  useTaskUpdates(enableRealtime ? projectId : null, handleTaskUpdate)

  // Fetch tasks
  useEffect(() => {
    const fetchTasks = async () => {
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
    }

    fetchTasks()
  }, [projectId, token])

  // Group tasks by status for board view, sorted by task_rank
  const tasksByStatus = useMemo(() => {
    return BOARD_COLUMNS.reduce(
      (acc, column) => {
        acc[column.id] = tasks
          .filter((t) => t.status === column.id)
          .sort((a, b) => {
            // Tasks without rank go to the end
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

  // Drag handlers
  const handleDragStart = useCallback((e: React.DragEvent, task: Task) => {
    setDraggingTaskId(task.id)
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', task.id)
  }, [])

  const handleDragEnd = useCallback(() => {
    setDraggingTaskId(null)
    setDragOverColumn(null)
  }, [])

  const handleDragOver = useCallback(
    (e: React.DragEvent, columnId: TaskStatus) => {
      e.preventDefault()
      e.dataTransfer.dropEffect = 'move'
      if (dragOverColumn !== columnId) {
        setDragOverColumn(columnId)
      }
    },
    [dragOverColumn]
  )

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    // Only clear if leaving the column entirely (not just moving to a child element)
    const relatedTarget = e.relatedTarget as HTMLElement
    const currentTarget = e.currentTarget as HTMLElement
    if (!currentTarget.contains(relatedTarget)) {
      setDragOverColumn(null)
    }
  }, [])

  const handleDrop = useCallback(
    async (e: React.DragEvent, targetStatus: TaskStatus) => {
      e.preventDefault()
      const taskId = e.dataTransfer.getData('text/plain')
      const task = tasks.find((t) => t.id === taskId)

      if (!task || task.status === targetStatus) {
        setDraggingTaskId(null)
        setDragOverColumn(null)
        return
      }

      // Optimistic update
      setTasks((currentTasks) =>
        currentTasks.map((t) =>
          t.id === taskId ? { ...t, status: targetStatus } : t
        )
      )

      // Reset drag state
      setDraggingTaskId(null)
      setDragOverColumn(null)

      // Call the status change callback
      if (onTaskStatusChange) {
        onTaskStatusChange(task, targetStatus)
      }

      // Make API call to move task
      const moveData: TaskMove = {
        target_status: targetStatus,
        row_version: task.row_version,
      }

      const result = await moveTask(token, taskId, moveData)

      if (!result) {
        // Revert on failure
        setTasks((currentTasks) =>
          currentTasks.map((t) =>
            t.id === taskId ? { ...t, status: task.status } : t
          )
        )
      }
    },
    [tasks, token, moveTask, onTaskStatusChange]
  )

  // Render error state
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
            <div className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-blue-500/10 text-blue-600 dark:text-blue-400 text-xs animate-in fade-in slide-in-from-left-2 duration-200">
              <Wifi className="h-3.5 w-3.5" />
              <span>{realtimeNotice}</span>
            </div>
          )}

          {/* Moving indicator */}
          {isMoving && (
            <div className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-amber-500/10 text-amber-600 dark:text-amber-400 text-xs animate-pulse">
              <span>Moving task...</span>
            </div>
          )}
        </div>

        {/* Add Task Button */}
        {onAddTask && (
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

      {/* Subtle progress bar when refreshing with existing data */}
      <ProgressBar isActive={isLoading && tasks.length > 0} />

      {/* Board View */}
      <div className="flex-1 overflow-x-auto">
        <div className="flex gap-4 pb-4 min-w-max">
          {BOARD_COLUMNS.map((column) => (
            <BoardColumnComponent
              key={column.id}
              column={column}
              tasks={tasksByStatus[column.id] || []}
              onTaskClick={onTaskClick}
              onAddTask={onAddTask}
              onDragStart={handleDragStart}
              onDragEnd={handleDragEnd}
              onDragOver={(e) => handleDragOver(e, column.id)}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              draggingTaskId={draggingTaskId}
              isDragOver={dragOverColumn === column.id}
              isLoading={isLoading && tasks.length === 0}
            />
          ))}
        </div>
      </div>

      {/* Empty State */}
      {!isLoading && tasks.length === 0 && (
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

export default TaskKanbanBoard
