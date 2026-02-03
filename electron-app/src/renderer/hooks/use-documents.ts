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
}

interface MoveDocumentParams {
  documentId: string
  folder_id: string | null
  row_version: number
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

  return useQuery({
    queryKey: [
      ...queryKeys.documents(scope, scopeId ?? ''),
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
    staleTime: 30 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
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
// Mutation Hooks
// ============================================================================

/**
 * Create a new document.
 */
export function useCreateDocument(): UseMutationResult<Document, Error, CreateDocumentParams> {
  const token = useAuthStore((s) => s.token)
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
    onSuccess: (_data, params) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.documents(params.scope, params.scope_id),
      })
      // Also invalidate folder tree since document_count changes
      queryClient.invalidateQueries({
        queryKey: queryKeys.documentFolders(params.scope, params.scope_id),
      })
      // Invalidate scopes summary so tab visibility updates
      queryClient.invalidateQueries({
        queryKey: queryKeys.scopesSummary(),
      })
    },
  })
}

/**
 * Rename a document (update title).
 */
export function useRenameDocument(
  scope: string,
  scopeId: string
): UseMutationResult<Document, Error, RenameDocumentParams> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

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
    onSuccess: (updatedDoc) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.documents(scope, scopeId),
      })
      queryClient.setQueryData(queryKeys.document(updatedDoc.id), updatedDoc)
    },
  })
}

/**
 * Move a document to a different folder.
 */
export function useMoveDocument(
  scope: string,
  scopeId: string
): UseMutationResult<Document, Error, MoveDocumentParams> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

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
    onSuccess: (updatedDoc) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.documents(scope, scopeId),
      })
      queryClient.invalidateQueries({
        queryKey: queryKeys.documentFolders(scope, scopeId),
      })
      queryClient.setQueryData(queryKeys.document(updatedDoc.id), updatedDoc)
    },
  })
}

/**
 * Soft delete a document (move to trash).
 */
export function useDeleteDocument(
  scope: string,
  scopeId: string
): UseMutationResult<void, Error, string> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (documentId: string) => {
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
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.documents(scope, scopeId),
      })
      queryClient.invalidateQueries({
        queryKey: queryKeys.documentFolders(scope, scopeId),
      })
      // Invalidate scopes summary so tab visibility updates
      queryClient.invalidateQueries({
        queryKey: queryKeys.scopesSummary(),
      })
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
 * Reorder a document by updating its sort_order.
 * Uses the existing PUT endpoint with sort_order field.
 */
export function useReorderDocument(
  scope: string,
  scopeId: string
): UseMutationResult<Document, Error, ReorderDocumentParams> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

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
    onSuccess: (updatedDoc) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.documents(scope, scopeId),
      })
      queryClient.invalidateQueries({
        queryKey: queryKeys.documentFolders(scope, scopeId),
      })
      queryClient.setQueryData(queryKeys.document(updatedDoc.id), updatedDoc)
    },
  })
}

// ============================================================================
// Scopes Summary Hook
// ============================================================================

export interface ApplicationWithDocs {
  id: string
  name: string
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
