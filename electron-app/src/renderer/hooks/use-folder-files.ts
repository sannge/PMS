/**
 * TanStack Query Hooks for Folder Files
 *
 * Provides React Query hooks for file upload/download/rename/delete/replace
 * operations on files attached to document folders.
 *
 * @see fastapi-backend/app/routers/folder_files.py
 */

import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryResult,
  type UseMutationResult,
} from '@tanstack/react-query'
import { useAuthToken } from '@/contexts/auth-context'
import { authGet, authPost, authPut, authDelete, getAccessToken, API_BASE, parseApiError } from '@/lib/api-client'
import { queryKeys } from '@/lib/query-client'
import { toast } from 'sonner'

// ============================================================================
// Types
// ============================================================================

export interface FolderFileListItem {
  id: string
  display_name: string
  original_name: string
  file_extension: string
  mime_type: string
  file_size: number
  extraction_status: 'pending' | 'processing' | 'completed' | 'failed' | 'unsupported'
  embedding_status: 'none' | 'stale' | 'syncing' | 'synced' | 'failed'
  sort_order: number
  folder_id: string | null
  created_by: string | null
  created_at: string
  updated_at: string
  row_version: number
}

interface FolderFilesResponse {
  items: FolderFileListItem[]
}

interface UploadFileParams {
  file: File
  folderId?: string | null
  scope?: string
  scopeId?: string
  displayName?: string
}

interface RenameFileParams {
  fileId: string
  displayName: string
  folderId: string
  rowVersion: number
  /** Scope info for unfiled files (folderId='') */
  scope?: string
  scopeId?: string
}

interface DeleteFileParams {
  fileId: string
  folderId: string
  /** Scope info for unfiled files (folderId='') */
  scope?: string
  scopeId?: string
}

interface MoveFileParams {
  fileId: string
  targetFolderId: string | null
  rowVersion: number
  sourceFolderId: string | null
  /** Scope info for cache invalidation */
  scope?: string
  scopeId?: string
}

interface ReplaceFileParams {
  fileId: string
  file: File
  folderId: string
  /** Scope info for unfiled files (folderId='') */
  scope?: string
  scopeId?: string
}

// ============================================================================
// Custom Error Type
// ============================================================================

/** Extended Error that carries HTTP status and conflict metadata from the backend. */
export interface UploadConflictError extends Error {
  status?: number
  existingFileId?: string
}

// ============================================================================
// Response Normalization
// ============================================================================

/**
 * Normalize folder-files API response to ensure consistent { items: [] } shape.
 * Backend may return a flat array or an object with items property.
 */
function normalizeFolderFilesResponse(
  data: FolderFileListItem[] | FolderFilesResponse
): FolderFilesResponse {
  const items = Array.isArray(data)
    ? data
    : ((data as FolderFilesResponse).items || [])
  return { items }
}

// ============================================================================
// Query Hooks
// ============================================================================

/**
 * Fetch files for a folder.
 */
export function useFolderFiles(
  folderId: string | null
): UseQueryResult<FolderFilesResponse, Error> {
  const token = useAuthToken()

  return useQuery({
    queryKey: queryKeys.folderFiles(folderId ?? ''),
    queryFn: async () => {
      if (!folderId) throw new Error('folderId required')

      const params = new URLSearchParams()
      params.set('folder_id', folderId)

      const response = await authGet<FolderFileListItem[] | FolderFilesResponse>(
        `/api/folder-files?${params.toString()}`
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data, 'File'))
      }

      return normalizeFolderFilesResponse(response.data)
    },
    enabled: !!token && !!folderId,
    staleTime: 30 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
    refetchOnWindowFocus: false,
    refetchOnMount: 'always',
  })
}

/**
 * Fetch unfiled files at a scope root (folder_id IS NULL).
 *
 * Used by KnowledgeTree to render files uploaded directly to an
 * application/project/personal scope without a folder.
 */
