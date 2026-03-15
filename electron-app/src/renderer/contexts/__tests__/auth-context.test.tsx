import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import type { ReactNode } from 'react'

// Use vi.hoisted so mock fns are available inside hoisted vi.mock factories
const { mockConfigureApiClient, mockSetTokens, mockAuthGet } = vi.hoisted(() => ({
  mockConfigureApiClient: vi.fn(),
  mockSetTokens: vi.fn(),
  mockAuthGet: vi.fn(),
}))

vi.mock('@/lib/api-client', () => ({
  configureApiClient: mockConfigureApiClient,
  setTokens: mockSetTokens,
  authGet: mockAuthGet,
}))

// Mock dynamic imports used by logout
vi.mock('@/lib/ai-navigation', () => ({
  resetAiNavigation: vi.fn(),
}))

vi.mock('@/lib/websocket', () => ({
  wsClient: {
    disconnect: vi.fn(),
    setToken: vi.fn(),
  },
}))

// Import after mocks are set up
import {
  AuthProvider,
  useAuthStore,
  useAuthState,
  useAuthActions,
  useAuthToken,
  useAuthUserId,
  useAuthUser,
  getAuthHeaders,
  parseAuthError,
  selectUser,
  selectIsAuthenticated,
  selectIsLoading,
  selectIsInitialized,
  selectError,
} from '../auth-context'
import type { User } from '../auth-context'

// ============================================================================
// Helpers
// ============================================================================

function wrapper({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>
}

const mockUser: User = {
  id: 'user-1',
  email: 'test@example.com',
  display_name: 'Test User',
  avatar_url: null,
  email_verified: true,
  is_developer: false,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

// ============================================================================
// Pure helper tests
// ============================================================================

describe('getAuthHeaders', () => {
  it('returns empty object when token is null', () => {
    expect(getAuthHeaders(null)).toEqual({})
  })

  it('returns Authorization header when token is provided', () => {
    expect(getAuthHeaders('abc123')).toEqual({ Authorization: 'Bearer abc123' })
  })
})

describe('parseAuthError', () => {
  it('extracts string detail', () => {
    expect(parseAuthError(400, { detail: 'Bad request' })).toEqual({ message: 'Bad request' })
  })

  it('extracts validation array detail', () => {
    const data = { detail: [{ loc: ['body', 'email'], msg: 'invalid email' }] }
    expect(parseAuthError(422, data)).toEqual({ message: 'invalid email', field: 'email' })
  })

  it('falls back to status-based messages', () => {
    expect(parseAuthError(401, {})).toEqual({ message: 'Invalid credentials. Please try again.' })
    expect(parseAuthError(403, {})).toEqual({ message: 'Access denied.' })
    expect(parseAuthError(404, {})).toEqual({ message: 'Resource not found.' })
    expect(parseAuthError(500, {})).toEqual({ message: 'Server error. Please try again later.' })
    expect(parseAuthError(418, {})).toEqual({ message: 'An unexpected error occurred.' })
  })

  it('handles null/non-object data', () => {
    expect(parseAuthError(400, null)).toEqual({ message: 'Invalid request. Please check your input.' })
    expect(parseAuthError(400, 'string')).toEqual({ message: 'Invalid request. Please check your input.' })
  })
})

// ============================================================================
// Selectors
// ============================================================================

describe('selectors', () => {
  const state = {
    user: mockUser,
    token: 'tok',
    refreshToken: 'ref',
    isAuthenticated: true,
    isLoading: false,
    isInitialized: true,
    error: null,
    pendingVerificationEmail: null,
    pendingVerificationContext: null,
  } as never

  it('selectUser returns user', () => {
    expect(selectUser(state)).toBe(mockUser)
  })

  it('selectIsAuthenticated returns boolean', () => {
    expect(selectIsAuthenticated(state)).toBe(true)
  })

  it('selectIsLoading returns boolean', () => {
    expect(selectIsLoading(state)).toBe(false)
  })

  it('selectIsInitialized returns boolean', () => {
    expect(selectIsInitialized(state)).toBe(true)
  })

  it('selectError returns null', () => {
    expect(selectError(state)).toBeNull()
  })
})

// ============================================================================
// AuthProvider and hooks
// ============================================================================

describe('AuthProvider', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.getItem.mockReturnValue(null)
    // Reset __apiClientState to prevent state leak between tests
    delete (window as Record<string, unknown>).__apiClientState
  })

  it('provides initial state with no persisted tokens', () => {
    const { result } = renderHook(() => useAuthState(), { wrapper })

    expect(result.current.user).toBeNull()
    expect(result.current.isAuthenticated).toBe(false)
    expect(result.current.isLoading).toBe(false)
    expect(result.current.isInitialized).toBe(false)
    expect(result.current.error).toBeNull()
  })

  it('calls configureApiClient on mount', () => {
    renderHook(() => useAuthState(), { wrapper })

    expect(mockConfigureApiClient).toHaveBeenCalledWith(
      expect.objectContaining({
        onTokensRefreshed: expect.any(Function),
        onSessionExpired: expect.any(Function),
      })
    )
  })

  it('persists tokens via setTokens on state change', async () => {
    const { result } = renderHook(() => useAuthActions(), { wrapper })

    await act(async () => {
      result.current.setToken('new-token')
    })

    // setTokens is called by the useEffect when token changes
    expect(mockSetTokens).toHaveBeenCalled()
  })

  // DA-008: localStorage is the authoritative token source; IndexedDB never stores auth tokens.
  // Verify that persistTokens writes to localStorage synchronously and loadPersistedTokens
  // validates token types (non-string or empty values become null).
  it('persistTokens writes to localStorage synchronously (DA-008)', async () => {
    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    await act(async () => {
      result.current.actions.setToken('tok-sync')
    })

    // persistTokens is called inside the useEffect on token change
    expect(window.localStorage.setItem).toHaveBeenCalledWith(
      'pm-desktop-auth',
      expect.stringContaining('tok-sync')
    )
  })

  it('loadPersistedTokens treats empty string tokens as null (DA-008)', () => {
    // Set up localStorage with empty string token
    window.localStorage.getItem.mockReturnValue(
      JSON.stringify({ state: { token: '', refreshToken: '' } })
    )

    // Re-render with the mocked localStorage
    const { result } = renderHook(() => useAuthState(), { wrapper })

    // Empty string tokens from localStorage should not be used as valid tokens
    // The provider should treat them as null (no auth)
    expect(result.current.token).toBeNull()
  })
})

