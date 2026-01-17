/**
 * Project Board Component
 *
 * Kanban-style board view for managing tasks within a project.
 * Displays tasks organized by status columns.
 *
 * Features:
 * - Multiple status columns (To Do, In Progress, In Review, Done)
 * - Task cards with status badges
 * - Column task counts
 * - Add task button per column
 * - Drag-and-drop ready structure (actual DnD to be implemented in phase-7)
 * - List view toggle
 * - Empty state handling
 * - Real-time updates via WebSocket
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth-store'
import { getAuthHeaders } from '@/stores/auth-store'
import {
  LayoutGrid,
  List,
  Plus,
  Loader2,
  AlertCircle,
  ChevronRight,
  ChevronDown,
  Clock,
  User,
  Flag,
  Bug,
  Bookmark,
  CheckCircle2,
  Circle,
  Timer,
  Eye,
  XCircle,
  Wifi,
  WifiOff,
} from 'lucide-react'
import {
  useTaskUpdates,
  useWebSocket,
  type TaskUpdateEventData,
} from '@/hooks/use-websocket'

// ============================================================================
// Types
// ============================================================================

/**
 * Task status enumeration
 */
export type TaskStatus = 'todo' | 'in_progress' | 'in_review' | 'done' | 'blocked'

/**
 * Task priority enumeration
 */
export type TaskPriority = 'lowest' | 'low' | 'medium' | 'high' | 'highest'

/**
 * Task type enumeration
 */
export type TaskType = 'story' | 'bug' | 'epic' | 'subtask' | 'task'

/**
 * Task data
 */
export interface Task {
  id: string
  project_id: string
  task_key: string
  title: string
  description: string | null
  task_type: TaskType
  status: TaskStatus
  priority: TaskPriority
  assignee_id: string | null
  reporter_id: string | null
  parent_id: string | null
  sprint_id: string | null
  story_points: number | null
  due_date: string | null
  created_at: string
  updated_at: string
  subtasks_count?: number
}

/**
 * Board column definition
 */
interface BoardColumn {
  id: TaskStatus
  title: string
  icon: JSX.Element
  color: string
}

export interface ProjectBoardProps {
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
  },
  {
    id: 'in_progress',
    title: 'In Progress',
    icon: <Timer className="h-4 w-4" />,
    color: 'bg-blue-500',
  },
  {
    id: 'in_review',
    title: 'In Review',
    icon: <Eye className="h-4 w-4" />,
    color: 'bg-purple-500',
  },
  {
    id: 'done',
    title: 'Done',
    icon: <CheckCircle2 className="h-4 w-4" />,
    color: 'bg-green-500',
  },
]

// ============================================================================
// Helper Components
// ============================================================================

/**
 * Get priority icon and color
 */
function getPriorityInfo(priority: TaskPriority): { icon: JSX.Element; color: string } {
  switch (priority) {
    case 'highest':
      return {
        icon: <Flag className="h-3 w-3" />,
        color: 'text-red-600 dark:text-red-400',
      }
    case 'high':
      return {
        icon: <Flag className="h-3 w-3" />,
        color: 'text-orange-600 dark:text-orange-400',
      }
    case 'medium':
      return {
        icon: <Flag className="h-3 w-3" />,
        color: 'text-yellow-600 dark:text-yellow-400',
      }
    case 'low':
      return {
        icon: <Flag className="h-3 w-3" />,
        color: 'text-blue-600 dark:text-blue-400',
      }
    case 'lowest':
      return {
        icon: <Flag className="h-3 w-3" />,
        color: 'text-slate-400 dark:text-slate-500',
      }
  }
}

/**
 * Get task type icon
 */
function getTaskTypeIcon(taskType: TaskType): JSX.Element {
  switch (taskType) {
    case 'bug':
      return <Bug className="h-3.5 w-3.5 text-red-500" />
    case 'epic':
      return <Bookmark className="h-3.5 w-3.5 text-purple-500" />
    case 'story':
      return <Bookmark className="h-3.5 w-3.5 text-green-500" />
    case 'subtask':
      return <CheckCircle2 className="h-3.5 w-3.5 text-blue-400" />
    case 'task':
    default:
      return <CheckCircle2 className="h-3.5 w-3.5 text-blue-500" />
  }
}

// ============================================================================
// Task Card Component
// ============================================================================

