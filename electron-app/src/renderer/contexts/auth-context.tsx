/**
 * Authentication Context
 *
 * React Context for managing authentication state.
 * Handles user sessions, JWT tokens, login/logout operations, and persistence.
 *
 * Features:
 * - Token persistence in localStorage
 * - Automatic token refresh on app start
 * - Type-safe state management
 * - Error handling for auth operations
 */

import {
  createContext,
  useContext,
  useReducer,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  type ReactNode,
} from 'react'
import { configureApiClient, setTokens, authGet } from '@/lib/api-client'

// ============================================================================
// Types
// ============================================================================

export interface User {
  id: string
  email: string
  display_name: string | null
  avatar_url: string | null
  email_verified: boolean
  is_developer: boolean
  created_at: string
  updated_at: string
}

export interface LoginCredentials {
  email: string
  password: string
}

export interface RegisterData {
  email: string
  password: string
  display_name?: string
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface AuthError {
  message: string
  code?: string
  field?: string
}

interface AuthState {
  user: User | null
  token: string | null
  refreshToken: string | null
  isAuthenticated: boolean
  isLoading: boolean
  isInitialized: boolean
  error: AuthError | null
  pendingVerificationEmail: string | null
  pendingVerificationContext: 'registration' | 'login' | null
}

interface AuthContextValue extends AuthState {
  login: (credentials: LoginCredentials) => Promise<boolean>
  register: (data: RegisterData) => Promise<boolean>
  logout: () => Promise<void>
  fetchCurrentUser: () => Promise<void>
  checkAuth: () => Promise<boolean>
  clearError: () => void
  setToken: (token: string | null) => void
  setUser: (user: User | null) => void
  reset: () => void
  verifyEmail: (email: string, code: string) => Promise<boolean>
  verifyLogin: (email: string, code: string) => Promise<boolean>
  resendVerification: (email: string) => Promise<boolean>
  forgotPassword: (email: string) => Promise<boolean>
  resetPassword: (email: string, code: string, newPassword: string) => Promise<boolean>
  clearPendingVerification: () => void
}

// ============================================================================
// Constants
// ============================================================================

const AUTH_STORAGE_KEY = 'pm-desktop-auth'

// ============================================================================
// Helper Functions
// ============================================================================

export function getAuthHeaders(token: string | null): Record<string, string> {
  if (!token) return {}
  return {
    Authorization: `Bearer ${token}`,
  }
}

export function parseAuthError(status: number, data: unknown): AuthError {
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

function loadPersistedTokens(): { token: string | null; refreshToken: string | null } {
  try {
    const stored = localStorage.getItem(AUTH_STORAGE_KEY)
    if (stored) {
      const data = JSON.parse(stored)
      const token = typeof data.state?.token === 'string' && data.state.token.length > 0
        ? data.state.token
        : null
      const refreshToken = typeof data.state?.refreshToken === 'string' && data.state.refreshToken.length > 0
        ? data.state.refreshToken
        : null
      return { token, refreshToken }
    }
  } catch {
    // Ignore parsing errors — treat as no persisted tokens
  }
  return { token: null, refreshToken: null }
}

function persistTokens(token: string | null, refreshToken: string | null): void {
  try {
    localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify({ state: { token, refreshToken } }))
  } catch {
    // Ignore storage errors
  }
}

// ============================================================================
// Reducer
// ============================================================================

type AuthAction =
  | { type: 'SET_LOADING'; payload: boolean }
  | { type: 'SET_ERROR'; payload: AuthError | null }
  | { type: 'SET_USER'; payload: User | null }
  | { type: 'SET_TOKEN'; payload: string | null }
  | { type: 'SET_AUTHENTICATED'; payload: boolean }
  | { type: 'SET_INITIALIZED'; payload: boolean }
  | { type: 'LOGIN_SUCCESS'; payload: { token: string; refreshToken: string; user?: User } }
  | { type: 'TOKENS_REFRESHED'; payload: { token: string; refreshToken: string } }
  | { type: 'SET_PENDING_VERIFICATION'; payload: string | null }
  | { type: 'SET_PENDING_CONTEXT'; payload: 'registration' | 'login' | null }
  | { type: 'LOGOUT' }
  | { type: 'RESET' }

const _persisted = loadPersistedTokens()

// Seed api-client module with persisted tokens immediately at module evaluation time.
// This ensures tokens are available before React effects run (child effects like
// useAuthInit's checkAuth() fire before parent AuthProvider effects).
setTokens(_persisted.token, _persisted.refreshToken)

const initialState: AuthState = {
  user: null,
  token: _persisted.token,
  refreshToken: _persisted.refreshToken,
  isAuthenticated: false,
  isLoading: false,
  isInitialized: false,
  error: null,
  pendingVerificationEmail: null,
  pendingVerificationContext: null,
}

function authReducer(state: AuthState, action: AuthAction): AuthState {
  switch (action.type) {
    case 'SET_LOADING':
      return { ...state, isLoading: action.payload }
    case 'SET_ERROR':
      return { ...state, error: action.payload }
    case 'SET_USER':
      return { ...state, user: action.payload, isAuthenticated: !!action.payload }
    case 'SET_TOKEN':
      return { ...state, token: action.payload, isAuthenticated: !!action.payload }
    case 'SET_AUTHENTICATED':
      return { ...state, isAuthenticated: action.payload }
    case 'SET_INITIALIZED':
      return { ...state, isInitialized: action.payload }
    case 'LOGIN_SUCCESS':
      return {
        ...state,
        token: action.payload.token,
        refreshToken: action.payload.refreshToken,
        user: action.payload.user || state.user,
        isAuthenticated: true,
        isLoading: false,
        error: null,
        pendingVerificationEmail: null,
        pendingVerificationContext: null,
      }
    case 'TOKENS_REFRESHED':
      // Lightweight update: only token + refreshToken changed.
      // Avoids resetting isLoading/error/pendingVerification like LOGIN_SUCCESS does,
      // which would cause unnecessary re-renders in 16+ consuming hooks.
      if (state.token === action.payload.token && state.refreshToken === action.payload.refreshToken) {
        return state // No change — skip re-render entirely
      }
      return {
        ...state,
        token: action.payload.token,
        refreshToken: action.payload.refreshToken,
      }
    case 'SET_PENDING_VERIFICATION':
      return {
        ...state,
        pendingVerificationEmail: action.payload,
      }
    case 'SET_PENDING_CONTEXT':
      return {
        ...state,
        pendingVerificationContext: action.payload,
      }
    case 'LOGOUT':
      return {
        ...state,
        user: null,
        token: null,
        refreshToken: null,
        isAuthenticated: false,
        error: null,
        pendingVerificationEmail: null,
        pendingVerificationContext: null,
      }
    case 'RESET':
      return { ...initialState, token: null, refreshToken: null }
    default:
      return state
  }
}

// ============================================================================
// Split Context Types
// ============================================================================

interface AuthActions {
  login: (credentials: LoginCredentials) => Promise<boolean>
  register: (data: RegisterData) => Promise<boolean>
  logout: () => Promise<void>
  fetchCurrentUser: () => Promise<void>
  checkAuth: () => Promise<boolean>
  clearError: () => void
  setToken: (token: string | null) => void
  setUser: (user: User | null) => void
  reset: () => void
  verifyEmail: (email: string, code: string) => Promise<boolean>
  verifyLogin: (email: string, code: string) => Promise<boolean>
  resendVerification: (email: string) => Promise<boolean>
  forgotPassword: (email: string) => Promise<boolean>
  resetPassword: (email: string, code: string, newPassword: string) => Promise<boolean>
  clearPendingVerification: () => void
}

// ============================================================================
// Context
// ============================================================================

const AuthStateContext = createContext<AuthState | null>(null)
const AuthActionsContext = createContext<AuthActions | null>(null)

// Legacy single context for backwards compatibility during migration
const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }): JSX.Element {
  const [state, dispatch] = useReducer(authReducer, initialState)

  // Refs for token values — lets callbacks close over refs instead of state,
  // so useCallback deps can be [] and actions stay truly stable.
  const tokenRef = useRef(state.token)
  const refreshTokenRef = useRef(state.refreshToken)
  useEffect(() => {
    tokenRef.current = state.token
    refreshTokenRef.current = state.refreshToken
  }, [state.token, state.refreshToken])

  // Persist token changes and sync to api-client module.
  // DA-008: localStorage is the authoritative source for auth tokens.
  // TanStack Query / IndexedDB does NOT cache auth tokens (they live in React
  // state seeded from localStorage at module evaluation time, line 190-196).
  // persistTokens writes synchronously to localStorage, so even if the app
  // crashes before IndexedDB flushes, relaunch reads fresh tokens from
  // localStorage via loadPersistedTokens(). No IndexedDB sync needed here.
  useEffect(() => {
    persistTokens(state.token, state.refreshToken)
    setTokens(state.token, state.refreshToken)
  }, [state.token, state.refreshToken])

  // Configure api-client callbacks on mount
  useEffect(() => {
    configureApiClient({
      onTokensRefreshed: (access: string, refresh: string) => {
        dispatch({
          type: 'TOKENS_REFRESHED',
          payload: { token: access, refreshToken: refresh },
        })
      },
      onSessionExpired: () => {
        dispatch({ type: 'LOGOUT' })
      },
    })
    // Seed api-client with persisted tokens on initial mount
    setTokens(state.token, state.refreshToken)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const fetchCurrentUser = useCallback(async (): Promise<void> => {
    if (!tokenRef.current) {
      dispatch({ type: 'SET_USER', payload: null })
      return
    }

    try {
      // Uses authGet which handles 401 → refresh → retry automatically
      const response = await authGet<User>('/auth/me')

      if (response.status === 200) {
        dispatch({ type: 'SET_USER', payload: response.data })
      } else if (response.status === 401 || response.status === 403) {
        // Auth failure after refresh attempt — session truly expired
        dispatch({ type: 'LOGOUT' })
      }
      // 5xx/other: keep existing state (transient server error)
    } catch {
      // Network error: keep existing state, don't logout
    }
  }, [])

  const login = useCallback(async (credentials: LoginCredentials): Promise<boolean> => {
    dispatch({ type: 'SET_LOADING', payload: true })
    dispatch({ type: 'SET_ERROR', payload: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const formData = new URLSearchParams()
      formData.append('username', credentials.email)
      formData.append('password', credentials.password)

      const response = await window.electronAPI.fetch<Record<string, unknown>>('/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: formData.toString(),
      })

      if (response.status === 403) {
        // Email not verified — redirect to verification page
        dispatch({ type: 'SET_PENDING_VERIFICATION', payload: credentials.email })
        dispatch({ type: 'SET_PENDING_CONTEXT', payload: 'registration' })
        dispatch({ type: 'SET_LOADING', payload: false })
        return false
      }

      if (response.status !== 200) {
        const error = parseAuthError(response.status, response.data)
        dispatch({ type: 'SET_ERROR', payload: error })
        dispatch({ type: 'SET_LOADING', payload: false })
        return false
      }

      const tokenData = response.data

      // Backend always requires 2FA — login returns requires_2fa instead of access_token
      if ('requires_2fa' in tokenData && tokenData.requires_2fa) {
        dispatch({ type: 'SET_PENDING_VERIFICATION', payload: credentials.email })
        dispatch({ type: 'SET_PENDING_CONTEXT', payload: 'login' })
        dispatch({ type: 'SET_LOADING', payload: false })
        return false
      }

      // Unreachable: backend always requires 2FA, but handle gracefully
      dispatch({ type: 'SET_LOADING', payload: false })
      return false
    } catch (err) {
      const error: AuthError = {
        message: err instanceof Error ? err.message : 'Login failed',
      }
      dispatch({ type: 'SET_ERROR', payload: error })
      dispatch({ type: 'SET_LOADING', payload: false })
      return false
    }
  }, [])

  const register = useCallback(async (data: RegisterData): Promise<boolean> => {
    dispatch({ type: 'SET_LOADING', payload: true })
    dispatch({ type: 'SET_ERROR', payload: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.post<{ message: string; email: string }>('/auth/register', {
        email: data.email,
        password: data.password,
        display_name: data.display_name || null,
      })

      if (response.status !== 201) {
        const error = parseAuthError(response.status, response.data)
        dispatch({ type: 'SET_ERROR', payload: error })
        dispatch({ type: 'SET_LOADING', payload: false })
        return false
      }

      dispatch({ type: 'SET_PENDING_VERIFICATION', payload: data.email })
      dispatch({ type: 'SET_PENDING_CONTEXT', payload: 'registration' })
      dispatch({ type: 'SET_LOADING', payload: false })
      return true
    } catch (err) {
      const error: AuthError = {
        message: err instanceof Error ? err.message : 'Registration failed',
      }
      dispatch({ type: 'SET_ERROR', payload: error })
      dispatch({ type: 'SET_LOADING', payload: false })
      return false
    }
  }, [])

  const logout = useCallback(async (): Promise<void> => {
    try {
      const tok = tokenRef.current
      const refTok = refreshTokenRef.current
      if (window.electronAPI && tok) {
        // Revoke refresh token + blacklist access token in parallel
        const revokePromise = refTok
          ? window.electronAPI.post('/auth/revoke', { refresh_token: refTok }, getAuthHeaders(tok))
          : Promise.resolve()
        const logoutPromise = window.electronAPI.post('/auth/logout', undefined, getAuthHeaders(tok))
        await Promise.allSettled([revokePromise, logoutPromise])
      }
    } catch {
      // Ignore logout errors
    }
    // Clear module-level AI navigation state to prevent cross-session leaks
    try {
      const { resetAiNavigation } = await import('@/lib/ai-navigation')
      resetAiNavigation()
    } catch {
      // Non-critical
    }
    // Clear WebSocket event dedup cache to prevent stale fingerprints across sessions
    try {
      const { clearEventDedup } = await import('@/hooks/use-websocket-cache')
      clearEventDedup()
    } catch {
      // Non-critical
    }
    // Disconnect WebSocket and clear its token to prevent stale connections
    try {
      const { wsClient } = await import('@/lib/websocket')
      wsClient.disconnect()
      wsClient.setToken(null)
    } catch {
      // Non-critical
    }
    dispatch({ type: 'LOGOUT' })
  }, [])

  const checkAuth = useCallback(async (): Promise<boolean> => {
    if (!tokenRef.current) {
      dispatch({ type: 'SET_INITIALIZED', payload: true })
      dispatch({ type: 'SET_AUTHENTICATED', payload: false })
      return false
    }

    dispatch({ type: 'SET_LOADING', payload: true })

    try {
      // Uses authGet which handles 401 → refresh → retry automatically
      const response = await authGet<User>('/auth/me')

      if (response.status === 200) {
        dispatch({ type: 'SET_USER', payload: response.data })
        dispatch({ type: 'SET_INITIALIZED', payload: true })
        dispatch({ type: 'SET_LOADING', payload: false })
        return true
      } else if (response.status === 401 || response.status === 403) {
        // Auth failure after refresh attempt — session truly expired
        dispatch({ type: 'LOGOUT' })
        dispatch({ type: 'SET_INITIALIZED', payload: true })
        dispatch({ type: 'SET_LOADING', payload: false })
        return false
      } else {
        // 5xx/other: transient error — keep existing state
        dispatch({ type: 'SET_INITIALIZED', payload: true })
        dispatch({ type: 'SET_LOADING', payload: false })
        return false
      }
    } catch {
      // Network error: keep existing state (do not log out)
      dispatch({ type: 'SET_INITIALIZED', payload: true })
      dispatch({ type: 'SET_LOADING', payload: false })
      return false
    }
  }, [])

  const clearError = useCallback((): void => {
    dispatch({ type: 'SET_ERROR', payload: null })
  }, [])

  const setToken = useCallback((token: string | null): void => {
    dispatch({ type: 'SET_TOKEN', payload: token })
  }, [])

  const setUser = useCallback((user: User | null): void => {
    dispatch({ type: 'SET_USER', payload: user })
  }, [])

  const reset = useCallback((): void => {
    dispatch({ type: 'RESET' })
  }, [])

  const verifyEmail = useCallback(async (email: string, code: string): Promise<boolean> => {
    dispatch({ type: 'SET_LOADING', payload: true })
    dispatch({ type: 'SET_ERROR', payload: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.post<TokenResponse>('/auth/verify-email', {
        email,
        code,
      })

      if (response.status !== 200) {
        const error = parseAuthError(response.status, response.data)
        dispatch({ type: 'SET_ERROR', payload: error })
        dispatch({ type: 'SET_LOADING', payload: false })
        return false
      }

      const tokenData = response.data
      dispatch({
        type: 'LOGIN_SUCCESS',
        payload: { token: tokenData.access_token, refreshToken: tokenData.refresh_token },
      })

      // Fetch user profile
      const userResponse = await window.electronAPI.get<User>(
        '/auth/me',
        getAuthHeaders(tokenData.access_token)
      )

      if (userResponse.status === 200) {
        dispatch({ type: 'SET_USER', payload: userResponse.data })
      }

      return true
    } catch (err) {
      const error: AuthError = {
        message: err instanceof Error ? err.message : 'Verification failed',
      }
      dispatch({ type: 'SET_ERROR', payload: error })
      dispatch({ type: 'SET_LOADING', payload: false })
      return false
    }
  }, [])

  const verifyLogin = useCallback(async (email: string, code: string): Promise<boolean> => {
    dispatch({ type: 'SET_LOADING', payload: true })
    dispatch({ type: 'SET_ERROR', payload: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.post<TokenResponse>('/auth/verify-login', {
        email,
        code,
      })

      if (response.status !== 200) {
        const error = parseAuthError(response.status, response.data)
        dispatch({ type: 'SET_ERROR', payload: error })
        dispatch({ type: 'SET_LOADING', payload: false })
        return false
      }

      const tokenData = response.data
      dispatch({
        type: 'LOGIN_SUCCESS',
        payload: { token: tokenData.access_token, refreshToken: tokenData.refresh_token },
      })

      // Fetch user profile
      const userResponse = await window.electronAPI.get<User>(
        '/auth/me',
        getAuthHeaders(tokenData.access_token)
      )

      if (userResponse.status === 200) {
        dispatch({ type: 'SET_USER', payload: userResponse.data })
      }

      return true
    } catch (err) {
      const error: AuthError = {
        message: err instanceof Error ? err.message : 'Verification failed',
      }
      dispatch({ type: 'SET_ERROR', payload: error })
      dispatch({ type: 'SET_LOADING', payload: false })
      return false
    }
  }, [])

  const resendVerification = useCallback(async (email: string): Promise<boolean> => {
    dispatch({ type: 'SET_ERROR', payload: null })
    dispatch({ type: 'SET_LOADING', payload: true })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.post<{ message: string }>('/auth/resend-verification', {
        email,
      })

      if (response.status !== 200) {
        const error = parseAuthError(response.status, response.data)
        dispatch({ type: 'SET_ERROR', payload: error })
        dispatch({ type: 'SET_LOADING', payload: false })
        return false
      }

      dispatch({ type: 'SET_LOADING', payload: false })
      return true
    } catch (err) {
      const error: AuthError = {
        message: err instanceof Error ? err.message : 'Failed to resend code',
      }
      dispatch({ type: 'SET_ERROR', payload: error })
      dispatch({ type: 'SET_LOADING', payload: false })
      return false
    }
  }, [])

  const forgotPassword = useCallback(async (email: string): Promise<boolean> => {
    dispatch({ type: 'SET_LOADING', payload: true })
    dispatch({ type: 'SET_ERROR', payload: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.post<{ message: string }>('/auth/forgot-password', {
        email,
      })

      if (response.status !== 200) {
        const error = parseAuthError(response.status, response.data)
        dispatch({ type: 'SET_ERROR', payload: error })
        dispatch({ type: 'SET_LOADING', payload: false })
        return false
      }

      dispatch({ type: 'SET_LOADING', payload: false })
      return true
    } catch (err) {
      const error: AuthError = {
        message: err instanceof Error ? err.message : 'Failed to send reset code',
      }
      dispatch({ type: 'SET_ERROR', payload: error })
      dispatch({ type: 'SET_LOADING', payload: false })
      return false
    }
  }, [])

  const resetPassword = useCallback(async (email: string, code: string, newPassword: string): Promise<boolean> => {
    dispatch({ type: 'SET_LOADING', payload: true })
    dispatch({ type: 'SET_ERROR', payload: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.post<{ message: string }>('/auth/reset-password', {
        email,
        code,
        new_password: newPassword,
      })

      if (response.status !== 200) {
        const error = parseAuthError(response.status, response.data)
        dispatch({ type: 'SET_ERROR', payload: error })
        dispatch({ type: 'SET_LOADING', payload: false })
        return false
      }

      dispatch({ type: 'SET_LOADING', payload: false })
      return true
    } catch (err) {
      const error: AuthError = {
        message: err instanceof Error ? err.message : 'Password reset failed',
      }
      dispatch({ type: 'SET_ERROR', payload: error })
      dispatch({ type: 'SET_LOADING', payload: false })
      return false
    }
  }, [])

  const clearPendingVerification = useCallback((): void => {
    dispatch({ type: 'SET_PENDING_VERIFICATION', payload: null })
  }, [])

  // Actions are stable (created via useCallback with [] or [state.token] deps).
  // Memoize the actions object so AuthActionsContext consumers don't re-render
  // when state changes -- only when action functions themselves change.
  const actions: AuthActions = useMemo(() => ({
    login,
    register,
    logout,
    fetchCurrentUser,
    checkAuth,
    clearError,
    setToken,
    setUser,
    reset,
    verifyEmail,
    verifyLogin,
    resendVerification,
    forgotPassword,
    resetPassword,
    clearPendingVerification,
  }), [
    login, register, logout, fetchCurrentUser, checkAuth, clearError,
    setToken, setUser, reset, verifyEmail, verifyLogin, resendVerification,
    forgotPassword, resetPassword, clearPendingVerification,
  ])

  const value: AuthContextValue = {
    ...state,
    ...actions,
  }

  return (
    <AuthContext.Provider value={value}>
      <AuthStateContext.Provider value={state}>
        <AuthActionsContext.Provider value={actions}>
          {children}
        </AuthActionsContext.Provider>
      </AuthStateContext.Provider>
    </AuthContext.Provider>
  )
}

// ============================================================================
// Hook
// ============================================================================

/**
 * @deprecated **DO NOT USE IN NEW CODE.** Use `useAuthState()` for state or
 * `useAuthActions()` for actions. This hook reads from the legacy monolithic
 * AuthContext and does not benefit from the split-context re-render
 * optimization. It will be removed in a future release.
 */
export function useAuthStore(): AuthContextValue
export function useAuthStore<T>(selector: (state: AuthContextValue) => T): T
export function useAuthStore<T>(selector?: (state: AuthContextValue) => T): AuthContextValue | T {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuthStore must be used within an AuthProvider')
  }
  return selector ? selector(context) : context
}

/**
 * Hook for auth state only. Consumers re-render only when state changes,
 * NOT when action functions are recreated.
 */
export function useAuthState(): AuthState {
  const context = useContext(AuthStateContext)
  if (!context) {
    throw new Error('useAuthState must be used within an AuthProvider')
  }
  return context
}

/**
 * Hook for auth actions only. Actions are stable (memoized),
 * so consumers almost never re-render from this context.
 */
export function useAuthActions(): AuthActions {
  const context = useContext(AuthActionsContext)
  if (!context) {
    throw new Error('useAuthActions must be used within an AuthProvider')
  }
  return context
}

// ============================================================================
// Convenience Hooks (thin wrappers over split contexts)
// ============================================================================

/**
 * Hook for the auth token. Components using this only re-render when state changes,
 * NOT when action callbacks are recreated.
 */
export function useAuthToken(): string | null {
  return useAuthState().token
}

/**
 * Hook for the current user's ID.
 */
export function useAuthUserId(): string | null {
  return useAuthState().user?.id ?? null
}

/**
 * Hook for the current user object.
 */
export function useAuthUser(): User | null {
  return useAuthState().user
}

// ============================================================================
// Selectors (kept for backwards compatibility with tests)
// ============================================================================

export const selectUser = (state: AuthContextValue): User | null => state.user
export const selectIsAuthenticated = (state: AuthContextValue): boolean => state.isAuthenticated
export const selectIsLoading = (state: AuthContextValue): boolean => state.isLoading
export const selectIsInitialized = (state: AuthContextValue): boolean => state.isInitialized
export const selectError = (state: AuthContextValue): AuthError | null => state.error

export default AuthContext
