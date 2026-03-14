/**
 * Authenticated API Client
 *
 * Module-level singleton that intercepts 401 responses, refreshes the
 * access token, and retries the original request. Used by all TanStack
 * Query hooks instead of raw `window.electronAPI.*` calls.
 *
 * Features:
 * - Single interception point for 401 handling
 * - Deduped token refresh (concurrent 401s trigger only one refresh)
 * - Circuit breaker: skips refresh if one just completed (prevents loops)
 * - Network-error resilience: transient failures don't trigger logout
 * - HMR-safe: state persisted on window to survive Vite hot reloads
 * - Callback hooks for React state sync (onTokensRefreshed / onSessionExpired)
 */

import type { ApiResponse } from '../../preload/index.d'

// ============================================================================
// HMR-safe State (persisted on window, like websocket.ts)
// ============================================================================

interface ApiClientState {
  accessToken: string | null
  refreshToken: string | null
  refreshPromise: Promise<string | null> | null
  lastRefreshAt: number
  onTokensRefreshed: ((access: string, refresh: string) => void) | null
  onSessionExpired: (() => void) | null
}

declare global {
  interface Window {
    __apiClientState?: ApiClientState
  }
}

function getState(): ApiClientState {
  if (typeof window !== 'undefined') {
    if (!window.__apiClientState) {
      window.__apiClientState = {
        accessToken: null,
        refreshToken: null,
        refreshPromise: null,
        lastRefreshAt: 0,
        onTokensRefreshed: null,
        onSessionExpired: null,
      }
    }
    return window.__apiClientState
  }
  // Fallback for non-browser (SSR/tests)
  return {
    accessToken: null,
    refreshToken: null,
    refreshPromise: null,
    lastRefreshAt: 0,
    onTokensRefreshed: null,
    onSessionExpired: null,
  }
}

// Circuit breaker: skip refresh if one completed within this window
const REFRESH_COOLDOWN_MS = 5_000

// ============================================================================
// Configuration
// ============================================================================

interface ApiClientConfig {
  onTokensRefreshed: (access: string, refresh: string) => void
  onSessionExpired: () => void
}

/**
 * Called once by AuthProvider on mount to wire up React state callbacks.
 */
export function configureApiClient(config: ApiClientConfig): void {
  const s = getState()
  s.onTokensRefreshed = config.onTokensRefreshed
  s.onSessionExpired = config.onSessionExpired
}

/**
 * Called by AuthProvider whenever tokens change (login, refresh, etc.).
 */
export function setTokens(access: string | null, refresh: string | null): void {
  const s = getState()
  s.accessToken = access
  s.refreshToken = refresh
  // Reset circuit breaker only on logout/fresh-login (null tokens), not after a
  // successful refresh.  refreshTokens() already updates the module state directly
  // and sets lastRefreshAt — if the React effect then calls setTokens() with the
  // refreshed tokens, we must NOT clear lastRefreshAt or the breaker is defeated.
  if (!access) {
    s.lastRefreshAt = 0
  }
}

/**
 * Get the current access token (used by WebSocket client and file uploads).
 */
export function getAccessToken(): string | null {
  return getState().accessToken
}

// ============================================================================
// Shared Constants
// ============================================================================

/** Base URL for the API (used by file uploads, downloads, and other raw fetch calls). */
export const API_BASE: string = import.meta.env.VITE_API_URL || 'http://localhost:8001'

// ============================================================================
// Shared Error Helpers
// ============================================================================

/**
 * Parse an API error response into a human-readable message.
 *
 * Used by TanStack Query hooks to translate HTTP status codes and
 * backend error payloads into user-friendly strings.
 *
 * @param status  HTTP status code
 * @param data    Response body (parsed JSON or unknown)
 * @param entityLabel  Optional entity label for 404 messages (e.g. "File", "Document")
 */
