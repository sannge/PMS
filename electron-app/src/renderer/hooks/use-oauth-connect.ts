/**
 * OAuth Subscription Connect Hooks
 *
 * React Query hooks for connecting/disconnecting AI provider
 * subscriptions via OAuth. Uses the Electron main process
 * BrowserWindow flow for the OAuth authorization step.
 *
 * @see electron-app/src/main/oauth-handler.ts
 * @see fastapi-backend/app/routers/ai_oauth.py
 */

import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryResult,
  type UseMutationResult,
} from '@tanstack/react-query'
import { useAuthToken, getAuthHeaders } from '@/contexts/auth-context'
import { queryKeys } from '@/lib/query-client'

// ============================================================================
// Types
// ============================================================================

export interface OAuthConnectionStatus {
  connected: boolean
  provider_type: string | null
  auth_method: 'api_key' | 'oauth' | null
  provider_user_id: string | null
  connected_at: string | null
  token_expires_at: string | null
  scopes: string[]
}

interface OAuthInitiateResponse {
  auth_url: string
  state: string
  expires_in: number
}

interface OAuthDisconnectResponse {
  disconnected: boolean
  fallback: string
}

export interface OAuthConnectResult {
  connected: boolean
  provider_type: string
}

// ============================================================================
// Hooks
// ============================================================================

/**
 * Fetch current OAuth connection status.
 * refetchOnWindowFocus: true — token may expire while user is away.
 */
export function useOAuthStatus(): UseQueryResult<OAuthConnectionStatus, Error> {
  const token = useAuthToken()

  return useQuery({
    queryKey: queryKeys.oauthStatus,
    queryFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.get<OAuthConnectionStatus>(
        '/api/ai/config/me/oauth/status',
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error('Failed to fetch OAuth status')
      }

      return response.data
    },
    enabled: !!token,
    refetchOnWindowFocus: true,
    staleTime: 60 * 1000, // 1 minute
  })
}

/**
 * Initiate OAuth flow:
 * 1. POST /initiate to get auth URL from backend
 * 2. Call electronAPI.initiateOAuth() to open BrowserWindow
 * 3. POST /callback with code + state to complete connection
 *
 * Handles: timeout, window closed, provider rejection.
 */
export function useOAuthInitiate(): UseMutationResult<
  OAuthConnectResult,
  Error,
  { provider_type: 'openai' | 'anthropic' }
> {
  const token = useAuthToken()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ provider_type }) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      // Step 1: Get auth URL from backend
      // Note: redirect_uri is a placeholder — the Electron oauth-handler
      // will replace it with the actual localhost:PORT/oauth/callback
      const initiateResponse = await window.electronAPI.post<OAuthInitiateResponse>(
        '/api/ai/config/me/oauth/initiate',
        {
          provider_type,
          redirect_uri: 'http://127.0.0.1:0/oauth/callback',
        },
        getAuthHeaders(token)
      )

      if (initiateResponse.status !== 200) {
        throw new Error('Failed to initiate OAuth flow')
      }

      const { auth_url, state } = initiateResponse.data

      // Step 2: Open BrowserWindow via Electron main process
      // This blocks until callback is received, window is closed, or timeout
      let oauthResult: { code: string; state: string; redirectUri: string }
      try {
        oauthResult = await window.electronAPI.initiateOAuth(auth_url)
      } catch (err) {
        const message = err instanceof Error ? err.message : 'OAuth flow failed'
        if (message.includes('closed by user')) {
          throw new Error('OAuth flow was cancelled')
        }
        if (message.includes('timed out')) {
          throw new Error('OAuth flow timed out. Please try again.')
        }
        throw new Error(message)
      }

      // Step 3: Exchange code for tokens via backend
      // Use the actual redirect_uri returned by Electron (with real port)
      const callbackResponse = await window.electronAPI.post<OAuthConnectResult>(
        '/api/ai/config/me/oauth/callback',
        {
          provider_type,
          code: oauthResult.code,
          state: oauthResult.state || state,
          redirect_uri: oauthResult.redirectUri,
        },
        getAuthHeaders(token)
      )

      if (callbackResponse.status !== 200) {
        throw new Error('Failed to complete OAuth connection')
      }

      return callbackResponse.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.oauthStatus })
      queryClient.invalidateQueries({ queryKey: queryKeys.userOverrides })
      queryClient.invalidateQueries({ queryKey: queryKeys.userEffectiveConfig })
    },
  })
}

/**
 * Disconnect OAuth provider.
 * Revokes tokens and falls back to company default.
 */
export function useOAuthDisconnect(): UseMutationResult<OAuthDisconnectResponse, Error, void> {
  const token = useAuthToken()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.delete<OAuthDisconnectResponse>(
        '/api/ai/config/me/oauth/disconnect',
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error('Failed to disconnect OAuth provider')
      }

      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.oauthStatus })
      queryClient.invalidateQueries({ queryKey: queryKeys.userOverrides })
      queryClient.invalidateQueries({ queryKey: queryKeys.userEffectiveConfig })
    },
  })
}
