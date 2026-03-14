import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { ApiResponse } from '../../../preload/index.d'
import {
  configureApiClient,
  setTokens,
  getAccessToken,
  refreshTokens,
  authGet,
  authPost,
  authPut,
  authPatch,
  authDelete,
  authFetch,
} from '../api-client'

// Helper to build a typed ApiResponse
function makeResponse<T>(status: number, data: T): ApiResponse<T> {
  return { data, status, statusText: 'OK', headers: {} }
}

function resetApiClientState() {
  delete window.__apiClientState
}

describe('api-client', () => {
  beforeEach(() => {
    resetApiClientState()
    vi.restoreAllMocks()
  })

  // ==========================================================================
  // HMR-safe state
  // ==========================================================================
  describe('HMR-safe state (getState via window.__apiClientState)', () => {
    it('creates state on first access and reuses on subsequent access', () => {
      expect(window.__apiClientState).toBeUndefined()
      // Trigger state creation via getAccessToken (calls getState internally)
      getAccessToken()
      expect(window.__apiClientState).toBeDefined()
      const first = window.__apiClientState
      getAccessToken()
      expect(window.__apiClientState).toBe(first)
    })

    it('preserves state across multiple module function calls', () => {
      setTokens('tok-a', 'ref-a')
      expect(getAccessToken()).toBe('tok-a')
      // State object is the same reference
      expect(window.__apiClientState?.accessToken).toBe('tok-a')
    })
  })

  // ==========================================================================
  // configureApiClient
  // ==========================================================================
  describe('configureApiClient', () => {
    it('wires onTokensRefreshed and onSessionExpired callbacks', () => {
      const onRefreshed = vi.fn()
      const onExpired = vi.fn()
      configureApiClient({ onTokensRefreshed: onRefreshed, onSessionExpired: onExpired })
      expect(window.__apiClientState?.onTokensRefreshed).toBe(onRefreshed)
      expect(window.__apiClientState?.onSessionExpired).toBe(onExpired)
    })
  })

  // ==========================================================================
  // setTokens / getAccessToken
  // ==========================================================================
  describe('setTokens / getAccessToken', () => {
    it('stores and retrieves access token', () => {
      setTokens('access-1', 'refresh-1')
      expect(getAccessToken()).toBe('access-1')
    })

    it('clears tokens when null is passed', () => {
      setTokens('a', 'r')
      setTokens(null, null)
      expect(getAccessToken()).toBeNull()
    })

    it('resets lastRefreshAt when access token is null (logout/fresh-login)', () => {
      setTokens('a', 'r')
      // Simulate a previous refresh by setting lastRefreshAt
      window.__apiClientState!.lastRefreshAt = 9999
      setTokens(null, null)
      expect(window.__apiClientState!.lastRefreshAt).toBe(0)
    })

    it('does NOT reset lastRefreshAt when access token is provided', () => {
      setTokens('a', 'r')
      window.__apiClientState!.lastRefreshAt = 9999
      setTokens('new-a', 'new-r')
      expect(window.__apiClientState!.lastRefreshAt).toBe(9999)
    })
  })

  // ==========================================================================
  // refreshTokens
  // ==========================================================================
  describe('refreshTokens', () => {
    it('returns null when no refresh token is set', async () => {
      setTokens('a', null)
      const result = await refreshTokens()
      expect(result).toBeNull()
    })

    it('refreshes successfully on 200 and updates state', async () => {
      const onRefreshed = vi.fn()
      configureApiClient({ onTokensRefreshed: onRefreshed, onSessionExpired: vi.fn() })
      setTokens('old-access', 'old-refresh')

      vi.mocked(window.electronAPI.post).mockResolvedValueOnce(
        makeResponse(200, {
          access_token: 'new-access',
          refresh_token: 'new-refresh',
          token_type: 'bearer',
        }),
      )

      const result = await refreshTokens()
      expect(result).toBe('new-access')
      expect(getAccessToken()).toBe('new-access')
      expect(window.__apiClientState!.refreshToken).toBe('new-refresh')
      expect(onRefreshed).toHaveBeenCalledWith('new-access', 'new-refresh')
      expect(window.electronAPI.post).toHaveBeenCalledWith('/auth/refresh', {
        refresh_token: 'old-refresh',
      })
    })

    it('calls onSessionExpired on 401 from refresh endpoint', async () => {
      const onExpired = vi.fn()
      configureApiClient({ onTokensRefreshed: vi.fn(), onSessionExpired: onExpired })
      setTokens('a', 'r')

      vi.mocked(window.electronAPI.post).mockResolvedValueOnce(
        makeResponse(401, null),
      )

      const result = await refreshTokens()
      expect(result).toBeNull()
      expect(onExpired).toHaveBeenCalledOnce()
    })

    it('calls onSessionExpired on 403 from refresh endpoint', async () => {
      const onExpired = vi.fn()
      configureApiClient({ onTokensRefreshed: vi.fn(), onSessionExpired: onExpired })
      setTokens('a', 'r')

      vi.mocked(window.electronAPI.post).mockResolvedValueOnce(
        makeResponse(403, null),
      )

      const result = await refreshTokens()
      expect(result).toBeNull()
      expect(onExpired).toHaveBeenCalledOnce()
    })

    it('returns null on server error (500) without logging out', async () => {
      const onExpired = vi.fn()
      configureApiClient({ onTokensRefreshed: vi.fn(), onSessionExpired: onExpired })
      setTokens('a', 'r')

      vi.mocked(window.electronAPI.post).mockResolvedValueOnce(
        makeResponse(500, null),
      )

      const result = await refreshTokens()
      expect(result).toBeNull()
      expect(onExpired).not.toHaveBeenCalled()
    })

    it('returns null on network error without logging out', async () => {
      const onExpired = vi.fn()
      configureApiClient({ onTokensRefreshed: vi.fn(), onSessionExpired: onExpired })
      setTokens('a', 'r')

      vi.mocked(window.electronAPI.post).mockRejectedValueOnce(new Error('Network failure'))

      const result = await refreshTokens()
      expect(result).toBeNull()
      expect(onExpired).not.toHaveBeenCalled()
    })

    it('deduplicates concurrent refresh calls (returns same promise)', async () => {
      setTokens('a', 'r')
      let resolvePost!: (v: ApiResponse<unknown>) => void
      vi.mocked(window.electronAPI.post).mockReturnValueOnce(
        new Promise((res) => { resolvePost = res }),
      )

      const p1 = refreshTokens()
      const p2 = refreshTokens()
      const p3 = refreshTokens()

      // Only one call to electronAPI.post (dedup proof)
      expect(window.electronAPI.post).toHaveBeenCalledTimes(1)

      resolvePost(makeResponse(200, {
        access_token: 'dedup-access',
        refresh_token: 'dedup-refresh',
        token_type: 'bearer',
      }))

      // All concurrent callers get the same result
      const [r1, r2, r3] = await Promise.all([p1, p2, p3])
      expect(r1).toBe('dedup-access')
      expect(r2).toBe('dedup-access')
      expect(r3).toBe('dedup-access')
    })

    it('circuit breaker: skips refresh within cooldown and returns cached token', async () => {
      setTokens('a', 'r')

      // Perform a successful refresh first
      vi.mocked(window.electronAPI.post).mockResolvedValueOnce(
        makeResponse(200, {
          access_token: 'refreshed',
          refresh_token: 'r2',
          token_type: 'bearer',
        }),
      )
      await refreshTokens()
      expect(getAccessToken()).toBe('refreshed')

      // Now try again immediately — circuit breaker should fire
      const result = await refreshTokens()
      expect(result).toBe('refreshed')
      // Still only 1 call total
      expect(window.electronAPI.post).toHaveBeenCalledTimes(1)
    })

    it('circuit breaker resets after cooldown expires', async () => {
      setTokens('a', 'r')

      // First refresh at time T
      vi.mocked(window.electronAPI.post).mockResolvedValueOnce(
        makeResponse(200, {
          access_token: 'first',
          refresh_token: 'r2',
          token_type: 'bearer',
        }),
      )
      await refreshTokens()

      // Advance past cooldown (5000ms) — vi.restoreAllMocks in beforeEach handles cleanup
      const now = Date.now()
      vi.spyOn(Date, 'now').mockReturnValue(now + 6000)

      vi.mocked(window.electronAPI.post).mockResolvedValueOnce(
        makeResponse(200, {
          access_token: 'second',
          refresh_token: 'r3',
          token_type: 'bearer',
        }),
      )
      const result = await refreshTokens()
      expect(result).toBe('second')
      expect(window.electronAPI.post).toHaveBeenCalledTimes(2)
    })

    it('clears refreshPromise after completion (allows future refreshes)', async () => {
      setTokens('a', 'r')
      vi.mocked(window.electronAPI.post).mockResolvedValueOnce(
        makeResponse(200, {
          access_token: 'tok1',
          refresh_token: 'ref1',
          token_type: 'bearer',
        }),
      )
      await refreshTokens()
      expect(window.__apiClientState!.refreshPromise).toBeNull()
    })
  })

  // ==========================================================================
  // withAuthRetry (tested via auth* methods)
  // ==========================================================================
  describe('withAuthRetry (via authGet)', () => {
    it('returns response directly when status is not 401', async () => {
      setTokens('tok', 'ref')
      vi.mocked(window.electronAPI.get).mockResolvedValueOnce(makeResponse(200, { ok: true }))

      const res = await authGet('/test')
      expect(res.status).toBe(200)
      expect(res.data).toEqual({ ok: true })
    })

    it('refreshes and retries on 401', async () => {
      setTokens('old-tok', 'ref')
      // First call: 401
      vi.mocked(window.electronAPI.get).mockResolvedValueOnce(makeResponse(401, null))
      // Refresh succeeds
      vi.mocked(window.electronAPI.post).mockResolvedValueOnce(
        makeResponse(200, {
          access_token: 'new-tok',
          refresh_token: 'new-ref',
          token_type: 'bearer',
        }),
      )
      // Retry call: 200
      vi.mocked(window.electronAPI.get).mockResolvedValueOnce(makeResponse(200, { retried: true }))

      const res = await authGet('/test')
      expect(res.status).toBe(200)
      expect(res.data).toEqual({ retried: true })
      expect(window.electronAPI.get).toHaveBeenCalledTimes(2)
    })

    it('calls onSessionExpired when retry also returns 401', async () => {
      const onExpired = vi.fn()
      configureApiClient({ onTokensRefreshed: vi.fn(), onSessionExpired: onExpired })
      setTokens('tok', 'ref')

      // First call: 401
      vi.mocked(window.electronAPI.get).mockResolvedValueOnce(makeResponse(401, null))
      // Refresh succeeds
      vi.mocked(window.electronAPI.post).mockResolvedValueOnce(
        makeResponse(200, {
          access_token: 'new-tok',
          refresh_token: 'new-ref',
          token_type: 'bearer',
        }),
      )
      // Retry: also 401
      vi.mocked(window.electronAPI.get).mockResolvedValueOnce(makeResponse(401, null))

      await authGet('/test')
      expect(onExpired).toHaveBeenCalledOnce()
    })

    it('returns 401 response without retry when refresh returns null', async () => {
      setTokens('tok', null) // no refresh token → refresh returns null

      vi.mocked(window.electronAPI.get).mockResolvedValueOnce(makeResponse(401, null))

      const res = await authGet('/test')
      expect(res.status).toBe(401)
      // No retry call
      expect(window.electronAPI.get).toHaveBeenCalledTimes(1)
    })

    it('concurrent 401s trigger only ONE refresh, both retries use new token', async () => {
      const onRefreshed = vi.fn()
      configureApiClient({ onTokensRefreshed: onRefreshed, onSessionExpired: vi.fn() })
      setTokens('old-tok', 'ref')

      // Both initial calls return 401
      vi.mocked(window.electronAPI.get)
        .mockResolvedValueOnce(makeResponse(401, null)) // call 1 initial
        .mockResolvedValueOnce(makeResponse(401, null)) // call 2 initial

      // Refresh succeeds (only once due to dedup)
      let resolveRefresh!: (v: ApiResponse<unknown>) => void
      vi.mocked(window.electronAPI.post).mockReturnValueOnce(
        new Promise((res) => { resolveRefresh = res }),
      )

      // Both retries succeed with new token
      vi.mocked(window.electronAPI.get)
        .mockResolvedValueOnce(makeResponse(200, { from: 'retry1' })) // call 1 retry
        .mockResolvedValueOnce(makeResponse(200, { from: 'retry2' })) // call 2 retry

      // Fire both concurrently
      const p1 = authGet<{ from: string }>('/ep1')
      const p2 = authGet<{ from: string }>('/ep2')

      // Resolve the single refresh
      resolveRefresh(makeResponse(200, {
        access_token: 'new-tok',
        refresh_token: 'new-ref',
        token_type: 'bearer',
      }))

      const [r1, r2] = await Promise.all([p1, p2])

      expect(r1.status).toBe(200)
      expect(r2.status).toBe(200)
      // Only one refresh call
      expect(window.electronAPI.post).toHaveBeenCalledTimes(1)
      // 2 initial + 2 retries = 4 get calls
      expect(window.electronAPI.get).toHaveBeenCalledTimes(4)
    })
  })

  // ==========================================================================
  // Authenticated API methods
  // ==========================================================================
  describe('auth methods — headers and electronAPI calls', () => {
    beforeEach(() => {
      setTokens('my-token', 'my-refresh')
    })

    it('authGet sends Authorization header', async () => {
      vi.mocked(window.electronAPI.get).mockResolvedValueOnce(makeResponse(200, {}))
      await authGet('/ep')
      expect(window.electronAPI.get).toHaveBeenCalledWith('/ep', {
        Authorization: 'Bearer my-token',
      })
    })

    it('authPost sends body and Authorization header', async () => {
      vi.mocked(window.electronAPI.post).mockResolvedValueOnce(makeResponse(200, {}))
      await authPost('/ep', { key: 'val' })
      expect(window.electronAPI.post).toHaveBeenCalledWith('/ep', { key: 'val' }, {
        Authorization: 'Bearer my-token',
      })
    })

    it('authPut sends body and Authorization header', async () => {
      vi.mocked(window.electronAPI.put).mockResolvedValueOnce(makeResponse(200, {}))
      await authPut('/ep', { k: 1 })
      expect(window.electronAPI.put).toHaveBeenCalledWith('/ep', { k: 1 }, {
        Authorization: 'Bearer my-token',
      })
    })

    it('authPatch sends body and Authorization header', async () => {
      vi.mocked(window.electronAPI.patch).mockResolvedValueOnce(makeResponse(200, {}))
      await authPatch('/ep', { p: true })
      expect(window.electronAPI.patch).toHaveBeenCalledWith('/ep', { p: true }, {
        Authorization: 'Bearer my-token',
      })
    })

    it('authDelete sends Authorization header', async () => {
      vi.mocked(window.electronAPI.delete).mockResolvedValueOnce(makeResponse(200, {}))
      await authDelete('/ep')
      expect(window.electronAPI.delete).toHaveBeenCalledWith('/ep', {
        Authorization: 'Bearer my-token',
      })
    })

    it('authFetch merges auth headers with custom headers', async () => {
      vi.mocked(window.electronAPI.fetch).mockResolvedValueOnce(makeResponse(200, {}))
      await authFetch('/ep', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: 'grant_type=password',
      })
      expect(window.electronAPI.fetch).toHaveBeenCalledWith('/ep', {
        method: 'POST',
        headers: {
          Authorization: 'Bearer my-token',
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: 'grant_type=password',
      })
    })

    it('authFetch custom headers override auth headers', async () => {
      vi.mocked(window.electronAPI.fetch).mockResolvedValueOnce(makeResponse(200, {}))
      await authFetch('/ep', {
        headers: { Authorization: 'Custom xyz' },
      })
      expect(window.electronAPI.fetch).toHaveBeenCalledWith('/ep', {
        headers: { Authorization: 'Custom xyz' },
      })
    })

    it('sends empty headers when no token is set', async () => {
      setTokens(null, null)
      vi.mocked(window.electronAPI.get).mockResolvedValueOnce(makeResponse(200, {}))
      await authGet('/ep')
      expect(window.electronAPI.get).toHaveBeenCalledWith('/ep', {})
    })
  })

  // ==========================================================================
  // electronAPI not available
  // ==========================================================================
  describe('throws when electronAPI is not available', () => {
    let originalElectronAPI: typeof window.electronAPI

    beforeEach(() => {
      originalElectronAPI = window.electronAPI
      ;(window as Record<string, unknown>).electronAPI = undefined
    })

    afterEach(() => {
      ;(window as Record<string, unknown>).electronAPI = originalElectronAPI
    })

    it('authGet throws', async () => {
      await expect(authGet('/x')).rejects.toThrow('Electron API not available')
    })

    it('authPost throws', async () => {
      await expect(authPost('/x')).rejects.toThrow('Electron API not available')
    })

    it('authPut throws', async () => {
      await expect(authPut('/x')).rejects.toThrow('Electron API not available')
    })

    it('authPatch throws', async () => {
      await expect(authPatch('/x')).rejects.toThrow('Electron API not available')
    })

    it('authDelete throws', async () => {
      await expect(authDelete('/x')).rejects.toThrow('Electron API not available')
    })

    it('authFetch throws', async () => {
      await expect(authFetch('/x', {})).rejects.toThrow('Electron API not available')
    })
  })
})