export function parseApiError(
  status: number,
  data: unknown,
  entityLabel = 'Resource',
): string {
  if (typeof data === 'object' && data !== null) {
    const errorData = data as Record<string, unknown>
    if (typeof errorData.detail === 'string') {
      return errorData.detail
    }
    // Preserve structured detail objects (e.g. {"detail": {"message": "...", "existing_file_id": "..."}})
    if (typeof errorData.detail === 'object' && errorData.detail !== null) {
      const detailObj = errorData.detail as Record<string, unknown>
      if (typeof detailObj.message === 'string') {
        return detailObj.message
      }
      // Fallback: serialize the detail object
      return JSON.stringify(errorData.detail)
    }
  }

  switch (status) {
    case 400:
      return 'Invalid request. Please check your input.'
    case 401:
      return 'Authentication required. Please log in again.'
    case 403:
      return 'Access denied.'
    case 404:
      return `${entityLabel} not found.`
    case 409:
      return `${entityLabel} conflict. Please refresh and try again.`
    case 413:
      return 'File too large.'
    default:
      return 'An unexpected error occurred.'
  }
}

// ============================================================================
// Token Refresh (with deduplication + circuit breaker)
// ============================================================================

/**
 * Refresh the access token using the stored refresh token.
 * Deduplicates concurrent calls — only one refresh request is in-flight at a time.
 * Circuit breaker: if a refresh completed within REFRESH_COOLDOWN_MS, skips
 * the refresh and returns the cached access token (so callers can retry with it).
 *
 * @returns The new access token, the cached token (circuit breaker), or null if refresh failed.
 */
export async function refreshTokens(): Promise<string | null> {
  const s = getState()

  // If a refresh is already in-flight, return the same promise (dedup)
  if (s.refreshPromise) return s.refreshPromise

  // Circuit breaker: if we just refreshed, don't try again.  Return the
  // current access token so callers (withAuthRetry) can retry with it.
  // If the cached token is genuinely bad, the retry will get 401 and
  // withAuthRetry will call onSessionExpired — no premature logout.
  const now = Date.now()
  if (s.lastRefreshAt > 0 && now - s.lastRefreshAt < REFRESH_COOLDOWN_MS) {
    if (import.meta.env.DEV) {
      console.warn('[api-client] Refresh skipped (circuit breaker — last refresh was', now - s.lastRefreshAt, 'ms ago, returning cached token)')
    }
    return s.accessToken
  }

  const doRefresh = async (): Promise<string | null> => {
    if (!s.refreshToken || !window.electronAPI) return null

    try {
      const res = await window.electronAPI.post<{
        access_token: string
        refresh_token: string
        token_type: string
      }>('/auth/refresh', { refresh_token: s.refreshToken })

      if (res.status === 200 && res.data) {
        const newAccess = res.data.access_token
        const newRefresh = res.data.refresh_token

        // Update module-level tokens immediately
        s.accessToken = newAccess
        s.refreshToken = newRefresh
        s.lastRefreshAt = Date.now()

        // Notify React state
        s.onTokensRefreshed?.(newAccess, newRefresh)

        if (import.meta.env.DEV) {
          console.log('[api-client] Token refreshed')
        }
        return newAccess
      }

      // Explicit auth failure (401/403 from refresh endpoint) — session expired
      if (res.status === 401 || res.status === 403) {
        if (import.meta.env.DEV) {
          console.warn('[api-client] Refresh token rejected (', res.status, '), session expired')
        }
        s.onSessionExpired?.()
        return null
      }

      // Server error (500, 502, etc.) — transient, don't logout
      if (import.meta.env.DEV) {
        console.warn('[api-client] Refresh endpoint returned', res.status, '— not logging out (transient error)')
      }
      return null
    } catch {
      // Network error (DNS, timeout, connection refused) — transient, don't logout
      if (import.meta.env.DEV) {
        console.warn('[api-client] Refresh network error — not logging out (transient)')
      }
      return null
    }
  }

  s.refreshPromise = doRefresh().finally(() => {
    s.refreshPromise = null
  })

  return s.refreshPromise
}

// ============================================================================
// Auth Headers Helper
// ============================================================================

function authHeaders(): Record<string, string> {
  const token = getState().accessToken
  if (!token) return {}
  return { Authorization: `Bearer ${token}` }
}

