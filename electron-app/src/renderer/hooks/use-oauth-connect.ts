/**
 * Subscription Token Connect Hooks
 *
 * React Query hooks for connecting/disconnecting AI provider
 * subscriptions via session tokens. Users obtain tokens from
 * their provider CLI (e.g. `claude setup-token`) and paste them
 * into the app.
 *
 * Replaces the previous OAuth BrowserWindow flow.
 *
 * @see fastapi-backend/app/routers/ai_oauth.py
 */

import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryResult,
  type UseMutationResult,
} from '@tanstack/react-query'
import { useAuthToken } from '@/contexts/auth-context'
import { queryKeys } from '@/lib/query-client'
import { authGet, authPost, authDelete } from '@/lib/api-client'

// ============================================================================
// Types
// ============================================================================

export interface SubscriptionTokenStatus {
  connected: boolean
  provider_type: string | null
  auth_method: 'api_key' | 'oauth' | 'session_token' | null
  connected_at: string | null
  model_id: string | null
}

interface SubscriptionTokenTestResult {
  success: boolean
  message: string | null
  latency_ms: number | null
}

interface SaveTokenRequest {
  provider_type: 'openai' | 'anthropic'
  token: string
  preferred_model?: string
}

interface DisconnectResponse {
  disconnected: boolean
  fallback: string
}

// ============================================================================
// Hooks
// ============================================================================

/**
 * Fetch current subscription token status.
 */
export function useSubscriptionTokenStatus(): UseQueryResult<SubscriptionTokenStatus, Error> {
  const token = useAuthToken()

  return useQuery({
    queryKey: queryKeys.oauthStatus,
    queryFn: async () => {
      const response = await authGet<SubscriptionTokenStatus>(
        '/api/ai/config/me/subscription-token/status'
      )

      if (response.status !== 200) {
        throw new Error('Failed to fetch subscription status')
      }

      return response.data
    },
    enabled: !!token,
    staleTime: 60 * 1000,
  })
}

/**
 * Save a subscription token.
 * Validates the token server-side before saving.
 */
export function useSaveSubscriptionToken(): UseMutationResult<
  SubscriptionTokenStatus,
  Error,
  SaveTokenRequest
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (body) => {
      const response = await authPost<SubscriptionTokenStatus>(
        '/api/ai/config/me/subscription-token',
        body
      )

      if (response.status !== 200) {
        const errData = response.data as unknown as { detail?: string }
        throw new Error(errData?.detail || 'Failed to save subscription token')
      }

      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.oauthStatus })
      queryClient.invalidateQueries({ queryKey: queryKeys.userEffectiveConfig })
    },
  })
}

/**
 * Test the stored subscription token.
 */
export function useTestSubscriptionToken(): UseMutationResult<
  SubscriptionTokenTestResult,
  Error,
  void
> {
  return useMutation({
    mutationFn: async () => {
      const response = await authPost<SubscriptionTokenTestResult>(
        '/api/ai/config/me/subscription-token/test',
        {}
      )

      if (response.status !== 200) {
        throw new Error('Failed to test subscription token')
      }

      return response.data
    },
  })
}

/**
 * Remove subscription token.
 * Falls back to company default.
 */
export function useDisconnectSubscription(): UseMutationResult<DisconnectResponse, Error, void> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async () => {
      const response = await authDelete<DisconnectResponse>(
        '/api/ai/config/me/subscription-token'
      )

      if (response.status !== 200) {
        throw new Error('Failed to remove subscription token')
      }

      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.oauthStatus })
      queryClient.invalidateQueries({ queryKey: queryKeys.userEffectiveConfig })
    },
  })
}

// Legacy hooks — kept as aliases for backwards compatibility
export const useOAuthStatus = useSubscriptionTokenStatus
export const useOAuthDisconnect = useDisconnectSubscription
