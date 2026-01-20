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
  AlertTriangle,
  Wifi,
  WifiOff,
} from 'lucide-react'
import type { ProjectDerivedStatus } from '@/stores/projects-store'
import {
  SkeletonTaskCard,
  SkeletonListView,
  ProgressBar,
} from '@/components/ui/skeleton'
import {
  useTaskUpdates,
  useWebSocket,
  type TaskUpdateEventData,
} from '@/hooks/use-websocket'
import type { TaskViewer } from '@/hooks/use-task-viewers'
import { TaskViewerDots } from '@/components/tasks/TaskViewerDots'
import { Virtuoso } from 'react-virtuoso'

// ============================================================================
// Types
// ============================================================================

/**
 * Task status enumeration
 */
export type TaskStatus = 'todo' | 'in_progress' | 'in_review' | 'issue' | 'done'

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
   * Project's derived status (computed from task distribution)
   */
  derivedStatus?: ProjectDerivedStatus | null
  /**
   * Callback when a task is clicked
   */
  onTaskClick?: (task: Task) => void
  /**
   * Callback when add task is clicked
   */
  onAddTask?: (status?: TaskStatus) => void
  /**
   * Function to get viewers for a specific task
   */
  getTaskViewers?: (taskId: string) => TaskViewer[]
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
}

// ============================================================================
// Constants
// ============================================================================

/** Threshold above which virtualization is enabled for task lists */
const VIRTUALIZATION_THRESHOLD = 50

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
    id: 'issue',
    title: 'Issue',
    icon: <AlertTriangle className="h-4 w-4" />,
    color: 'bg-red-500',
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

/**
 * Get derived status display info (icon, color, label)
 */
function getDerivedStatusInfo(status: ProjectDerivedStatus | null | undefined): {
  icon: JSX.Element
  label: string
  color: string
  bgColor: string
  textColor: string
} {
  switch (status) {
    case 'Done':
      return {
        icon: <CheckCircle2 className="h-4 w-4" />,
        label: 'Done',
        color: 'bg-green-500',
        bgColor: 'bg-green-500/10',
        textColor: 'text-green-600 dark:text-green-400',
      }
    case 'Issue':
      return {
        icon: <AlertTriangle className="h-4 w-4" />,
        label: 'Issue',
        color: 'bg-red-500',
        bgColor: 'bg-red-500/10',
        textColor: 'text-red-600 dark:text-red-400',
      }
    case 'In Review':
      return {
        icon: <Eye className="h-4 w-4" />,
        label: 'In Review',
        color: 'bg-purple-500',
        bgColor: 'bg-purple-500/10',
        textColor: 'text-purple-600 dark:text-purple-400',
      }
    case 'In Progress':
      return {
        icon: <Timer className="h-4 w-4" />,
        label: 'In Progress',
        color: 'bg-blue-500',
        bgColor: 'bg-blue-500/10',
        textColor: 'text-blue-600 dark:text-blue-400',
      }
    case 'Todo':
    default:
      return {
        icon: <Circle className="h-4 w-4" />,
        label: 'Todo',
        color: 'bg-slate-500',
        bgColor: 'bg-slate-500/10',
        textColor: 'text-slate-500 dark:text-slate-400',
      }
  }
}

// ============================================================================
// Task Card Component
// ============================================================================

interface TaskCardProps {
  task: Task
  onClick?: (task: Task) => void
  viewers?: TaskViewer[]
}

function TaskCard({ task, onClick, viewers = [] }: TaskCardProps): JSX.Element {
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
        {/* Task Viewers */}
        {viewers.length > 0 && (
          <TaskViewerDots viewers={viewers} maxDots={3} className="ml-auto" />
        )}
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
  getTaskViewers?: (taskId: string) => TaskViewer[]
  isLoading?: boolean
}