// ============================================================================
// Split context hooks
// ============================================================================

describe('split context hooks', () => {
  it('useAuthState returns state object', () => {
    const { result } = renderHook(() => useAuthState(), { wrapper })
    expect(result.current).toHaveProperty('isAuthenticated')
    expect(result.current).toHaveProperty('token')
    expect(result.current).toHaveProperty('user')
  })

  it('useAuthActions returns action functions', () => {
    const { result } = renderHook(() => useAuthActions(), { wrapper })
    expect(typeof result.current.login).toBe('function')
    expect(typeof result.current.logout).toBe('function')
    expect(typeof result.current.register).toBe('function')
    expect(typeof result.current.checkAuth).toBe('function')
    expect(typeof result.current.fetchCurrentUser).toBe('function')
  })

  it('useAuthToken returns token from state', () => {
    const { result } = renderHook(() => useAuthToken(), { wrapper })
    expect(result.current).toBeNull()
  })

  it('useAuthUserId returns null when no user', () => {
    const { result } = renderHook(() => useAuthUserId(), { wrapper })
    expect(result.current).toBeNull()
  })

  it('useAuthUser returns null when no user', () => {
    const { result } = renderHook(() => useAuthUser(), { wrapper })
    expect(result.current).toBeNull()
  })

  it('useAuthStore throws outside AuthProvider', () => {
    expect(() => {
      renderHook(() => useAuthStore())
    }).toThrow('useAuthStore must be used within an AuthProvider')
  })

  it('useAuthState throws outside AuthProvider', () => {
    expect(() => {
      renderHook(() => useAuthState())
    }).toThrow('useAuthState must be used within an AuthProvider')
  })

  it('useAuthActions throws outside AuthProvider', () => {
    expect(() => {
      renderHook(() => useAuthActions())
    }).toThrow('useAuthActions must be used within an AuthProvider')
  })

  it('useAuthStore with selector returns selected value', () => {
    const { result } = renderHook(() => useAuthStore((s) => s.isAuthenticated), { wrapper })
    expect(result.current).toBe(false)
  })
})

// ============================================================================
// login
// ============================================================================