export function useUnfiledFiles(
  scope: string | null,
  scopeId: string | null
): UseQueryResult<FolderFilesResponse, Error> {
  const token = useAuthToken()

  return useQuery({
    queryKey: queryKeys.unfiledFiles(scope ?? '', scopeId ?? ''),
    queryFn: async () => {
      if (!scope || !scopeId) throw new Error('scope and scopeId required')

      const params = new URLSearchParams()
      params.set('scope', scope)
      params.set('scope_id', scopeId)

      const response = await authGet<FolderFileListItem[] | FolderFilesResponse>(
        `/api/folder-files?${params.toString()}`
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data, 'File'))
      }

      return normalizeFolderFilesResponse(response.data)
    },
    enabled: !!token && !!scope && !!scopeId,
    staleTime: 30 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
    refetchOnWindowFocus: false,
    refetchOnMount: 'always',
  })
}

// ============================================================================
// Mutation Hooks
// ============================================================================

/**
 * Upload a file to a folder.
 *
 * Sends the file as multipart/form-data to POST /api/folder-files/upload.
 * On success, invalidates the folderFiles query and shows a toast.
 *
 * On 409, attaches `status` and `existingFileId` to the thrown error
 * so callers can show the conflict dialog with the Replace option.
 */
export function useUploadFile(): UseMutationResult<
  FolderFileListItem,
  UploadConflictError,
  UploadFileParams
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ file, folderId, scope, scopeId, displayName }: UploadFileParams) => {
      const params = new URLSearchParams()
      if (folderId) params.set('folder_id', folderId)
      if (scope) params.set('scope', scope)
      if (scopeId) params.set('scope_id', scopeId)
      if (displayName) params.set('display_name', displayName)

      const formData = new FormData()
      formData.append('file', file)

      const accessToken = getAccessToken()
      const qs = params.toString()
      const response = await fetch(`${API_BASE}/api/folder-files/upload${qs ? `?${qs}` : ''}`, {
        method: 'POST',
        headers: {
          ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        },
        body: formData,
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        const error: UploadConflictError = new Error(
          parseApiError(response.status, errorData, 'File')
        )
        // Attach status code for conflict detection
        error.status = response.status
        // Extract existing_file_id from 409 response for Replace action
        // Backend returns 409 with body: {"detail": {"message": "...", "existing_file_id": "uuid"}}
        // so we check both top-level and nested under detail.
        if (response.status === 409 && typeof errorData === 'object' && errorData !== null) {
          const raw = errorData as Record<string, unknown>
          const detail = typeof raw.detail === 'object' && raw.detail !== null
            ? (raw.detail as Record<string, unknown>)
            : raw
          if (typeof detail.existing_file_id === 'string') {
            error.existingFileId = detail.existing_file_id as string
          }
        }
        throw error
      }

      return (await response.json()) as FolderFileListItem
    },
    onSuccess: (_data, { folderId, scope, scopeId }) => {
      if (folderId) {
        queryClient.invalidateQueries({ queryKey: queryKeys.folderFiles(folderId) })
      }
      // Invalidate unfiled files + scope-level queries only when uploading without a folder
      if (!folderId && scope && scopeId) {
        queryClient.invalidateQueries({ queryKey: queryKeys.unfiledFiles(scope, scopeId) })
        queryClient.invalidateQueries({ queryKey: ['documents', scope, scopeId] })
      }
    },
  })
}

/**
 * Rename a file with optimistic update.
 *
 * Sends row_version alongside display_name for optimistic concurrency.
 */
