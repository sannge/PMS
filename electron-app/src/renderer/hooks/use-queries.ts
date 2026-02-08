/**
 * TanStack Query Hooks for Data Fetching
 *
 * Provides React Query hooks for applications, projects, and tasks.
 * Implements stale-while-revalidate pattern with optimistic updates.
 *
 * @see https://tanstack.com/query/latest
 */

import {
  useQuery,
  useInfiniteQuery,
  useMutation,
  useQueryClient,
  UseQueryResult,
  UseMutationResult,
  UseInfiniteQueryResult,
  InfiniteData,
} from '@tanstack/react-query'
import { useAuthStore } from '@/contexts/auth-context'
import { queryKeys, queryClient } from '@/lib/query-client'

// ============================================================================
// Types
// ============================================================================

// Re-export types from existing stores for compatibility
export type OwnershipType = 'created' | 'invited'
export type ApplicationRole = 'owner' | 'editor' | 'viewer'
export type ProjectType = 'kanban' | 'scrum'
export type ProjectDerivedStatus = 'Todo' | 'In Progress' | 'Issue' | 'Done'

// Task-related types (matching backend API)
export type TaskPriority = 'lowest' | 'low' | 'medium' | 'high' | 'highest'
export type TaskType = 'story' | 'bug' | 'epic' | 'subtask' | 'task'

/** Check if a task is in Done status using task_status */
export function isTaskDone(task: { task_status: TaskStatusInfo }): boolean {
  return task.task_status.category === 'Done'
}

/** Nested task status info returned from the API */
export interface TaskStatusInfo {
  id: string
  name: string
  category: string
  rank: number
}

export interface TaskUserInfo {
  id: string
  email: string
  display_name: string | null
  full_name: string | null
  avatar_url: string | null
}

export interface Application {
  id: string
  name: string
  description: string | null
  owner_id: string | null
  projects_count: number
  created_at: string
  updated_at: string
  ownership_type?: OwnershipType
  user_role?: ApplicationRole
}

export interface ApplicationCreate {
  name: string
  description?: string | null
}

export interface ApplicationUpdate {
  name?: string
  description?: string | null
}

export interface Project {
  id: string
  application_id: string
  name: string
  key: string
  description: string | null
  project_type: ProjectType
  tasks_count: number
  due_date: string
  created_at: string
  updated_at: string
  created_by: string | null
  project_owner_user_id: string | null
  derived_status: ProjectDerivedStatus | null
  derived_status_id: string | null
  override_status_id: string | null
  override_reason: string | null
  override_by_user_id: string | null
  override_expires_at: string | null
  row_version: number
  archived_at: string | null
  application_name?: string | null
}

export interface ProjectCursorPage {
  items: Project[]
  next_cursor: string | null
  total?: number
  can_restore?: boolean
}

export interface ProjectCreate {
  name: string
  key: string
  description?: string | null
  project_type?: ProjectType
  project_owner_user_id?: string | null
  due_date: string
}

export interface ProjectUpdate {
  name?: string
  description?: string | null
  project_type?: ProjectType
  project_owner_user_id?: string | null
  due_date?: string
  row_version?: number
}

export interface Task {
  id: string
  project_id: string
  task_key: string
  title: string
  description: string | null
  task_type: TaskType
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
  completed_at: string | null
  archived_at: string | null
  subtasks_count?: number
  // Kanban board fields
  task_status_id: string
  task_status: TaskStatusInfo
  task_rank: string | null
  // Optimistic concurrency control
  row_version: number
  // Checklist aggregates (populated by API)
  checklist_total?: number
  checklist_done?: number
  // Cross-app fields (populated by /api/me/tasks only)
  application_id?: string | null
  application_name?: string | null
}

export interface TaskCursorPage {
  items: Task[]
  next_cursor: string | null
  total?: number
  can_restore?: boolean
}