describe('login', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.getItem.mockReturnValue(null)
    delete (window as Record<string, unknown>).__apiClientState
  })

  it('successful login dispatches LOGIN_SUCCESS and fetches user', async () => {
    window.electronAPI.fetch.mockResolvedValueOnce({
      status: 200,
      data: { access_token: 'at-1', refresh_token: 'rt-1', token_type: 'bearer' },
    })
    window.electronAPI.get.mockResolvedValueOnce({
      status: 200,
      data: mockUser,
    })

    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    let success: boolean
    await act(async () => {
      success = await result.current.actions.login({ email: 'test@example.com', password: 'pass' })
    })

    expect(success!).toBe(true)
    expect(result.current.state.isAuthenticated).toBe(true)
    expect(result.current.state.token).toBe('at-1')
    expect(result.current.state.user).toEqual(mockUser)
    expect(result.current.state.isLoading).toBe(false)

    // Verify form-urlencoded POST was used
    expect(window.electronAPI.fetch).toHaveBeenCalledWith('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: expect.stringContaining('username=test%40example.com'),
    })
  })

  it('login with 2FA required sets pending verification context to login', async () => {
    window.electronAPI.fetch.mockResolvedValueOnce({
      status: 200,
      data: { requires_2fa: true },
    })

    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    let success: boolean
    await act(async () => {
      success = await result.current.actions.login({ email: 'test@example.com', password: 'pass' })
    })

    expect(success!).toBe(false)
    expect(result.current.state.pendingVerificationEmail).toBe('test@example.com')
    expect(result.current.state.pendingVerificationContext).toBe('login')
    expect(result.current.state.isLoading).toBe(false)
  })

  it('login with 403 (email unverified) sets pending verification context to registration', async () => {
    window.electronAPI.fetch.mockResolvedValueOnce({
      status: 403,
      data: { detail: 'Email not verified' },
    })

    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    let success: boolean
    await act(async () => {
      success = await result.current.actions.login({ email: 'test@example.com', password: 'pass' })
    })

    expect(success!).toBe(false)
    expect(result.current.state.pendingVerificationEmail).toBe('test@example.com')
    expect(result.current.state.pendingVerificationContext).toBe('registration')
    expect(result.current.state.isLoading).toBe(false)
  })

  it('login with non-200 non-403 sets error', async () => {
    window.electronAPI.fetch.mockResolvedValueOnce({
      status: 401,
      data: { detail: 'Invalid credentials' },
    })

    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    await act(async () => {
      await result.current.actions.login({ email: 'test@example.com', password: 'wrong' })
    })

    expect(result.current.state.error).toEqual({ message: 'Invalid credentials' })
    expect(result.current.state.isLoading).toBe(false)
  })

  it('login catches exceptions and sets error', async () => {
    window.electronAPI.fetch.mockRejectedValueOnce(new Error('Network error'))

    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    let success: boolean
    await act(async () => {
      success = await result.current.actions.login({ email: 'test@example.com', password: 'pass' })
    })

    expect(success!).toBe(false)
    expect(result.current.state.error?.message).toBe('Network error')
  })
})

// ============================================================================
// register
// ============================================================================

describe('register', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.getItem.mockReturnValue(null)
    delete (window as Record<string, unknown>).__apiClientState
  })

  it('successful registration sets pending verification', async () => {
    window.electronAPI.post.mockResolvedValueOnce({
      status: 201,
      data: { message: 'Verification email sent', email: 'new@example.com' },
    })

    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    let success: boolean
    await act(async () => {
      success = await result.current.actions.register({
        email: 'new@example.com',
        password: 'pass123',
        display_name: 'New User',
      })
    })

    expect(success!).toBe(true)
    expect(result.current.state.pendingVerificationEmail).toBe('new@example.com')
    expect(result.current.state.pendingVerificationContext).toBe('registration')
    expect(result.current.state.isLoading).toBe(false)
  })

  it('registration failure sets error', async () => {
    window.electronAPI.post.mockResolvedValueOnce({
      status: 409,
      data: { detail: 'Email already registered' },
    })

    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    let success: boolean
    await act(async () => {
      success = await result.current.actions.register({
        email: 'existing@example.com',
        password: 'pass123',
      })
    })

    expect(success!).toBe(false)
    expect(result.current.state.error?.message).toBe('Email already registered')
  })
})

// ============================================================================
// logout
// ============================================================================

