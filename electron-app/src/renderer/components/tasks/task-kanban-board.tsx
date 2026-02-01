/**
 * Task Kanban Board Component
 *
 * Kanban-style board view for managing tasks within a project.
 * Uses @dnd-kit for reliable drag-and-drop in Electron.
 */

import { useState, useCallback, useEffect, useMemo, useRef } from 'react'
import { cn } from '@/lib/utils'
import { useAuthStore, getAuthHeaders } from '@/contexts/auth-context'
import { useMoveTask, type Task } from '@/hooks/use-queries'
import {
  DndContext,
  DragOverlay,
  closestCenter,
  MouseSensor,
  TouchSensor,
  useSensor,
  useSensors,
  type DragStartEvent,
  type DragEndEvent,
} from '@dnd-kit/core'
import { useDraggable, useDroppable } from '@dnd-kit/core'
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

interface BoardColumn {
  id: string
  title: string
  icon: JSX.Element
  color: string
  bgColor: string
}

export interface TaskKanbanBoardProps {
  projectId: string
  projectKey: string
  onTaskClick?: (task: Task) => void
  onAddTask?: (status?: string) => void
  onTaskStatusChange?: (task: Task, newStatus: string) => void
  className?: string
  enableRealtime?: boolean
}

// ============================================================================
// Constants
// ============================================================================

const BOARD_COLUMNS: BoardColumn[] = [
  { id: 'Todo', title: 'To Do', icon: <Circle className="h-4 w-4" />, color: 'bg-slate-500', bgColor: 'bg-slate-500/10' },
  { id: 'In Progress', title: 'In Progress', icon: <Timer className="h-4 w-4" />, color: 'bg-blue-500', bgColor: 'bg-blue-500/10' },
  { id: 'In Review', title: 'In Review', icon: <Eye className="h-4 w-4" />, color: 'bg-purple-500', bgColor: 'bg-purple-500/10' },
  { id: 'Issue', title: 'Issue', icon: <XCircle className="h-4 w-4" />, color: 'bg-red-500', bgColor: 'bg-red-500/10' },
  { id: 'Done', title: 'Done', icon: <CheckCircle2 className="h-4 w-4" />, color: 'bg-green-500', bgColor: 'bg-green-500/10' },
]

// ============================================================================
// Draggable Task Card Component
// ============================================================================

interface DraggableTaskCardProps {
  task: Task
  onClick?: (task: Task) => void
  disabled?: boolean
}

function DraggableTaskCard({ task, onClick, disabled = false }: DraggableTaskCardProps): JSX.Element {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: task.id,
    data: { task },
    disabled,
  })

  // Track drag state to differentiate from click
  const isDraggingRef = useRef(false)

  // When drag actually starts, mark it
  useEffect(() => {
    if (isDragging) {
      isDraggingRef.current = true
    }
  }, [isDragging])

  const handleClick = useCallback(() => {
    // Only fire click if we didn't drag
    setTimeout(() => {
      if (!isDraggingRef.current && onClick) {
        onClick(task)
      }
      isDraggingRef.current = false
    }, 0)
  }, [onClick, task])

  return (
    <div
      ref={setNodeRef}
      {...attributes}
      {...listeners}
      onClick={handleClick}
      style={{ touchAction: 'none' }}
      className={cn(
        disabled ? 'cursor-default' : 'cursor-grab active:cursor-grabbing',
        isDragging && 'opacity-50'
      )}
    >
      <TaskCard task={task} variant="default" />
    </div>
  )
}

// ============================================================================
// Droppable Column Component
// ============================================================================

interface DroppableColumnProps {
  column: BoardColumn
  tasks: Task[]
  onTaskClick?: (task: Task) => void
  onAddTask?: (status: string) => void
  isLoading?: boolean
}

