/**
 * TanStack Query Hooks for AI Configuration
 *
 * Provides React Query hooks for managing AI providers, models,
 * index status, import jobs, and user chat overrides.
 *
 * @see fastapi-backend/app/routers/ai_config.py
 * @see fastapi-backend/app/routers/ai_query.py
 */

import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryResult,
  type UseMutationResult,
} from '@tanstack/react-query'
import { useAuthToken, parseApiError as parseApiErrorAuth } from '@/contexts/auth-context'
import { authGet, authPost, authPut, authDelete } from '@/lib/api-client'
import { queryKeys } from '@/lib/query-client'

// ============================================================================
// Types
// ============================================================================

export interface AiProviderCreate {
  name: string
  display_name: string
  provider_type: string
  base_url?: string | null
  api_key?: string | null
  is_enabled?: boolean
}

export interface AiProviderUpdate {
  name?: string
  display_name?: string
  provider_type?: string
  base_url?: string | null
  api_key?: string | null
  is_enabled?: boolean
}

export interface AiProviderResponse {
  id: string
  name: string
  display_name: string
  provider_type: string
  base_url: string | null
  is_enabled: boolean
  scope: string
  user_id: string | null
  has_api_key: boolean
  created_at: string
  updated_at: string
  models: AiModelResponse[]
}

export interface AiModelCreate {
  provider_id: string
  model_id: string
  display_name: string
  capability: string
  embedding_dimensions?: number | null
  max_tokens?: number | null
  is_default?: boolean
  is_enabled?: boolean
}

export interface AiModelUpdate {
  model_id?: string
  display_name?: string
  capability?: string
  embedding_dimensions?: number | null
  max_tokens?: number | null
  is_default?: boolean
  is_enabled?: boolean
}

export interface AiModelResponse {
  id: string
  provider_id: string
  model_id: string
  display_name: string
  capability: string
  embedding_dimensions: number | null
  max_tokens: number | null
  is_default: boolean
  is_enabled: boolean
  created_at: string
  updated_at: string
  provider_name: string
}

export interface IndexStatusResponse {
  document_id: string
  embedding_updated_at: string | null
  chunk_count?: number
}

export interface IndexProgressResponse {
  status: 'idle' | 'running' | 'completed'
  total: number
  processed: number
  failed: number
  application_id?: string
}

// ImportJobResponse is canonically defined in use-document-import.ts
export type { ImportJobResponse } from '@/hooks/use-document-import'

export interface AiConfigSummaryResponse {
  providers: AiProviderResponse[]
  default_chat_model: AiModelResponse | null
  default_embedding_model: AiModelResponse | null
  default_vision_model: AiModelResponse | null
}

export interface TestProviderResult {
  success: boolean
  message?: string
  error?: string
  latency_ms?: number
}

export interface CapabilityConfig {
  capability: string
  provider_id: string | null
  provider_type: string | null
  base_url: string | null
  model_id: string | null
  model_display_name: string | null
  has_api_key: boolean
}

export interface UserOverrideConfig {
  provider_type: string
  api_key: string
  base_url?: string | null
  preferred_model?: string | null
}

// EffectiveChatConfig is structurally identical to AiConfigSummaryResponse.
// The backend endpoint /me/summary returns AiConfigSummary, so reuse that type.
export type EffectiveChatConfig = AiConfigSummaryResponse

// ============================================================================
// Helper Functions
// ============================================================================

function parseApiError(status: number, data: unknown): string {
  const result = parseApiErrorAuth(status, data)
  return result.message
}

// ============================================================================
// Provider Hooks
// ============================================================================

/**
 * Fetch all global AI providers with their models.
 */
export function useAiProviders(): UseQueryResult<AiProviderResponse[], Error> {
  const token = useAuthToken()

  return useQuery({
    queryKey: queryKeys.aiProviders,
    queryFn: async () => {
      const response = await authGet<AiProviderResponse[]>(
        '/api/ai/config/providers'
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data))
      }

      return response.data
    },
    enabled: !!token,
    staleTime: 5 * 60 * 1000, // 5 min — admin config changes rarely
  })
}