describe('logout', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.getItem.mockReturnValue(null)
    delete (window as Record<string, unknown>).__apiClientState
  })

  it('clears auth state on logout', async () => {
    // First login
    window.electronAPI.fetch.mockResolvedValueOnce({
      status: 200,
      data: { access_token: 'at', refresh_token: 'rt', token_type: 'bearer' },
    })
    window.electronAPI.get.mockResolvedValueOnce({ status: 200, data: mockUser })
    // Revoke + logout calls
    window.electronAPI.post.mockResolvedValue({ status: 200, data: {} })

    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    await act(async () => {
      await result.current.actions.login({ email: 'test@example.com', password: 'pass' })
    })

    expect(result.current.state.isAuthenticated).toBe(true)

    await act(async () => {
      await result.current.actions.logout()
    })

    expect(result.current.state.isAuthenticated).toBe(false)
    expect(result.current.state.user).toBeNull()
    expect(result.current.state.token).toBeNull()
    expect(result.current.state.refreshToken).toBeNull()
  })
})

// ============================================================================
// checkAuth
// ============================================================================

describe('checkAuth', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.getItem.mockReturnValue(null)
    delete (window as Record<string, unknown>).__apiClientState
  })

  it('returns false and sets initialized when no token', async () => {
    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    let authenticated: boolean
    await act(async () => {
      authenticated = await result.current.actions.checkAuth()
    })

    expect(authenticated!).toBe(false)
    expect(result.current.state.isInitialized).toBe(true)
    expect(result.current.state.isAuthenticated).toBe(false)
  })

  it('returns true on successful auth check with token', async () => {
    // Login first to get a token
    window.electronAPI.fetch.mockResolvedValueOnce({
      status: 200,
      data: { access_token: 'at', refresh_token: 'rt', token_type: 'bearer' },
    })
    window.electronAPI.get.mockResolvedValueOnce({ status: 200, data: mockUser })

    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    await act(async () => {
      await result.current.actions.login({ email: 'test@example.com', password: 'pass' })
    })

    // Now mock authGet for checkAuth
    mockAuthGet.mockResolvedValueOnce({ status: 200, data: mockUser })

    let authenticated: boolean
    await act(async () => {
      authenticated = await result.current.actions.checkAuth()
    })

    expect(authenticated!).toBe(true)
    expect(result.current.state.isInitialized).toBe(true)
    expect(result.current.state.user).toEqual(mockUser)
  })

  it('dispatches LOGOUT on 401 response', async () => {
    // Login first
    window.electronAPI.fetch.mockResolvedValueOnce({
      status: 200,
      data: { access_token: 'at', refresh_token: 'rt', token_type: 'bearer' },
    })
    window.electronAPI.get.mockResolvedValueOnce({ status: 200, data: mockUser })

    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    await act(async () => {
      await result.current.actions.login({ email: 'test@example.com', password: 'pass' })
    })

    expect(result.current.state.isAuthenticated).toBe(true)

    // checkAuth returns 401 -> LOGOUT
    mockAuthGet.mockResolvedValueOnce({ status: 401, data: { detail: 'Expired' } })

    await act(async () => {
      await result.current.actions.checkAuth()
    })

    expect(result.current.state.isAuthenticated).toBe(false)
    expect(result.current.state.user).toBeNull()
    expect(result.current.state.token).toBeNull()
  })

  it('does NOT logout on 500 (transient server error)', async () => {
    // Login first
    window.electronAPI.fetch.mockResolvedValueOnce({
      status: 200,
      data: { access_token: 'at', refresh_token: 'rt', token_type: 'bearer' },
    })
    window.electronAPI.get.mockResolvedValueOnce({ status: 200, data: mockUser })

    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    await act(async () => {
      await result.current.actions.login({ email: 'test@example.com', password: 'pass' })
    })

    expect(result.current.state.isAuthenticated).toBe(true)

    // checkAuth returns 500 -> should NOT logout
    mockAuthGet.mockResolvedValueOnce({ status: 500, data: { detail: 'Server error' } })

    let authenticated: boolean
    await act(async () => {
      authenticated = await result.current.actions.checkAuth()
    })

    expect(authenticated!).toBe(false)
    // Should keep existing auth state (not LOGOUT)
    expect(result.current.state.token).toBe('at')
    expect(result.current.state.user).toEqual(mockUser)
    expect(result.current.state.isInitialized).toBe(true)
  })

  it('sets authenticated false on network error (does not LOGOUT)', async () => {
    // Login first
    window.electronAPI.fetch.mockResolvedValueOnce({
      status: 200,
      data: { access_token: 'at', refresh_token: 'rt', token_type: 'bearer' },
    })
    window.electronAPI.get.mockResolvedValueOnce({ status: 200, data: mockUser })

    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    await act(async () => {
      await result.current.actions.login({ email: 'test@example.com', password: 'pass' })
    })

    // checkAuth throws network error
    mockAuthGet.mockRejectedValueOnce(new Error('Network error'))

    let authenticated: boolean
    await act(async () => {
      authenticated = await result.current.actions.checkAuth()
    })

    expect(authenticated!).toBe(false)
    expect(result.current.state.isInitialized).toBe(true)
  })
})

