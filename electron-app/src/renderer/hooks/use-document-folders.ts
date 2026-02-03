/**
 * TanStack Query Hooks for Document Folders
 *
 * Provides React Query hooks for folder tree CRUD operations.
 * Uses the per-query-persister for automatic IndexedDB caching.
 *
 * @see fastapi-backend/app/routers/document_folders.py
 */

import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryResult,
  type UseMutationResult,
} from '@tanstack/react-query'
import { useAuthStore } from '@/contexts/auth-context'
import { queryKeys } from '@/lib/query-client'

// ============================================================================
// Types
// ============================================================================

export interface DocumentFolder {
  id: string
  name: string
  parent_id: string | null
  materialized_path: string
  depth: number
  sort_order: number
  application_id: string | null
  project_id: string | null
  user_id: string | null
  created_by: string | null
  created_at: string
  updated_at: string
}

export interface FolderTreeNode {
  id: string
  name: string
  parent_id: string | null
  materialized_path: string
  depth: number
  sort_order: number
  children: FolderTreeNode[]
  document_count: number
}

interface CreateFolderParams {
  name: string
  parent_id?: string | null
  scope: string
  scope_id: string
}

interface RenameFolderParams {
  folderId: string
  name: string
}

interface MoveFolderParams {
  folderId: string
  parent_id: string | null
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
    case 404:
      return 'Folder not found.'
    default:
      return 'An unexpected error occurred.'
  }
}

/**
 * Map frontend scope to API scope and scope_id.
 * Frontend uses 'personal' with no scopeId; API requires scope='personal' + scope_id=userId.
 */
function resolveScope(
  scope: string,
  scopeId: string | null,
  userId: string | null
): { apiScope: string; apiScopeId: string } | null {
  if (scope === 'personal') {
    if (!userId) return null
    return { apiScope: 'personal', apiScopeId: userId }
  }
  if (!scopeId) return null
  return { apiScope: scope, apiScopeId: scopeId }
}

// ============================================================================
// Query Hooks
// ============================================================================

/**
 * Fetch the full folder tree for a scope.
 * Returns nested FolderTreeNode[] from the /tree endpoint.
 */
export function useFolderTree(
  scope: string,
  scopeId: string | null
): UseQueryResult<FolderTreeNode[], Error> {
  const token = useAuthStore((s) => s.token)
  const userId = useAuthStore((s) => s.user?.id ?? null)

  return useQuery({
    queryKey: queryKeys.documentFolders(scope, scopeId ?? ''),
    queryFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const resolved = resolveScope(scope, scopeId, userId)
      if (!resolved) {
        return []
      }

      const params = new URLSearchParams()
      params.set('scope', resolved.apiScope)
      params.set('scope_id', resolved.apiScopeId)

      const response = await window.electronAPI.get<FolderTreeNode[]>(
        `/api/document-folders/tree?${params.toString()}`,
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
    staleTime: 30 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
  })
}

// ============================================================================
// Mutation Hooks
// ============================================================================

/**
 * Create a new folder.
 */
export function useCreateFolder(): UseMutationResult<DocumentFolder, Error, CreateFolderParams> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (params: CreateFolderParams) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.post<DocumentFolder>(
        '/api/document-folders',
        {
          name: params.name,
          parent_id: params.parent_id ?? null,
          scope: params.scope,
          scope_id: params.scope_id,
        },
        getAuthHeaders(token)
      )

      if (response.status !== 201) {
        throw new Error(parseApiError(response.status, response.data))
      }

      return response.data
    },
    onSuccess: (_data, params) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.documentFolders(params.scope, params.scope_id),
      })
    },
  })
}

/**
 * Rename a folder.
 */
export function useRenameFolder(
  scope: string,
  scopeId: string
): UseMutationResult<DocumentFolder, Error, RenameFolderParams> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ folderId, name }: RenameFolderParams) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.put<DocumentFolder>(
        `/api/document-folders/${folderId}`,
        { name },
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data))
      }

      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.documentFolders(scope, scopeId),
      })
    },
  })
}

/**
 * Move a folder to a new parent.
 */
export function useMoveFolder(
  scope: string,
  scopeId: string
): UseMutationResult<DocumentFolder, Error, MoveFolderParams> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ folderId, parent_id }: MoveFolderParams) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.put<DocumentFolder>(
        `/api/document-folders/${folderId}`,
        { parent_id },
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data))
      }

      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.documentFolders(scope, scopeId),
      })
    },
  })
}

/**
 * Delete a folder.
 */
export function useDeleteFolder(
  scope: string,
  scopeId: string
): UseMutationResult<void, Error, string> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (folderId: string) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.delete<void>(
        `/api/document-folders/${folderId}`,
        getAuthHeaders(token)
      )

      if (response.status !== 204 && response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data))
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.documentFolders(scope, scopeId),
      })
    },
  })
}

// ============================================================================
// Reorder Mutation
// ============================================================================

interface ReorderFolderParams {
  folderId: string
  sortOrder: number
  parentId?: string | null
}

/**
 * Reorder a folder by updating its sort_order.
 * Uses the existing PUT endpoint with sort_order field.
 */
export function useReorderFolder(
  scope: string,
  scopeId: string
): UseMutationResult<DocumentFolder, Error, ReorderFolderParams> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ folderId, sortOrder, parentId }: ReorderFolderParams) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const body: { sort_order: number; parent_id?: string | null } = {
        sort_order: sortOrder,
      }
      if (parentId !== undefined) {
        body.parent_id = parentId
      }

      const response = await window.electronAPI.put<DocumentFolder>(
        `/api/document-folders/${folderId}`,
        body,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data))
      }

      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.documentFolders(scope, scopeId),
      })
    },
  })
}