export interface TaskCreate {
  project_id?: string
  title: string
  description?: string | null
  task_type?: TaskType
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

export interface TaskUpdate {
  title?: string
  description?: string | null
  task_type?: TaskType
  priority?: TaskPriority
  assignee_id?: string | null
  reporter_id?: string | null
  parent_id?: string | null
  sprint_id?: string | null
  story_points?: number | null
  due_date?: string | null
  task_status_id?: string | null
  task_rank?: string | null
  row_version?: number
}

export interface TaskMovePayload {
  taskId: string
  /** Target task_status_id (UUID from TaskStatuses table) */
  targetStatusId: string
  /** Target status name for optimistic updates */
  targetStatusName?: string
  /** Target status category for optimistic done-check */
  targetStatusCategory?: string
  /** Target status rank for optimistic updates */
  targetStatusRank?: number
  /** Direct rank string (optional, auto-calculated if not provided) */
  targetRank?: string
  /** Task ID to position before (optional) */
  beforeTaskId?: string
  /** Task ID to position after (optional) */
  afterTaskId?: string
}

export interface ApiError {
  message: string
  code?: string
  field?: string
}

export interface TaskStatus {
  id: string
  project_id: string
  name: string
  category: string
  rank: number
  created_at: string
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Get authorization headers with bearer token
 */
function getAuthHeaders(token: string | null): Record<string, string> {
  if (!token) return {}
  return { Authorization: `Bearer ${token}` }
}

/**
 * Parse API error response
 */
function parseApiError(status: number, data: unknown): ApiError {
  if (typeof data === 'object' && data !== null) {
    const errorData = data as Record<string, unknown>
    if (typeof errorData.detail === 'string') {
      return { message: errorData.detail }
    }
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

  switch (status) {
    case 400:
      return { message: 'Invalid request. Please check your input.' }
    case 401:
      return { message: 'Authentication required. Please log in again.' }
    case 403:
      return { message: 'Access denied.' }
    case 404:
      return { message: 'Resource not found.' }
    case 422:
      return { message: 'Validation error. Please check your input.' }
    case 500:
      return { message: 'Server error. Please try again later.' }
    default:
      return { message: 'An unexpected error occurred.' }
  }
}

// ============================================================================
// Application Queries
// ============================================================================

/**
 * Fetch all applications for the current user.
 * Uses 5 min stale time, 24h cache for offline support.
 */
export function useApplications(): UseQueryResult<Application[], Error> {
  const token = useAuthStore((s) => s.token)

  return useQuery({
    queryKey: queryKeys.applications,
    queryFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.get<Application[]>(
        '/api/applications',
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data || []
    },
    enabled: !!token,
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 24 * 60 * 60 * 1000, // 24 hours
  })
}

/**
 * Fetch a single application by ID.
 */
export function useApplication(id: string | undefined): UseQueryResult<Application, Error> {
  const token = useAuthStore((s) => s.token)

  return useQuery({
    queryKey: queryKeys.application(id || ''),
    queryFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.get<Application>(
        `/api/applications/${id}`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
    enabled: !!token && !!id,
    staleTime: 5 * 60 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
  })
}

/**
 * Create a new application.
 */
export function useCreateApplication(): UseMutationResult<Application, Error, ApplicationCreate> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: ApplicationCreate) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.post<Application>(
        '/api/applications',
        data,
        getAuthHeaders(token)
      )

      if (response.status !== 201) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
    onSuccess: (newApp) => {
      // Add to applications list
      queryClient.setQueryData<Application[]>(queryKeys.applications, (old) =>
        old ? [newApp, ...old] : [newApp]
      )
    },
  })
}

/**
 * Update an application.
 */
export function useUpdateApplication(
  id: string
): UseMutationResult<Application, Error, ApplicationUpdate> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: ApplicationUpdate) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.put<Application>(
        `/api/applications/${id}`,
        data,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
    onSuccess: (updatedApp) => {
      // Update in applications list
      queryClient.setQueryData<Application[]>(queryKeys.applications, (old) =>
        old?.map((app) => (app.id === id ? updatedApp : app))
      )
      // Update individual application
      queryClient.setQueryData(queryKeys.application(id), updatedApp)
    },
  })
}

/**
 * Delete an application.
 */
export function useDeleteApplication(id: string): UseMutationResult<void, Error, void> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.delete<void>(
        `/api/applications/${id}`,
        getAuthHeaders(token)
      )

      if (response.status !== 204 && response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }
    },
    onSuccess: () => {
      // Remove from applications list
      queryClient.setQueryData<Application[]>(queryKeys.applications, (old) =>
        old?.filter((app) => app.id !== id)
      )
      // Remove individual application cache
      queryClient.removeQueries({ queryKey: queryKeys.application(id) })
    },
  })
}

// ============================================================================
// Project Queries
// ============================================================================

/**
 * Fetch projects for an application.
 * Uses 1 min stale time to keep task counts relatively fresh.
 */
export function useProjects(applicationId: string | undefined): UseQueryResult<Project[], Error> {
  const token = useAuthStore((s) => s.token)

  return useQuery({
    queryKey: queryKeys.projects(applicationId || ''),
    queryFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.get<Project[]>(
        `/api/applications/${applicationId}/projects`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data || []
    },
    enabled: !!token && !!applicationId,
    staleTime: 60 * 1000, // 1 minute - task counts can change frequently
    gcTime: 24 * 60 * 60 * 1000,
  })
}