// ============================================================================
// fetchCurrentUser
// ============================================================================

describe('fetchCurrentUser', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.getItem.mockReturnValue(null)
    delete (window as Record<string, unknown>).__apiClientState
  })

  it('sets user to null when no token', async () => {
    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    await act(async () => {
      await result.current.actions.fetchCurrentUser()
    })

    expect(result.current.state.user).toBeNull()
    expect(mockAuthGet).not.toHaveBeenCalled()
  })

  it('sets user on successful fetch', async () => {
    // Login first
    window.electronAPI.fetch.mockResolvedValueOnce({
      status: 200,
      data: { access_token: 'at', refresh_token: 'rt', token_type: 'bearer' },
    })
    window.electronAPI.get.mockResolvedValueOnce({ status: 200, data: mockUser })

    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    await act(async () => {
      await result.current.actions.login({ email: 'test@example.com', password: 'pass' })
    })

    mockAuthGet.mockResolvedValueOnce({ status: 200, data: { ...mockUser, display_name: 'Updated' } })

    await act(async () => {
      await result.current.actions.fetchCurrentUser()
    })

    expect(result.current.state.user?.display_name).toBe('Updated')
  })

  it('dispatches LOGOUT on 401 response', async () => {
    // Login first
    window.electronAPI.fetch.mockResolvedValueOnce({
      status: 200,
      data: { access_token: 'at', refresh_token: 'rt', token_type: 'bearer' },
    })
    window.electronAPI.get.mockResolvedValueOnce({ status: 200, data: mockUser })

    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    await act(async () => {
      await result.current.actions.login({ email: 'test@example.com', password: 'pass' })
    })

    expect(result.current.state.isAuthenticated).toBe(true)

    // fetchCurrentUser returns 401
    mockAuthGet.mockResolvedValueOnce({ status: 401, data: {} })

    await act(async () => {
      await result.current.actions.fetchCurrentUser()
    })

    expect(result.current.state.isAuthenticated).toBe(false)
    expect(result.current.state.user).toBeNull()
    expect(result.current.state.token).toBeNull()
  })

  it('does NOT logout on 500 (transient server error)', async () => {
    // Login first
    window.electronAPI.fetch.mockResolvedValueOnce({
      status: 200,
      data: { access_token: 'at', refresh_token: 'rt', token_type: 'bearer' },
    })
    window.electronAPI.get.mockResolvedValueOnce({ status: 200, data: mockUser })

    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    await act(async () => {
      await result.current.actions.login({ email: 'test@example.com', password: 'pass' })
    })

    expect(result.current.state.isAuthenticated).toBe(true)

    // fetchCurrentUser returns 500 -> should NOT logout
    mockAuthGet.mockResolvedValueOnce({ status: 500, data: {} })

    await act(async () => {
      await result.current.actions.fetchCurrentUser()
    })

    // Should keep existing auth state
    expect(result.current.state.token).toBe('at')
    expect(result.current.state.user).toEqual(mockUser)
  })

  it('does NOT logout on network exception', async () => {
    // Login first
    window.electronAPI.fetch.mockResolvedValueOnce({
      status: 200,
      data: { access_token: 'at', refresh_token: 'rt', token_type: 'bearer' },
    })
    window.electronAPI.get.mockResolvedValueOnce({ status: 200, data: mockUser })

    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    await act(async () => {
      await result.current.actions.login({ email: 'test@example.com', password: 'pass' })
    })

    mockAuthGet.mockRejectedValueOnce(new Error('Fail'))

    await act(async () => {
      await result.current.actions.fetchCurrentUser()
    })

    // Network error should NOT logout — keep existing state
    expect(result.current.state.token).toBe('at')
    expect(result.current.state.user).toEqual(mockUser)
  })
})

// ============================================================================
// TOKENS_REFRESHED reducer optimization
// ============================================================================

