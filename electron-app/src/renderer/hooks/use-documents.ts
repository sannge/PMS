/**
 * TanStack Query Hooks for Documents
 *
 * Provides React Query hooks for document CRUD operations.
 * Uses the per-query-persister for automatic IndexedDB caching.
 *
 * @see fastapi-backend/app/routers/documents.py
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

export interface Document {
  id: string
  title: string
  application_id: string | null
  project_id: string | null
  user_id: string | null
  folder_id: string | null
  content_json: string | null
  content_markdown: string | null
  content_plain: string | null
  sort_order: number
  created_by: string | null
  row_version: number
  schema_version: number
  deleted_at: string | null
  created_at: string
  updated_at: string
  tags: DocumentTagRef[]
}

export interface DocumentTagRef {
  id: string
  name: string
  color: string | null
  application_id: string | null
  user_id: string | null
  created_at: string
}

export interface DocumentListItem {
  id: string
  title: string
  folder_id: string | null
  sort_order: number
  row_version: number
  created_by: string | null
  created_at: string
  updated_at: string
  deleted_at: string | null
}

export interface DocumentListResponse {
  items: DocumentListItem[]
  next_cursor: string | null
}

interface CreateDocumentParams {
  title: string
  scope: string
  scope_id: string
  folder_id?: string | null
}

interface RenameDocumentParams {
  documentId: string
  title: string
  row_version: number
  scope: string
  scopeId: string
}

interface MoveDocumentParams {
  documentId: string
  folder_id: string | null
  row_version: number
  scope: string
  scopeId: string
}

interface DocumentsQueryOptions {
  folderId?: string | null
  includeUnfiled?: boolean
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
      return 'Document not found.'
    case 409:
      return 'Document has been modified by another user. Please refresh and try again.'
    default:
      return 'An unexpected error occurred.'
  }
}

/**
 * Map frontend scope to API scope and scope_id.
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
 * Fetch documents for a scope with optional folder and tag filtering.
 */
export function useDocuments(
  scope: string,
  scopeId: string | null,
  options?: DocumentsQueryOptions
): UseQueryResult<DocumentListResponse, Error> {
  const token = useAuthStore((s) => s.token)
  const userId = useAuthStore((s) => s.user?.id ?? null)

  // For personal scope, use userId as the cache key so WebSocket invalidation works
  const effectiveScopeId = scope === 'personal' ? (userId ?? '') : (scopeId ?? '')

  return useQuery({
    queryKey: [
      ...queryKeys.documents(scope, effectiveScopeId),
      options?.folderId ?? '',
      options?.includeUnfiled ?? false,
    ],
    queryFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const resolved = resolveScope(scope, scopeId, userId)
      if (!resolved) {
        return { items: [], next_cursor: null }
      }

      const params = new URLSearchParams()
      params.set('scope', resolved.apiScope)
      params.set('scope_id', resolved.apiScopeId)

      if (options?.folderId) {
        params.set('folder_id', options.folderId)
      }
      if (options?.includeUnfiled) {
        params.set('include_unfiled', 'true')
      }

      const response = await window.electronAPI.get<DocumentListResponse>(
        `/api/documents?${params.toString()}`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data))
      }

      return response.data
    },
    enabled:
      !!token &&
      !!scope &&
      (scope === 'personal' || !!scopeId),
    // Sort items case-insensitively so order is consistent regardless of
    // backend collation, stale cache, or optimistic update timing.
    select: (data) => ({
      ...data,
      items: [...data.items].sort((a, b) =>
        a.title.localeCompare(b.title, undefined, { sensitivity: 'base' })
      ),
    }),
    // Use default staleTime (30s) - fresh data won't refetch on focus, stale data will
    gcTime: 24 * 60 * 60 * 1000,
    // WebSocket subscriptions keep cache fresh while mounted; window focus refetch is redundant.
    refetchOnWindowFocus: false,
    // No placeholderData - let isLoading be true on initial fetch so skeleton shows
  })
}