/**
 * Fetch a single project by ID.
 */
export function useProject(id: string | undefined): UseQueryResult<Project, Error> {
  const token = useAuthStore((s) => s.token)

  return useQuery({
    queryKey: queryKeys.project(id || ''),
    queryFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.get<Project>(`/api/projects/${id}`, getAuthHeaders(token))

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
    enabled: !!token && !!id,
    staleTime: 5 * 60 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
  })
}

/**
 * Create a new project.
 */
export function useCreateProject(
  applicationId: string
): UseMutationResult<Project, Error, ProjectCreate> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: ProjectCreate) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.post<Project>(
        `/api/applications/${applicationId}/projects`,
        data,
        getAuthHeaders(token)
      )

      if (response.status !== 201) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
    onSuccess: (newProject) => {
      // Add to projects list
      queryClient.setQueryData<Project[]>(queryKeys.projects(applicationId), (old) =>
        old ? [newProject, ...old] : [newProject]
      )
      // Increment projects_count in application
      queryClient.setQueryData<Application[]>(queryKeys.applications, (old) =>
        old?.map((app) =>
          app.id === applicationId ? { ...app, projects_count: app.projects_count + 1 } : app
        )
      )
    },
  })
}

/**
 * Update a project.
 */
export function useUpdateProject(
  id: string,
  applicationId: string
): UseMutationResult<Project, Error, ProjectUpdate> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: ProjectUpdate) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.put<Project>(
        `/api/projects/${id}`,
        data,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
    onSuccess: (updatedProject) => {
      // Update in projects list
      queryClient.setQueryData<Project[]>(queryKeys.projects(applicationId), (old) =>
        old?.map((p) => (p.id === id ? updatedProject : p))
      )
      // Update individual project
      queryClient.setQueryData(queryKeys.project(id), updatedProject)
    },
  })
}

/**
 * Delete a project.
 */
export function useDeleteProject(
  id: string,
  applicationId: string
): UseMutationResult<void, Error, void> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.delete<void>(
        `/api/projects/${id}`,
        getAuthHeaders(token)
      )

      if (response.status !== 204 && response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }
    },
    onSuccess: () => {
      // Remove from projects list
      queryClient.setQueryData<Project[]>(queryKeys.projects(applicationId), (old) =>
        old?.filter((p) => p.id !== id)
      )
      // Decrement projects_count in application
      queryClient.setQueryData<Application[]>(queryKeys.applications, (old) =>
        old?.map((app) =>
          app.id === applicationId
            ? { ...app, projects_count: Math.max(0, app.projects_count - 1) }
            : app
        )
      )
      // Remove individual project cache
      queryClient.removeQueries({ queryKey: queryKeys.project(id) })
    },
  })
}

// ============================================================================
// Task Queries
// ============================================================================

/**
 * Fetch tasks for a project.
 * Uses 30 sec stale time since tasks change frequently.
 */
export function useTasks(projectId: string | undefined): UseQueryResult<Task[], Error> {
  const token = useAuthStore((s) => s.token)

  return useQuery({
    queryKey: queryKeys.tasks(projectId || ''),
    queryFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.get<Task[]>(
        `/api/projects/${projectId}/tasks`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data || []
    },
    enabled: !!token && !!projectId,
    staleTime: 30 * 1000, // 30 seconds - tasks change frequently
    gcTime: 24 * 60 * 60 * 1000,
  })
}

/**
 * Fetch a single task by ID.
 */
export function useTask(id: string | undefined): UseQueryResult<Task, Error> {
  const token = useAuthStore((s) => s.token)

  return useQuery({
    queryKey: queryKeys.task(id || ''),
    queryFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.get<Task>(`/api/tasks/${id}`, getAuthHeaders(token))

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
    enabled: !!token && !!id,
    staleTime: 30 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
  })
}

/**
 * Create a new task.
 */
export function useCreateTask(projectId: string): UseMutationResult<Task, Error, TaskCreate> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: TaskCreate) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.post<Task>(
        `/api/projects/${projectId}/tasks`,
        { ...data, project_id: projectId },
        getAuthHeaders(token)
      )

      if (response.status !== 201) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
    onSuccess: (newTask) => {
      // Add to tasks list
      queryClient.setQueryData<Task[]>(queryKeys.tasks(projectId), (old) =>
        old ? [...old, newTask] : [newTask]
      )
      // Optimistically increment tasks_count on the single project cache
      queryClient.setQueryData<Project>(queryKeys.project(projectId), (old) =>
        old ? { ...old, tasks_count: old.tasks_count + 1 } : old
      )
      // Also update tasks_count in any project list caches that contain this project.
      // queryKeys.projects(appId) = ['projects', appId] — we don't know appId here,
      // so scan all ['projects', *] list caches (but NOT ['projects', *, 'archived']).
      const allProjectQueries = queryClient.getQueriesData<Project[]>({
        queryKey: ['projects'],
      })
      for (const [queryKey, projects] of allProjectQueries) {
        // Skip archived project queries (InfiniteData, not Project[]) and non-arrays
        if (!projects || !Array.isArray(projects)) continue
        if (projects.some((p) => p.id === projectId)) {
          queryClient.setQueryData<Project[]>(queryKey, (old) =>
            old?.map((p) =>
              p.id === projectId ? { ...p, tasks_count: p.tasks_count + 1 } : p
            )
          )
        }
      }
    },
  })
}