/**
 * Create a new global AI provider.
 * Optimistically appends to the provider list.
 */
export function useCreateAiProvider(): UseMutationResult<AiProviderResponse, Error, AiProviderCreate> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (body: AiProviderCreate) => {
      const response = await authPost<AiProviderResponse>(
        '/api/ai/config/providers',
        body
      )

      if (response.status !== 201) {
        throw new Error(parseApiError(response.status, response.data))
      }

      return response.data
    },
    onMutate: async (body) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.aiProviders })
      const previous = queryClient.getQueryData<AiProviderResponse[]>(queryKeys.aiProviders)

      const optimistic: AiProviderResponse = {
        id: `__temp_${Date.now()}`,
        name: body.name,
        display_name: body.display_name,
        provider_type: body.provider_type,
        base_url: body.base_url ?? null,
        is_enabled: body.is_enabled ?? true,
        scope: 'global',
        user_id: null,
        has_api_key: !!body.api_key,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        models: [],
      }

      queryClient.setQueryData<AiProviderResponse[]>(
        queryKeys.aiProviders,
        (old) => [...(old ?? []), optimistic]
      )

      return { previous }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.aiProviders })
      queryClient.invalidateQueries({ queryKey: queryKeys.aiModels })
      queryClient.invalidateQueries({ queryKey: queryKeys.aiConfigSummary })
    },
    onError: (_error, _body, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.aiProviders, context.previous)
      }
      queryClient.invalidateQueries({ queryKey: queryKeys.aiModels })
      queryClient.invalidateQueries({ queryKey: queryKeys.aiConfigSummary })
    },
  })
}

/**
 * Update a global AI provider.
 */
export function useUpdateAiProvider(): UseMutationResult<
  AiProviderResponse,
  Error,
  { providerId: string; body: AiProviderUpdate }
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ providerId, body }) => {
      const response = await authPut<AiProviderResponse>(
        `/api/ai/config/providers/${providerId}`,
        body
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data))
      }

      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.aiProviders })
      queryClient.invalidateQueries({ queryKey: queryKeys.aiModels })
      queryClient.invalidateQueries({ queryKey: queryKeys.aiConfigSummary })
    },
  })
}

/**
 * Delete a global AI provider. Cascades to its models.
 */
export function useDeleteAiProvider(): UseMutationResult<void, Error, string> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (providerId: string) => {
      const response = await authDelete<void>(
        `/api/ai/config/providers/${providerId}`
      )

      if (response.status !== 204 && response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data))
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.aiProviders })
      queryClient.invalidateQueries({ queryKey: queryKeys.aiModels })
      queryClient.invalidateQueries({ queryKey: queryKeys.aiConfigSummary })
    },
  })
}

/**
 * Test connectivity for a global AI provider.
 */
export function useTestAiProvider(): UseMutationResult<TestProviderResult, Error, string> {
  return useMutation({
    mutationFn: async (providerId: string) => {
      const response = await authPost<TestProviderResult>(
        `/api/ai/config/providers/${providerId}/test`,
        undefined
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data))
      }

      return response.data
    },
  })
}

// ============================================================================
// Model Hooks
// ============================================================================

/**
 * Fetch all AI models across all global providers.
 * Optionally filter by provider_type and/or capability via params.
 */
export function useAiModels(params?: {
  provider_type?: string
  capability?: string
}): UseQueryResult<AiModelResponse[], Error> {
  const token = useAuthToken()

  return useQuery({
    queryKey: [
      ...queryKeys.aiModels,
      params?.provider_type ?? null,
      params?.capability ?? null,
    ],
    queryFn: async () => {
      const searchParams = new URLSearchParams()
      if (params?.provider_type) {
        searchParams.set('provider_type', params.provider_type)
      }
      if (params?.capability) {
        searchParams.set('capability', params.capability)
      }
      const queryString = searchParams.toString() ? `?${searchParams.toString()}` : ''

      const response = await authGet<AiModelResponse[]>(
        `/api/ai/config/models${queryString}`
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data))
      }

      return response.data
    },
    enabled: !!token,
  })
}

/**
 * Create a new AI model under a global provider.
 */