/**
 * Fetch a single document by ID with full content.
 */
export function useDocument(id: string | null): UseQueryResult<Document, Error> {
  const token = useAuthStore((s) => s.token)

  return useQuery({
    queryKey: queryKeys.document(id ?? ''),
    queryFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.get<Document>(
        `/api/documents/${id}`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data))
      }

      return response.data
    },
    enabled: !!token && !!id,
    staleTime: 30 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
  })
}

// ============================================================================
// Mutation Hooks (with Optimistic Updates)
// ============================================================================

// Temporary ID prefix for optimistic items
export const TEMP_ID_PREFIX = '__temp_'

/**
 * Check if an ID is a temporary optimistic update ID.
 * Temp IDs are created during optimistic updates before the server responds.
 */
export function isTempId(id: string | null | undefined): boolean {
  return !!id && id.startsWith(TEMP_ID_PREFIX)
}

/**
 * Create a new document with optimistic update.
 * Adds document to cache immediately, replaces with server data on success.
 */
export function useCreateDocument(): UseMutationResult<Document, Error, CreateDocumentParams> {
  const token = useAuthStore((s) => s.token)
  const userId = useAuthStore((s) => s.user?.id ?? null)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (params: CreateDocumentParams) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.post<Document>(
        '/api/documents',
        {
          title: params.title,
          scope: params.scope,
          scope_id: params.scope_id,
          folder_id: params.folder_id ?? null,
        },
        getAuthHeaders(token)
      )

      if (response.status !== 201) {
        throw new Error(parseApiError(response.status, response.data))
      }

      return response.data
    },
    onMutate: async (params) => {
      // Resolve effective scope ID for cache key
      const effectiveScopeId = params.scope === 'personal' ? (userId ?? '') : params.scope_id

      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: queryKeys.documents(params.scope, effectiveScopeId) })

      // Snapshot previous value
      // When folder_id is set, target the folder-specific query key (includeUnfiled=false)
      // When no folder_id, target the unfiled query key (includeUnfiled=true)
      const queryKey = params.folder_id
        ? [...queryKeys.documents(params.scope, effectiveScopeId), params.folder_id, false]
        : [...queryKeys.documents(params.scope, effectiveScopeId), '', true]
      const previous = queryClient.getQueryData<DocumentListResponse>(queryKey)

      // Create optimistic document
      const tempId = TEMP_ID_PREFIX + Date.now()
      const tempDoc: DocumentListItem = {
        id: tempId,
        title: params.title,
        folder_id: params.folder_id ?? null,
        sort_order: 0,
        row_version: 1,
        created_by: userId,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        deleted_at: null,
      }

      // Append to cache — select transform handles sorting
      queryClient.setQueryData<DocumentListResponse>(queryKey, (old) => ({
        items: [...(old?.items ?? []), tempDoc],
        next_cursor: old?.next_cursor ?? null,
      }))

      return { previous, queryKey, tempId, effectiveScopeId, scope: params.scope }
    },
    onSuccess: (data, _params, context) => {
      if (!context) return

      // Replace temp document with real document
      queryClient.setQueryData<DocumentListResponse>(context.queryKey, (old) => ({
        items: (old?.items ?? []).map((item) =>
          item.id === context.tempId ? { ...item, id: data.id } : item
        ),
        next_cursor: old?.next_cursor ?? null,
      }))

      // Set the full document data
      queryClient.setQueryData(queryKeys.document(data.id), data)
    },
    onError: (_error, _params, context) => {
      // Rollback to previous state
      if (context?.previous) {
        queryClient.setQueryData(context.queryKey, context.previous)
      }
    },
  })
}

/**
 * Rename a document with optimistic update.
 */
