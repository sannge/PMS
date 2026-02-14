/**
 * TanStack Query Hooks for Attachments
 *
 * Provides React Query hooks for file attachment management with:
 * - Entity-based attachments (task, note, comment)
 * - Attachment list with IndexedDB persistence
 * - Download URL management (NOT persisted - presigned URLs expire)
 * - File upload mutation with progress tracking
 * - Optimistic updates for delete operations
 *
 * @see https://tanstack.com/query/latest
 */

import { useState, useCallback } from 'react'
import {
  useQuery,
  useMutation,
  useQueryClient,
  UseQueryResult,
  UseMutationResult,
} from '@tanstack/react-query'
import { useAuthStore } from '@/contexts/auth-context'
import { queryKeys } from '@/lib/query-client'

// ============================================================================
// Types
// ============================================================================

export type EntityType = 'task' | 'comment' | 'document'

export interface Attachment {
  id: string
  file_name: string
  file_type: string | null
  file_size: number | null
  minio_bucket?: string | null
  minio_key?: string | null
  entity_type?: string | null
  entity_id?: string | null
  task_id?: string | null
  note_id?: string | null
  uploaded_by?: string | null
  uploader_id?: string
  uploader_name?: string | null
  created_at: string
}

export interface DownloadUrl {
  attachment_id?: string
  id?: string
  url: string
  download_url?: string
  expires_at?: string
}

export interface UploadProgress {
  fileId: string
  fileName: string
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
      return { message: 'File too large. Maximum size is 100MB.' }
    case 415:
      return { message: 'File type not allowed.' }
    case 500:
      return { message: 'Server error. Please try again later.' }
    default:
      return { message: 'An unexpected error occurred.' }
  }
}

function getEntityQueryKey(entityType: EntityType, entityId: string): readonly string[] {
  return ['attachments', entityType, entityId] as const
}

// ============================================================================
// Attachment Queries
// ============================================================================

/**
 * Fetch attachments for a task (legacy API - /api/tasks/:id/attachments).
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
    staleTime: 30 * 1000, // 30 seconds - attachments can change when comments are deleted
    gcTime: 24 * 60 * 60 * 1000, // 24 hours for offline
  })
}

/**
 * Fetch attachments for any entity type (task, note, comment).
 * Uses the generic /api/files/entity/:type/:id endpoint.
 */
export function useEntityAttachments(
  entityType: EntityType | undefined,
  entityId: string | undefined
): UseQueryResult<Attachment[], Error> {
  const token = useAuthStore((s) => s.token)

  return useQuery({
    queryKey: entityType && entityId ? getEntityQueryKey(entityType, entityId) : ['attachments', 'none'],
    queryFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.get<Attachment[]>(
        `/api/files/entity/${entityType}/${entityId}`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data || []
    },
    enabled: !!token && !!entityType && !!entityId,
    staleTime: 30 * 1000, // 30 seconds - consistent with useAttachments
    gcTime: 24 * 60 * 60 * 1000, // 24 hours for offline
  })
}

/**
 * Get presigned download URL for an attachment.
 * NOT persisted to IndexedDB since presigned URLs expire.
 */
export function useDownloadUrl(
  attachmentId: string | undefined
): UseQueryResult<string | null, Error> {
  const token = useAuthStore((s) => s.token)

  return useQuery({
    queryKey: queryKeys.downloadUrl(attachmentId || ''),
    queryFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.get<{ download_url: string }>(
        `/api/files/${attachmentId}/download-url`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data?.download_url || null
    },
    enabled: !!token && !!attachmentId,
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 15 * 60 * 1000, // 15 minutes only - URLs expire
  })
}

/**
 * Get presigned download URLs for multiple attachments.
 * Returns a map of attachment ID to URL.
 */
export function useDownloadUrls(
  attachmentIds: string[]
): UseQueryResult<Record<string, string>, Error> {
  const token = useAuthStore((s) => s.token)
  const sortedIds = [...attachmentIds].sort()

  return useQuery({
    queryKey: queryKeys.downloadUrls(sortedIds),
    queryFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.post<Record<string, string>>(
        '/api/files/download-urls',
        { ids: sortedIds },
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data || {}
    },
    enabled: !!token && sortedIds.length > 0,
    staleTime: 5 * 60 * 1000,
    gcTime: 15 * 60 * 1000, // Short GC time - URLs expire
  })
}

// ============================================================================
// Upload Progress Hook
// ============================================================================

/**
 * Hook for managing upload progress state.
 * Use this alongside useUploadFile for progress tracking.
 */