export function useRenameFile(): UseMutationResult<
  FolderFileListItem,
  Error,
  RenameFileParams
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ fileId, displayName, rowVersion }: RenameFileParams) => {
      const response = await authPut<FolderFileListItem>(
        `/api/folder-files/${fileId}`,
        { display_name: displayName, row_version: rowVersion }
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data, 'File'))
      }

      return response.data
    },
    onMutate: async ({ fileId, displayName, folderId, scope, scopeId }) => {
      const cacheKey = folderId
        ? queryKeys.folderFiles(folderId)
        : queryKeys.unfiledFiles(scope ?? '', scopeId ?? '')
      await queryClient.cancelQueries({ queryKey: cacheKey })

      const previous = queryClient.getQueryData<FolderFilesResponse>(cacheKey)

      queryClient.setQueryData<FolderFilesResponse>(
        cacheKey,
        (old) => {
          if (!old) return old
          return {
            ...old,
            items: old.items.map((item) =>
              item.id === fileId
                ? { ...item, display_name: displayName, updated_at: new Date().toISOString(), row_version: item.row_version + 1 }
                : item
            ),
          }
        }
      )

      return { previous, cacheKey }
    },
    onError: (_error, _params, context) => {
      if (context?.previous && context.cacheKey) {
        queryClient.setQueryData(context.cacheKey, context.previous)
      }
    },
    onSettled: (_data, _error, { fileId, folderId, scope, scopeId }) => {
      if (folderId) {
        queryClient.invalidateQueries({ queryKey: queryKeys.folderFiles(folderId) })
      } else if (scope && scopeId) {
        queryClient.invalidateQueries({ queryKey: queryKeys.unfiledFiles(scope, scopeId) })
      }
      // Invalidate detail cache so viewer picks up the new name
      queryClient.invalidateQueries({ queryKey: queryKeys.folderFile(fileId) })
    },
  })
}

/**
 * Delete a file with optimistic removal from cache.
 *
 * Added onSettled invalidation to ensure cache consistency
 * even when the mutation errors after the optimistic update.
 */
export function useDeleteFile(): UseMutationResult<void, Error, DeleteFileParams> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ fileId }: DeleteFileParams) => {
      const response = await authDelete<void>(`/api/folder-files/${fileId}`)

      if (response.status !== 204 && response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data, 'File'))
      }
    },
    onMutate: async ({ fileId, folderId, scope, scopeId }) => {
      const cacheKey = folderId
        ? queryKeys.folderFiles(folderId)
        : queryKeys.unfiledFiles(scope ?? '', scopeId ?? '')
      await queryClient.cancelQueries({ queryKey: cacheKey })

      const previous = queryClient.getQueryData<FolderFilesResponse>(cacheKey)

      queryClient.setQueryData<FolderFilesResponse>(
        cacheKey,
        (old) => {
          if (!old) return old
          return {
            ...old,
            items: old.items.filter((item) => item.id !== fileId),
          }
        }
      )

      return { previous, cacheKey }
    },
    onSuccess: () => {
      toast.success('File deleted')
    },
    onError: (_error, _params, context) => {
      if (context?.previous && context.cacheKey) {
        queryClient.setQueryData(context.cacheKey, context.previous)
      }
    },
    onSettled: (_data, _error, { fileId, folderId, scope, scopeId }) => {
      if (folderId) {
        queryClient.invalidateQueries({ queryKey: queryKeys.folderFiles(folderId) })
      } else if (scope && scopeId) {
        queryClient.invalidateQueries({ queryKey: queryKeys.unfiledFiles(scope, scopeId) })
      }
      // Remove stale detail + download URL caches for deleted file
      queryClient.removeQueries({ queryKey: queryKeys.folderFile(fileId) })
      queryClient.removeQueries({ queryKey: queryKeys.folderFileDownloadUrl(fileId) })
    },
  })
}

/**
 * Replace a file with a new version.
 *
 * Sends the new file as multipart/form-data to POST /api/folder-files/{fileId}/replace.
 */
export function useReplaceFile(): UseMutationResult<
  FolderFileListItem,
  Error,
  ReplaceFileParams
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ fileId, file }: ReplaceFileParams) => {
      const formData = new FormData()
      formData.append('file', file)

      const accessToken = getAccessToken()
      const response = await fetch(`${API_BASE}/api/folder-files/${fileId}/replace`, {
        method: 'POST',
        headers: {
          ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        },
        body: formData,
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(parseApiError(response.status, errorData, 'File'))
      }

      return (await response.json()) as FolderFileListItem
    },
    onSettled: (_data, _error, { fileId, folderId, scope, scopeId }) => {
      if (folderId) {
        queryClient.invalidateQueries({ queryKey: queryKeys.folderFiles(folderId) })
      } else if (scope && scopeId) {
        queryClient.invalidateQueries({ queryKey: queryKeys.unfiledFiles(scope, scopeId) })
      }
      // Always invalidate detail + download URL (file content changed)
      queryClient.invalidateQueries({ queryKey: queryKeys.folderFile(fileId) })
      queryClient.invalidateQueries({ queryKey: queryKeys.folderFileDownloadUrl(fileId) })
      if (!_error) {
        toast.success('File replaced')
      } else {
        toast.error('Failed to replace file')
      }
    },
  })
}

