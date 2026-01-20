/**
 * Tasks Store
 *
 * Zustand store for managing task state in the renderer process.
 * Handles CRUD operations for tasks with API integration.
 *
 * Features:
 * - Task list with pagination
 * - Create, read, update, delete operations
 * - Loading and error states
 * - Search and filtering
 * - Status transitions
 * - Project-scoped task fetching
 * - Task status_id and rank for Kanban board
 * - Drag-and-drop task move operations
 * - Real-time task updates via WebSocket
 */

import { create } from 'zustand'
import { getAuthHeaders } from './auth-store'

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
 * Minimal user information for task assignee/reporter display
 */
export interface TaskUserInfo {
  id: string
  email: string
  display_name: string | null
}

/**
 * Task data from the API
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
  assignee: TaskUserInfo | null
  reporter: TaskUserInfo | null
  parent_id: string | null
  sprint_id: string | null
  story_points: number | null
  due_date: string | null
  created_at: string
  updated_at: string
  subtasks_count?: number

  // Kanban board fields
  task_status_id: string | null
  task_rank: string | null

  // Optimistic concurrency control
  row_version: number
}

/**
 * Data for creating a task
 */
export interface TaskCreate {
  project_id?: string
  title: string
  description?: string | null
  task_type?: TaskType
  status?: TaskStatus
  priority?: TaskPriority
  assignee_id?: string | null
  reporter_id?: string | null
  parent_id?: string | null
  sprint_id?: string | null
  story_points?: number | null
  due_date?: string | null
  task_status_id?: string | null
  task_rank?: string | null
}

/**
 * Data for updating a task
 */
export interface TaskUpdate {
  title?: string
  description?: string | null
  task_type?: TaskType
  status?: TaskStatus
  priority?: TaskPriority
  assignee_id?: string | null
  story_points?: number | null
  due_date?: string | null
  parent_id?: string | null
  sprint_id?: string | null
  task_status_id?: string | null
  task_rank?: string | null
  row_version?: number
}

/**
 * Data for moving a task (Kanban drag-and-drop)
 */
export interface TaskMove {
  target_status?: TaskStatus
  target_status_id?: string
  target_rank?: string
  before_task_id?: string
  after_task_id?: string
  row_version?: number
}

/**
 * WebSocket event data for task moved events
 */
export interface TaskMovedEventData {
  task_id: string
  project_id: string
  old_status: string | null
  new_status: string
  old_status_id: string | null
  new_status_id: string | null
  old_rank: string | null
  new_rank: string
  task: Task
  timestamp: string
  changed_by?: string
}

/**
 * Error with details
 */
export interface TaskError {
  message: string
  code?: string
  field?: string
}

/**
 * Task filter options
 */
export interface TaskFilters {
  status?: TaskStatus
  priority?: TaskPriority
  task_type?: TaskType
  assignee_id?: string
  task_status_id?: string
}

/**
 * Tasks store state
 */
export interface TasksState {
  // State
  tasks: Task[]
  selectedTask: Task | null
  isLoading: boolean
  isCreating: boolean
  isUpdating: boolean
  isDeleting: boolean
  isMoving: boolean
  error: TaskError | null

  // Pagination
  skip: number
  limit: number
  total: number
  hasMore: boolean

  // Search and filtering
  searchQuery: string
  filters: TaskFilters
  currentProjectId: string | null

  // Actions
  fetchTasks: (
    token: string | null,
    projectId: string,
    options?: { skip?: number; search?: string; filters?: TaskFilters }
  ) => Promise<void>
  fetchTask: (token: string | null, id: string) => Promise<Task | null>
  createTask: (
    token: string | null,
    projectId: string,
    data: TaskCreate
  ) => Promise<Task | null>
  updateTask: (
    token: string | null,
    id: string,
    data: TaskUpdate
  ) => Promise<Task | null>
  updateTaskStatus: (
    token: string | null,
    id: string,
    status: TaskStatus
  ) => Promise<Task | null>
  deleteTask: (token: string | null, id: string) => Promise<boolean>
  selectTask: (task: Task | null) => void
  setSearchQuery: (query: string) => void
  setFilters: (filters: TaskFilters) => void
  clearFilters: () => void
  clearError: () => void
  reset: () => void

