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
import { TEMP_ID_PREFIX } from './use-documents'

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
  scope: string
  scopeId: string
}

interface MoveFolderParams {
  folderId: string
  parent_id: string | null
  scope: string
  scopeId: string
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

  // For personal scope, use userId as the cache key so WebSocket invalidation works
  const effectiveScopeId = scope === 'personal' ? (userId ?? '') : (scopeId ?? '')

  return useQuery({
    queryKey: queryKeys.documentFolders(scope, effectiveScopeId),
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
    // Sort folders case-insensitively at every tree level so order is consistent
    // regardless of backend collation, stale cache, or optimistic update timing.
    select: (data) => {
      const sortTree = (nodes: FolderTreeNode[]): FolderTreeNode[] =>
        [...nodes]
          .sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }))
          .map(n => ({ ...n, children: sortTree(n.children) }))
      return sortTree(data)
    },
    // Use default staleTime (30s) - fresh data won't refetch on focus, stale data will
    gcTime: 24 * 60 * 60 * 1000,
    // WebSocket subscriptions keep cache fresh while mounted; window focus refetch is redundant.
    // On remount (screen navigation), refetchOnMount: true (default) ensures stale data is refreshed.
    refetchOnWindowFocus: false,
    // No placeholderData - let isLoading be true on initial fetch so skeleton shows
  })
}

// ============================================================================
// Mutation Hooks (with Optimistic Updates)
// ============================================================================

// TEMP_ID_PREFIX imported from use-documents.ts

// Helper to add a folder to tree — select transform handles sorting
function addFolderToTree(tree: FolderTreeNode[], folder: FolderTreeNode, parentId: string | null): FolderTreeNode[] {
  if (!parentId) {
    return [...tree, folder]
  }

  return tree.map(node => {
    if (node.id === parentId) {
      return { ...node, children: [...node.children, folder] }
    }
    if (node.children.length > 0) {
      return { ...node, children: addFolderToTree(node.children, folder, parentId) }
    }
    return node
  })
}

// Helper to update a folder in tree
function updateFolderInTree(tree: FolderTreeNode[], folderId: string, updates: Partial<FolderTreeNode>): FolderTreeNode[] {
  return tree.map(node => {
    if (node.id === folderId) {
      return { ...node, ...updates }
    }
    if (node.children.length > 0) {
      return { ...node, children: updateFolderInTree(node.children, folderId, updates) }
    }
    return node
  })
}

// Helper to remove a folder from tree
function removeFolderFromTree(tree: FolderTreeNode[], folderId: string): FolderTreeNode[] {
  return tree
    .filter(node => node.id !== folderId)
    .map(node => ({
      ...node,
      children: removeFolderFromTree(node.children, folderId),
    }))
}

/**
 * Create a new folder with optimistic update.
 */
export function useCreateFolder(): UseMutationResult<DocumentFolder, Error, CreateFolderParams> {
  const token = useAuthStore((s) => s.token)
  const userId = useAuthStore((s) => s.user?.id ?? null)
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
    onMutate: async (params) => {
      const effectiveScopeId = params.scope === 'personal' ? (userId ?? '') : params.scope_id
      const queryKey = queryKeys.documentFolders(params.scope, effectiveScopeId)

      await queryClient.cancelQueries({ queryKey })

      const previous = queryClient.getQueryData<FolderTreeNode[]>(queryKey)

      // Create optimistic folder
      const tempId = TEMP_ID_PREFIX + Date.now()
      const tempFolder: FolderTreeNode = {
        id: tempId,
        name: params.name,
        parent_id: params.parent_id ?? null,
        materialized_path: tempId,
        depth: params.parent_id ? 1 : 0, // Simplified depth
        sort_order: 0,
        children: [],
        document_count: 0,
      }

      // Add to tree
      queryClient.setQueryData<FolderTreeNode[]>(queryKey, (old) =>
        addFolderToTree(old ?? [], tempFolder, params.parent_id ?? null)
      )

      return { previous, queryKey, tempId }
    },
    onSuccess: (data, params, context) => {
      if (!context) return

      // Replace temp folder with real folder
      const effectiveScopeId = params.scope === 'personal' ? (userId ?? '') : params.scope_id
      const queryKey = queryKeys.documentFolders(params.scope, effectiveScopeId)

      queryClient.setQueryData<FolderTreeNode[]>(queryKey, (old) =>
        updateFolderInTree(old ?? [], context.tempId, {
          id: data.id,
          materialized_path: data.materialized_path,
          depth: data.depth,
        })
      )
    },
    onError: (_error, _params, context) => {
      if (context?.previous) {
        queryClient.setQueryData(context.queryKey, context.previous)
      }
    },
  })
}

/**
 * Rename a folder with optimistic update.
 */