export function useCreateAiModel(): UseMutationResult<AiModelResponse, Error, AiModelCreate> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (body: AiModelCreate) => {
      const response = await authPost<AiModelResponse>(
        '/api/ai/config/models',
        body
      )

      if (response.status !== 201) {
        throw new Error(parseApiError(response.status, response.data))
      }

      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.aiModels })
      queryClient.invalidateQueries({ queryKey: queryKeys.aiConfigSummary })
    },
  })
}

/**
 * Update an AI model entry.
 */
export function useUpdateAiModel(): UseMutationResult<
  AiModelResponse,
  Error,
  { modelId: string; body: AiModelUpdate }
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ modelId, body }) => {
      const response = await authPut<AiModelResponse>(
        `/api/ai/config/models/${modelId}`,
        body
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data))
      }

      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.aiModels })
      queryClient.invalidateQueries({ queryKey: queryKeys.aiConfigSummary })
    },
  })
}

/**
 * Delete an AI model entry.
 */
export function useDeleteAiModel(): UseMutationResult<void, Error, string> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (modelId: string) => {
      const response = await authDelete<void>(
        `/api/ai/config/models/${modelId}`
      )

      if (response.status !== 204 && response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data))
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.aiModels })
      queryClient.invalidateQueries({ queryKey: queryKeys.aiConfigSummary })
    },
  })
}

/**
 * Fetch available models from the public endpoint (no developer auth required).
 * Used by the user chat override panel so non-developers can see model options.
 */
export function useAvailableModels(params?: {
  provider_type?: string
  capability?: string
}): UseQueryResult<AiModelResponse[], Error> {
  const token = useAuthToken()

  return useQuery({
    queryKey: [
      'ai', 'models', 'available',
      params?.provider_type ?? null,
      params?.capability ?? null,
    ],
    queryFn: async () => {
      const searchParams = new URLSearchParams()
      if (params?.provider_type) {
        searchParams.set('provider_type', params.provider_type)
      }
      if (params?.capability) {
        searchParams.set('capability', params.capability)
      }
      const queryString = searchParams.toString() ? `?${searchParams.toString()}` : ''

      const response = await authGet<AiModelResponse[]>(
        `/api/ai/config/models/available${queryString}`
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data))
      }

      return response.data
    },
    enabled: !!token,
  })
}

// ============================================================================
// Index Status Hooks
// ============================================================================

/**
 * Fetch embedding index status for a single document.
 * WebSocket EMBEDDING_UPDATED events keep this fresh.
 */
export function useDocumentIndexStatus(
  documentId: string | null
): UseQueryResult<IndexStatusResponse, Error> {
  const token = useAuthToken()

  return useQuery({
    queryKey: queryKeys.documentIndexStatus(documentId ?? ''),
    queryFn: async () => {
      const response = await authGet<IndexStatusResponse>(
        `/api/ai/index-status/${documentId}`
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data))
      }

      return response.data
    },
    enabled: !!token && !!documentId,
    staleTime: 60 * 1000,
    refetchOnWindowFocus: false,
  })
}

/**
 * Fetch index status summary for an application.
 */
export function useApplicationIndexStatus(
  applicationId: string | null
): UseQueryResult<IndexProgressResponse, Error> {
  const token = useAuthToken()

  return useQuery({
    queryKey: queryKeys.applicationIndexStatus(applicationId ?? ''),
    queryFn: async () => {
      const response = await authGet<IndexProgressResponse>(
        `/api/ai/index-status/application/${applicationId}`
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data))
      }

      return response.data
    },
    enabled: !!token && !!applicationId,
    staleTime: 5 * 60 * 1000,
    refetchOnWindowFocus: false,
  })
}

/**
 * Sync embeddings for a single document via POST /api/documents/{id}/sync-embeddings.
 * Clears old ARQ job/result keys to ensure the job re-queues reliably.
 */
