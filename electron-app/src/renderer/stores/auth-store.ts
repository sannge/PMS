/**
 * Authentication Store
 *
 * Zustand store for managing authentication state in the renderer process.
 * Handles user sessions, JWT tokens, login/logout operations, and persistence.
 *
 * Features:
 * - Token persistence in localStorage
 * - Automatic token refresh on app start
 * - Type-safe state management
 * - Error handling for auth operations
 */

import { create } from 'zustand'
import { persist } from 'zustand/middleware'

// ============================================================================
// Types
// ============================================================================

/**
 * User data returned from the API
 */
export interface User {
  id: string
  email: string
  display_name: string | null
  avatar_url: string | null
  created_at: string
  updated_at: string
}

/**
 * Credentials for login
 */
export interface LoginCredentials {
  email: string
  password: string
}

/**
 * Data for user registration
 */
export interface RegisterData {
  email: string
  password: string
  display_name?: string
}

/**
 * Token response from login endpoint
 */
export interface TokenResponse {
  access_token: string
  token_type: string
}

/**
 * Authentication error with details
 */
export interface AuthError {
  message: string
  code?: string
  field?: string
}

/**
 * Authentication state
 */
export interface AuthState {
  // State
  user: User | null
  token: string | null
  isAuthenticated: boolean
  isLoading: boolean
  isInitialized: boolean
  error: AuthError | null

  // Actions
  login: (credentials: LoginCredentials) => Promise<boolean>
  register: (data: RegisterData) => Promise<boolean>
  logout: () => Promise<void>
  fetchCurrentUser: () => Promise<void>
  checkAuth: () => Promise<boolean>
  clearError: () => void
  setToken: (token: string | null) => void
  setUser: (user: User | null) => void
  reset: () => void
}

// ============================================================================
// Constants
// ============================================================================

const TOKEN_STORAGE_KEY = 'pm-desktop-auth-token'
const AUTH_STORAGE_KEY = 'pm-desktop-auth'

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Get authorization headers with bearer token
 */
export function getAuthHeaders(token: string | null): Record<string, string> {
  if (!token) return {}
  return {
    Authorization: `Bearer ${token}`,
  }
}

/**
 * Parse API error response
 */
function parseApiError(status: number, data: unknown): AuthError {
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
      return { message: 'Invalid credentials. Please try again.' }
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
// Initial State
// ============================================================================

const initialState = {
  user: null,
  token: null,
  isAuthenticated: false,
  isLoading: false,
  isInitialized: false,
  error: null,
}

// ============================================================================
// Store
// ============================================================================

/**
 * Authentication store using zustand with persistence
 */
export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      // Initial state
      ...initialState,

      /**
       * Login with email and password
       * Uses OAuth2 password flow
       */
      login: async (credentials: LoginCredentials): Promise<boolean> => {
        set({ isLoading: true, error: null })

        try {
          // Check if electronAPI is available
          if (!window.electronAPI) {
            throw new Error('Electron API not available')
          }

          // Use form data format for OAuth2 password flow
          const formData = new URLSearchParams()
          formData.append('username', credentials.email)
          formData.append('password', credentials.password)

          const response = await window.electronAPI.fetch<TokenResponse>('/auth/login', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: formData.toString(),
          })

          if (response.status !== 200) {
            const error = parseApiError(response.status, response.data)
            set({ isLoading: false, error })
            return false
          }

          const tokenData = response.data
          set({ token: tokenData.access_token })

          // Fetch user profile after successful login
          await get().fetchCurrentUser()

          set({ isLoading: false, isAuthenticated: true })
          return true
        } catch (err) {
          const error: AuthError = {
            message: err instanceof Error ? err.message : 'Login failed',
          }
          set({ isLoading: false, error, isAuthenticated: false })
          return false
        }
      },

      /**
       * Register a new user
       */
      register: async (data: RegisterData): Promise<boolean> => {
        set({ isLoading: true, error: null })

        try {
          if (!window.electronAPI) {
            throw new Error('Electron API not available')
          }

          const response = await window.electronAPI.post<User>('/auth/register', {
            email: data.email,
            password: data.password,
            display_name: data.display_name || null,
          })

          if (response.status !== 201) {
            const error = parseApiError(response.status, response.data)
            set({ isLoading: false, error })
            return false
          }

          // Registration successful - user should now login
          set({ isLoading: false })
          return true
        } catch (err) {
          const error: AuthError = {
            message: err instanceof Error ? err.message : 'Registration failed',
          }
          set({ isLoading: false, error })
          return false
        }
      },

      /**
       * Logout the current user
       */
      logout: async (): Promise<void> => {
        const token = get().token

        try {
          if (window.electronAPI && token) {
            // Call logout endpoint to notify server
            await window.electronAPI.post('/auth/logout', undefined, getAuthHeaders(token))
          }
        } catch {
          // Ignore logout errors - we still want to clear local state
        }

        // Clear all auth state
        set({
          user: null,
          token: null,
          isAuthenticated: false,
          error: null,
        })
      },

      /**
       * Fetch the current user's profile
       */
      fetchCurrentUser: async (): Promise<void> => {
        const token = get().token

        if (!token) {
          set({ user: null, isAuthenticated: false })
          return
        }

        try {
          if (!window.electronAPI) {
            throw new Error('Electron API not available')
          }

          const response = await window.electronAPI.get<User>(
            '/auth/me',
            getAuthHeaders(token)
          )

          if (response.status === 200) {
            set({ user: response.data, isAuthenticated: true })
          } else if (response.status === 401) {
            // Token expired or invalid
            set({ user: null, token: null, isAuthenticated: false })
          }
        } catch {
          // Failed to fetch user - token might be invalid
          set({ user: null, token: null, isAuthenticated: false })
        }
      },

      /**
       * Check if user is authenticated and refresh user data
       * Call this on app startup
       */
      checkAuth: async (): Promise<boolean> => {
        const token = get().token

        if (!token) {
          set({ isInitialized: true, isAuthenticated: false })
          return false
        }

        set({ isLoading: true })

        try {
          await get().fetchCurrentUser()
          const isAuthenticated = get().isAuthenticated
          set({ isInitialized: true, isLoading: false })
          return isAuthenticated
        } catch {
          set({ isInitialized: true, isLoading: false, isAuthenticated: false })
          return false
        }
      },

      /**
       * Clear the current error
       */
      clearError: (): void => {
        set({ error: null })
      },

      /**
       * Set the authentication token
       */
      setToken: (token: string | null): void => {
        set({ token, isAuthenticated: !!token })
      },

      /**
       * Set the current user
       */
      setUser: (user: User | null): void => {
        set({ user, isAuthenticated: !!user })
      },

      /**
       * Reset the store to initial state
       */
      reset: (): void => {
        set(initialState)
      },
    }),
    {
      name: AUTH_STORAGE_KEY,
      // Only persist token, not loading states
      partialize: (state) => ({
        token: state.token,
      }),
    }
  )
)

// ============================================================================
// Selectors (for optimized re-renders)
// ============================================================================

/**
 * Select only the user
 */
export const selectUser = (state: AuthState): User | null => state.user

/**
 * Select authentication status
 */
export const selectIsAuthenticated = (state: AuthState): boolean => state.isAuthenticated

/**
 * Select loading status
 */
export const selectIsLoading = (state: AuthState): boolean => state.isLoading

/**
 * Select initialization status
 */
export const selectIsInitialized = (state: AuthState): boolean => state.isInitialized

/**
 * Select error
 */
export const selectError = (state: AuthState): AuthError | null => state.error

export default useAuthStore
