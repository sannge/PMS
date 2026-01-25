/**
 * TanStack Query Hooks for Attachments
 *
 * Provides React Query hooks for task attachment management with:
 * - Attachment list with IndexedDB persistence
 * - Download URL management (NOT persisted - presigned URLs expire)
 * - File upload mutation with progress tracking
 *
 * @see https://tanstack.com/query/latest
 */

import {
  useQuery,
  useMutation,
  useQueryClient,
  UseQueryResult,
  UseMutationResult,
} from '@tanstack/react-query'
import { useAuthStore } from '@/stores/auth-store'
import { queryKeys } from '@/lib/query-client'

// ============================================================================
// Types
// ============================================================================

export interface Attachment {
  id: string
  task_id: string
  file_name: string
  file_type: string | null
  file_size: number
  uploader_id: string
  uploader_name: string | null
  created_at: string
}

export interface DownloadUrl {
  attachment_id: string
  url: string
  expires_at: string
}

export interface UploadProgress {
  attachmentId?: string
  progress: number
  status: 'pending' | 'uploading' | 'complete' | 'error'
  error?: string
}

export interface ApiError {
  message: string
  code?: string
  field?: string
}

// ============================================================================
// Helper Functions
// ============================================================================

function getAuthHeaders(token: string | null): Record<string, string> {
  if (!token) return {}
  return { Authorization: `Bearer ${token}` }
}

function parseApiError(status: number, data: unknown): ApiError {
  if (typeof data === 'object' && data !== null) {
    const errorData = data as Record<string, unknown>
    if (typeof errorData.detail === 'string') {
      return { message: errorData.detail }
    }
  }

  switch (status) {
    case 400:
      return { message: 'Invalid request. Please check your input.' }
    case 401:
      return { message: 'Authentication required.' }
    case 403:
      return { message: 'Access denied.' }
    case 404:
      return { message: 'Attachment not found.' }
    case 413:
      return { message: 'File too large. Maximum size is 50MB.' }
    case 415:
      return { message: 'File type not allowed.' }
    case 500:
      return { message: 'Server error. Please try again later.' }
    default:
      return { message: 'An unexpected error occurred.' }
  }
}

// ============================================================================
// Attachment Queries
// ============================================================================

/**
 * Fetch attachments for a task.
 * Persisted to IndexedDB for offline access.
 */
export function useAttachments(taskId: string | undefined): UseQueryResult<Attachment[], Error> {
  const token = useAuthStore((s) => s.token)

  return useQuery({
    queryKey: queryKeys.attachments(taskId || ''),
    queryFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.get<Attachment[]>(
        `/api/tasks/${taskId}/attachments`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data || []
    },
    enabled: !!token && !!taskId,
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 24 * 60 * 60 * 1000, // 24 hours for offline
  })
}

/**
 * Get presigned download URL for an attachment.
 * NOT persisted to IndexedDB since presigned URLs expire.
 */
export function useDownloadUrl(
  attachmentId: string | undefined
): UseQueryResult<DownloadUrl, Error> {
  const token = useAuthStore((s) => s.token)

  return useQuery({
    queryKey: queryKeys.downloadUrl(attachmentId || ''),
    queryFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.get<DownloadUrl>(
        `/api/attachments/${attachmentId}/download-url`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
    enabled: !!token && !!attachmentId,
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 15 * 60 * 1000, // 15 minutes only - URLs expire
    // Don't persist to IndexedDB (handled by query-client filter)
  })
}

/**
 * Get presigned download URLs for multiple attachments.
 * Useful for bulk downloads or previews.
 */
export function useDownloadUrls(
  attachmentIds: string[]
): UseQueryResult<DownloadUrl[], Error> {
  const token = useAuthStore((s) => s.token)
  const sortedIds = [...attachmentIds].sort()

  return useQuery({
    queryKey: queryKeys.downloadUrls(sortedIds),
    queryFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.post<DownloadUrl[]>(
        '/api/attachments/download-urls',
        { attachment_ids: sortedIds },
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data || []
    },
    enabled: !!token && sortedIds.length > 0,
    staleTime: 5 * 60 * 1000,
    gcTime: 15 * 60 * 1000, // Short GC time - URLs expire
  })
}

// ============================================================================
// Attachment Mutations
// ============================================================================

interface UploadAttachmentPayload {
  taskId: string
  file: File
  onProgress?: (progress: number) => void
}

/**
 * Upload an attachment to a task.
 * Uses FormData for file upload.
 */
export function useUploadAttachment(): UseMutationResult<Attachment, Error, UploadAttachmentPayload> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ taskId, file, onProgress }: UploadAttachmentPayload) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      // Create FormData for file upload
      const formData = new FormData()
      formData.append('file', file)

      // Note: Progress tracking would require native implementation
      // For now, we'll use a simple upload without progress
      const response = await window.electronAPI.uploadFile<Attachment>(
        `/api/tasks/${taskId}/attachments`,
        formData,
        getAuthHeaders(token),
        onProgress
      )

      if (response.status !== 201) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
    onSuccess: (newAttachment, { taskId }) => {
      // Add to attachments list
      queryClient.setQueryData<Attachment[]>(queryKeys.attachments(taskId), (old) =>
        old ? [...old, newAttachment] : [newAttachment]
      )
    },
  })
}

/**
 * Delete an attachment.
 */
export function useDeleteAttachment(
  attachmentId: string,
  taskId: string
): UseMutationResult<void, Error, void, { previous?: Attachment[] }> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.delete<void>(
        `/api/attachments/${attachmentId}`,
        getAuthHeaders(token)
      )

      if (response.status !== 204 && response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }
    },
    // Optimistic delete
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: queryKeys.attachments(taskId) })

      const previous = queryClient.getQueryData<Attachment[]>(queryKeys.attachments(taskId))

      queryClient.setQueryData<Attachment[]>(queryKeys.attachments(taskId), (old) =>
        old?.filter((a) => a.id !== attachmentId)
      )

      return { previous }
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.attachments(taskId), context.previous)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.attachments(taskId) })
      // Also remove download URL cache
      queryClient.removeQueries({ queryKey: queryKeys.downloadUrl(attachmentId) })
    },
  })
}

// ============================================================================
// Utility Hooks
// ============================================================================

/**
 * Helper hook to get attachment download URL and trigger download.
 */
export function useDownloadAttachment(): UseMutationResult<void, Error, Attachment> {
  const token = useAuthStore((s) => s.token)

  return useMutation({
    mutationFn: async (attachment: Attachment) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      // Get presigned URL
      const response = await window.electronAPI.get<DownloadUrl>(
        `/api/attachments/${attachment.id}/download-url`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      // Trigger download via Electron
      await window.electronAPI.downloadFile(response.data.url, attachment.file_name)
    },
  })
}
