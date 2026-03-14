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
import { authGet, authPut, authDelete, getAccessToken, API_BASE, parseApiError } from '@/lib/api-client'
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
  folder_id: string
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
  folderId: string
  displayName?: string
}

interface RenameFileParams {
  fileId: string
  displayName: string
  folderId: string
  rowVersion: number
}

interface DeleteFileParams {
  fileId: string
  folderId: string
}

interface ReplaceFileParams {
  fileId: string
  file: File
  folderId: string
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

      // CRIT-1: Handle both { items: [...] } and flat array shapes
      const items = Array.isArray(response.data)
        ? response.data
        : ((response.data as FolderFilesResponse).items || [])

      return { items }
    },
    enabled: !!token && !!folderId,
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
    mutationFn: async ({ file, folderId, displayName }: UploadFileParams) => {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('folder_id', folderId)
      if (displayName) {
        formData.append('display_name', displayName)
      }

      const accessToken = getAccessToken()
      const response = await fetch(`${API_BASE}/api/folder-files/upload`, {
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
        // CRIT-5: Extract existing_file_id from 409 response for Replace action
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
    onSuccess: (_data, { folderId }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.folderFiles(folderId) })
      toast.success('File uploaded')
    },
  })
}

/**
 * Rename a file with optimistic update.
 *
 * CRIT-2: Sends row_version alongside display_name for optimistic concurrency.
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
    onMutate: async ({ fileId, displayName, folderId }) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.folderFiles(folderId) })

      const previous = queryClient.getQueryData<FolderFilesResponse>(
        queryKeys.folderFiles(folderId)
      )

      queryClient.setQueryData<FolderFilesResponse>(
        queryKeys.folderFiles(folderId),
        (old) => {
          if (!old) return old
          return {
            ...old,
            items: old.items.map((item) =>
              item.id === fileId
                ? { ...item, display_name: displayName, updated_at: new Date().toISOString() }
                : item
            ),
          }
        }
      )

      return { previous, folderId }
    },
    onError: (_error, _params, context) => {
      if (context?.previous) {
        queryClient.setQueryData(
          queryKeys.folderFiles(context.folderId),
          context.previous
        )
      }
    },
    onSettled: (_data, _error, { folderId }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.folderFiles(folderId) })
    },
  })
}

/**
 * Delete a file with optimistic removal from cache.
 *
 * MED-1: Added onSettled invalidation to ensure cache consistency
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
    onMutate: async ({ fileId, folderId }) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.folderFiles(folderId) })

      const previous = queryClient.getQueryData<FolderFilesResponse>(
        queryKeys.folderFiles(folderId)
      )

      queryClient.setQueryData<FolderFilesResponse>(
        queryKeys.folderFiles(folderId),
        (old) => {
          if (!old) return old
          return {
            ...old,
            items: old.items.filter((item) => item.id !== fileId),
          }
        }
      )

      return { previous, folderId }
    },
    onSuccess: () => {
      toast.success('File deleted')
    },
    onError: (_error, _params, context) => {
      if (context?.previous) {
        queryClient.setQueryData(
          queryKeys.folderFiles(context.folderId),
          context.previous
        )
      }
    },
    onSettled: (_data, _error, { folderId }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.folderFiles(folderId) })
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
    onSuccess: (_data, { folderId }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.folderFiles(folderId) })
      toast.success('File replaced')
    },
    onSettled: (_data, _error, { folderId }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.folderFiles(folderId) })
    },
  })
}

/**
 * Get a download URL for a file.
 *
 * CRIT-3: Reads `download_url` from response (not `url`).
 * MED-2: Uses dedicated `folderFileDownloadUrl` query key.
 * LOW-4: gcTime set to 5 minutes to match presigned URL lifetime.
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