function BoardColumnComponent({
  column,
  tasks,
  onTaskClick,
  onAddTask,
  getTaskViewers,
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
      <div className="flex-1 overflow-y-auto p-2">
        {isLoading ? (
          <div className="space-y-2">
            <SkeletonTaskCard />
            <SkeletonTaskCard />
          </div>
        ) : tasks.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted text-muted-foreground">
              {column.icon}
            </div>
            <p className="mt-2 text-sm text-muted-foreground">No tasks</p>
          </div>
        ) : tasks.length > VIRTUALIZATION_THRESHOLD ? (
          /* Virtualized rendering for large lists */
          <Virtuoso
            data={tasks}
            itemContent={(index, task) => (
              <div className="pb-2">
                <TaskCard
                  key={task.id}
                  task={task}
                  onClick={onTaskClick}
                  viewers={getTaskViewers?.(task.id)}
                />
              </div>
            )}
            className="h-full"
          />
        ) : (
          /* Standard rendering for small lists */
          <div className="space-y-2">
            {tasks.map((task) => (
              <TaskCard
                key={task.id}
                task={task}
                onClick={onTaskClick}
                viewers={getTaskViewers?.(task.id)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ============================================================================
// List View Component
// ============================================================================

interface ListTaskRowProps {
  task: Task
  onTaskClick?: (task: Task) => void
  getTaskViewers?: (taskId: string) => TaskViewer[]
}

function ListTaskRow({ task, onTaskClick, getTaskViewers }: ListTaskRowProps): JSX.Element {
  const priorityInfo = getPriorityInfo(task.priority)

  return (
    <div
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
        'hover:bg-accent/50 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-ring',
        'border-b border-border last:border-b-0'
      )}
    >
      {/* Type Icon */}
      <div className="flex-shrink-0">{getTaskTypeIcon(task.task_type)}</div>

      {/* Task Viewers */}
      {getTaskViewers && getTaskViewers(task.id).length > 0 && (
        <TaskViewerDots viewers={getTaskViewers(task.id)} maxDots={3} className="flex-shrink-0" />
      )}

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
}

interface ListViewProps {
  tasks: Task[]
  onTaskClick?: (task: Task) => void
  getTaskViewers?: (taskId: string) => TaskViewer[]
  isLoading?: boolean
}

function ListView({ tasks, onTaskClick, getTaskViewers, isLoading }: ListViewProps): JSX.Element {
  const [expandedStatuses, setExpandedStatuses] = useState<Set<TaskStatus>>(
    new Set(['todo', 'in_progress', 'in_review', 'issue'])
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
    return <SkeletonListView />
  }

  return (
    <div className="space-y-4">
      {BOARD_COLUMNS.map((column) => {
        const columnTasks = tasks.filter((t) => t.status === column.id)
        const isExpanded = expandedStatuses.has(column.id)
        const useVirtualization = columnTasks.length > VIRTUALIZATION_THRESHOLD

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
              <div className="border-t border-border">
                {useVirtualization ? (
                  /* Virtualized rendering for large lists */
                  <Virtuoso
                    data={columnTasks}
                    itemContent={(index, task) => (
                      <ListTaskRow
                        key={task.id}
                        task={task}
                        onTaskClick={onTaskClick}
                        getTaskViewers={getTaskViewers}
                      />
                    )}
                    style={{ height: Math.min(columnTasks.length * 52, 400) }}
                  />
                ) : (
                  /* Standard rendering for small lists */
                  columnTasks.map((task) => (
                    <ListTaskRow
                      key={task.id}
                      task={task}
                      onTaskClick={onTaskClick}
                      getTaskViewers={getTaskViewers}
                    />
                  ))
                )}
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
  derivedStatus,
  onTaskClick,
  onAddTask,
  getTaskViewers,
  className,
  enableRealtime = true,
  onRefresh,
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

  // Ref to track refresh requests
  const refreshCountRef = useRef(0)

  // Fetch tasks function
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

  // Expose refresh method via callback prop
  const onRefreshRef = useRef(onRefresh)
  onRefreshRef.current = onRefresh
  useEffect(() => {
    // Register the refresh callback with parent if provided
    if (onRefreshRef.current) {
      onRefreshRef.current(fetchTasks)
    }
  }, [fetchTasks])

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
      {/* Compact real-time status bar */}
      <div className="flex items-center gap-2 mb-2">
        {/* Real-time connection indicator */}
        {enableRealtime && (
          <div
            className={cn(
              'flex items-center gap-1 px-2 py-0.5 rounded text-xs',
              status.isConnected
                ? 'bg-green-500/10 text-green-600 dark:text-green-400'
                : 'bg-muted text-muted-foreground'
            )}
            title={status.isConnected ? 'Real-time updates active' : 'Not connected'}
          >
            {status.isConnected ? (
              <Wifi className="h-3 w-3" />
            ) : (
              <WifiOff className="h-3 w-3" />
            )}
            <span>{status.isConnected ? 'Live' : 'Offline'}</span>
          </div>
        )}

        {/* Real-time update notice */}
        {realtimeNotice && (
          <div className="flex items-center gap-1 px-2 py-0.5 rounded bg-blue-500/10 text-blue-600 dark:text-blue-400 text-xs animate-in fade-in slide-in-from-left-2 duration-200">
            <Wifi className="h-3 w-3" />
            <span>{realtimeNotice}</span>
          </div>
        )}
      </div>

      {/* Subtle progress bar when refreshing with existing data */}
      <ProgressBar isActive={isLoading && tasks.length > 0} />

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
                getTaskViewers={getTaskViewers}
                isLoading={isLoading && tasks.length === 0}
              />
            ))}
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto">
          <ListView
            tasks={tasks}
            onTaskClick={onTaskClick}
            getTaskViewers={getTaskViewers}
            isLoading={isLoading && tasks.length === 0}
          />
        </div>
      )}

    </div>
  )
}

export default ProjectBoard