  // Kanban board actions
  moveTask: (
    token: string | null,
    taskId: string,
    data: TaskMove
  ) => Promise<Task | null>

  // Real-time update handlers
  handleTaskMoved: (event: TaskMovedEventData) => void
  updateTaskInStore: (task: Task) => void
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Parse API error response
 */
function parseApiError(status: number, data: unknown): TaskError {
  // Handle FastAPI validation errors
  if (typeof data === 'object' && data !== null) {
    const errorData = data as Record<string, unknown>

    // FastAPI HTTPException format
    if (typeof errorData.detail === 'string') {
      return { message: errorData.detail }
    }

    // FastAPI validation error format
    if (Array.isArray(errorData.detail)) {
      const firstError = errorData.detail[0]
      if (firstError && typeof firstError === 'object') {
        const field = (firstError as Record<string, unknown>).loc
        const msg = (firstError as Record<string, unknown>).msg
        return {
          message: String(msg || 'Validation error'),
          field: Array.isArray(field) ? String(field[field.length - 1]) : undefined,
        }
      }
    }
  }

  // Default error messages based on status
  switch (status) {
    case 400:
      return { message: 'Invalid request. Please check your input.' }
    case 401:
      return { message: 'Authentication required. Please log in again.' }
    case 403:
      return { message: 'Access denied.' }
    case 404:
      return { message: 'Task not found.' }
    case 422:
      return { message: 'Validation error. Please check your input.' }
    case 500:
      return { message: 'Server error. Please try again later.' }
    default:
      return { message: 'An unexpected error occurred.' }
  }
}

// ============================================================================
// Initial State
// ============================================================================

const initialState = {
  tasks: [],
  selectedTask: null,
  isLoading: false,
  isCreating: false,
  isUpdating: false,
  isDeleting: false,
  isMoving: false,
  error: null,
  skip: 0,
  limit: 50,
  total: 0,
  hasMore: false,
  searchQuery: '',
  filters: {},
  currentProjectId: null,
}

// ============================================================================
// Store
// ============================================================================

/**
 * Tasks store using zustand
 */
export const useTasksStore = create<TasksState>((set, get) => ({
  // Initial state
  ...initialState,

  /**
   * Fetch tasks list for a project
   */
  fetchTasks: async (token, projectId, options = {}) => {
    const { skip = 0, search, filters } = options

    // Clear tasks if fetching a different project to avoid showing stale data
    const currentId = get().currentProjectId
    if (currentId && currentId !== projectId) {
      set({ tasks: [], selectedTask: null, isLoading: true, error: null, currentProjectId: projectId })
    } else {
      set({ isLoading: true, error: null, currentProjectId: projectId })
    }

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const params = new URLSearchParams()
      params.append('skip', String(skip))
      params.append('limit', String(get().limit))
      if (search) {
        params.append('search', search)
      }
      // Add filter params
      if (filters?.status) {
        params.append('status', filters.status)
      }
      if (filters?.priority) {
        params.append('priority', filters.priority)
      }
      if (filters?.task_type) {
        params.append('task_type', filters.task_type)
      }
      if (filters?.assignee_id) {
        params.append('assignee_id', filters.assignee_id)
      }
      if (filters?.task_status_id) {
        params.append('task_status_id', filters.task_status_id)
      }

      const response = await window.electronAPI.get<Task[]>(
        `/api/projects/${projectId}/tasks?${params.toString()}`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        const error = parseApiError(response.status, response.data)
        set({ isLoading: false, error })
        return
      }

      const tasks = response.data || []
      set({
        tasks: skip === 0 ? tasks : [...get().tasks, ...tasks],
        skip,
        hasMore: tasks.length === get().limit,
        isLoading: false,
        searchQuery: search || '',
        filters: filters || get().filters,
      })
    } catch (err) {
      const error: TaskError = {
        message: err instanceof Error ? err.message : 'Failed to fetch tasks',
      }
      set({ isLoading: false, error })
    }
  },

  /**
   * Fetch a single task by ID
   */
  fetchTask: async (token, id) => {
    set({ isLoading: true, error: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.get<Task>(
        `/api/tasks/${id}`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        const error = parseApiError(response.status, response.data)
        set({ isLoading: false, error })
        return null
      }

      const task = response.data
      set({ selectedTask: task, isLoading: false })
      return task
    } catch (err) {
      const error: TaskError = {
        message: err instanceof Error ? err.message : 'Failed to fetch task',
      }
      set({ isLoading: false, error })
      return null
    }
  },

  /**
   * Create a new task
   */
  createTask: async (token, projectId, data) => {
    set({ isCreating: true, error: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      // Include project_id in the request body (required by backend)
      const requestData = { ...data, project_id: projectId }

      const response = await window.electronAPI.post<Task>(
        `/api/projects/${projectId}/tasks`,
        requestData,
        getAuthHeaders(token)
      )

      if (response.status !== 201) {
        const error = parseApiError(response.status, response.data)
        set({ isCreating: false, error })
        return null
      }

      const task = response.data
      // Add the new task to the list
      set({
        tasks: [task, ...get().tasks],
        isCreating: false,
      })
      return task
    } catch (err) {
      const error: TaskError = {
        message: err instanceof Error ? err.message : 'Failed to create task',
      }
      set({ isCreating: false, error })
      return null
    }
  },

  /**
   * Update an existing task
   */
  updateTask: async (token, id, data) => {
    set({ isUpdating: true, error: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.put<Task>(
        `/api/tasks/${id}`,
        data,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        const error = parseApiError(response.status, response.data)
        set({ isUpdating: false, error })
        return null
      }

      const task = response.data
      // Update the task in the list
      const tasks = get().tasks.map((t) => (t.id === id ? task : t))
      set({
        tasks,
        selectedTask: task,
        isUpdating: false,
      })
      return task
    } catch (err) {
      const error: TaskError = {
        message: err instanceof Error ? err.message : 'Failed to update task',
      }
      set({ isUpdating: false, error })
      return null
    }
  },

  /**
   * Update task status (convenience method for status transitions)
   */
  updateTaskStatus: async (token, id, status) => {
    return get().updateTask(token, id, { status })
  },

  /**
   * Delete a task
   */
  deleteTask: async (token, id) => {
    set({ isDeleting: true, error: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.delete<void>(
        `/api/tasks/${id}`,
        getAuthHeaders(token)
      )

      if (response.status !== 204 && response.status !== 200) {
        const error = parseApiError(response.status, response.data)
        set({ isDeleting: false, error })
        return false
      }

      // Remove the task from the list
      const tasks = get().tasks.filter((t) => t.id !== id)
      set({
        tasks,
        selectedTask: null,
        isDeleting: false,
      })
      return true
    } catch (err) {
      const error: TaskError = {
        message: err instanceof Error ? err.message : 'Failed to delete task',
      }
      set({ isDeleting: false, error })
      return false
    }
  },

  /**
   * Select a task
   */
  selectTask: (task) => {
    set({ selectedTask: task })
  },

  /**
   * Set search query
   */
  setSearchQuery: (query) => {
    set({ searchQuery: query })
  },

  /**
   * Set filters
   */
  setFilters: (filters) => {
    set({ filters })
  },

  /**
   * Clear all filters
   */
  clearFilters: () => {
    set({ filters: {} })
  },

  /**
   * Clear the current error
   */
  clearError: () => {
    set({ error: null })
  },

  /**
   * Reset the store to initial state
   */
  reset: () => {
    set(initialState)
  },

  /**
   * Move a task to a new status column and/or position (Kanban drag-and-drop)
   * Supports both status changes and reordering within the same column
   */
  moveTask: async (token, taskId, data) => {
    set({ isMoving: true, error: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.put<Task>(
        `/api/tasks/${taskId}/move`,
        data,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        const error = parseApiError(response.status, response.data)
        set({ isMoving: false, error })
        return null
      }

      const task = response.data
      // Update the task in the list
      const tasks = get().tasks.map((t) => (t.id === taskId ? task : t))
      set({
        tasks,
        selectedTask: get().selectedTask?.id === taskId ? task : get().selectedTask,
        isMoving: false,
      })
      return task
    } catch (err) {
      const error: TaskError = {
        message: err instanceof Error ? err.message : 'Failed to move task',
      }
      set({ isMoving: false, error })
      return null
    }
  },

  /**
   * Handle WebSocket task_moved event
   * Updates the task's status and rank based on real-time changes from other users
   */
  handleTaskMoved: (event) => {
    const { task_id, task } = event
    const currentProjectId = get().currentProjectId

    // Only update if the task belongs to the currently viewed project
    if (currentProjectId && task.project_id === currentProjectId) {
      // Update the task in the list with the new status and rank
      const tasks = get().tasks.map((t) =>
        t.id === task_id
          ? {
              ...t,
              status: task.status,
              task_status_id: task.task_status_id,
              task_rank: task.task_rank,
              row_version: task.row_version,
            }
          : t
      )
      const selectedTask = get().selectedTask
      set({
        tasks,
        selectedTask:
          selectedTask?.id === task_id
            ? {
                ...selectedTask,
                status: task.status,
                task_status_id: task.task_status_id,
                task_rank: task.task_rank,
                row_version: task.row_version,
              }
            : selectedTask,
      })
    }
  },

  /**
   * Update a task in the store (for real-time updates)
   * Called when a WebSocket event updates a task
   */
  updateTaskInStore: (task) => {
    const currentProjectId = get().currentProjectId

    // Only update if the task belongs to the currently viewed project
    if (currentProjectId && task.project_id === currentProjectId) {
      const tasks = get().tasks.map((t) => (t.id === task.id ? task : t))
      const selectedTask = get().selectedTask
      set({
        tasks,
        selectedTask: selectedTask?.id === task.id ? task : selectedTask,
      })
    }
  },
}))

// ============================================================================
// Selectors
// ============================================================================

export const selectTasks = (state: TasksState): Task[] => state.tasks

export const selectSelectedTask = (state: TasksState): Task | null =>
  state.selectedTask

export const selectIsLoading = (state: TasksState): boolean => state.isLoading

export const selectError = (state: TasksState): TaskError | null => state.error

export const selectTasksByStatus = (status: TaskStatus) => (state: TasksState): Task[] =>
  state.tasks.filter((task) => task.status === status)

/**
 * Select tasks by task_status_id (for Kanban columns)
 */
export const selectTasksByStatusId =
  (taskStatusId: string) =>
  (state: TasksState): Task[] =>
    state.tasks.filter((task) => task.task_status_id === taskStatusId)

/**
 * Select tasks by task_status_id, sorted by task_rank (for Kanban columns)
 * Tasks without rank are sorted to the end
 */
export const selectTasksByStatusIdSorted =
  (taskStatusId: string) =>
  (state: TasksState): Task[] =>
    state.tasks
      .filter((task) => task.task_status_id === taskStatusId)
      .sort((a, b) => {
        // Tasks without rank go to the end
        if (!a.task_rank && !b.task_rank) return 0
        if (!a.task_rank) return 1
        if (!b.task_rank) return -1
        return a.task_rank.localeCompare(b.task_rank)
      })

/**
 * Select a task by ID
 */
export const selectTaskById =
  (taskId: string) =>
  (state: TasksState): Task | undefined =>
    state.tasks.find((task) => task.id === taskId)

/**
 * Select if the store is currently moving a task
 */
export const selectIsMoving = (state: TasksState): boolean => state.isMoving

/**
 * Select all tasks sorted by task_rank within each status
 * Returns tasks grouped by task_status_id
 */
export const selectTasksGroupedByStatusId = (state: TasksState): Map<string | null, Task[]> => {
  const grouped = new Map<string | null, Task[]>()

  for (const task of state.tasks) {
    const statusId = task.task_status_id
    if (!grouped.has(statusId)) {
      grouped.set(statusId, [])
    }
    grouped.get(statusId)!.push(task)
  }

  // Sort tasks within each group by task_rank
  for (const [, tasks] of grouped) {
    tasks.sort((a, b) => {
      if (!a.task_rank && !b.task_rank) return 0
      if (!a.task_rank) return 1
      if (!b.task_rank) return -1
      return a.task_rank.localeCompare(b.task_rank)
    })
  }

  return grouped
}

export default useTasksStore