describe('TOKENS_REFRESHED skip-rerender optimization', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.getItem.mockReturnValue(null)
    delete (window as Record<string, unknown>).__apiClientState
  })

  it('does not update state when tokens are identical (skip re-render)', async () => {
    // Login to set tokens
    window.electronAPI.fetch.mockResolvedValueOnce({
      status: 200,
      data: { access_token: 'at-same', refresh_token: 'rt-same', token_type: 'bearer' },
    })
    window.electronAPI.get.mockResolvedValueOnce({ status: 200, data: mockUser })

    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    await act(async () => {
      await result.current.actions.login({ email: 'test@example.com', password: 'pass' })
    })

    const stateBeforeRefresh = result.current.state

    // Simulate onTokensRefreshed callback from configureApiClient with same tokens
    const configCall = mockConfigureApiClient.mock.calls[0][0]
    await act(async () => {
      configCall.onTokensRefreshed('at-same', 'rt-same')
    })

    // State reference should be the same (skip re-render)
    expect(result.current.state.token).toBe('at-same')
    expect(result.current.state.refreshToken).toBe('rt-same')
  })

  it('updates state when tokens differ', async () => {
    // Login to set tokens
    window.electronAPI.fetch.mockResolvedValueOnce({
      status: 200,
      data: { access_token: 'at-old', refresh_token: 'rt-old', token_type: 'bearer' },
    })
    window.electronAPI.get.mockResolvedValueOnce({ status: 200, data: mockUser })

    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    await act(async () => {
      await result.current.actions.login({ email: 'test@example.com', password: 'pass' })
    })

    // Simulate onTokensRefreshed with NEW tokens
    const configCall = mockConfigureApiClient.mock.calls[0][0]
    await act(async () => {
      configCall.onTokensRefreshed('at-new', 'rt-new')
    })

    expect(result.current.state.token).toBe('at-new')
    expect(result.current.state.refreshToken).toBe('rt-new')
    // Should still be authenticated
    expect(result.current.state.isAuthenticated).toBe(true)
  })

  it('onSessionExpired triggers LOGOUT', async () => {
    // Login first
    window.electronAPI.fetch.mockResolvedValueOnce({
      status: 200,
      data: { access_token: 'at', refresh_token: 'rt', token_type: 'bearer' },
    })
    window.electronAPI.get.mockResolvedValueOnce({ status: 200, data: mockUser })

    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    await act(async () => {
      await result.current.actions.login({ email: 'test@example.com', password: 'pass' })
    })

    expect(result.current.state.isAuthenticated).toBe(true)

    // Simulate session expired callback
    const configCall = mockConfigureApiClient.mock.calls[0][0]
    await act(async () => {
      configCall.onSessionExpired()
    })

    expect(result.current.state.isAuthenticated).toBe(false)
    expect(result.current.state.token).toBeNull()
  })
})

// ============================================================================
// verifyEmail
// ============================================================================

describe('verifyEmail', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.getItem.mockReturnValue(null)
    delete (window as Record<string, unknown>).__apiClientState
  })

  it('successful verification logs user in', async () => {
    window.electronAPI.post.mockResolvedValueOnce({
      status: 200,
      data: { access_token: 'at-verify', refresh_token: 'rt-verify', token_type: 'bearer' },
    })
    window.electronAPI.get.mockResolvedValueOnce({ status: 200, data: mockUser })

    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    let success: boolean
    await act(async () => {
      success = await result.current.actions.verifyEmail('test@example.com', '123456')
    })

    expect(success!).toBe(true)
    expect(result.current.state.isAuthenticated).toBe(true)
    expect(result.current.state.token).toBe('at-verify')
    expect(result.current.state.user).toEqual(mockUser)
  })

  it('verification failure sets error', async () => {
    window.electronAPI.post.mockResolvedValueOnce({
      status: 400,
      data: { detail: 'Invalid code' },
    })

    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    let success: boolean
    await act(async () => {
      success = await result.current.actions.verifyEmail('test@example.com', 'bad')
    })

    expect(success!).toBe(false)
    expect(result.current.state.error?.message).toBe('Invalid code')
  })
})

// ============================================================================
// verifyLogin
// ============================================================================