export function useRenameFolder(): UseMutationResult<DocumentFolder, Error, RenameFolderParams> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()
  const userId = useAuthStore((s) => s.user?.id ?? null)

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
    onMutate: async ({ folderId, name, scope, scopeId }) => {
      const effectiveScopeId = scope === 'personal' ? (userId ?? '') : scopeId
      const queryKey = queryKeys.documentFolders(scope, effectiveScopeId)

      await queryClient.cancelQueries({ queryKey })

      const previous = queryClient.getQueryData<FolderTreeNode[]>(queryKey)

      // Optimistically update folder name
      queryClient.setQueryData<FolderTreeNode[]>(queryKey, (old) =>
        updateFolderInTree(old ?? [], folderId, { name })
      )

      return { previous, queryKey }
    },
    onError: (_error, _params, context) => {
      if (context?.previous) {
        queryClient.setQueryData(context.queryKey, context.previous)
      }
    },
  })
}

/**
 * Move a folder to a new parent with optimistic update.
 */
export function useMoveFolder(): UseMutationResult<DocumentFolder, Error, MoveFolderParams> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()
  const userId = useAuthStore((s) => s.user?.id ?? null)

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
    onMutate: async ({ folderId, parent_id, scope, scopeId }) => {
      const effectiveScopeId = scope === 'personal' ? (userId ?? '') : scopeId
      const queryKey = queryKeys.documentFolders(scope, effectiveScopeId)

      await queryClient.cancelQueries({ queryKey })

      const previous = queryClient.getQueryData<FolderTreeNode[]>(queryKey)

      // For move, we need to:
      // 1. Find and remove the folder from its current location
      // 2. Add it to the new parent
      if (previous) {
        // Find the folder to move
        const findFolder = (nodes: FolderTreeNode[], id: string): FolderTreeNode | null => {
          for (const node of nodes) {
            if (node.id === id) return node
            const found = findFolder(node.children, id)
            if (found) return found
          }
          return null
        }

        const folderToMove = findFolder(previous, folderId)
        if (folderToMove) {
          // Remove from old location, add to new
          const removed = removeFolderFromTree(previous, folderId)
          const updated = addFolderToTree(removed, { ...folderToMove, parent_id }, parent_id)
          queryClient.setQueryData<FolderTreeNode[]>(queryKey, updated)
        }
      }

      return { previous, queryKey }
    },
    onSuccess: (_data, { scope, scopeId }) => {
      const effectiveScopeId = scope === 'personal' ? (userId ?? '') : scopeId
      // Refetch the full tree to get accurate materialized_path and depth
      queryClient.invalidateQueries({
        queryKey: queryKeys.documentFolders(scope, effectiveScopeId),
      })
      // Update project section visibility
      queryClient.invalidateQueries({ queryKey: ['projects-with-content'] })
    },
    onError: (_error, _params, context) => {
      if (context?.previous) {
        queryClient.setQueryData(context.queryKey, context.previous)
      }
    },
  })
}

/**
 * Delete a folder with optimistic update.
 */
export function useDeleteFolder(): UseMutationResult<void, Error, { folderId: string; scope: string; scopeId: string }> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()
  const userId = useAuthStore((s) => s.user?.id ?? null)

  return useMutation({
    mutationFn: async ({ folderId }: { folderId: string; scope: string; scopeId: string }) => {
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
    onMutate: async ({ folderId, scope, scopeId }) => {
      const effectiveScopeId = scope === 'personal' ? (userId ?? '') : scopeId
      const queryKey = queryKeys.documentFolders(scope, effectiveScopeId)

      await queryClient.cancelQueries({ queryKey })

      const previous = queryClient.getQueryData<FolderTreeNode[]>(queryKey)

      // Optimistically remove folder from tree
      queryClient.setQueryData<FolderTreeNode[]>(queryKey, (old) =>
        removeFolderFromTree(old ?? [], folderId)
      )

      return { previous, queryKey }
    },
    onSuccess: (_data, { scope, scopeId }) => {
      const effectiveScopeId = scope === 'personal' ? (userId ?? '') : scopeId
      // Documents in the deleted folder are soft-deleted on the server.
      // Invalidate document queries so they disappear from the UI.
      queryClient.invalidateQueries({
        queryKey: queryKeys.documents(scope, effectiveScopeId),
        exact: false,
      })
      queryClient.invalidateQueries({
        queryKey: queryKeys.scopesSummary(),
      })
      queryClient.invalidateQueries({
        queryKey: ['projects-with-content'],
      })
    },
    onError: (_error, _params, context) => {
      if (context?.previous) {
        queryClient.setQueryData(context.queryKey, context.previous)
      }
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
 * Reorder a folder with optimistic update.
 */
export function useReorderFolder(
  scope: string,
  scopeId: string
): UseMutationResult<DocumentFolder, Error, ReorderFolderParams> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()
  const userId = useAuthStore((s) => s.user?.id ?? null)

  const effectiveScopeId = scope === 'personal' ? (userId ?? '') : scopeId

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
    onMutate: async ({ folderId, sortOrder }) => {
      const queryKey = queryKeys.documentFolders(scope, effectiveScopeId)

      // Optimistically update sort_order
      queryClient.setQueryData<FolderTreeNode[]>(queryKey, (old) =>
        updateFolderInTree(old ?? [], folderId, { sort_order: sortOrder })
      )
    },
    // No rollback needed for reorder
  })
}
