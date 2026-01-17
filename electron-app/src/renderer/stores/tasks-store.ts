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
 */

import { create } from 'zustand'
import { getAuthHeaders } from './auth-store'

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
  parent_id: string | null
  sprint_id: string | null
  story_points: number | null
  due_date: string | null
  created_at: string
  updated_at: string
  subtasks_count?: number
}

/**
 * Data for creating a task
 */
export interface TaskCreate {
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

    set({ isLoading: true, error: null, currentProjectId: projectId })

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

      const response = await window.electronAPI.post<Task>(
        `/api/projects/${projectId}/tasks`,
        data,
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

export default useTasksStore