export function useUploadProgress() {
  const [uploads, setUploads] = useState<UploadProgress[]>([])

  const addUpload = useCallback((fileId: string, fileName: string) => {
    setUploads((prev) => [
      ...prev,
      { fileId, fileName, progress: 0, status: 'pending' },
    ])
  }, [])

  const updateProgress = useCallback((fileId: string, progress: number) => {
    setUploads((prev) =>
      prev.map((u) =>
        u.fileId === fileId ? { ...u, progress, status: 'uploading' } : u
      )
    )
  }, [])

  const completeUpload = useCallback((fileId: string) => {
    setUploads((prev) =>
      prev.map((u) =>
        u.fileId === fileId ? { ...u, progress: 100, status: 'complete' } : u
      )
    )
    // Auto-remove after 1 second
    setTimeout(() => {
      setUploads((prev) => prev.filter((u) => u.fileId !== fileId))
    }, 1000)
  }, [])

  const failUpload = useCallback((fileId: string, error: string) => {
    setUploads((prev) =>
      prev.map((u) =>
        u.fileId === fileId ? { ...u, status: 'error', error } : u
      )
    )
  }, [])

  const removeUpload = useCallback((fileId: string) => {
    setUploads((prev) => prev.filter((u) => u.fileId !== fileId))
  }, [])

  const clearUploads = useCallback(() => {
    setUploads((prev) => prev.filter((u) => u.status === 'uploading' || u.status === 'pending'))
  }, [])

  return {
    uploads,
    addUpload,
    updateProgress,
    completeUpload,
    failUpload,
    removeUpload,
    clearUploads,
  }
}

// ============================================================================
// Attachment Mutations
// ============================================================================

interface UploadFilePayload {
  file: File
  entityType?: EntityType
  entityId?: string
  taskId?: string // Legacy support
  onProgress?: (progress: number) => void
}

/**
 * Upload a file attachment.
 * Supports both legacy task-specific and generic entity uploads.
 */
export function useUploadFile(): UseMutationResult<Attachment, Error, UploadFilePayload> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ file, entityType, entityId, taskId, onProgress }: UploadFilePayload) => {
      // Build query params for entity association
      const params = new URLSearchParams()
      if (taskId) {
        params.append('task_id', taskId)
      } else if (entityType === 'task' && entityId) {
        params.append('task_id', entityId)
      } else if (entityType && entityId) {
        params.append('entity_type', entityType)
        params.append('entity_id', entityId)
      }
      const queryString = params.toString() ? `?${params.toString()}` : ''

      // Create FormData
      const formData = new FormData()
      formData.append('file', file)

      // Use fetch directly for multipart/form-data
      const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8001'

      // Simulate progress updates
      onProgress?.(10)

      const response = await fetch(`${apiUrl}/api/files/upload${queryString}`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: formData,
      })

      onProgress?.(80)

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || 'Failed to upload file')
      }

      const attachment = (await response.json()) as Attachment
      onProgress?.(100)

      return attachment
    },
    onSuccess: (_newAttachment, { entityType, entityId, taskId }) => {
      // Invalidate relevant queries
      if (taskId) {
        queryClient.invalidateQueries({ queryKey: queryKeys.attachments(taskId) })
      }
      if (entityType && entityId) {
        queryClient.invalidateQueries({ queryKey: getEntityQueryKey(entityType, entityId) })
      }
      // Also invalidate task attachments if entity is a task
      if (entityType === 'task' && entityId) {
        queryClient.invalidateQueries({ queryKey: queryKeys.attachments(entityId) })
      }
    },
  })
}

/**
 * Legacy upload hook for task attachments.
 */
export function useUploadAttachment(): UseMutationResult<
  Attachment,
  Error,
  { taskId: string; file: File; onProgress?: (progress: number) => void }
> {
  const uploadFile = useUploadFile()

  return {
    ...uploadFile,
    mutate: ({ taskId, file, onProgress }) => {
      uploadFile.mutate({ file, taskId, onProgress })
    },
    mutateAsync: async ({ taskId, file, onProgress }) => {
      return uploadFile.mutateAsync({ file, taskId, onProgress })
    },
  } as UseMutationResult<
    Attachment,
    Error,
    { taskId: string; file: File; onProgress?: (progress: number) => void }
  >
}

/**
 * Delete an attachment.
 */
export function useDeleteAttachment(): UseMutationResult<
  void,
  Error,
  { attachmentId: string; entityType?: EntityType; entityId?: string; taskId?: string },
  { previous?: Attachment[] }
> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ attachmentId }) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.delete<void>(
        `/api/files/${attachmentId}`,
        getAuthHeaders(token)
      )

      if (response.status !== 204 && response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }
    },
    onMutate: async ({ attachmentId, entityType, entityId, taskId }) => {
      // Cancel any outgoing queries
      if (taskId) {
        await queryClient.cancelQueries({ queryKey: queryKeys.attachments(taskId) })
      }
      if (entityType && entityId) {
        await queryClient.cancelQueries({ queryKey: getEntityQueryKey(entityType, entityId) })
      }

      // Optimistic delete from task attachments
      if (taskId) {
        const previous = queryClient.getQueryData<Attachment[]>(queryKeys.attachments(taskId))
        queryClient.setQueryData<Attachment[]>(queryKeys.attachments(taskId), (old) =>
          old?.filter((a) => a.id !== attachmentId)
        )
        return { previous }
      }

      // Optimistic delete from entity attachments
      if (entityType && entityId) {
        const previous = queryClient.getQueryData<Attachment[]>(
          getEntityQueryKey(entityType, entityId)
        )
        queryClient.setQueryData<Attachment[]>(
          getEntityQueryKey(entityType, entityId),
          (old) => old?.filter((a) => a.id !== attachmentId)
        )
        return { previous }
      }

      return {}
    },
    onError: (_err, { entityType, entityId, taskId }, context) => {
      // Rollback on error
      if (context?.previous) {
        if (taskId) {
          queryClient.setQueryData(queryKeys.attachments(taskId), context.previous)
        }
        if (entityType && entityId) {
          queryClient.setQueryData(getEntityQueryKey(entityType, entityId), context.previous)
        }
      }
    },
    onSettled: (_data, _err, { attachmentId, entityType, entityId, taskId }) => {
      // Invalidate queries
      if (taskId) {
        queryClient.invalidateQueries({ queryKey: queryKeys.attachments(taskId) })
      }
      if (entityType && entityId) {
        queryClient.invalidateQueries({ queryKey: getEntityQueryKey(entityType, entityId) })
      }
      // Remove download URL cache
      queryClient.removeQueries({ queryKey: queryKeys.downloadUrl(attachmentId) })
    },
  })
}

/**
 * Delete multiple attachments by IDs.
 */
export function useDeleteAttachments(): UseMutationResult<void, Error, string[]> {
  const deleteAttachment = useDeleteAttachment()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (attachmentIds: string[]) => {
      // Delete all attachments in parallel
      await Promise.all(
        attachmentIds.map((id) =>
          deleteAttachment.mutateAsync({ attachmentId: id })
        )
      )
    },
    onSettled: () => {
      // Invalidate all attachment queries
      queryClient.invalidateQueries({ queryKey: ['attachments'] })
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
      const response = await window.electronAPI.get<{ download_url: string }>(
        `/api/files/${attachment.id}/download-url`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      const url = response.data?.download_url
      if (!url) {
        throw new Error('No download URL returned')
      }

      // Open presigned URL in new tab for download
      window.open(url, '_blank')
    },
  })
}

/**
 * Get a single download URL imperatively (for use outside of React Query).
 * Returns a function that fetches the URL.
 */
export function useGetDownloadUrl(): (attachmentId: string) => Promise<string | null> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useCallback(
    async (attachmentId: string) => {
      // Check cache first
      const cached = queryClient.getQueryData<string>(queryKeys.downloadUrl(attachmentId))
      if (cached) return cached

      if (!window.electronAPI) {
        console.error('[Attachments] Electron API not available')
        return null
      }

      try {
        const response = await window.electronAPI.get<{ download_url: string }>(
          `/api/files/${attachmentId}/download-url`,
          getAuthHeaders(token)
        )

        if (response.status !== 200 || !response.data?.download_url) {
          return null
        }

        const url = response.data.download_url

        // Cache the URL
        queryClient.setQueryData(queryKeys.downloadUrl(attachmentId), url)

        return url
      } catch (error) {
        console.error('[Attachments] Failed to get download URL:', error)
        return null
      }
    },
    [token, queryClient]
  )
}

/**
 * Get multiple download URLs imperatively.
 * Returns a function that fetches URLs for multiple attachments.
 */
export function useGetDownloadUrls(): (
  attachmentIds: string[]
) => Promise<Record<string, string>> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useCallback(
    async (attachmentIds: string[]) => {
      if (attachmentIds.length === 0) return {}

      const result: Record<string, string> = {}
      const uncachedIds: string[] = []

      // Check cache first
      for (const id of attachmentIds) {
        const cached = queryClient.getQueryData<string>(queryKeys.downloadUrl(id))
        if (cached) {
          result[id] = cached
        } else {
          uncachedIds.push(id)
        }
      }

      // If all cached, return immediately
      if (uncachedIds.length === 0) return result

      if (!window.electronAPI) {
        console.error('[Attachments] Electron API not available')
        return result
      }

      try {
        const response = await window.electronAPI.post<Record<string, string>>(
          '/api/files/download-urls',
          { ids: uncachedIds },
          getAuthHeaders(token)
        )

        if (response.status === 200 && response.data) {
          // Add to result and cache
          for (const [id, url] of Object.entries(response.data)) {
            result[id] = url
            queryClient.setQueryData(queryKeys.downloadUrl(id), url)
          }
        }
      } catch (error) {
        console.error('[Attachments] Failed to get download URLs:', error)
      }

      return result
    },
    [token, queryClient]
  )
}
