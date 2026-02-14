/**
 * TanStack Query Hooks for Document Tags
 *
 * Provides React Query hooks for fetching document tags.
 * Uses the per-query-persister for automatic IndexedDB caching.
 *
 * @see fastapi-backend/app/routers/document_tags.py
 */

import {
  useQuery,
  type UseQueryResult,
} from '@tanstack/react-query'
import { useAuthStore } from '@/contexts/auth-context'
import { queryKeys } from '@/lib/query-client'

// ============================================================================
// Types
// ============================================================================

export interface DocumentTag {
  id: string
  name: string
  color: string | null
  application_id: string | null
  user_id: string | null
  created_at: string
}

// ============================================================================
// Helper Functions
// ============================================================================

function getAuthHeaders(token: string | null): Record<string, string> {
  if (!token) return {}
  return { Authorization: `Bearer ${token}` }
}

function parseApiError(status: number, data: unknown): string {
  if (typeof data === 'object' && data !== null) {
    const errorData = data as Record<string, unknown>
    if (typeof errorData.detail === 'string') {
      return errorData.detail
    }
  }

  switch (status) {
    case 400:
      return 'Invalid request. Please check your input.'
    case 401:
      return 'Authentication required. Please log in again.'
    case 403:
      return 'Access denied.'
    default:
      return 'An unexpected error occurred.'
  }
}

/**
 * Map frontend scope to API scope and scope_id.
 * Tags only support 'application' and 'personal' scopes.
 */
function resolveTagScope(
  scope: string,
  scopeId: string | null,
  userId: string | null
): { apiScope: string; apiScopeId: string } | null {
  if (scope === 'personal') {
    if (!userId) return null
    return { apiScope: 'personal', apiScopeId: userId }
  }
  if (scope === 'application') {
    if (!scopeId) return null
    return { apiScope: 'application', apiScopeId: scopeId }
  }
  // For 'project' scope, tags are at the application level
  // The caller should pass the application ID as scopeId for tag queries
  if (!scopeId) return null
  return { apiScope: 'application', apiScopeId: scopeId }
}

// ============================================================================
// Query Hooks
// ============================================================================

/**
 * Fetch tags for a scope.
 * Tags are scoped to application or personal (user).
 * For project scope, pass the parent application ID.
 */
export function useDocumentTags(
  scope: string,
  scopeId: string | null
): UseQueryResult<DocumentTag[], Error> {
  const token = useAuthStore((s) => s.token)
  const userId = useAuthStore((s) => s.user?.id ?? null)

  return useQuery({
    queryKey: queryKeys.documentTags(scope, scopeId ?? ''),
    queryFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const resolved = resolveTagScope(scope, scopeId, userId)
      if (!resolved) {
        return []
      }

      const params = new URLSearchParams()
      params.set('scope', resolved.apiScope)
      params.set('scope_id', resolved.apiScopeId)

      const response = await window.electronAPI.get<DocumentTag[]>(
        `/api/document-tags?${params.toString()}`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data))
      }

      return response.data ?? []
    },
    enabled:
      !!token &&
      !!scope &&
      (scope === 'personal' || !!scopeId),
    staleTime: 60 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
  })
}