/**
 * Update a task with optimistic update.
 */
export function useUpdateTask(
  taskId: string,
  projectId: string
): UseMutationResult<Task, Error, TaskUpdate, { previous?: Task }> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: TaskUpdate) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.put<Task>(
        `/api/tasks/${taskId}`,
        data,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
    // Optimistic update
    onMutate: async (newData) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: queryKeys.task(taskId) })

      // Snapshot previous value
      const previous = queryClient.getQueryData<Task>(queryKeys.task(taskId))

      // Optimistically update
      if (previous) {
        queryClient.setQueryData(queryKeys.task(taskId), { ...previous, ...newData })
      }

      // Update in list too
      queryClient.setQueryData<Task[]>(queryKeys.tasks(projectId), (old) =>
        old?.map((t) => (t.id === taskId ? { ...t, ...newData } as Task : t))
      )

      return { previous }
    },
    onSuccess: (updatedTask) => {
      // Sync authoritative server response to cache
      queryClient.setQueryData(queryKeys.task(taskId), updatedTask)
      queryClient.setQueryData<Task[]>(queryKeys.tasks(projectId), (old) =>
        old?.map((t) => (t.id === taskId ? updatedTask : t))
      )
    },
    onError: (_err, _newData, context) => {
      // Rollback on error
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.task(taskId), context.previous)
      }
      // Re-sync cache after failed optimistic update
      queryClient.invalidateQueries({ queryKey: queryKeys.task(taskId) })
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks(projectId) })
    },
  })
}

/**
 * Delete a task.
 */
export function useDeleteTask(
  taskId: string,
  projectId: string
): UseMutationResult<void, Error, void> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.delete<void>(
        `/api/tasks/${taskId}`,
        getAuthHeaders(token)
      )

      if (response.status !== 204 && response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }
    },
    onSuccess: () => {
      // Remove from tasks list
      queryClient.setQueryData<Task[]>(queryKeys.tasks(projectId), (old) =>
        old?.filter((t) => t.id !== taskId)
      )
      // Remove individual task cache
      queryClient.removeQueries({ queryKey: queryKeys.task(taskId) })
      // Optimistically decrement tasks_count on the single project cache
      queryClient.setQueryData<Project>(queryKeys.project(projectId), (old) =>
        old ? { ...old, tasks_count: Math.max(0, old.tasks_count - 1) } : old
      )
      // Also update tasks_count in any project list caches that contain this project
      const allProjectQueries = queryClient.getQueriesData<Project[]>({
        queryKey: ['projects'],
      })
      for (const [queryKey, projects] of allProjectQueries) {
        if (!projects || !Array.isArray(projects)) continue
        if (projects.some((p) => p.id === projectId)) {
          queryClient.setQueryData<Project[]>(queryKey, (old) =>
            old?.map((p) =>
              p.id === projectId ? { ...p, tasks_count: Math.max(0, p.tasks_count - 1) } : p
            )
          )
        }
      }
    },
  })
}

/**
 * Move a task (change status/position) with optimistic update.
 * Used for Kanban drag-and-drop.
 *
 * @example
 * ```tsx
 * const moveTask = useMoveTask(projectId)
 *
 * // Move task to new status
 * moveTask.mutate({
 *   taskId: 'task-123',
 *   targetStatus: 'in_progress',
 * })
 *
 * // Move task to new position within column
 * moveTask.mutate({
 *   taskId: 'task-123',
 *   targetStatus: 'todo',
 *   beforeTaskId: 'task-456', // position before this task
 * })
 * ```
 */
