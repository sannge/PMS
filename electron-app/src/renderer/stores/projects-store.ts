/**
 * Projects Store
 *
 * Zustand store for managing project state in the renderer process.
 * Handles CRUD operations for projects with API integration.
 *
 * Features:
 * - Project list with pagination
 * - Create, read, update, delete operations
 * - Loading and error states
 * - Search and filtering
 * - Application-scoped project fetching
 * - Derived status from task distribution
 * - Status override support (Owner-only)
 * - Real-time status change handling via WebSocket
 */

import { create } from 'zustand'
import { getAuthHeaders } from './auth-store'

// ============================================================================
// Types
// ============================================================================

/**
 * Project type options
 */
export type ProjectType = 'kanban' | 'scrum'

/**
 * Project status values (derived from task distribution)
 * Note: "In Review" is a task status only, not a project status.
 * Project status is derived: Todo, In Progress (includes tasks in review), Issue, Done
 */
export type ProjectDerivedStatus = 'Todo' | 'In Progress' | 'Issue' | 'Done'

/**
 * Project data from the API
 */
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

  // Creator and owner
  created_by: string | null
  project_owner_user_id: string | null

  // Derived status (computed from task distribution)
  derived_status: ProjectDerivedStatus | null
  derived_status_id: string | null

  // Status override fields (Owner-only)
  override_status_id: string | null
  override_reason: string | null
  override_by_user_id: string | null
  override_expires_at: string | null

  // Optimistic concurrency control
  row_version: number
}

/**
 * Data for creating a project
 */
export interface ProjectCreate {
  name: string
  key: string
  description?: string | null
  project_type?: ProjectType
  project_owner_user_id?: string | null
}

/**
 * Data for updating a project
 */
export interface ProjectUpdate {
  name?: string
  description?: string | null
  project_type?: ProjectType
  project_owner_user_id?: string | null
  row_version?: number
}

/**
 * Data for setting a project status override (Owner-only)
 */
export interface ProjectStatusOverride {
  override_status_id: string
  override_reason?: string | null
  override_expires_at?: string | null
}

/**
 * WebSocket event data for project status changes
 */
export interface ProjectStatusChangedEventData {
  project_id: string
  application_id: string
  old_status: string | null
  new_status: string
  project: {
    id: string
    application_id: string
    name: string
    key: string
    derived_status: string
    derived_status_id: string | null
  }
  timestamp: string
  changed_by?: string
}

/**
 * WebSocket event data for project deletion
 */
export interface ProjectDeletedEventData {
  project_id: string
  application_id: string
  project_name: string
  project_key: string
  deleted_by: string
}

/**
 * WebSocket event data for project update
 */
export interface ProjectUpdatedEventData {
  project_id: string
  name: string
  description: string | null
  project_type: string
  project_key: string
  updated_at: string | null
  updated_by: string
}

/**
 * Error with details
 */
export interface ProjectError {
  message: string
  code?: string
  field?: string
}

/**
 * Projects store state
 */
export interface ProjectsState {
  // State
  projects: Project[]
  selectedProject: Project | null
  isLoading: boolean
  isCreating: boolean
  isUpdating: boolean
  isDeleting: boolean
  error: ProjectError | null

  // Pagination
  skip: number
  limit: number
  total: number
  hasMore: boolean

  // Search and filtering
  searchQuery: string
  currentApplicationId: string | null

  // Actions
  fetchProjects: (
    token: string | null,
    applicationId: string,
    options?: { skip?: number; search?: string }
  ) => Promise<void>
  fetchProject: (token: string | null, id: string) => Promise<Project | null>
  createProject: (
    token: string | null,
    applicationId: string,
    data: ProjectCreate
  ) => Promise<Project | null>
  updateProject: (
    token: string | null,
    id: string,
    data: ProjectUpdate
  ) => Promise<Project | null>
  deleteProject: (token: string | null, id: string) => Promise<boolean>
  selectProject: (project: Project | null) => void
  setSearchQuery: (query: string) => void
  clearError: () => void
  reset: () => void