export function useRenameDocument(): UseMutationResult<Document, Error, RenameDocumentParams> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()
  const userId = useAuthStore((s) => s.user?.id ?? null)

  return useMutation({
    mutationFn: async ({ documentId, title, row_version }: RenameDocumentParams) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.put<Document>(
        `/api/documents/${documentId}`,
        { title, row_version },
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data))
      }

      return response.data
    },
    onMutate: async ({ documentId, title, scope, scopeId }) => {
      const effectiveScopeId = scope === 'personal' ? (userId ?? '') : scopeId
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: queryKeys.document(documentId) })

      // Snapshot previous values
      const previousDoc = queryClient.getQueryData<Document>(queryKeys.document(documentId))

      // Snapshot list caches for rollback
      const previousLists: Map<string, DocumentListResponse | undefined> = new Map()
      queryClient.getQueriesData<DocumentListResponse>({
        queryKey: queryKeys.documents(scope, effectiveScopeId),
        exact: false,
      }).forEach(([key, data]) => {
        previousLists.set(JSON.stringify(key), data)
      })

      // Optimistically update document
      if (previousDoc) {
        queryClient.setQueryData<Document>(queryKeys.document(documentId), {
          ...previousDoc,
          title,
          updated_at: new Date().toISOString(),
        })
      }

      // Also update in list caches
      queryClient.setQueriesData<DocumentListResponse>(
        { queryKey: queryKeys.documents(scope, effectiveScopeId), exact: false },
        (old) => old ? {
          ...old,
          items: old.items.map((item) =>
            item.id === documentId ? { ...item, title } : item
          ),
        } : old
      )

      return { previousDoc, previousLists, documentId }
    },
    onSuccess: (data) => {
      // Update with server data
      queryClient.setQueryData(queryKeys.document(data.id), data)
    },
    onError: (_error, { documentId }, context) => {
      // Rollback single doc
      if (context?.previousDoc) {
        queryClient.setQueryData(queryKeys.document(documentId), context.previousDoc)
      }
      // Rollback list caches
      if (context?.previousLists) {
        context.previousLists.forEach((data, keyStr) => {
          const key = JSON.parse(keyStr) as readonly unknown[]
          if (data) {
            queryClient.setQueryData(key, data)
          }
        })
      }
    },
  })
}

/**
 * Move a document to a different folder with optimistic update.
 */
