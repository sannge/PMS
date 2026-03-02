/**
 * Authentication Hook
 *
 * A convenience hook that wraps the auth store and provides
 * a cleaner API for authentication operations in components.
 *
 * Usage:
 * ```tsx
 * const { user, isAuthenticated, login, logout } = useAuth()
 * ```
 */

import { useCallback, useEffect } from 'react'
import {
  useAuthState,
  useAuthActions,
  getAuthHeaders,
  type User,
  type LoginCredentials,
  type RegisterData,
  type AuthError,
} from '@/contexts/auth-context'

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
  pendingVerificationEmail: string | null
  pendingVerificationContext: 'registration' | 'login' | null

  // Actions
  login: (credentials: LoginCredentials) => Promise<boolean>
  register: (data: RegisterData) => Promise<boolean>
  logout: () => Promise<void>
  checkAuth: () => Promise<boolean>
  clearError: () => void
  verifyEmail: (email: string, code: string) => Promise<boolean>
  verifyLogin: (email: string, code: string) => Promise<boolean>
  resendVerification: (email: string) => Promise<boolean>
  forgotPassword: (email: string) => Promise<boolean>
  resetPassword: (email: string, code: string, newPassword: string) => Promise<boolean>
  clearPendingVerification: () => void

  // Helpers
  getAuthHeaders: () => Record<string, string>
}

// ============================================================================
// Hook
// ============================================================================

/**
 * Hook for authentication state and operations.
 * Uses split contexts: AuthStateContext for state (re-renders on state change)
 * and AuthActionsContext for actions (stable, never causes re-render).
 */
export function useAuth(): UseAuthReturn {
  const state = useAuthState()
  const actions = useAuthActions()

  const getAuthHeadersCallback = useCallback((): Record<string, string> => {
    return getAuthHeaders(state.token)
  }, [state.token])

  return {
    // State (from AuthStateContext)
    user: state.user,
    isAuthenticated: state.isAuthenticated,
    isLoading: state.isLoading,
    isInitialized: state.isInitialized,
    error: state.error,
    pendingVerificationEmail: state.pendingVerificationEmail,
    pendingVerificationContext: state.pendingVerificationContext,

    // Actions (from AuthActionsContext -- stable references)
    login: actions.login,
    register: actions.register,
    logout: actions.logout,
    checkAuth: actions.checkAuth,
    clearError: actions.clearError,
    verifyEmail: actions.verifyEmail,
    verifyLogin: actions.verifyLogin,
    resendVerification: actions.resendVerification,
    forgotPassword: actions.forgotPassword,
    resetPassword: actions.resetPassword,
    clearPendingVerification: actions.clearPendingVerification,

    // Helpers
    getAuthHeaders: getAuthHeadersCallback,
  }
}

// ============================================================================
// Additional Hooks
// ============================================================================

/**
 * Hook that initializes authentication on mount.
 * Use this in your app's root component to check auth status on startup.
 */
export function useAuthInit(): {
  isInitialized: boolean
  isAuthenticated: boolean
  isLoading: boolean
} {
  const { checkAuth } = useAuthActions()
  const { isInitialized, isAuthenticated, isLoading } = useAuthState()

  useEffect(() => {
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
 * Hook to access only the current user.
 * Optimized for components that only need user data.
 */
export function useCurrentUser(): User | null {
  return useAuthState().user
}

/**
 * Hook to check if user is authenticated.
 * Optimized for components that only need auth status.
 */
export function useIsAuthenticated(): boolean {
  return useAuthState().isAuthenticated
}

// useAuthToken is exported from @/contexts/auth-context (canonical location).
// Import it from there to avoid duplicate definitions.

/**
 * Hook to get auth loading and error states.
 * Useful for forms that need to show loading/error feedback.
 */
export function useAuthStatus(): {
  isLoading: boolean
  error: AuthError | null
  clearError: () => void
} {
  const { isLoading, error } = useAuthState()
  const { clearError } = useAuthActions()

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
} from '@/contexts/auth-context'

export default useAuth