/**
 * Move a file to a different folder (or to root).
 *
 * Calls PUT /api/folder-files/{id} with folder_id and row_version.
 * Invalidates both source and target folder file caches.
 */
export function useMoveFile(): UseMutationResult<
  FolderFileListItem,
  Error,
  MoveFileParams
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ fileId, targetFolderId, rowVersion }: MoveFileParams) => {
      const response = await authPut<FolderFileListItem>(
        `/api/folder-files/${fileId}`,
        { folder_id: targetFolderId, row_version: rowVersion }
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data, 'File'))
      }

      return response.data
    },
    onMutate: async ({ fileId, sourceFolderId, targetFolderId, scope, scopeId }) => {
      // Cancel outgoing refetches so they don't overwrite our optimistic update
      const sourceKey = sourceFolderId
        ? queryKeys.folderFiles(sourceFolderId)
        : scope && scopeId ? queryKeys.unfiledFiles(scope, scopeId) : null
      const targetKey = targetFolderId
        ? queryKeys.folderFiles(targetFolderId)
        : scope && scopeId ? queryKeys.unfiledFiles(scope, scopeId) : null

      const isSameList = sourceFolderId === targetFolderId
      if (sourceKey) await queryClient.cancelQueries({ queryKey: sourceKey })
      if (targetKey && !isSameList) await queryClient.cancelQueries({ queryKey: targetKey })
      await queryClient.cancelQueries({ queryKey: queryKeys.folderFile(fileId) })

      // Snapshot previous values for rollback
      const previousSource = sourceKey ? queryClient.getQueryData<FolderFilesResponse>(sourceKey) : undefined
      const previousTarget = targetKey ? queryClient.getQueryData<FolderFilesResponse>(targetKey) : undefined
      const previousDetail = queryClient.getQueryData<FolderFileListItem>(queryKeys.folderFile(fileId))

      // Optimistically remove file from source cache
      let movedFile: FolderFileListItem | undefined
      if (sourceKey && previousSource) {
        movedFile = previousSource.items?.find((f) => f.id === fileId)
        queryClient.setQueryData<FolderFilesResponse>(sourceKey, (old) => {
          if (!old?.items) return old
          return { ...old, items: old.items.filter((f) => f.id !== fileId) }
        })
      }

      // Optimistically add file to target cache
      if (targetKey && !isSameList && movedFile) {
        const updatedFile = { ...movedFile, folder_id: targetFolderId, row_version: movedFile.row_version + 1 }
        queryClient.setQueryData<FolderFilesResponse>(targetKey, (old) => {
          if (!old) return { items: [updatedFile] }
          return { ...old, items: [...old.items, updatedFile] }
        })
      }

      // Optimistically update single file detail cache (like useMoveDocument)
      if (previousDetail) {
        queryClient.setQueryData<FolderFileListItem>(queryKeys.folderFile(fileId), {
          ...previousDetail,
          folder_id: targetFolderId,
          row_version: previousDetail.row_version + 1,
        })
      }

      return { previousSource, previousTarget, previousDetail, sourceKey, targetKey }
    },
    onError: (_error, { fileId }, context) => {
      // Rollback all caches on failure
      if (context?.sourceKey && context.previousSource) {
        queryClient.setQueryData(context.sourceKey, context.previousSource)
      }
      if (context?.targetKey && context.previousTarget) {
        queryClient.setQueryData(context.targetKey, context.previousTarget)
      }
      if (context?.previousDetail) {
        queryClient.setQueryData(queryKeys.folderFile(fileId), context.previousDetail)
      }
    },
    onSettled: (_data, _error, { fileId, sourceFolderId, targetFolderId, scope, scopeId }) => {
      // Always refetch to ensure server state consistency
      if (sourceFolderId) {
        queryClient.invalidateQueries({ queryKey: queryKeys.folderFiles(sourceFolderId) })
      } else if (scope && scopeId) {
        queryClient.invalidateQueries({ queryKey: queryKeys.unfiledFiles(scope, scopeId) })
      }
      if (targetFolderId) {
        queryClient.invalidateQueries({ queryKey: queryKeys.folderFiles(targetFolderId) })
      } else if (scope && scopeId) {
        queryClient.invalidateQueries({ queryKey: queryKeys.unfiledFiles(scope, scopeId) })
      }
      // Invalidate file detail and folder tree (for file counts)
      queryClient.invalidateQueries({ queryKey: queryKeys.folderFile(fileId) })
      if (scope && scopeId) {
        queryClient.invalidateQueries({ queryKey: queryKeys.documentFolders(scope, scopeId) })
      }
    },
  })
}