describe('verifyLogin', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.getItem.mockReturnValue(null)
    delete (window as Record<string, unknown>).__apiClientState
  })

  it('successful 2FA verification logs user in', async () => {
    window.electronAPI.post.mockResolvedValueOnce({
      status: 200,
      data: { access_token: 'at-2fa', refresh_token: 'rt-2fa', token_type: 'bearer' },
    })
    window.electronAPI.get.mockResolvedValueOnce({ status: 200, data: mockUser })

    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    let success: boolean
    await act(async () => {
      success = await result.current.actions.verifyLogin('test@example.com', '123456')
    })

    expect(success!).toBe(true)
    expect(result.current.state.isAuthenticated).toBe(true)
    expect(result.current.state.token).toBe('at-2fa')
  })

  it('2FA failure sets error', async () => {
    window.electronAPI.post.mockResolvedValueOnce({
      status: 400,
      data: { detail: 'Invalid 2FA code' },
    })

    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    let success: boolean
    await act(async () => {
      success = await result.current.actions.verifyLogin('test@example.com', 'bad')
    })

    expect(success!).toBe(false)
    expect(result.current.state.error?.message).toBe('Invalid 2FA code')
  })
})

// ============================================================================
// Misc actions
// ============================================================================

describe('misc actions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.getItem.mockReturnValue(null)
    delete (window as Record<string, unknown>).__apiClientState
  })

  it('clearError clears error state', async () => {
    // Trigger an error first
    window.electronAPI.fetch.mockResolvedValueOnce({
      status: 401,
      data: { detail: 'Bad creds' },
    })

    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    await act(async () => {
      await result.current.actions.login({ email: 'x', password: 'y' })
    })

    expect(result.current.state.error).not.toBeNull()

    await act(async () => {
      result.current.actions.clearError()
    })

    expect(result.current.state.error).toBeNull()
  })

  it('setUser updates user and isAuthenticated', async () => {
    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    await act(async () => {
      result.current.actions.setUser(mockUser)
    })

    expect(result.current.state.user).toEqual(mockUser)
    expect(result.current.state.isAuthenticated).toBe(true)

    await act(async () => {
      result.current.actions.setUser(null)
    })

    expect(result.current.state.user).toBeNull()
    expect(result.current.state.isAuthenticated).toBe(false)
  })

  it('reset returns to initial state', async () => {
    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    await act(async () => {
      result.current.actions.setUser(mockUser)
    })

    await act(async () => {
      result.current.actions.reset()
    })

    expect(result.current.state.user).toBeNull()
    expect(result.current.state.isAuthenticated).toBe(false)
    expect(result.current.state.token).toBeNull()
  })

  it('clearPendingVerification clears pending email', async () => {
    // Register to set pending verification
    window.electronAPI.post.mockResolvedValueOnce({
      status: 201,
      data: { message: 'ok', email: 'x@y.com' },
    })

    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    await act(async () => {
      await result.current.actions.register({ email: 'x@y.com', password: 'pass' })
    })

    expect(result.current.state.pendingVerificationEmail).toBe('x@y.com')

    await act(async () => {
      result.current.actions.clearPendingVerification()
    })

    expect(result.current.state.pendingVerificationEmail).toBeNull()
  })
})

// ============================================================================
// resendVerification
// ============================================================================

describe('resendVerification', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.getItem.mockReturnValue(null)
    delete (window as Record<string, unknown>).__apiClientState
  })

  it('returns true on success', async () => {
    window.electronAPI.post.mockResolvedValueOnce({
      status: 200,
      data: { message: 'Code sent' },
    })

    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    let success: boolean
    await act(async () => {
      success = await result.current.actions.resendVerification('test@example.com')
    })

    expect(success!).toBe(true)
    expect(result.current.state.isLoading).toBe(false)
    expect(result.current.state.error).toBeNull()
  })

  it('sets error on failure', async () => {
    window.electronAPI.post.mockResolvedValueOnce({
      status: 429,
      data: { detail: 'Too many requests' },
    })

    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    let success: boolean
    await act(async () => {
      success = await result.current.actions.resendVerification('test@example.com')
    })

    expect(success!).toBe(false)
    expect(result.current.state.error?.message).toBe('Too many requests')
    expect(result.current.state.isLoading).toBe(false)
  })
})

// ============================================================================
// forgotPassword
// ============================================================================