export function useSyncDocumentEmbeddings(): UseMutationResult<
  { status: string; document_id: string },
  Error,
  string
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (documentId: string) => {
      const response = await authPost<{ status: string; document_id: string }>(
        `/api/documents/${documentId}/sync-embeddings`,
        undefined
      )

      if (response.status !== 202 && response.status !== 200) {
        const errorData = response.data as { detail?: string } | undefined
        throw new Error(errorData?.detail || `Sync failed (${response.status})`)
      }

      return response.data
    },
    onSuccess: (_data, documentId) => {
      // Mark pending on individual document cache
      queryClient.setQueryData(
        queryKeys.document(documentId),
        (old: Record<string, unknown> | undefined) =>
          old ? { ...old, embedding_status: 'syncing' } : old
      )
      // Also mark pending in document list caches so tree-view dots update
      queryClient.setQueriesData<{ items: Array<Record<string, unknown>> }>(
        { queryKey: ['documents'] },
        (old) => {
          if (!old?.items) return old
          const idx = old.items.findIndex((d) => d.id === documentId)
          if (idx === -1) return old
          const updated = [...old.items]
          updated[idx] = { ...updated[idx], embedding_status: 'syncing' }
          return { ...old, items: updated }
        }
      )
    },
  })
}

/**
 * Re-embed all stale documents in an application.
 */
export function useReindexApplication(): UseMutationResult<
  { status: string; application_id: string },
  Error,
  string
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (applicationId: string) => {
      const response = await authPost<{ status: string; application_id: string }>(
        `/api/ai/reindex/application/${applicationId}`,
        undefined
      )

      if (response.status !== 202 && response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data))
      }

      return response.data
    },
    onSuccess: (_data, applicationId) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.applicationIndexStatus(applicationId) })
    },
  })
}

/**
 * Poll index progress. Refetches every 15s while status is "running".
 *
 * NOTE: The backend already pushes EMBEDDING_UPDATED events via WebSocket,
 * so this polling could be replaced with WS-driven cache invalidation
 * (e.g., invalidateQueries on EMBEDDING_UPDATED in use-websocket-cache.ts).
 * Keeping polling as a fallback for reliability.
 */
export function useIndexProgress(): UseQueryResult<IndexProgressResponse, Error> {
  const token = useAuthToken()

  return useQuery({
    queryKey: queryKeys.indexProgress,
    queryFn: async () => {
      const response = await authGet<IndexProgressResponse>(
        '/api/ai/index-progress'
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data))
      }

      return response.data
    },
    enabled: !!token,
    refetchInterval: (query) => {
      const data = query.state.data as IndexProgressResponse | undefined
      return data?.status === 'running' ? 15_000 : false
    },
    refetchOnWindowFocus: false,
  })
}

// useImportJobs is canonically defined in use-document-import.ts
// Import from there: import { useImportJobs } from '@/hooks/use-document-import'

// ============================================================================
// Config Summary Hooks
// ============================================================================

/**
 * Fetch the full AI config summary with default models per capability.
 */
export function useAiConfigSummary(): UseQueryResult<AiConfigSummaryResponse, Error> {
  const token = useAuthToken()

  return useQuery({
    queryKey: queryKeys.aiConfigSummary,
    queryFn: async () => {
      const response = await authGet<AiConfigSummaryResponse>(
        '/api/ai/config/summary'
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data))
      }

      return response.data
    },
    enabled: !!token,
    staleTime: 5 * 60 * 1000, // 5 min — admin config changes rarely
  })
}

/**
 * Fetch the current global config for a specific capability.
 */
export function useCapabilityConfig(
  capability: string | null
): UseQueryResult<CapabilityConfig, Error> {
  const token = useAuthToken()

  return useQuery({
    queryKey: queryKeys.capabilityConfig(capability ?? ''),
    queryFn: async () => {
      const response = await authGet<CapabilityConfig>(
        `/api/ai/config/capability/${capability}`
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data))
      }

      return response.data
    },
    enabled: !!token && !!capability,
  })
}

/**
 * Save the global config for a specific capability.
 */