interface TaskCardProps {
  task: Task
  onClick?: (task: Task) => void
}

function TaskCard({ task, onClick }: TaskCardProps): JSX.Element {
  const priorityInfo = getPriorityInfo(task.priority)

  return (
    <div
      onClick={() => onClick?.(task)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if ((e.key === 'Enter' || e.key === ' ') && onClick) {
          e.preventDefault()
          onClick(task)
        }
      }}
      className={cn(
        'group rounded-lg border border-border bg-card p-3 transition-all cursor-pointer',
        'hover:border-primary/50 hover:shadow-sm',
        'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1'
      )}
    >
      {/* Task Key and Type */}
      <div className="flex items-center gap-2 mb-2">
        {getTaskTypeIcon(task.task_type)}
        <span className="text-xs font-medium text-muted-foreground">
          {task.task_key}
        </span>
      </div>

      {/* Task Title */}
      <h4 className="text-sm font-medium text-foreground line-clamp-2">
        {task.title}
      </h4>

      {/* Task Meta */}
      <div className="mt-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {/* Priority */}
          <span className={cn('flex items-center', priorityInfo.color)} title={task.priority}>
            {priorityInfo.icon}
          </span>
          {/* Story Points */}
          {task.story_points != null && (
            <span className="rounded-full bg-muted px-1.5 py-0.5 text-xs font-medium text-muted-foreground">
              {task.story_points}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* Due Date */}
          {task.due_date && (
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              <Clock className="h-3 w-3" />
              {new Date(task.due_date).toLocaleDateString(undefined, {
                month: 'short',
                day: 'numeric',
              })}
            </span>
          )}
          {/* Assignee */}
          {task.assignee_id && (
            <div className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 text-primary">
              <User className="h-3 w-3" />
            </div>
          )}
        </div>
      </div>
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
  isLoading?: boolean
}

function BoardColumnComponent({
  column,
  tasks,
  onTaskClick,
  onAddTask,
  isLoading,
}: BoardColumnProps): JSX.Element {
  return (
    <div className="flex h-full w-72 flex-shrink-0 flex-col rounded-lg bg-muted/30">
      {/* Column Header */}
      <div className="flex items-center justify-between p-3 border-b border-border">
        <div className="flex items-center gap-2">
          <div className={cn('flex h-6 w-6 items-center justify-center rounded text-white', column.color)}>
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
          <div className="flex items-center justify-center py-4">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : tasks.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted text-muted-foreground">
              {column.icon}
            </div>
            <p className="mt-2 text-sm text-muted-foreground">No tasks</p>
          </div>
        ) : (
          tasks.map((task) => (
            <TaskCard key={task.id} task={task} onClick={onTaskClick} />
          ))
        )}
      </div>
    </div>
  )
}

// ============================================================================
// List View Component
// ============================================================================

interface ListViewProps {
  tasks: Task[]
  onTaskClick?: (task: Task) => void
  isLoading?: boolean
}

