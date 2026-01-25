/**
 * Files Store
 *
 * Zustand store for managing file attachments.
 *
 * Features:
 * - Upload files to backend/MinIO
 * - Download files
 * - List attachments for entities
 * - Delete attachments
 * - Track upload progress
 */

import { create } from 'zustand'
import { getAuthHeaders } from './auth-store'

// ============================================================================
// Types
// ============================================================================

export type EntityType = 'task' | 'note' | 'comment'

export interface Attachment {
  id: string
  file_name: string
  file_type: string | null
  file_size: number | null
  minio_bucket: string | null
  minio_key: string | null
  entity_type: string | null
  entity_id: string | null
  task_id: string | null
  note_id: string | null
  uploaded_by: string | null
  created_at: string
}

export interface FileUploadData {
  file: File
  entityType?: EntityType
  entityId?: string
}

export interface UploadProgress {
  fileId: string
  fileName: string
  progress: number
  status: 'pending' | 'uploading' | 'completed' | 'error'
  error?: string
}

// URL cache entry with expiration
interface CachedUrl {
  url: string
  expiresAt: number
}

interface FilesState {
  // Data
  attachments: Record<string, Attachment[]>  // Keyed by "entityType:entityId"
  uploads: UploadProgress[]
  urlCache: Record<string, CachedUrl>  // Cache for presigned URLs

  // UI state
  isLoading: boolean
  error: string | null

  // Actions
  fetchAttachments: (entityType: EntityType, entityId: string) => Promise<void>
  uploadFile: (data: FileUploadData) => Promise<Attachment | null>
  deleteAttachment: (id: string) => Promise<boolean>
  getDownloadUrl: (id: string) => Promise<string | null>
  getDownloadUrls: (ids: string[]) => Promise<Record<string, string>>  // Batch fetch
  clearExpiredUrls: () => void  // Clean up expired cache entries
  clearError: () => void
  clearUploads: () => void

  // WebSocket handlers for real-time updates
  handleAttachmentUploaded: (entityType: string, entityId: string, attachment: Attachment) => void
  handleAttachmentDeleted: (entityType: string, entityId: string, attachmentId: string) => void

  // Remove multiple attachments by IDs (for comment deletion cleanup)
  removeAttachmentsByIds: (attachmentIds: string[]) => void
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Get cache key for entity attachments
 */
function getEntityKey(entityType: EntityType, entityId: string): string {
  return `${entityType}:${entityId}`
}

/**
 * Format file size for display
 */
export function formatFileSize(bytes: number | null): string {
  if (bytes === null || bytes === undefined) return 'Unknown size'
  if (bytes === 0) return '0 B'

  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))

  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}

/**
 * Get file extension from filename
 */
export function getFileExtension(fileName: string): string {
  const parts = fileName.split('.')
  return parts.length > 1 ? parts[parts.length - 1].toLowerCase() : ''
}

/**
 * Check if file is an image
 */
export function isImageFile(fileType: string | null): boolean {
  if (!fileType) return false
  return fileType.startsWith('image/')
}

/**
 * Check if file is a PDF
 */
export function isPdfFile(fileType: string | null): boolean {
  return fileType === 'application/pdf'
}

/**
 * Check if file is a video
 */
export function isVideoFile(fileType: string | null): boolean {
  if (!fileType) return false
  return fileType.startsWith('video/')
}

/**
 * Check if file is an audio
 */
export function isAudioFile(fileType: string | null): boolean {
  if (!fileType) return false
  return fileType.startsWith('audio/')
}

/**
 * Get file icon name based on type
 */
export function getFileIconType(fileType: string | null, fileName: string): string {
  if (isImageFile(fileType)) return 'image'
  if (isPdfFile(fileType)) return 'pdf'
  if (isVideoFile(fileType)) return 'video'
  if (isAudioFile(fileType)) return 'audio'

  const ext = getFileExtension(fileName)

  // Common document types
  if (['doc', 'docx'].includes(ext)) return 'word'
  if (['xls', 'xlsx'].includes(ext)) return 'excel'
  if (['ppt', 'pptx'].includes(ext)) return 'powerpoint'
  if (['txt', 'md', 'rtf'].includes(ext)) return 'text'
  if (['zip', 'rar', '7z', 'tar', 'gz'].includes(ext)) return 'archive'
  if (['js', 'ts', 'py', 'java', 'cpp', 'c', 'h', 'css', 'html', 'json', 'xml'].includes(ext)) return 'code'

  return 'file'
}