  // Status override actions (Owner-only)
  overrideProjectStatus: (
    token: string | null,
    projectId: string,
    data: ProjectStatusOverride
  ) => Promise<Project | null>
  clearStatusOverride: (token: string | null, projectId: string) => Promise<Project | null>

  // Real-time status update handlers
  updateProjectDerivedStatus: (
    projectId: string,
    derivedStatusId: string | null,
    derivedStatus?: ProjectDerivedStatus | null
  ) => void
  handleProjectStatusChanged: (event: ProjectStatusChangedEventData) => void
  handleProjectDeleted: (event: ProjectDeletedEventData) => void
  handleProjectUpdated: (event: ProjectUpdatedEventData) => void
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Parse API error response
 */
function parseApiError(status: number, data: unknown): ProjectError {
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
      return { message: 'Project not found.' }
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
  projects: [],
  selectedProject: null,
  isLoading: false,
  isCreating: false,
  isUpdating: false,
  isDeleting: false,
  error: null,
  skip: 0,
  limit: 20,
  total: 0,
  hasMore: false,
  searchQuery: '',
  currentApplicationId: null,
}

// ============================================================================
// Store
// ============================================================================

/**
 * Projects store using zustand
 */
export const useProjectsStore = create<ProjectsState>((set, get) => ({
  // Initial state
  ...initialState,

  /**
   * Fetch projects list for an application
   */
  fetchProjects: async (token, applicationId, options = {}) => {
    const { skip = 0, search } = options

    // Clear projects when switching applications to show skeleton loader
    const currentAppId = get().currentApplicationId
    const isNewApplication = currentAppId !== applicationId

    set({
      isLoading: true,
      error: null,
      currentApplicationId: applicationId,
      // Clear projects when switching to a different application
      ...(isNewApplication && { projects: [] }),
    })

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

      const response = await window.electronAPI.get<Project[]>(
        `/api/applications/${applicationId}/projects?${params.toString()}`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        const error = parseApiError(response.status, response.data)
        set({ isLoading: false, error })
        return
      }

      const projects = response.data || []
      set({
        projects: skip === 0 ? projects : [...get().projects, ...projects],
        skip,
        hasMore: projects.length === get().limit,
        isLoading: false,
        searchQuery: search || '',
      })
    } catch (err) {
      const error: ProjectError = {
        message: err instanceof Error ? err.message : 'Failed to fetch projects',
      }
      set({ isLoading: false, error })
    }
  },

  /**
   * Fetch a single project by ID
   */
  fetchProject: async (token, id) => {
    // Clear selectedProject if fetching a different project to avoid showing stale data
    const currentSelected = get().selectedProject
    if (currentSelected && currentSelected.id !== id) {
      set({ selectedProject: null, isLoading: true, error: null })
    } else {
      set({ isLoading: true, error: null })
    }

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.get<Project>(
        `/api/projects/${id}`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        const error = parseApiError(response.status, response.data)
        set({ isLoading: false, error })
        return null
      }

      const project = response.data
      set({ selectedProject: project, isLoading: false })
      return project
    } catch (err) {
      const error: ProjectError = {
        message: err instanceof Error ? err.message : 'Failed to fetch project',
      }
      set({ isLoading: false, error })
      return null
    }
  },

  /**
   * Create a new project
   */
  createProject: async (token, applicationId, data) => {
    set({ isCreating: true, error: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.post<Project>(
        `/api/applications/${applicationId}/projects`,
        data,
        getAuthHeaders(token)
      )

      if (response.status !== 201) {
        const error = parseApiError(response.status, response.data)
        set({ isCreating: false, error })
        return null
      }

      const project = response.data
      // Add the new project to the list
      set({
        projects: [project, ...get().projects],
        isCreating: false,
      })
      return project
    } catch (err) {
      const error: ProjectError = {
        message: err instanceof Error ? err.message : 'Failed to create project',
      }
      set({ isCreating: false, error })
      return null
    }
  },

  /**
   * Update an existing project
   */
  updateProject: async (token, id, data) => {
    set({ isUpdating: true, error: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.put<Project>(
        `/api/projects/${id}`,
        data,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        const error = parseApiError(response.status, response.data)
        set({ isUpdating: false, error })
        return null
      }

      const project = response.data
      // Update the project in the list
      const projects = get().projects.map((p) => (p.id === id ? project : p))
      set({
        projects,
        selectedProject: project,
        isUpdating: false,
      })
      return project
    } catch (err) {
      const error: ProjectError = {
        message: err instanceof Error ? err.message : 'Failed to update project',
      }
      set({ isUpdating: false, error })
      return null
    }
  },

  /**
   * Delete a project
   */
  deleteProject: async (token, id) => {
    set({ isDeleting: true, error: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.delete<void>(
        `/api/projects/${id}`,
        getAuthHeaders(token)
      )

      if (response.status !== 204 && response.status !== 200) {
        const error = parseApiError(response.status, response.data)
        set({ isDeleting: false, error })
        return false
      }

      // Remove the project from the list
      const projects = get().projects.filter((p) => p.id !== id)
      set({
        projects,
        selectedProject: null,
        isDeleting: false,
      })
      return true
    } catch (err) {
      const error: ProjectError = {
        message: err instanceof Error ? err.message : 'Failed to delete project',
      }
      set({ isDeleting: false, error })
      return false
    }
  },

  /**
   * Select a project
   */
  selectProject: (project) => {
    set({ selectedProject: project })
  },

  /**
   * Set search query
   */
  setSearchQuery: (query) => {
    set({ searchQuery: query })
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
   * Override project status (Owner-only)
   * Sets a manual status override that takes precedence over the derived status
   */
  overrideProjectStatus: async (token, projectId, data) => {
    set({ isUpdating: true, error: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.put<Project>(
        `/api/projects/${projectId}/override-status`,
        data,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        const error = parseApiError(response.status, response.data)
        set({ isUpdating: false, error })
        return null
      }

      const project = response.data
      // Update the project in the list
      const projects = get().projects.map((p) => (p.id === projectId ? project : p))
      set({
        projects,
        selectedProject: get().selectedProject?.id === projectId ? project : get().selectedProject,
        isUpdating: false,
      })
      return project
    } catch (err) {
      const error: ProjectError = {
        message: err instanceof Error ? err.message : 'Failed to override project status',
      }
      set({ isUpdating: false, error })
      return null
    }
  },

  /**
   * Clear project status override (Owner-only)
   * Reverts the project to using the derived status from task distribution
   */
  clearStatusOverride: async (token, projectId) => {
    set({ isUpdating: true, error: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.delete<Project>(
        `/api/projects/${projectId}/override-status`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        const error = parseApiError(response.status, response.data)
        set({ isUpdating: false, error })
        return null
      }

      const project = response.data
      // Update the project in the list
      const projects = get().projects.map((p) => (p.id === projectId ? project : p))
      set({
        projects,
        selectedProject: get().selectedProject?.id === projectId ? project : get().selectedProject,
        isUpdating: false,
      })
      return project
    } catch (err) {
      const error: ProjectError = {
        message: err instanceof Error ? err.message : 'Failed to clear status override',
      }
      set({ isUpdating: false, error })
      return null
    }
  },

  /**
   * Update a project's derived status (for real-time updates)
   * Called when a WebSocket project_status_changed event is received
   */
  updateProjectDerivedStatus: (projectId, derivedStatusId, derivedStatus) => {
    const projects = get().projects.map((p) =>
      p.id === projectId
        ? {
            ...p,
            derived_status_id: derivedStatusId,
            ...(derivedStatus !== undefined && { derived_status: derivedStatus }),
          }
        : p
    )
    const selectedProject = get().selectedProject
    set({
      projects,
      selectedProject:
        selectedProject?.id === projectId
          ? {
              ...selectedProject,
              derived_status_id: derivedStatusId,
              ...(derivedStatus !== undefined && { derived_status: derivedStatus }),
            }
          : selectedProject,
    })
  },

  /**
   * Handle WebSocket project_status_changed event
   * Updates the project's derived status based on task distribution changes
   */
  handleProjectStatusChanged: (event) => {
    const { project_id, project } = event
    const currentApplicationId = get().currentApplicationId

    // Only update if the project belongs to the currently viewed application
    if (currentApplicationId && project.application_id === currentApplicationId) {
      // Update the project in the list with the new derived status (both ID and name)
      const derivedStatus = project.derived_status as ProjectDerivedStatus | null
      const projects = get().projects.map((p) =>
        p.id === project_id
          ? {
              ...p,
              derived_status: derivedStatus,
              derived_status_id: project.derived_status_id,
            }
          : p
      )
      const selectedProject = get().selectedProject
      set({
        projects,
        selectedProject:
          selectedProject?.id === project_id
            ? {
                ...selectedProject,
                derived_status: derivedStatus,
                derived_status_id: project.derived_status_id,
              }
            : selectedProject,
      })
    }
  },

  /**
   * Handle WebSocket project_deleted event
   * Removes the project from the list and clears selectedProject if it was deleted
   */
  handleProjectDeleted: (event) => {
    const { project_id, application_id } = event
    const currentApplicationId = get().currentApplicationId

    // Only update if the project belongs to the currently viewed application
    if (currentApplicationId && application_id === currentApplicationId) {
      const projects = get().projects.filter((p) => p.id !== project_id)
      const selectedProject = get().selectedProject

      set({
        projects,
        // Clear selectedProject if it was the deleted project
        selectedProject: selectedProject?.id === project_id ? null : selectedProject,
      })
    }
  },

  handleProjectUpdated: (event) => {
    const { project_id, name, description, project_type, updated_at } = event

    // Update the project in the list
    const projects = get().projects.map((p) => {
      if (p.id === project_id) {
        return {
          ...p,
          name,
          description,
          project_type: project_type as ProjectType,
          updated_at: updated_at || p.updated_at,
        }
      }
      return p
    })

    // Update selectedProject if it's the updated project
    const selectedProject = get().selectedProject
    const updatedSelectedProject =
      selectedProject?.id === project_id
        ? {
            ...selectedProject,
            name,
            description,
            project_type: project_type as ProjectType,
            updated_at: updated_at || selectedProject.updated_at,
          }
        : selectedProject

    set({
      projects,
      selectedProject: updatedSelectedProject,
    })
  },
}))

// ============================================================================
// Selectors
// ============================================================================

export const selectProjects = (state: ProjectsState): Project[] => state.projects

export const selectSelectedProject = (state: ProjectsState): Project | null =>
  state.selectedProject

export const selectIsLoading = (state: ProjectsState): boolean => state.isLoading

export const selectError = (state: ProjectsState): ProjectError | null => state.error

/**
 * Select a project by ID
 */
export const selectProjectById =
  (projectId: string) =>
  (state: ProjectsState): Project | undefined =>
    state.projects.find((p) => p.id === projectId)

/**
 * Select projects with status override
 */
export const selectProjectsWithOverride = (state: ProjectsState): Project[] =>
  state.projects.filter((p) => p.override_status_id !== null)

/**
 * Check if a project has an active status override
 */
export const selectHasStatusOverride =
  (projectId: string) =>
  (state: ProjectsState): boolean => {
    const project = state.projects.find((p) => p.id === projectId)
    if (!project || !project.override_status_id) return false
    // Check if override has expired
    if (project.override_expires_at) {
      const expiresAt = new Date(project.override_expires_at)
      if (expiresAt < new Date()) return false
    }
    return true
  }

/**
 * Get the effective status ID for a project (override if active, otherwise derived)
 */
export const selectEffectiveStatusId =
  (projectId: string) =>
  (state: ProjectsState): string | null => {
    const project = state.projects.find((p) => p.id === projectId)
    if (!project) return null
    // Check for active override
    if (project.override_status_id) {
      // Check if override has expired
      if (project.override_expires_at) {
        const expiresAt = new Date(project.override_expires_at)
        if (expiresAt >= new Date()) {
          return project.override_status_id
        }
      } else {
        return project.override_status_id
      }
    }
    return project.derived_status_id
  }

export default useProjectsStore
