/**
 * Applications Store
 *
 * Zustand store for managing application state in the renderer process.
 * Handles CRUD operations for applications with API integration.
 *
 * Features:
 * - Application list with pagination
 * - Create, read, update, delete operations
 * - Loading and error states
 * - Search and filtering
 */

import { create } from 'zustand'
import { getAuthHeaders } from './auth-store'

// ============================================================================
// Types
// ============================================================================

/**
 * Ownership type indicating how user relates to the application
 */
export type OwnershipType = 'created' | 'invited'

/**
 * Application role enumeration
 */
export type ApplicationRole = 'owner' | 'editor' | 'viewer'

/**
 * Application data from the API
 */
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

/**
 * Data for creating an application
 */
export interface ApplicationCreate {
  name: string
  description?: string | null
}

/**
 * Data for updating an application
 */
export interface ApplicationUpdate {
  name?: string
  description?: string | null
}

/**
 * Error with details
 */
export interface ApplicationError {
  message: string
  code?: string
  field?: string
}

/**
 * Applications store state
 */
export interface ApplicationsState {
  // State
  applications: Application[]
  selectedApplication: Application | null
  isLoading: boolean
  isCreating: boolean
  isUpdating: boolean
  isDeleting: boolean
  error: ApplicationError | null

  // Pagination
  skip: number
  limit: number
  total: number
  hasMore: boolean

  // Search
  searchQuery: string

  // Actions
  fetchApplications: (token: string | null, options?: { skip?: number; search?: string }) => Promise<void>
  fetchApplication: (token: string | null, id: string) => Promise<Application | null>
  createApplication: (token: string | null, data: ApplicationCreate) => Promise<Application | null>
  updateApplication: (token: string | null, id: string, data: ApplicationUpdate) => Promise<Application | null>
  deleteApplication: (token: string | null, id: string) => Promise<boolean>
  selectApplication: (application: Application | null) => void
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
function parseApiError(status: number, data: unknown): ApplicationError {
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
      return { message: 'Application not found.' }
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
  applications: [],
  selectedApplication: null,
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
}

// ============================================================================
// Store
// ============================================================================

/**
 * Applications store using zustand
 */
export const useApplicationsStore = create<ApplicationsState>((set, get) => ({
  // Initial state
  ...initialState,

  /**
   * Fetch applications list
   */
  fetchApplications: async (token, options = {}) => {
    const { skip = 0, search } = options

    set({ isLoading: true, error: null })

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

      const response = await window.electronAPI.get<Application[]>(
        `/api/applications?${params.toString()}`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        const error = parseApiError(response.status, response.data)
        set({ isLoading: false, error })
        return
      }

      const applications = response.data || []
      set({
        applications: skip === 0 ? applications : [...get().applications, ...applications],
        skip,
        hasMore: applications.length === get().limit,
        isLoading: false,
        searchQuery: search || '',
      })
    } catch (err) {
      const error: ApplicationError = {
        message: err instanceof Error ? err.message : 'Failed to fetch applications',
      }
      set({ isLoading: false, error })
    }
  },

  /**
   * Fetch a single application by ID
   */
  fetchApplication: async (token, id) => {
    set({ isLoading: true, error: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.get<Application>(
        `/api/applications/${id}`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        const error = parseApiError(response.status, response.data)
        set({ isLoading: false, error })
        return null
      }

      const application = response.data
      set({ selectedApplication: application, isLoading: false })
      return application
    } catch (err) {
      const error: ApplicationError = {
        message: err instanceof Error ? err.message : 'Failed to fetch application',
      }
      set({ isLoading: false, error })
      return null
    }
  },

  /**
   * Create a new application
   */
  createApplication: async (token, data) => {
    set({ isCreating: true, error: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.post<Application>(
        '/api/applications',
        data,
        getAuthHeaders(token)
      )

      if (response.status !== 201) {
        const error = parseApiError(response.status, response.data)
        set({ isCreating: false, error })
        return null
      }

      const application = response.data
      // Add the new application to the list
      set({
        applications: [application, ...get().applications],
        isCreating: false,
      })
      return application
    } catch (err) {
      const error: ApplicationError = {
        message: err instanceof Error ? err.message : 'Failed to create application',
      }
      set({ isCreating: false, error })
      return null
    }
  },

  /**
   * Update an existing application
   */
  updateApplication: async (token, id, data) => {
    set({ isUpdating: true, error: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.put<Application>(
        `/api/applications/${id}`,
        data,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        const error = parseApiError(response.status, response.data)
        set({ isUpdating: false, error })
        return null
      }

      const application = response.data
      // Update the application in the list
      const applications = get().applications.map((app) =>
        app.id === id ? application : app
      )
      set({
        applications,
        selectedApplication: application,
        isUpdating: false,
      })
      return application
    } catch (err) {
      const error: ApplicationError = {
        message: err instanceof Error ? err.message : 'Failed to update application',
      }
      set({ isUpdating: false, error })
      return null
    }
  },

  /**
   * Delete an application
   */
  deleteApplication: async (token, id) => {
    set({ isDeleting: true, error: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.delete<void>(
        `/api/applications/${id}`,
        getAuthHeaders(token)
      )

      if (response.status !== 204 && response.status !== 200) {
        const error = parseApiError(response.status, response.data)
        set({ isDeleting: false, error })
        return false
      }

      // Remove the application from the list
      const applications = get().applications.filter((app) => app.id !== id)
      set({
        applications,
        selectedApplication: null,
        isDeleting: false,
      })
      return true
    } catch (err) {
      const error: ApplicationError = {
        message: err instanceof Error ? err.message : 'Failed to delete application',
      }
      set({ isDeleting: false, error })
      return false
    }
  },

  /**
   * Select an application
   */
  selectApplication: (application) => {
    set({ selectedApplication: application })
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

export const selectApplications = (state: ApplicationsState): Application[] =>
  state.applications

export const selectSelectedApplication = (state: ApplicationsState): Application | null =>
  state.selectedApplication

export const selectIsLoading = (state: ApplicationsState): boolean =>
  state.isLoading

export const selectError = (state: ApplicationsState): ApplicationError | null =>
  state.error

export default useApplicationsStore
