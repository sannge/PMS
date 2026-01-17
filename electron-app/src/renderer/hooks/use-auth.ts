/**
 * Authentication Hook
 *
 * A convenience hook that wraps the auth store and provides
 * a cleaner API for authentication operations in components.
 *
 * Usage:
 * ```tsx
 * const { user, isAuthenticated, login, logout } = useAuth()
 *
 * // In a form submit handler
 * const success = await login({ email, password })
 * if (success) {
 *   navigate('/dashboard')
 * }
 * ```
 */

import { useCallback, useEffect } from 'react'
import { shallow } from 'zustand/shallow'
import {
  useAuthStore,
  selectUser,
  selectIsAuthenticated,
  selectIsLoading,
  selectIsInitialized,
  selectError,
  getAuthHeaders,
  type User,
  type LoginCredentials,
  type RegisterData,
  type AuthError,
} from '@/stores/auth-store'

// ============================================================================
// Types
// ============================================================================

export interface UseAuthReturn {
  // State
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  isInitialized: boolean
  error: AuthError | null

  // Actions
  login: (credentials: LoginCredentials) => Promise<boolean>
  register: (data: RegisterData) => Promise<boolean>
  logout: () => Promise<void>
  checkAuth: () => Promise<boolean>
  clearError: () => void

  // Helpers
  getAuthHeaders: () => Record<string, string>
}

// ============================================================================
// Hook
// ============================================================================

/**
 * Hook for authentication state and operations
 *
 * Provides access to:
 * - Current user and authentication status
 * - Login, register, and logout functions
 * - Loading and error states
 * - Helper for getting auth headers
 */
export function useAuth(): UseAuthReturn {
  // Select state using individual selectors for optimal re-renders
  const user = useAuthStore(selectUser)
  const isAuthenticated = useAuthStore(selectIsAuthenticated)
  const isLoading = useAuthStore(selectIsLoading)
  const isInitialized = useAuthStore(selectIsInitialized)
  const error = useAuthStore(selectError)

  // Get actions from store
  const storeLogin = useAuthStore((state) => state.login)
  const storeRegister = useAuthStore((state) => state.register)
  const storeLogout = useAuthStore((state) => state.logout)
  const storeCheckAuth = useAuthStore((state) => state.checkAuth)
  const storeClearError = useAuthStore((state) => state.clearError)
  const token = useAuthStore((state) => state.token)

  // Stable action references
  const login = useCallback(
    async (credentials: LoginCredentials): Promise<boolean> => {
      return storeLogin(credentials)
    },
    [storeLogin]
  )

  const register = useCallback(
    async (data: RegisterData): Promise<boolean> => {
      return storeRegister(data)
    },
    [storeRegister]
  )

  const logout = useCallback(async (): Promise<void> => {
    return storeLogout()
  }, [storeLogout])

  const checkAuth = useCallback(async (): Promise<boolean> => {
    return storeCheckAuth()
  }, [storeCheckAuth])

  const clearError = useCallback((): void => {
    storeClearError()
  }, [storeClearError])

  // Helper to get auth headers for API calls
  const getAuthHeadersCallback = useCallback((): Record<string, string> => {
    return getAuthHeaders(token)
  }, [token])

  return {
    // State
    user,
    isAuthenticated,
    isLoading,
    isInitialized,
    error,

    // Actions
    login,
    register,
    logout,
    checkAuth,
    clearError,

    // Helpers
    getAuthHeaders: getAuthHeadersCallback,
  }
}

// ============================================================================
// Additional Hooks
// ============================================================================

/**
 * Hook that initializes authentication on mount
 *
 * Use this in your app's root component to check auth status on startup.
 *
 * ```tsx
 * function App() {
 *   const { isInitialized, isAuthenticated } = useAuthInit()
 *
 *   if (!isInitialized) {
 *     return <LoadingScreen />
 *   }
 *
 *   return isAuthenticated ? <Dashboard /> : <Login />
 * }
 * ```
 */
export function useAuthInit(): {
  isInitialized: boolean
  isAuthenticated: boolean
  isLoading: boolean
} {
  const checkAuth = useAuthStore((state) => state.checkAuth)
  const isInitialized = useAuthStore(selectIsInitialized)
  const isAuthenticated = useAuthStore(selectIsAuthenticated)
  const isLoading = useAuthStore(selectIsLoading)

  useEffect(() => {
    // Only check auth once on mount
    if (!isInitialized) {
      checkAuth()
    }
  }, [checkAuth, isInitialized])

  return {
    isInitialized,
    isAuthenticated,
    isLoading,
  }
}

/**
 * Hook to access only the current user
 *
 * Optimized for components that only need user data.
 *
 * ```tsx
 * function UserAvatar() {
 *   const user = useCurrentUser()
 *   if (!user) return null
 *   return <Avatar src={user.avatar_url} name={user.display_name} />
 * }
 * ```
 */
export function useCurrentUser(): User | null {
  return useAuthStore(selectUser)
}

/**
 * Hook to check if user is authenticated
 *
 * Optimized for components that only need auth status.
 *
 * ```tsx
 * function NavBar() {
 *   const isAuthenticated = useIsAuthenticated()
 *   return isAuthenticated ? <UserMenu /> : <LoginButton />
 * }
 * ```
 */
export function useIsAuthenticated(): boolean {
  return useAuthStore(selectIsAuthenticated)
}

/**
 * Hook to get the auth token
 *
 * Useful for components that need to make authenticated API calls.
 *
 * ```tsx
 * function DataFetcher() {
 *   const token = useAuthToken()
 *   // Use token for API calls
 * }
 * ```
 */
export function useAuthToken(): string | null {
  return useAuthStore((state) => state.token)
}

/**
 * Hook to get auth loading and error states
 *
 * Useful for forms that need to show loading/error feedback.
 *
 * ```tsx
 * function LoginForm() {
 *   const { isLoading, error, clearError } = useAuthStatus()
 *   // Show loading spinner, error messages
 * }
 * ```
 */
export function useAuthStatus(): {
  isLoading: boolean
  error: AuthError | null
  clearError: () => void
} {
  const isLoading = useAuthStore(selectIsLoading)
  const error = useAuthStore(selectError)
  const clearError = useAuthStore((state) => state.clearError)

  return {
    isLoading,
    error,
    clearError,
  }
}

// ============================================================================
// Exports
// ============================================================================

export type {
  User,
  LoginCredentials,
  RegisterData,
  AuthError,
} from '@/stores/auth-store'

export default useAuth