export function useMoveTask(
  projectId: string
): UseMutationResult<Task, Error, TaskMovePayload, { previous?: Task[] }> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ taskId, targetStatusId, targetRank, beforeTaskId, afterTaskId }: TaskMovePayload) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      // Build request body matching backend API
      const body: Record<string, unknown> = {
        target_status_id: targetStatusId,
      }
      if (targetRank !== undefined) {
        body.target_rank = targetRank
      }
      if (beforeTaskId !== undefined) {
        body.before_task_id = beforeTaskId
      }
      if (afterTaskId !== undefined) {
        body.after_task_id = afterTaskId
      }

      const response = await window.electronAPI.put<Task>(
        `/api/tasks/${taskId}/move`,
        body,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
    // Optimistic update for instant drag-drop feedback
    onMutate: async ({ taskId, targetStatusId, targetStatusName, targetStatusCategory, targetStatusRank }) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.tasks(projectId) })

      const previous = queryClient.getQueryData<Task[]>(queryKeys.tasks(projectId))

      // Optimistically update task status and completed_at
      const now = new Date().toISOString()
      queryClient.setQueryData<Task[]>(queryKeys.tasks(projectId), (old) =>
        old?.map((t) => {
          if (t.id !== taskId) return t
          const isDone = (targetStatusCategory ?? targetStatusName) === 'Done'
          const wasDone = t.task_status.category === 'Done'
          const completed_at = isDone
            ? (t.completed_at || now)
            : (wasDone ? null : t.completed_at)
          return {
            ...t,
            task_status_id: targetStatusId,
            task_status: {
              id: targetStatusId,
              name: targetStatusName ?? t.task_status.name,
              category: targetStatusCategory ?? t.task_status.category,
              rank: targetStatusRank ?? t.task_status.rank,
            },
            completed_at,
          }
        })
      )

      return { previous }
    },
    onSuccess: (movedTask) => {
      // Sync authoritative server response to cache
      queryClient.setQueryData<Task[]>(queryKeys.tasks(projectId), (old) =>
        old?.map((t) => (t.id === movedTask.id ? movedTask : t))
      )
    },
    onError: (_err, _vars, context) => {
      // Rollback on error
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.tasks(projectId), context.previous)
      }
      // Re-sync cache after failed optimistic update
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks(projectId) })
    },
  })
}

// ============================================================================
// Task Status Queries
// ============================================================================

/**
 * Fetch task statuses for a project.
 */
export function useTaskStatuses(projectId: string | undefined): UseQueryResult<TaskStatus[], Error> {
  const token = useAuthStore((s) => s.token)

  return useQuery({
    queryKey: queryKeys.statuses(projectId || ''),
    queryFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.get<TaskStatus[]>(
        `/api/projects/${projectId}/statuses`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data || []
    },
    enabled: !!token && !!projectId,
    staleTime: 5 * 60 * 1000, // Statuses don't change often
    gcTime: 24 * 60 * 60 * 1000,
  })
}

// ============================================================================
// Archived Tasks Queries
// ============================================================================

/**
 * Fetch archived tasks count for a project (lightweight).
 * Only fetches 1 item to get the total count for display on tabs.
 */
export function useArchivedTasksCount(
  projectId: string | undefined
): UseQueryResult<number, Error> {
  const token = useAuthStore((s) => s.token)

  return useQuery({
    queryKey: [...queryKeys.archivedTasks(projectId || ''), 'count'],
    queryFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      // Fetch with limit=1 just to get the total count
      const response = await window.electronAPI.get<TaskCursorPage>(
        `/api/projects/${projectId}/tasks/archived?limit=1`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data.total ?? 0
    },
    enabled: !!token && !!projectId,
    staleTime: 30 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
  })
}

/**
 * Fetch archived tasks for a project with infinite scroll.
 * Uses cursor-based pagination with optional search.
 */
