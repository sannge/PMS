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
  useMutation,
  useQueryClient,
  UseQueryResult,
  UseMutationResult,
} from '@tanstack/react-query'
import { useAuthStore } from '@/stores/auth-store'
import { queryKeys, queryClient } from '@/lib/query-client'

// ============================================================================
// Types
// ============================================================================

// Re-export types from existing stores for compatibility
export type OwnershipType = 'created' | 'invited'
export type ApplicationRole = 'owner' | 'editor' | 'viewer'
export type ProjectType = 'kanban' | 'scrum'
export type ProjectDerivedStatus = 'Todo' | 'In Progress' | 'Issue' | 'Done'

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
}

export interface ProjectCreate {
  name: string
  key: string
  description?: string | null
  project_type?: ProjectType
  project_owner_user_id?: string | null
}

export interface ProjectUpdate {
  name?: string
  description?: string | null
  project_type?: ProjectType
  project_owner_user_id?: string | null
  row_version?: number
}

export interface Task {
  id: string
  project_id: string
  title: string
  description: string | null
  status_id: string
  status_name: string
  assignee_id: string | null
  reporter_id: string | null
  rank: string
  created_at: string
  updated_at: string
  due_date: string | null
  priority: string | null
}

export interface TaskCreate {
  title: string
  description?: string | null
  status_id?: string
  assignee_id?: string | null
  priority?: string | null
  due_date?: string | null
}

export interface TaskUpdate {
  title?: string
  description?: string | null
  status_id?: string
  assignee_id?: string | null
  priority?: string | null
  due_date?: string | null
}

export interface TaskMovePayload {
  taskId: string
  newStatusId: string
  newRank?: string
  targetTaskId?: string
  position?: 'before' | 'after'
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
  description: string | null
  color: string
  position: number
  is_done: boolean
  created_at: string
  updated_at: string
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
 * Uses 5 min stale time since projects change less frequently.
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
    staleTime: 5 * 60 * 1000,
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
        data,
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
      // Increment tasks_count in project
      queryClient.setQueryData<Project[]>(queryKeys.projects(newTask.project_id), (old) =>
        old?.map((p) =>
          p.id === projectId ? { ...p, tasks_count: p.tasks_count + 1 } : p
        )
      )
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

      const response = await window.electronAPI.patch<Task>(
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
        old?.map((t) => (t.id === taskId ? { ...t, ...newData } : t))
      )

      return { previous }
    },
    onError: (_err, _newData, context) => {
      // Rollback on error
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.task(taskId), context.previous)
      }
    },
    onSettled: () => {
      // Refetch to ensure consistency
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
    },
  })
}

/**
 * Move a task (change status/position) with optimistic update.
 * Used for Kanban drag-and-drop.
 */
export function useMoveTask(
  projectId: string
): UseMutationResult<Task, Error, TaskMovePayload, { previous?: Task[] }> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ taskId, newStatusId, newRank, targetTaskId, position }: TaskMovePayload) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.patch<Task>(
        `/api/tasks/${taskId}/move`,
        {
          status_id: newStatusId,
          rank: newRank,
          target_task_id: targetTaskId,
          position,
        },
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
    // Optimistic update for instant drag-drop feedback
    onMutate: async ({ taskId, newStatusId }) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.tasks(projectId) })

      const previous = queryClient.getQueryData<Task[]>(queryKeys.tasks(projectId))

      // Optimistically update task status
      queryClient.setQueryData<Task[]>(queryKeys.tasks(projectId), (old) =>
        old?.map((t) => (t.id === taskId ? { ...t, status_id: newStatusId } : t))
      )

      return { previous }
    },
    onError: (_err, _vars, context) => {
      // Rollback on error
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.tasks(projectId), context.previous)
      }
    },
    onSettled: () => {
      // Refetch to ensure consistency
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
