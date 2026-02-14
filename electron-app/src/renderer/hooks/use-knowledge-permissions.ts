/**
 * Knowledge Permissions Hooks
 *
 * Provides permission checks for the knowledge base:
 * - useKnowledgePermissions: canView/canEdit for a given scope
 * - useProjectPermissionsMap: per-project canEdit map for application trees
 *
 * Permission rules:
 * - Personal scope: always canView + canEdit (user's own data)
 * - Application scope: derived from user_role in scopes-summary data
 * - Project scope: fetched from dedicated backend endpoint
 */

import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useAuthStore } from '@/contexts/auth-context'
import { queryKeys } from '@/lib/query-client'
import { useApplicationsWithDocs, useProjectsWithContent } from './use-documents'
import type { ScopeType } from '@/contexts/knowledge-base-context'

// ============================================================================
// Types
// ============================================================================

export interface KnowledgePermissions {
  canView: boolean
  canEdit: boolean
  /** Whether the current user is an application owner (for force-take locks) */
  isOwner: boolean
  isLoading: boolean
}

interface PermissionResponse {
  can_view: boolean
  can_edit: boolean
  is_owner: boolean
}

// ============================================================================
// Helpers
// ============================================================================

function getAuthHeaders(token: string | null): Record<string, string> {
  if (!token) return {}
  return { Authorization: `Bearer ${token}` }
}

// ============================================================================
// useKnowledgePermissions
// ============================================================================

/**
 * Returns canView/canEdit permissions for a given knowledge base scope.
 *
 * - Personal: always { canView: true, canEdit: true }
 * - Application: derived from user_role in scopes-summary
 * - Project: fetched from GET /documents/knowledge-permissions
 */
export function useKnowledgePermissions(
  scope: ScopeType | null,
  scopeId: string | null
): KnowledgePermissions {
  const token = useAuthStore((s) => s.token)

  // Application scope: derive from scopes-summary (which already has user_role)
  const { data: scopesSummary, isLoading: isScopesLoading } = useApplicationsWithDocs()

  // Project scope: dedicated endpoint
  const projectQuery = useQuery({
    queryKey: queryKeys.knowledgePermissions('project', scopeId ?? ''),
    queryFn: async () => {
      if (!window.electronAPI || !scopeId) {
        throw new Error('Electron API not available or no scope ID')
      }

      const params = new URLSearchParams()
      params.set('scope', 'project')
      params.set('scope_id', scopeId)

      const response = await window.electronAPI.get<PermissionResponse>(
        `/api/documents/knowledge-permissions?${params.toString()}`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error('Failed to fetch permissions')
      }

      return response.data
    },
    enabled: !!token && scope === 'project' && !!scopeId,
    staleTime: 5 * 60 * 1000, // 5 min — permissions rarely change
    gcTime: 24 * 60 * 60 * 1000,
    refetchOnWindowFocus: false,
    refetchOnMount: 'always', // Revalidate on remount after WS reconnect (subscriptions lost on unmount)
  })

  return useMemo(() => {
    // Personal scope: always full access (user is "owner" of their own scope)
    if (scope === 'personal' || scope === null) {
      return { canView: true, canEdit: true, isOwner: true, isLoading: false }
    }

    // Application scope: derive from scopes-summary user_role
    if (scope === 'application') {
      if (isScopesLoading) {
        return { canView: true, canEdit: false, isOwner: false, isLoading: true }
      }
      const app = scopesSummary?.applications?.find((a) => a.id === scopeId)
      const role = app?.user_role
      const canView = !!role
      const canEdit = role === 'owner' || role === 'editor'
      const isOwner = role === 'owner'
      return { canView, canEdit, isOwner, isLoading: false }
    }

    // Project scope: from dedicated endpoint
    if (scope === 'project') {
      if (projectQuery.isLoading) {
        return { canView: true, canEdit: false, isOwner: false, isLoading: true }
      }
      if (projectQuery.data) {
        return {
          canView: projectQuery.data.can_view,
          canEdit: projectQuery.data.can_edit,
          isOwner: projectQuery.data.is_owner,
          isLoading: false,
        }
      }
      // Fallback: no data yet, default to view-only
      return { canView: true, canEdit: false, isOwner: false, isLoading: false }
    }

    // Unreachable for valid ScopeType — default to view-only for safety
    return { canView: true, canEdit: false, isOwner: false, isLoading: false }
  }, [scope, scopeId, isScopesLoading, scopesSummary, projectQuery.isLoading, projectQuery.data])
}

// ============================================================================
// useProjectPermissionsMap
// ============================================================================

/**
 * Returns a Map<projectId, canEdit> for all projects in an application.
 * Derived from the enriched projects-with-content endpoint.
 */
export function useProjectPermissionsMap(
  applicationId: string | undefined
): { permissionsMap: Map<string, boolean>; isLoading: boolean } {
  const { data, isLoading } = useProjectsWithContent(applicationId ?? null)

  const permissionsMap = useMemo(() => {
    const map = new Map<string, boolean>()
    if (data?.project_permissions) {
      for (const perm of data.project_permissions) {
        map.set(perm.project_id, perm.can_edit)
      }
    }
    return map
  }, [data])

  return { permissionsMap, isLoading }
}