export function useMoveDocument(): UseMutationResult<Document, Error, MoveDocumentParams> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()
  const userId = useAuthStore((s) => s.user?.id ?? null)

  return useMutation({
    mutationFn: async ({ documentId, folder_id, row_version }: MoveDocumentParams) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.put<Document>(
        `/api/documents/${documentId}`,
        { folder_id, row_version },
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data))
      }

      return response.data
    },
    onMutate: async ({ documentId, folder_id, scope, scopeId }) => {
      const effectiveScopeId = scope === 'personal' ? (userId ?? '') : scopeId
      // Cancel outgoing refetches for all document list queries in this scope
      await queryClient.cancelQueries({ queryKey: queryKeys.documents(scope, effectiveScopeId) })
      await queryClient.cancelQueries({ queryKey: queryKeys.document(documentId) })

      // Snapshot previous values
      const previousDoc = queryClient.getQueryData<Document>(queryKeys.document(documentId))

      // Optimistically update the single document cache
      if (previousDoc) {
        queryClient.setQueryData<Document>(queryKeys.document(documentId), {
          ...previousDoc,
          folder_id,
          updated_at: new Date().toISOString(),
        })
      }

      // Snapshot all list caches for rollback
      const previousLists: Map<string, DocumentListResponse | undefined> = new Map()
      queryClient.getQueriesData<DocumentListResponse>({
        queryKey: queryKeys.documents(scope, effectiveScopeId),
        exact: false,
      }).forEach(([key, data]) => {
        previousLists.set(JSON.stringify(key), data)
      })

      // Find the document's list item data before removing it
      let docItem: DocumentListItem | undefined
      for (const [, data] of previousLists) {
        const found = data?.items.find(i => i.id === documentId)
        if (found) {
          docItem = found
          break
        }
      }

      // Remove document from ALL current list caches
      queryClient.setQueriesData<DocumentListResponse>(
        { queryKey: queryKeys.documents(scope, effectiveScopeId), exact: false },
        (old) => old ? {
          ...old,
          items: old.items.filter((item) => item.id !== documentId),
        } : old
      )

      // Optimistically add to the target folder's list (so it appears immediately)
      if (docItem) {
        const updatedItem: DocumentListItem = { ...docItem, folder_id }
        const targetKey = folder_id
          ? [...queryKeys.documents(scope, effectiveScopeId), folder_id, false]
          : [...queryKeys.documents(scope, effectiveScopeId), '', true]

        queryClient.setQueryData<DocumentListResponse>(targetKey, (old) => ({
          items: [updatedItem, ...(old?.items ?? [])],
          next_cursor: old?.next_cursor ?? null,
        }))
      }

      return { previousDoc, documentId, previousLists }
    },
    onSuccess: (data, { scope, scopeId }) => {
      const effectiveScopeId = scope === 'personal' ? (userId ?? '') : scopeId
      queryClient.setQueryData(queryKeys.document(data.id), data)
      // Invalidate both source and target folder caches to get accurate lists
      queryClient.invalidateQueries({
        queryKey: queryKeys.documents(scope, effectiveScopeId),
        exact: false,
      })
      // Invalidate folder tree to update document_count
      queryClient.invalidateQueries({
        queryKey: queryKeys.documentFolders(scope, effectiveScopeId),
      })
      // Update project section visibility
      queryClient.invalidateQueries({ queryKey: ['projects-with-content'] })
    },
    onError: (_error, { documentId }, context) => {
      // Rollback single doc
      if (context?.previousDoc) {
        queryClient.setQueryData(queryKeys.document(documentId), context.previousDoc)
      }
      // Rollback all list caches
      if (context?.previousLists) {
        context.previousLists.forEach((data, keyStr) => {
          const key = JSON.parse(keyStr) as readonly unknown[]
          if (data) {
            queryClient.setQueryData(key, data)
          }
        })
      }
    },
  })
}

/**
 * Soft delete a document with optimistic update.
 * Removes document from cache immediately, rollback on error.
 */
export function useDeleteDocument(): UseMutationResult<void, Error, { documentId: string; scope: string; scopeId: string }> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()
  const userId = useAuthStore((s) => s.user?.id ?? null)

  return useMutation({
    mutationFn: async ({ documentId }: { documentId: string; scope: string; scopeId: string }) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.delete<void>(
        `/api/documents/${documentId}`,
        getAuthHeaders(token)
      )

      if (response.status !== 204 && response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data))
      }
    },
    onMutate: async ({ documentId, scope, scopeId }) => {
      const effectiveScopeId = scope === 'personal' ? (userId ?? '') : scopeId
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: queryKeys.documents(scope, effectiveScopeId) })

      // Snapshot all document list caches that might contain this document
      const previousLists: Map<string, DocumentListResponse | undefined> = new Map()
      queryClient.getQueriesData<DocumentListResponse>({
        queryKey: queryKeys.documents(scope, effectiveScopeId),
        exact: false,
      }).forEach(([key, data]) => {
        previousLists.set(JSON.stringify(key), data)
      })

      // Optimistically remove from all list caches
      queryClient.setQueriesData<DocumentListResponse>(
        { queryKey: queryKeys.documents(scope, effectiveScopeId), exact: false },
        (old) => old ? {
          ...old,
          items: old.items.filter((item) => item.id !== documentId),
        } : old
      )

      // Remove from individual document cache
      queryClient.removeQueries({ queryKey: queryKeys.document(documentId) })

      return { previousLists, documentId }
    },
    onSuccess: () => {
      // Invalidate projects-with-content to update project section visibility
      queryClient.invalidateQueries({ queryKey: ['projects-with-content'] })
    },
    onError: (_error, _params, context) => {
      // Rollback all list caches
      if (context?.previousLists) {
        context.previousLists.forEach((data, keyStr) => {
          const key = JSON.parse(keyStr) as readonly unknown[]
          if (data) {
            queryClient.setQueryData(key, data)
          }
        })
      }
    },
  })
}