export function useSaveCapabilityConfig(): UseMutationResult<
  AiProviderResponse,
  Error,
  { capability: string; body: Record<string, unknown> }
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ capability, body }) => {
      const response = await authPut<AiProviderResponse>(
        `/api/ai/config/capability/${capability}`,
        body
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data))
      }

      return response.data
    },
    onSuccess: (data: AiProviderResponse, { capability }) => {
      // Backend returns AiProviderResponse; transform to CapabilityConfig for the cache
      const defaultModel = data.models?.find(
        (m: AiModelResponse) => m.capability === capability && m.is_default
      )
      const configForCache: CapabilityConfig = {
        capability,
        provider_id: data.id,
        provider_type: data.provider_type,
        base_url: data.base_url ?? null,
        model_id: defaultModel?.model_id ?? null,
        model_display_name: defaultModel?.display_name ?? null,
        has_api_key: data.has_api_key,
      }
      queryClient.setQueryData(queryKeys.capabilityConfig(capability), configForCache)

      // Invalidate other capability configs — the saved provider's API key
      // may be shared across capabilities (e.g., same OpenAI key for chat
      // and vision). This ensures has_api_key updates in sibling sections.
      const ALL_CAPABILITIES = ['chat', 'embedding', 'vision']
      for (const cap of ALL_CAPABILITIES) {
        if (cap !== capability) {
          queryClient.invalidateQueries({ queryKey: queryKeys.capabilityConfig(cap) })
        }
      }

      queryClient.invalidateQueries({ queryKey: queryKeys.aiConfigSummary })
      queryClient.invalidateQueries({ queryKey: queryKeys.aiProviders })
      queryClient.invalidateQueries({ queryKey: queryKeys.aiModels })
    },
  })
}

// ============================================================================
// User Chat Override Hooks
// ============================================================================

/**
 * Fetch the current user's provider overrides.
 */
export function useUserOverrides(): UseQueryResult<AiProviderResponse[], Error> {
  const token = useAuthToken()

  return useQuery({
    queryKey: queryKeys.userOverrides,
    queryFn: async () => {
      const response = await authGet<AiProviderResponse[]>(
        '/api/ai/config/me/providers'
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data))
      }

      return response.data
    },
    enabled: !!token,
  })
}

/**
 * Create a user-scoped provider override with a personal API key.
 */
export function useCreateUserOverride(): UseMutationResult<
  AiProviderResponse,
  Error,
  UserOverrideConfig
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (body: UserOverrideConfig) => {
      const response = await authPost<AiProviderResponse>(
        '/api/ai/config/me/providers',
        body
      )

      if (response.status !== 201) {
        throw new Error(parseApiError(response.status, response.data))
      }

      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.userOverrides })
    },
  })
}

/**
 * Update a user's provider override.
 */
export function useUpdateUserOverride(): UseMutationResult<
  AiProviderResponse,
  Error,
  { providerType: string; body: UserOverrideConfig }
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ providerType, body }) => {
      const response = await authPut<AiProviderResponse>(
        `/api/ai/config/me/providers/${providerType}`,
        body
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data))
      }

      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.userOverrides })
    },
  })
}

/**
 * Delete a user's provider override (fall back to global config).
 */
export function useDeleteUserOverride(): UseMutationResult<void, Error, string> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (providerType: string) => {
      const response = await authDelete<void>(
        `/api/ai/config/me/providers/${providerType}`
      )

      if (response.status !== 204 && response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data))
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.userOverrides })
    },
  })
}

/**
 * Test connectivity for a user's provider override.
 */
export function useTestUserOverride(): UseMutationResult<TestProviderResult, Error, string> {
  return useMutation({
    mutationFn: async (providerType: string) => {
      const response = await authPost<TestProviderResult>(
        `/api/ai/config/me/providers/${providerType}/test`,
        undefined
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data))
      }

      return response.data
    },
  })
}

/**
 * Fetch the current user's effective AI config (global + user overrides merged).
 */
export function useUserEffectiveConfig(): UseQueryResult<EffectiveChatConfig, Error> {
  const token = useAuthToken()

  return useQuery({
    queryKey: queryKeys.userEffectiveConfig,
    queryFn: async () => {
      const response = await authGet<EffectiveChatConfig>(
        '/api/ai/config/me/summary'
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data))
      }

      return response.data
    },
    enabled: !!token,
    staleTime: 5 * 60 * 1000,
  })
}