function ListView({ tasks, onTaskClick, isLoading }: ListViewProps): JSX.Element {
  const [expandedStatuses, setExpandedStatuses] = useState<Set<TaskStatus>>(
    new Set(['todo', 'in_progress', 'in_review'])
  )

  const toggleStatus = (status: TaskStatus) => {
    setExpandedStatuses((prev) => {
      const next = new Set(prev)
      if (next.has(status)) {
        next.delete(status)
      } else {
        next.add(status)
      }
      return next
    })
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {BOARD_COLUMNS.map((column) => {
        const columnTasks = tasks.filter((t) => t.status === column.id)
        const isExpanded = expandedStatuses.has(column.id)

        return (
          <div key={column.id} className="rounded-lg border border-border bg-card">
            {/* Status Header */}
            <button
              onClick={() => toggleStatus(column.id)}
              className={cn(
                'flex w-full items-center gap-3 p-3 text-left transition-colors',
                'hover:bg-accent/50 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-ring'
              )}
            >
              {isExpanded ? (
                <ChevronDown className="h-4 w-4 text-muted-foreground" />
              ) : (
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              )}
              <div className={cn('flex h-6 w-6 items-center justify-center rounded text-white', column.color)}>
                {column.icon}
              </div>
              <span className="font-medium text-foreground">{column.title}</span>
              <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                {columnTasks.length}
              </span>
            </button>

            {/* Tasks List */}
            {isExpanded && columnTasks.length > 0 && (
              <div className="border-t border-border divide-y divide-border">
                {columnTasks.map((task) => {
                  const priorityInfo = getPriorityInfo(task.priority)
                  return (
                    <div
                      key={task.id}
                      onClick={() => onTaskClick?.(task)}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => {
                        if ((e.key === 'Enter' || e.key === ' ') && onTaskClick) {
                          e.preventDefault()
                          onTaskClick(task)
                        }
                      }}
                      className={cn(
                        'flex items-center gap-4 p-3 cursor-pointer transition-colors',
                        'hover:bg-accent/50 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-ring'
                      )}
                    >
                      {/* Type Icon */}
                      <div className="flex-shrink-0">{getTaskTypeIcon(task.task_type)}</div>

                      {/* Task Key */}
                      <span className="flex-shrink-0 text-xs font-medium text-muted-foreground min-w-[70px]">
                        {task.task_key}
                      </span>

                      {/* Title */}
                      <span className="flex-1 text-sm text-foreground truncate">{task.title}</span>

                      {/* Priority */}
                      <span className={cn('flex-shrink-0', priorityInfo.color)}>
                        {priorityInfo.icon}
                      </span>

                      {/* Story Points */}
                      {task.story_points != null && (
                        <span className="flex-shrink-0 rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                          {task.story_points}
                        </span>
                      )}

                      {/* Assignee */}
                      {task.assignee_id && (
                        <div className="flex-shrink-0 flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 text-primary">
                          <User className="h-3 w-3" />
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}

            {/* Empty State */}
            {isExpanded && columnTasks.length === 0 && (
              <div className="border-t border-border p-6 text-center text-sm text-muted-foreground">
                No tasks in this status
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ============================================================================
// Main Component
// ============================================================================

export function ProjectBoard({
  projectId,
  projectKey,
  onTaskClick,
  onAddTask,
  className,
  enableRealtime = true,
}: ProjectBoardProps): JSX.Element {
  // State
  const [viewMode, setViewMode] = useState<'board' | 'list'>('board')
  const [tasks, setTasks] = useState<Task[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [realtimeNotice, setRealtimeNotice] = useState<string | null>(null)

  // Auth
  const token = useAuthStore((state) => state.token)

  // WebSocket status
  const { status } = useWebSocket()

  // Handle real-time task updates
  const handleTaskUpdate = useCallback((data: TaskUpdateEventData) => {
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
  }, [projectId])

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

  // Group tasks by status for board view
  const tasksByStatus = BOARD_COLUMNS.reduce(
    (acc, column) => {
      acc[column.id] = tasks.filter((t) => t.status === column.id)
      return acc
    },
    {} as Record<TaskStatus, Task[]>
  )

  // Render error state
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
          {/* View Mode Toggle */}
          <div className="flex items-center rounded-lg border border-border bg-muted/50 p-1">
            <button
              onClick={() => setViewMode('board')}
              className={cn(
                'flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                viewMode === 'board'
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              <LayoutGrid className="h-4 w-4" />
              Board
            </button>
            <button
              onClick={() => setViewMode('list')}
              className={cn(
                'flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                viewMode === 'list'
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              <List className="h-4 w-4" />
              List
            </button>
          </div>

          {/* Real-time connection indicator */}
          {enableRealtime && (
            <div
              className={cn(
                'flex items-center gap-1.5 px-2 py-1 rounded-md text-xs',
                status.isConnected
                  ? 'bg-green-500/10 text-green-600 dark:text-green-400'
                  : 'bg-muted text-muted-foreground'
              )}
              title={status.isConnected ? 'Real-time updates active' : 'Not connected to real-time updates'}
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

      {/* Board or List View */}
      {viewMode === 'board' ? (
        <div className="flex-1 overflow-x-auto">
          <div className="flex gap-4 pb-4 min-w-max">
            {BOARD_COLUMNS.map((column) => (
              <BoardColumnComponent
                key={column.id}
                column={column}
                tasks={tasksByStatus[column.id] || []}
                onTaskClick={onTaskClick}
                onAddTask={onAddTask}
                isLoading={isLoading}
              />
            ))}
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto">
          <ListView tasks={tasks} onTaskClick={onTaskClick} isLoading={isLoading} />
        </div>
      )}

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

export default ProjectBoard