// ============================================================================
// Reorder Mutation
// ============================================================================

interface ReorderDocumentParams {
  documentId: string
  sortOrder: number
  folderId?: string | null
  rowVersion: number
}

/**
 * Reorder a document with optimistic update.
 * Updates sort_order in cache immediately.
 */
export function useReorderDocument(
  scope: string,
  scopeId: string
): UseMutationResult<Document, Error, ReorderDocumentParams> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()
  const userId = useAuthStore((s) => s.user?.id ?? null)

  const effectiveScopeId = scope === 'personal' ? (userId ?? '') : scopeId

  return useMutation({
    mutationFn: async ({ documentId, sortOrder, folderId, rowVersion }: ReorderDocumentParams) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const body: { sort_order: number; folder_id?: string | null; row_version: number } = {
        sort_order: sortOrder,
        row_version: rowVersion,
      }
      if (folderId !== undefined) {
        body.folder_id = folderId
      }

      const response = await window.electronAPI.put<Document>(
        `/api/documents/${documentId}`,
        body,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data))
      }

      return response.data
    },
    onMutate: async ({ documentId, sortOrder }) => {
      // Optimistically update sort_order in list caches
      queryClient.setQueriesData<DocumentListResponse>(
        { queryKey: queryKeys.documents(scope, effectiveScopeId), exact: false },
        (old) => old ? {
          ...old,
          items: old.items.map((item) =>
            item.id === documentId ? { ...item, sort_order: sortOrder } : item
          ),
        } : old
      )
    },
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.document(data.id), data)
    },
    // No rollback needed for reorder - worst case user refreshes
  })
}

// ============================================================================
// Scopes Summary Hook
// ============================================================================

export interface ApplicationWithDocs {
  id: string
  name: string
  description?: string | null
  user_role?: string | null
}

export interface ScopesSummaryResponse {
  has_personal_docs: boolean
  applications: ApplicationWithDocs[]
}

/**
 * Fetch which scopes have documents for auto-managed tab visibility.
 */
export function useApplicationsWithDocs(): UseQueryResult<ScopesSummaryResponse, Error> {
  const token = useAuthStore((s) => s.token)

  return useQuery({
    queryKey: queryKeys.scopesSummary(),
    queryFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.get<ScopesSummaryResponse>(
        '/api/documents/scopes-summary',
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data))
      }

      return response.data
    },
    staleTime: 30_000,
    enabled: !!token,
  })
}

// ============================================================================
// Projects With Content Hook
// ============================================================================

export interface ProjectPermissionItem {
  project_id: string
  can_edit: boolean
}

export interface ProjectsWithContentResponse {
  project_ids: string[]
  project_permissions: ProjectPermissionItem[]
}

/**
 * Fetch project IDs that have knowledge content (documents or folders).
 * Used to filter out empty projects in the application tree.
 */
export function useProjectsWithContent(
  applicationId: string | null
): UseQueryResult<ProjectsWithContentResponse, Error> {
  const token = useAuthStore((s) => s.token)

  return useQuery({
    queryKey: ['projects-with-content', applicationId],
    queryFn: async () => {
      if (!window.electronAPI || !applicationId) {
        throw new Error('Electron API not available or no application ID')
      }

      const response = await window.electronAPI.get<ProjectsWithContentResponse>(
        `/api/documents/projects-with-content?application_id=${applicationId}`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data))
      }

      return response.data
    },
    staleTime: 30_000,
    enabled: !!token && !!applicationId,
    // WebSocket subscriptions keep cache fresh while mounted; window focus refetch is redundant.
    refetchOnWindowFocus: false,
  })
}
