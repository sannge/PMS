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
}

/**
 * Data for creating a project
 */
export interface ProjectCreate {
  name: string
  key: string
  description?: string | null
  project_type?: ProjectType
}

/**
 * Data for updating a project
 */
export interface ProjectUpdate {
  name?: string
  description?: string | null
  project_type?: ProjectType
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
    set({ isLoading: true, error: null })

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
}))

// ============================================================================
// Selectors
// ============================================================================

export const selectProjects = (state: ProjectsState): Project[] => state.projects

export const selectSelectedProject = (state: ProjectsState): Project | null =>
  state.selectedProject

export const selectIsLoading = (state: ProjectsState): boolean => state.isLoading

export const selectError = (state: ProjectsState): ProjectError | null => state.error

export default useProjectsStore