export function useArchivedTasks(
  projectId: string | undefined,
  search?: string
): UseInfiniteQueryResult<InfiniteData<TaskCursorPage>, Error> {
  const token = useAuthStore((s) => s.token)

  return useInfiniteQuery({
    queryKey: [...queryKeys.archivedTasks(projectId || ''), search || ''],
    queryFn: async ({ pageParam }) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const params = new URLSearchParams()
      params.set('limit', '30')
      if (pageParam) {
        params.set('cursor', pageParam)
      }
      if (search) {
        params.set('search', search)
      }

      const response = await window.electronAPI.get<TaskCursorPage>(
        `/api/projects/${projectId}/tasks/archived?${params.toString()}`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: !!token && !!projectId,
    staleTime: 30 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
  })
}

/**
 * Unarchive a task (restore it to Done column).
 * Uses optimistic updates for instant feedback.
 */
export function useUnarchiveTask(
  projectId: string
): UseMutationResult<Task, Error, string, { removedTask: Task | undefined }> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (taskId: string) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.post<Task>(
        `/api/tasks/${taskId}/unarchive`,
        {},
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
    // Optimistic update: remove task from all archived query caches
    onMutate: async (taskId: string) => {
      // Cancel any outgoing refetches (partial match cancels all search variants)
      await queryClient.cancelQueries({ queryKey: queryKeys.archivedTasks(projectId) })
      await queryClient.cancelQueries({ queryKey: queryKeys.tasks(projectId) })

      // Find the task being removed (for toast message in component)
      let removedTask: Task | undefined

      // Get all cached queries that match archived tasks for this project
      // This handles both with and without search parameter
      const archivedQueries = queryClient.getQueriesData<InfiniteData<TaskCursorPage>>({
        queryKey: queryKeys.archivedTasks(projectId),
      })

      // Optimistically remove from ALL matching caches (handles search variants)
      let taskWasFound = false
      for (const [queryKey, data] of archivedQueries) {
        // Skip non-infinite query data (e.g., the count query which is just a number)
        if (!data || !data.pages || !Array.isArray(data.pages)) {
          continue
        }
        // Check if this task exists in this specific query's data
        let taskFoundInThisQuery = false
        for (const page of data.pages) {
          const found = page.items.find((t) => t.id === taskId)
          if (found) {
            taskFoundInThisQuery = true
            taskWasFound = true
            // Save the task for return value (only need to find once across all queries)
            if (!removedTask) {
              removedTask = found
            }
            break
          }
        }

        // Only update cache if task exists in this query
        if (taskFoundInThisQuery) {
          queryClient.setQueryData<InfiniteData<TaskCursorPage>>(queryKey, {
            ...data,
            pages: data.pages.map((page) => ({
              ...page,
              items: page.items.filter((t) => t.id !== taskId),
            })),
          })
        }
      }

      // Also update the standalone count query used for tab badge
      if (taskWasFound) {
        queryClient.setQueryData<number>(
          [...queryKeys.archivedTasks(projectId), 'count'],
          (old) => (old != null && old > 0 ? old - 1 : 0)
        )
      }

      return { removedTask }
    },
    onSuccess: (restoredTask) => {
      // Add the restored task to the main tasks list (with archived_at cleared)
      queryClient.setQueryData<Task[]>(queryKeys.tasks(projectId), (old) => {
        if (!old) return [restoredTask]
        // Check if task already exists (avoid duplicates)
        const exists = old.some((t) => t.id === restoredTask.id)
        return exists ? old.map((t) => (t.id === restoredTask.id ? restoredTask : t)) : [...old, restoredTask]
      })

      // Get the project to check if it might have been restored
      const cachedProject = queryClient.getQueryData<Project>(queryKeys.project(projectId))

      // Check if project was archived - if so, the backend will restore it
      const projectWasArchived = cachedProject?.archived_at != null

      // Update project cache: clear archived_at if it was archived.
      // tasks_count is NOT incremented because it now counts all tasks (active + archived),
      // and the unarchived task was already included in the total.
      queryClient.setQueryData<Project>(queryKeys.project(projectId), (old) => {
        if (!old) return old
        return {
          ...old,
          archived_at: null, // Clear archived_at since restoring a task restores the project
        }
      })

      if (projectWasArchived && cachedProject?.application_id) {
        // Project was archived and is now restored
        // Invalidate the specific application's projects and archived projects lists
        queryClient.invalidateQueries({ queryKey: queryKeys.projects(cachedProject.application_id) })
        queryClient.invalidateQueries({ queryKey: queryKeys.archivedProjects(cachedProject.application_id) })
      } else {
        // Project wasn't archived — no tasks_count update needed.
        // tasks_count now includes all tasks (active + archived), so unarchiving
        // a task doesn't change the total. The task was already counted.
      }
    },
    onError: () => {
      // On error, invalidate to refetch correct state
      queryClient.invalidateQueries({ queryKey: queryKeys.archivedTasks(projectId) })
    },
    // No onSettled - optimistic updates handle the UI, avoid unnecessary refetches
  })
}

// ============================================================================
// Archived Projects Queries
// ============================================================================

/**
 * Fetch archived projects count for an application (lightweight).
 * Only fetches 1 item to get the total count for display on tabs.
 */
export function useArchivedProjectsCount(
  applicationId: string | undefined
): UseQueryResult<number, Error> {
  const token = useAuthStore((s) => s.token)

  return useQuery({
    queryKey: [...queryKeys.archivedProjects(applicationId || ''), 'count'],
    queryFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      // Fetch with limit=1 just to get the total count
      const response = await window.electronAPI.get<ProjectCursorPage>(
        `/api/applications/${applicationId}/projects/archived?limit=1`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data.total ?? 0
    },
    enabled: !!token && !!applicationId,
    staleTime: 30 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
  })
}