// ============================================================================
// Internal: 401 intercept + refresh + retry (shared by all auth* methods)
// ============================================================================

type ApiCall<T> = () => Promise<ApiResponse<T>>

/**
 * Execute an API call. If it returns 401, attempt a token refresh and retry once.
 * If the retry also returns 401, trigger session expiration.
 */
async function withAuthRetry<T>(call: ApiCall<T>, retryCall: ApiCall<T>): Promise<ApiResponse<T>> {
  const res = await call()

  if (res.status === 401) {
    const newToken = await refreshTokens()
    if (newToken) {
      const retryRes = await retryCall()
      // If retry ALSO returns 401, the new token is invalid — session expired
      if (retryRes.status === 401) {
        getState().onSessionExpired?.()
      }
      return retryRes
    }
  }

  return res
}

// ============================================================================
// Authenticated API Methods
// ============================================================================

/**
 * Authenticated GET request with auto 401 refresh + retry.
 */
export async function authGet<T>(endpoint: string): Promise<ApiResponse<T>> {
  if (!window.electronAPI) {
    throw new Error('Electron API not available')
  }

  return withAuthRetry(
    () => window.electronAPI.get<T>(endpoint, authHeaders()),
    () => window.electronAPI.get<T>(endpoint, authHeaders()),
  )
}

/**
 * Authenticated POST request with auto 401 refresh + retry.
 */
export async function authPost<T>(
  endpoint: string,
  body?: unknown,
): Promise<ApiResponse<T>> {
  if (!window.electronAPI) {
    throw new Error('Electron API not available')
  }

  return withAuthRetry(
    () => window.electronAPI.post<T>(endpoint, body, authHeaders()),
    () => window.electronAPI.post<T>(endpoint, body, authHeaders()),
  )
}

/**
 * Authenticated PUT request with auto 401 refresh + retry.
 */
export async function authPut<T>(
  endpoint: string,
  body?: unknown,
): Promise<ApiResponse<T>> {
  if (!window.electronAPI) {
    throw new Error('Electron API not available')
  }

  return withAuthRetry(
    () => window.electronAPI.put<T>(endpoint, body, authHeaders()),
    () => window.electronAPI.put<T>(endpoint, body, authHeaders()),
  )
}

/**
 * Authenticated PATCH request with auto 401 refresh + retry.
 */
export async function authPatch<T>(
  endpoint: string,
  body?: unknown,
): Promise<ApiResponse<T>> {
  if (!window.electronAPI) {
    throw new Error('Electron API not available')
  }

  return withAuthRetry(
    () => window.electronAPI.patch<T>(endpoint, body, authHeaders()),
    () => window.electronAPI.patch<T>(endpoint, body, authHeaders()),
  )
}

/**
 * Authenticated DELETE request with auto 401 refresh + retry.
 */
export async function authDelete<T>(endpoint: string): Promise<ApiResponse<T>> {
  if (!window.electronAPI) {
    throw new Error('Electron API not available')
  }

  return withAuthRetry(
    () => window.electronAPI.delete<T>(endpoint, authHeaders()),
    () => window.electronAPI.delete<T>(endpoint, authHeaders()),
  )
}

/**
 * Authenticated custom fetch request with auto 401 refresh + retry.
 * Used for non-standard requests (e.g., form-urlencoded login).
 */
export async function authFetch<T>(
  endpoint: string,
  options: {
    method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
    headers?: Record<string, string>
    body?: unknown
  },
): Promise<ApiResponse<T>> {
  if (!window.electronAPI) {
    throw new Error('Electron API not available')
  }

  return withAuthRetry(
    () => {
      const mergedHeaders = { ...authHeaders(), ...options.headers }
      return window.electronAPI.fetch<T>(endpoint, { ...options, headers: mergedHeaders })
    },
    () => {
      const retryHeaders = { ...authHeaders(), ...options.headers }
      return window.electronAPI.fetch<T>(endpoint, { ...options, headers: retryHeaders })
    },
  )
}