function DroppableColumn({
  column,
  tasks,
  onTaskClick,
  onAddTask,
  isLoading,
}: DroppableColumnProps): JSX.Element {
  const { setNodeRef, isOver } = useDroppable({
    id: column.id,
    data: { status: column.id },
  })

  return (
    <div
      ref={setNodeRef}
      className={cn(
        'flex h-full w-72 flex-shrink-0 flex-col rounded-lg bg-muted/30 transition-all duration-200',
        isOver && 'ring-2 ring-primary/50 bg-primary/5'
      )}
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
              isOver && 'bg-primary/10 rounded-lg border-2 border-dashed border-primary/50'
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
              {isOver ? 'Drop task here' : 'No tasks'}
            </p>
          </div>
        ) : (
          <>
            {tasks.map((task) => (
              <DraggableTaskCard
                key={task.id}
                task={task}
                onClick={onTaskClick}
                disabled={!!task.archived_at}
              />
            ))}
            {/* Drop indicator at bottom */}
            {isOver && (
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
// Drag Overlay Card (shown while dragging)
// ============================================================================

interface DragOverlayCardProps {
  task: Task
}

function DragOverlayCard({ task }: DragOverlayCardProps): JSX.Element {
  return (
    <div className="opacity-90 shadow-lg rotate-2 scale-105">
      <TaskCard task={task} variant="default" />
    </div>
  )
}

// ============================================================================
// Main Component
// ============================================================================

export function TaskKanbanBoard({
  projectId,
  projectKey: _projectKey,
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
  const [activeTask, setActiveTask] = useState<Task | null>(null)

  // Auth
  const token = useAuthStore((state) => state.token)

  // Task move mutation
  const moveTaskMutation = useMoveTask(projectId)
  const isMoving = moveTaskMutation.isPending

  // WebSocket status
  const { status } = useWebSocket()

  // Configure dnd-kit sensors - use MouseSensor for desktop
  const sensors = useSensors(
    useSensor(MouseSensor, {
      activationConstraint: {
        // Require small movement before starting drag
        distance: 5,
      },
    }),
    useSensor(TouchSensor, {
      activationConstraint: {
        delay: 250,
        tolerance: 5,
      },
    })
  )

  // Handle real-time task updates
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

  // Group tasks by status
  const tasksByStatus = useMemo(() => {
    return BOARD_COLUMNS.reduce(
      (acc, column) => {
        acc[column.id] = tasks
          .filter((t) => t.task_status?.name === column.id)
          .sort((a, b) => {
            if (!a.task_rank && !b.task_rank) return 0
            if (!a.task_rank) return 1
            if (!b.task_rank) return -1
            return a.task_rank.localeCompare(b.task_rank)
          })
        return acc
      },
      {} as Record<string, Task[]>
    )
  }, [tasks])

  // Handle drag start
  const handleDragStart = useCallback(
    (event: DragStartEvent) => {
      const { active } = event
      const task = tasks.find((t) => t.id === active.id)
      if (task) {
        setActiveTask(task)
      }
    },
    [tasks]
  )

  // Handle drag end
  const handleDragEnd = useCallback(
    async (event: DragEndEvent) => {
      const { active, over } = event
      setActiveTask(null)

      if (!over) return

      const taskId = active.id as string
      const task = tasks.find((t) => t.id === taskId)
      if (!task) return

      // Get target status from drop zone
      const targetStatus = over.id as string

      // Skip if dropping on same column
      if (task.task_status?.name === targetStatus) return

      // Optimistic update - save original for revert
      const originalTask = { ...task }
      setTasks((currentTasks) =>
        currentTasks.map((t) =>
          t.id === taskId ? { ...t } : t
        )
      )

      // Callback
      if (onTaskStatusChange) {
        onTaskStatusChange(task, targetStatus)
      }

      try {
        // API call using TanStack Query mutation
        await moveTaskMutation.mutateAsync({
          taskId,
          targetStatusId: task.task_status_id,
          targetStatusName: targetStatus,
        })
      } catch {
        // Revert on failure
        setTasks((currentTasks) =>
          currentTasks.map((t) =>
            t.id === taskId ? originalTask : t
          )
        )
      }
    },
    [tasks, moveTaskMutation, onTaskStatusChange]
  )

  // Error state
  if (error && !isLoading && tasks.length === 0) {
    return (
      <div className={cn('flex flex-col items-center justify-center py-12', className)}>
        <div className="flex h-16 w-16 items-center justify-center rounded-full bg-destructive/10">
          <AlertCircle className="h-8 w-8 text-destructive" />
        </div>
        <h3 className="mt-4 text-lg font-semibold text-foreground">Failed to load tasks</h3>
        <p className="mt-2 text-muted-foreground">{error}</p>
      </div>
    )
  }

  return (
    <div className={cn('flex flex-col h-full', className)}>
      {/* Toolbar */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          {enableRealtime && (
            <div
              className={cn(
                'flex items-center gap-1.5 px-2 py-1 rounded-md text-xs',
                status.isConnected
                  ? 'bg-green-500/10 text-green-600 dark:text-green-400'
                  : 'bg-muted text-muted-foreground'
              )}
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

          {realtimeNotice && (
            <div className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-blue-500/10 text-blue-600 dark:text-blue-400 text-xs animate-in fade-in slide-in-from-left-2 duration-200">
              <Wifi className="h-3.5 w-3.5" />
              <span>{realtimeNotice}</span>
            </div>
          )}

          {isMoving && (
            <div className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-amber-500/10 text-amber-600 dark:text-amber-400 text-xs animate-pulse">
              <span>Moving task...</span>
            </div>
          )}
        </div>

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

      <ProgressBar isActive={isLoading && tasks.length > 0} />

      {/* Kanban Board with DnD Context */}
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
      >
        <div className="flex-1 overflow-x-auto">
          <div className="flex gap-4 pb-4 min-w-max h-full">
            {BOARD_COLUMNS.map((column) => (
              <DroppableColumn
                key={column.id}
                column={column}
                tasks={tasksByStatus[column.id] || []}
                onTaskClick={onTaskClick}
                onAddTask={onAddTask}
                isLoading={isLoading && tasks.length === 0}
              />
            ))}
          </div>
        </div>

        {/* Drag Overlay - shows the card being dragged */}
        <DragOverlay>
          {activeTask ? <DragOverlayCard task={activeTask} /> : null}
        </DragOverlay>
      </DndContext>

      {/* Empty State */}
      {!isLoading && tasks.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12">
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-muted">
            <LayoutGrid className="h-8 w-8 text-muted-foreground" />
          </div>
          <h3 className="mt-4 text-lg font-semibold text-foreground">No tasks yet</h3>
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
