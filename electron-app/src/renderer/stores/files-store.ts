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

interface FilesState {
  // Data
  attachments: Record<string, Attachment[]>  // Keyed by "entityType:entityId"
  uploads: UploadProgress[]

  // UI state
  isLoading: boolean
  error: string | null

  // Actions
  fetchAttachments: (entityType: EntityType, entityId: string) => Promise<void>
  uploadFile: (data: FileUploadData) => Promise<Attachment | null>
  deleteAttachment: (id: string) => Promise<boolean>
  getDownloadUrl: (id: string) => Promise<string | null>
  clearError: () => void
  clearUploads: () => void
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

export const useFilesStore = create<FilesState>()((set, get) => ({
  // Initial state
  attachments: {},
  uploads: [],
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
    const uploadId = `upload-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`

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

      // Read file as ArrayBuffer
      const arrayBuffer = await file.arrayBuffer()

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

      // Use fetch directly for multipart/form-data since IPC doesn't handle it well
      const response = await fetch(`http://localhost:8000/api/files/upload`, {
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

      const data = await response.json()
      const attachment = data.attachment as Attachment

      // Update upload status to completed
      set((state) => ({
        uploads: state.uploads.map((u) =>
          u.fileId === uploadId ? { ...u, status: 'completed' as const, progress: 100 } : u
        ),
      }))

      // Add to attachments cache if entity info provided
      if (entityType && entityId) {
        const key = getEntityKey(entityType, entityId)
        set((state) => ({
          attachments: {
            ...state.attachments,
            [key]: [...(state.attachments[key] || []), attachment],
          },
        }))
      }

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
        // Remove from all attachment lists
        set((state) => {
          const newAttachments: Record<string, Attachment[]> = {}
          for (const key of Object.keys(state.attachments)) {
            newAttachments[key] = state.attachments[key].filter((a) => a.id !== id)
          }
          return { attachments: newAttachments }
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

  // Get download URL for an attachment
  getDownloadUrl: async (id: string) => {
    try {
      const token = localStorage.getItem('pm-desktop-auth')
      const parsedToken = token ? JSON.parse(token)?.state?.token : null

      if (!parsedToken) {
        throw new Error('Not authenticated')
      }

      const response = await window.electronAPI.get<{ download_url: string }>(
        `/api/files/${id}/download-url`,
        getAuthHeaders(parsedToken)
      )

      if (response.status >= 200 && response.status < 300) {
        return response.data.download_url
      }

      return null
    } catch {
      return null
    }
  },

  // Clear error
  clearError: () => set({ error: null }),

  // Clear completed/errored uploads
  clearUploads: () => set((state) => ({
    uploads: state.uploads.filter((u) => u.status === 'uploading' || u.status === 'pending'),
  })),
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