/**
 * Fetch a single file's details.
 */
export function useFileDetail(
  fileId: string | null
): UseQueryResult<FolderFileListItem, Error> {
  const token = useAuthToken()

  return useQuery({
    queryKey: queryKeys.folderFile(fileId ?? ''),
    queryFn: async () => {
      const response = await authGet<FolderFileListItem>(
        `/api/folder-files/${fileId}`
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data, 'File'))
      }

      return response.data
    },
    enabled: !!token && !!fileId,
    staleTime: 30 * 1000,
    refetchOnWindowFocus: false,
    refetchOnMount: 'always',
  })
}

/**
 * Get a download URL for a file.
 *
 * Reads `download_url` from response (not `url`).
 * Uses dedicated `folderFileDownloadUrl` query key.
 * gcTime set to 5 minutes to match presigned URL lifetime.
 */
export function useFileDownloadUrl(
  fileId: string | null
): UseQueryResult<string, Error> {
  const token = useAuthToken()

  return useQuery({
    queryKey: queryKeys.folderFileDownloadUrl(fileId ?? ''),
    queryFn: async () => {
      const response = await authGet<{ download_url: string }>(
        `/api/folder-files/${fileId}/download`
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data, 'File'))
      }

      return response.data.download_url
    },
    enabled: !!token && !!fileId,
    staleTime: 4 * 60 * 1000, // Slightly under 5m to refetch before expiry
    gcTime: 5 * 60 * 1000,
    refetchOnWindowFocus: false,
  })
}

/**
 * Imperatively fetch a download URL for a file (not a hook).
 *
 * Used by knowledge-tree.tsx to download files on click without
 * needing to persist a query subscription.
 */
export async function fetchFileDownloadUrl(fileId: string): Promise<string> {
  const response = await authGet<{ download_url: string }>(
    `/api/folder-files/${fileId}/download`
  )

  if (response.status !== 200) {
    throw new Error(parseApiError(response.status, response.data, 'File'))
  }

  return response.data.download_url
}

/**
 * Sync embeddings for a single file via POST /api/folder-files/{id}/sync-embeddings.
 * Mirrors useSyncDocumentEmbeddings but for folder files.
 */
export function useSyncFileEmbeddings(): UseMutationResult<
  { status: string; file_id: string },
  Error,
  string
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (fileId: string) => {
      const response = await authPost<{ status: string; file_id: string }>(
        `/api/folder-files/${fileId}/sync-embeddings`,
        undefined
      )

      if (response.status !== 202 && response.status !== 200) {
        const errorData = response.data as { detail?: string } | undefined
        throw new Error(errorData?.detail || `Sync failed (${response.status})`)
      }

      return response.data
    },
    onSuccess: (_data, fileId) => {
      // Mark syncing in folder file list caches so tree dots update
      queryClient.setQueriesData<FolderFilesResponse>(
        { queryKey: ['folderFiles'] },
        (old) => {
          if (!old?.items) return old
          const idx = old.items.findIndex((f) => f.id === fileId)
          if (idx === -1) return old
          const updated = [...old.items]
          updated[idx] = { ...updated[idx], embedding_status: 'syncing' }
          return { ...old, items: updated }
        }
      )
      // Also update singular detail cache to eliminate flicker
      queryClient.setQueryData<FolderFileListItem>(
        queryKeys.folderFile(fileId),
        (old) => old ? { ...old, embedding_status: 'syncing' } : old
      )
      // WS broadcast from the worker will handle invalidation when embedding completes
    },
  })
}