// ============================================================================
// Store
// ============================================================================

// URL cache TTL (50 minutes - presigned URLs are typically valid for 1 hour)
const URL_CACHE_TTL_MS = 50 * 60 * 1000
// Maximum cache entries before forced cleanup
const MAX_CACHE_SIZE = 200

export const useFilesStore = create<FilesState>()((set, get) => ({
  // Initial state
  attachments: {},
  uploads: [],
  urlCache: {},
  isLoading: false,
  error: null,

  // Fetch attachments for an entity
  fetchAttachments: async (entityType: EntityType, entityId: string) => {
    const key = getEntityKey(entityType, entityId)
    set({ isLoading: true, error: null })

    try {
      const token = localStorage.getItem('pm-desktop-auth')
      const parsedToken = token ? JSON.parse(token)?.state?.token : null

      if (!parsedToken) {
        throw new Error('Not authenticated')
      }

      const response = await window.electronAPI.get<Attachment[]>(
        `/api/files/entity/${entityType}/${entityId}`,
        getAuthHeaders(parsedToken)
      )

      if (response.status >= 200 && response.status < 300) {
        set((state) => ({
          attachments: {
            ...state.attachments,
            [key]: response.data,
          },
          isLoading: false,
        }))
      } else {
        throw new Error('Failed to fetch attachments')
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to fetch attachments'
      set({ error: errorMessage, isLoading: false })
    }
  },

  // Upload a file
  uploadFile: async ({ file, entityType, entityId }: FileUploadData) => {
    const uploadId = `upload-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`

    // Add to uploads list
    set((state) => ({
      uploads: [
        ...state.uploads,
        {
          fileId: uploadId,
          fileName: file.name,
          progress: 0,
          status: 'pending' as const,
        },
      ],
    }))

    try {
      const token = localStorage.getItem('pm-desktop-auth')
      const parsedToken = token ? JSON.parse(token)?.state?.token : null

      if (!parsedToken) {
        throw new Error('Not authenticated')
      }

      // Update status to uploading
      set((state) => ({
        uploads: state.uploads.map((u) =>
          u.fileId === uploadId ? { ...u, status: 'uploading' as const, progress: 10 } : u
        ),
      }))

      // Update progress
      set((state) => ({
        uploads: state.uploads.map((u) =>
          u.fileId === uploadId ? { ...u, progress: 30 } : u
        ),
      }))

      // Create form data for multipart upload
      // We'll use a direct API call since the IPC handler may not support FormData well
      const formData = new FormData()
      formData.append('file', file)
      if (entityType) formData.append('entity_type', entityType)
      if (entityId) formData.append('entity_id', entityId)

      // Update progress
      set((state) => ({
        uploads: state.uploads.map((u) =>
          u.fileId === uploadId ? { ...u, progress: 50 } : u
        ),
      }))

      // Build query params for entity association
      const params = new URLSearchParams()
      if (entityType === 'task' && entityId) {
        params.append('task_id', entityId)
      } else if (entityType === 'note' && entityId) {
        params.append('note_id', entityId)
      } else if (entityType && entityId) {
        params.append('entity_type', entityType)
        params.append('entity_id', entityId)
      }
      const queryString = params.toString() ? `?${params.toString()}` : ''

      // Use fetch directly for multipart/form-data since IPC doesn't handle it well
      const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8001'
      const response = await fetch(`${apiUrl}/api/files/upload${queryString}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${parsedToken}`,
        },
        body: formData,
      })

      // Update progress
      set((state) => ({
        uploads: state.uploads.map((u) =>
          u.fileId === uploadId ? { ...u, progress: 80 } : u
        ),
      }))

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || 'Failed to upload file')
      }

      const attachment = await response.json() as Attachment

      // Update upload status to completed
      set((state) => ({
        uploads: state.uploads.map((u) =>
          u.fileId === uploadId ? { ...u, status: 'completed' as const, progress: 100 } : u
        ),
      }))

      // NOTE: Don't add to attachments cache here - let the WebSocket event handle it
      // to avoid duplicates. The WebSocket handler has duplicate detection.

      // Auto-clear the completed upload after a brief moment so user sees success
      setTimeout(() => {
        set((state) => ({
          uploads: state.uploads.filter((u) => u.fileId !== uploadId),
        }))
      }, 1000)

      return attachment
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Upload failed'

      // Update upload status to error
      set((state) => ({
        uploads: state.uploads.map((u) =>
          u.fileId === uploadId
            ? { ...u, status: 'error' as const, error: errorMessage }
            : u
        ),
        error: errorMessage,
      }))

      return null
    }
  },

  // Delete an attachment
  deleteAttachment: async (id: string) => {
    set({ error: null })

    try {
      const token = localStorage.getItem('pm-desktop-auth')
      const parsedToken = token ? JSON.parse(token)?.state?.token : null

      if (!parsedToken) {
        throw new Error('Not authenticated')
      }

      const response = await window.electronAPI.delete(
        `/api/files/${id}`,
        getAuthHeaders(parsedToken)
      )

      if (response.status >= 200 && response.status < 300) {
        // Remove from all attachment lists and clear cached URL
        set((state) => {
          const newAttachments: Record<string, Attachment[]> = {}
          for (const key of Object.keys(state.attachments)) {
            newAttachments[key] = state.attachments[key].filter((a) => a.id !== id)
          }
          // Remove from URL cache
          const { [id]: _, ...remainingCache } = state.urlCache
          return { attachments: newAttachments, urlCache: remainingCache }
        })
        return true
      } else {
        throw new Error('Failed to delete attachment')
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to delete attachment'
      set({ error: errorMessage })
      return false
    }
  },

  // Get download URL for an attachment (presigned URL from MinIO) with caching
  getDownloadUrl: async (id: string) => {
    // Check cache first
    const cached = get().urlCache[id]
    if (cached && cached.expiresAt > Date.now()) {
      return cached.url
    }

    try {
      const token = localStorage.getItem('pm-desktop-auth')
      const parsedToken = token ? JSON.parse(token)?.state?.token : null

      if (!parsedToken) {
        console.error('[Files] getDownloadUrl: Not authenticated')
        return null
      }

      const response = await window.electronAPI.get<{ download_url: string }>(
        `/api/files/${id}/download-url`,
        getAuthHeaders(parsedToken)
      )

      if (response.status >= 200 && response.status < 300 && response.data?.download_url) {
        const url = response.data.download_url
        // Cache the URL with size limit enforcement
        set((state) => {
          let updatedCache = {
            ...state.urlCache,
            [id]: { url, expiresAt: Date.now() + URL_CACHE_TTL_MS },
          }

          // If cache exceeds max size, remove oldest entries
          const cacheSize = Object.keys(updatedCache).length
          if (cacheSize > MAX_CACHE_SIZE) {
            const entries = Object.entries(updatedCache)
            entries.sort((a, b) => a[1].expiresAt - b[1].expiresAt)
            const keepEntries = entries.slice(-MAX_CACHE_SIZE)
            updatedCache = Object.fromEntries(keepEntries)
          }

          return { urlCache: updatedCache }
        })
        return url
      }

      console.error('[Files] getDownloadUrl: Failed', response.status, response.data)
      return null
    } catch (error) {
      console.error('[Files] getDownloadUrl: Error', error)
      return null
    }
  },

  // Batch get download URLs for multiple attachments
  getDownloadUrls: async (ids: string[]) => {
    if (ids.length === 0) return {}

    const now = Date.now()
    const result: Record<string, string> = {}
    const uncachedIds: string[] = []
    const expiredIds: string[] = []

    // Check cache first and track expired entries for cleanup
    const cache = get().urlCache
    for (const id of ids) {
      const cached = cache[id]
      if (cached) {
        if (cached.expiresAt > now) {
          result[id] = cached.url
        } else {
          expiredIds.push(id)
          uncachedIds.push(id)
        }
      } else {
        uncachedIds.push(id)
      }
    }

    // Clean up expired entries we found (lazy cleanup)
    if (expiredIds.length > 0) {
      set((state) => {
        const newCache = { ...state.urlCache }
        for (const id of expiredIds) {
          delete newCache[id]
        }
        return { urlCache: newCache }
      })
    }

    // If all URLs are cached, return immediately
    if (uncachedIds.length === 0) {
      return result
    }

    try {
      const token = localStorage.getItem('pm-desktop-auth')
      const parsedToken = token ? JSON.parse(token)?.state?.token : null

      if (!parsedToken) {
        console.error('[Files] getDownloadUrls: Not authenticated')
        return result
      }

      // Batch fetch uncached URLs
      const response = await window.electronAPI.post<Record<string, string>>(
        '/api/files/download-urls',
        { ids: uncachedIds },
        getAuthHeaders(parsedToken)
      )

      if (response.status >= 200 && response.status < 300 && response.data) {
        const newUrls = response.data
        const newCache: Record<string, CachedUrl> = {}

        for (const [id, url] of Object.entries(newUrls)) {
          result[id] = url
          newCache[id] = { url, expiresAt: now + URL_CACHE_TTL_MS }
        }

        // Update cache with size limit enforcement
        set((state) => {
          let updatedCache = { ...state.urlCache, ...newCache }

          // If cache exceeds max size, remove oldest expired entries first, then oldest entries
          const cacheSize = Object.keys(updatedCache).length
          if (cacheSize > MAX_CACHE_SIZE) {
            const entries = Object.entries(updatedCache)
            // Sort by expiration time (oldest first)
            entries.sort((a, b) => a[1].expiresAt - b[1].expiresAt)
            // Keep only the newest MAX_CACHE_SIZE entries
            const keepEntries = entries.slice(-MAX_CACHE_SIZE)
            updatedCache = Object.fromEntries(keepEntries)
          }

          return { urlCache: updatedCache }
        })
      }
    } catch (error) {
      console.error('[Files] getDownloadUrls: Error', error)
    }

    return result
  },

  // Clean up expired URL cache entries (call periodically or on navigation)
  clearExpiredUrls: () => {
    const now = Date.now()
    set((state) => {
      const newCache: Record<string, CachedUrl> = {}
      for (const [id, entry] of Object.entries(state.urlCache)) {
        if (entry.expiresAt > now) {
          newCache[id] = entry
        }
      }
      return { urlCache: newCache }
    })
  },

  // Clear error
  clearError: () => set({ error: null }),

  // Clear completed/errored uploads
  clearUploads: () => set((state) => ({
    uploads: state.uploads.filter((u) => u.status === 'uploading' || u.status === 'pending'),
  })),

  // WebSocket handler: attachment uploaded by another user
  handleAttachmentUploaded: (entityType: string, entityId: string, attachment: Attachment) => {
    const key = `${entityType}:${entityId}`
    set((state) => {
      // Check if attachment already exists (avoid duplicates from own uploads)
      const existing = state.attachments[key] || []
      if (existing.some((a) => a.id === attachment.id)) {
        return state
      }
      return {
        attachments: {
          ...state.attachments,
          [key]: [...existing, attachment],
        },
      }
    })
  },

  // WebSocket handler: attachment deleted by another user
  handleAttachmentDeleted: (entityType: string, entityId: string, attachmentId: string) => {
    const key = `${entityType}:${entityId}`
    set((state) => ({
      attachments: {
        ...state.attachments,
        [key]: (state.attachments[key] || []).filter((a) => a.id !== attachmentId),
      },
    }))
  },

  // Remove multiple attachments by IDs (for comment deletion cleanup)
  removeAttachmentsByIds: (attachmentIds: string[]) => {
    if (attachmentIds.length === 0) return

    const idsSet = new Set(attachmentIds)
    set((state) => {
      const newAttachments: Record<string, Attachment[]> = {}
      for (const key of Object.keys(state.attachments)) {
        newAttachments[key] = state.attachments[key].filter((a) => !idsSet.has(a.id))
      }
      // Also remove from URL cache
      const newCache = { ...state.urlCache }
      for (const id of attachmentIds) {
        delete newCache[id]
      }
      return { attachments: newAttachments, urlCache: newCache }
    })
  },
}))

// ============================================================================
// Selectors
// ============================================================================

/**
 * Get attachments for an entity
 */
export function getEntityAttachments(
  state: FilesState,
  entityType: EntityType,
  entityId: string
): Attachment[] {
  const key = getEntityKey(entityType, entityId)
  return state.attachments[key] || []
}

export default useFilesStore