describe('forgotPassword', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.getItem.mockReturnValue(null)
    delete (window as Record<string, unknown>).__apiClientState
  })

  it('returns true on success', async () => {
    window.electronAPI.post.mockResolvedValueOnce({
      status: 200,
      data: { message: 'Reset code sent' },
    })

    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    let success: boolean
    await act(async () => {
      success = await result.current.actions.forgotPassword('test@example.com')
    })

    expect(success!).toBe(true)
    expect(result.current.state.isLoading).toBe(false)
  })

  it('sets error on failure', async () => {
    window.electronAPI.post.mockResolvedValueOnce({
      status: 404,
      data: { detail: 'User not found' },
    })

    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    let success: boolean
    await act(async () => {
      success = await result.current.actions.forgotPassword('unknown@example.com')
    })

    expect(success!).toBe(false)
    expect(result.current.state.error?.message).toBe('User not found')
  })
})

// ============================================================================
// resetPassword
// ============================================================================

describe('resetPassword', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.getItem.mockReturnValue(null)
    delete (window as Record<string, unknown>).__apiClientState
  })

  it('returns true on success', async () => {
    window.electronAPI.post.mockResolvedValueOnce({
      status: 200,
      data: { message: 'Password reset' },
    })

    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    let success: boolean
    await act(async () => {
      success = await result.current.actions.resetPassword('test@example.com', '123456', 'newPass!')
    })

    expect(success!).toBe(true)
    expect(result.current.state.isLoading).toBe(false)
  })

  it('sets error on failure', async () => {
    window.electronAPI.post.mockResolvedValueOnce({
      status: 400,
      data: { detail: 'Invalid reset code' },
    })

    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    let success: boolean
    await act(async () => {
      success = await result.current.actions.resetPassword('test@example.com', 'bad', 'newPass!')
    })

    expect(success!).toBe(false)
    expect(result.current.state.error?.message).toBe('Invalid reset code')
  })
})

// ============================================================================
// TOKENS_REFRESHED identity check (CR-016)
// ============================================================================

describe('TOKENS_REFRESHED state identity', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.getItem.mockReturnValue(null)
    delete (window as Record<string, unknown>).__apiClientState
  })

  it('preserves state object identity when tokens are unchanged', async () => {
    window.electronAPI.fetch.mockResolvedValueOnce({
      status: 200,
      data: { access_token: 'at-id', refresh_token: 'rt-id', token_type: 'bearer' },
    })
    window.electronAPI.get.mockResolvedValueOnce({ status: 200, data: mockUser })

    let renderCount = 0
    const { result } = renderHook(
      () => {
        renderCount++
        return { state: useAuthState(), actions: useAuthActions() }
      },
      { wrapper }
    )

    await act(async () => {
      await result.current.actions.login({ email: 'test@example.com', password: 'pass' })
    })

    const countAfterLogin = renderCount
    const stateRef = result.current.state

    // Dispatch TOKENS_REFRESHED with identical tokens
    const configCall = mockConfigureApiClient.mock.calls[0][0]
    await act(async () => {
      configCall.onTokensRefreshed('at-id', 'rt-id')
    })

    // State object identity should be preserved (no re-render from reducer)
    expect(result.current.state).toBe(stateRef)
    expect(renderCount).toBe(countAfterLogin)
  })
})

// ============================================================================
// localStorage persistence (CR-002)
// ============================================================================

describe('localStorage persistence', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.getItem.mockReturnValue(null)
    delete (window as Record<string, unknown>).__apiClientState
  })

  it('calls localStorage.setItem with AUTH_STORAGE_KEY after login', async () => {
    window.electronAPI.fetch.mockResolvedValueOnce({
      status: 200,
      data: { access_token: 'at-persist', refresh_token: 'rt-persist', token_type: 'bearer' },
    })
    window.electronAPI.get.mockResolvedValueOnce({ status: 200, data: mockUser })

    const { result } = renderHook(
      () => ({ state: useAuthState(), actions: useAuthActions() }),
      { wrapper }
    )

    await act(async () => {
      await result.current.actions.login({ email: 'test@example.com', password: 'pass' })
    })

    // localStorage.setItem should have been called with the auth storage key
    const setItemCalls = window.localStorage.setItem.mock.calls
    const authStorageCalls = setItemCalls.filter(
      (call: [string, string]) => call[0] === 'pm-desktop-auth'
    )
    expect(authStorageCalls.length).toBeGreaterThan(0)

    // Verify the persisted data contains the tokens
    const lastCall = authStorageCalls[authStorageCalls.length - 1]
    const persisted = JSON.parse(lastCall[1])
    expect(persisted.state.token).toBe('at-persist')
    expect(persisted.state.refreshToken).toBe('rt-persist')
  })
})