/**
 * Fetch archived projects for an application with infinite scroll.
 * Uses cursor-based pagination with optional search.
 */
export function useArchivedProjects(
  applicationId: string | undefined,
  search?: string
): UseInfiniteQueryResult<InfiniteData<ProjectCursorPage>, Error> {
  const token = useAuthStore((s) => s.token)

  return useInfiniteQuery({
    queryKey: [...queryKeys.archivedProjects(applicationId || ''), search || ''],
    queryFn: async ({ pageParam }) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const params = new URLSearchParams()
      params.set('limit', '30')
      if (pageParam) {
        params.set('cursor', pageParam)
      }
      if (search) {
        params.set('search', search)
      }

      const response = await window.electronAPI.get<ProjectCursorPage>(
        `/api/applications/${applicationId}/projects/archived?${params.toString()}`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: !!token && !!applicationId,
    staleTime: 30 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
  })
}

// ============================================================================
// My Tasks Queries (Application-Level)
// ============================================================================

/**
 * Fetch pending tasks assigned to the current user across all projects in an application.
 * Uses infinite scroll with cursor-based pagination and optional search.
 */
export function useMyPendingTasks(
  applicationId: string | undefined,
  search?: string
): UseInfiniteQueryResult<InfiniteData<TaskCursorPage>, Error> {
  const token = useAuthStore((s) => s.token)

  return useInfiniteQuery({
    queryKey: [...queryKeys.myPendingTasks(applicationId || ''), search || ''],
    queryFn: async ({ pageParam }) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const params = new URLSearchParams()
      params.set('limit', '30')
      if (pageParam) {
        params.set('cursor', pageParam)
      }
      if (search) {
        params.set('search', search)
      }

      const response = await window.electronAPI.get<TaskCursorPage>(
        `/api/applications/${applicationId}/tasks/my?${params.toString()}`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: !!token && !!applicationId,
    staleTime: 30 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
  })
}

/**
 * Fetch recently completed tasks assigned to the current user.
 * Tasks completed within the last 7 days (not yet archived).
 */
export function useMyCompletedTasks(
  applicationId: string | undefined,
  search?: string
): UseInfiniteQueryResult<InfiniteData<TaskCursorPage>, Error> {
  const token = useAuthStore((s) => s.token)

  return useInfiniteQuery({
    queryKey: [...queryKeys.myCompletedTasks(applicationId || ''), search || ''],
    queryFn: async ({ pageParam }) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const params = new URLSearchParams()
      params.set('limit', '30')
      if (pageParam) {
        params.set('cursor', pageParam)
      }
      if (search) {
        params.set('search', search)
      }

      const response = await window.electronAPI.get<TaskCursorPage>(
        `/api/applications/${applicationId}/tasks/my/completed?${params.toString()}`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: !!token && !!applicationId,
    staleTime: 30 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
  })
}

// ============================================================================
// Document Content Mutations
// ============================================================================

/** Input type for saving document content */
export interface SaveDocumentContentInput {
  documentId: string
  content_json: string
  row_version: number
}

/** Response type for document content save (matches backend DocumentResponse) */
export interface DocumentContentResponse {
  id: string
  content_json: string | null
  content_markdown: string | null
  content_plain: string | null
  row_version: number
  updated_at: string
}

/**
 * Save document content with optimistic concurrency control.
 * Sends PUT to /api/documents/{documentId}/content with content_json and row_version.
 * Returns 409 on version conflict.
 */
export function useSaveDocumentContent(): UseMutationResult<
  DocumentContentResponse,
  Error,
  SaveDocumentContentInput
> {
  const token = useAuthStore((s) => s.token)

  return useMutation({
    mutationFn: async ({ documentId, content_json, row_version }: SaveDocumentContentInput) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.put<DocumentContentResponse>(
        `/api/documents/${documentId}/content`,
        { content_json, row_version },
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
  })
}

/**
 * Fetch archived tasks assigned to the current user.
 * Tasks that have been in Done status for 7+ days.
 */
export function useMyArchivedTasks(
  applicationId: string | undefined,
  search?: string
): UseInfiniteQueryResult<InfiniteData<TaskCursorPage>, Error> {
  const token = useAuthStore((s) => s.token)

  return useInfiniteQuery({
    queryKey: [...queryKeys.myArchivedTasks(applicationId || ''), search || ''],
    queryFn: async ({ pageParam }) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const params = new URLSearchParams()
      params.set('limit', '30')
      if (pageParam) {
        params.set('cursor', pageParam)
      }
      if (search) {
        params.set('search', search)
      }

      const response = await window.electronAPI.get<TaskCursorPage>(
        `/api/applications/${applicationId}/tasks/my/archived?${params.toString()}`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: !!token && !!applicationId,
    staleTime: 30 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
  })
}

// ============================================================================
// My Projects Queries (Dashboard)
// ============================================================================

export interface MyProjectsParams {
  search?: string
  sortBy?: 'due_date' | 'name' | 'updated_at'
  sortOrder?: 'asc' | 'desc'
  status?: string
}

/**
 * Fetch projects for the dashboard with sorting and filtering.
 * Uses infinite scroll with cursor-based pagination.
 */
export function useMyProjects(
  applicationId: string | undefined,
  params?: MyProjectsParams
): UseInfiniteQueryResult<InfiniteData<ProjectCursorPage>, Error> {
  const token = useAuthStore((s) => s.token)

  return useInfiniteQuery({
    queryKey: [
      ...queryKeys.myProjects(applicationId || ''),
      params?.search || '',
      params?.sortBy || 'due_date',
      params?.sortOrder || 'asc',
      params?.status || '',
    ],
    queryFn: async ({ pageParam }) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const searchParams = new URLSearchParams()
      searchParams.set('limit', '30')
      if (pageParam) {
        searchParams.set('cursor', pageParam)
      }
      if (params?.search) {
        searchParams.set('search', params.search)
      }
      if (params?.sortBy) {
        searchParams.set('sort_by', params.sortBy)
      }
      if (params?.sortOrder) {
        searchParams.set('sort_order', params.sortOrder)
      }
      if (params?.status) {
        searchParams.set('status', params.status)
      }

      const response = await window.electronAPI.get<ProjectCursorPage>(
        `/api/applications/${applicationId}/projects/my?${searchParams.toString()}`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: !!token && !!applicationId,
    staleTime: 30 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
  })
}

/**
 * Fetch projects across all applications for the dashboard.
 * Uses infinite scroll with cursor-based pagination.
 */
export function useMyProjectsCrossApp(
  params?: MyProjectsParams
): UseInfiniteQueryResult<InfiniteData<ProjectCursorPage>, Error> {
  const token = useAuthStore((s) => s.token)

  return useInfiniteQuery({
    queryKey: [
      ...queryKeys.myProjectsCrossApp,
      params?.search || '',
      params?.sortBy || 'due_date',
      params?.sortOrder || 'asc',
      params?.status || '',
    ],
    queryFn: async ({ pageParam }) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const searchParams = new URLSearchParams()
      searchParams.set('limit', '30')
      if (pageParam) {
        searchParams.set('cursor', pageParam)
      }
      if (params?.search) {
        searchParams.set('search', params.search)
      }
      if (params?.sortBy) {
        searchParams.set('sort_by', params.sortBy)
      }
      if (params?.sortOrder) {
        searchParams.set('sort_order', params.sortOrder)
      }
      if (params?.status) {
        searchParams.set('status', params.status)
      }

      const response = await window.electronAPI.get<ProjectCursorPage>(
        `/api/me/projects?${searchParams.toString()}`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: !!token,
    staleTime: 30 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
  })
}

/**
 * Parameters for cross-app task queries.
 */
export interface MyTasksParams {
  search?: string
  sortBy?: 'due_date' | 'title' | 'updated_at'
  sortOrder?: 'asc' | 'desc'
  status?: string
}

/**
 * Fetch pending tasks across all applications for the dashboard.
 * Uses infinite scroll with cursor-based pagination.
 */
export function useMyTasksCrossApp(
  params?: MyTasksParams
): UseInfiniteQueryResult<InfiniteData<TaskCursorPage>, Error> {
  const token = useAuthStore((s) => s.token)

  return useInfiniteQuery({
    queryKey: [
      ...queryKeys.myTasksCrossApp,
      params?.search || '',
      params?.sortBy || 'updated_at',
      params?.sortOrder || 'desc',
      params?.status || '',
    ],
    queryFn: async ({ pageParam }) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const searchParams = new URLSearchParams()
      searchParams.set('limit', '30')
      if (pageParam) {
        searchParams.set('cursor', pageParam)
      }
      if (params?.search) {
        searchParams.set('search', params.search)
      }
      if (params?.sortBy) {
        searchParams.set('sort_by', params.sortBy)
      }
      if (params?.sortOrder) {
        searchParams.set('sort_order', params.sortOrder)
      }
      if (params?.status) {
        searchParams.set('status_name', params.status)
      }

      const response = await window.electronAPI.get<TaskCursorPage>(
        `/api/me/tasks?${searchParams.toString()}`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: !!token,
    staleTime: 30 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
  })
}
