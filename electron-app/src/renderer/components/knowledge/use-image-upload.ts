/**
 * Shared Image Upload Hook
 *
 * Extracts common image upload logic used by both DocumentEditor and CanvasEditor.
 * Handles file validation, upload to /api/files/upload, and download URL retrieval.
 */

import { useCallback } from 'react'
import { toast } from 'sonner'

const ALLOWED_IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/gif', 'image/webp']

export function useImageUpload(
  token: string | null,
  documentId?: string
): (file: File) => Promise<{ url: string; attachmentId: string } | null> {
  return useCallback(async (file: File) => {
    if (!token) {
      toast.error('Session expired. Please sign in again.')
      return null
    }
    if (!ALLOWED_IMAGE_TYPES.includes(file.type)) {
      toast.error('Unsupported image format. Use PNG, JPEG, GIF, or WebP.')
      return null
    }
    if (file.size > 10 * 1024 * 1024) {
      toast.error('Image must be less than 10 MB')
      return null
    }

    const toastId = toast.loading('Uploading image...')
    try {
      const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8001'
      const params = new URLSearchParams()
      if (documentId) {
        params.append('entity_type', 'document')
        params.append('entity_id', documentId)
      }
      const queryString = params.toString() ? `?${params.toString()}` : ''

      const formData = new FormData()
      formData.append('file', file)

      const uploadResponse = await fetch(`${apiUrl}/api/files/upload${queryString}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      })

      if (!uploadResponse.ok) {
        const errorData = await uploadResponse.json().catch(() => ({}))
        throw new Error((errorData as { detail?: string }).detail || 'Failed to upload image')
      }

      const attachment = await uploadResponse.json() as { id: string }

      const downloadResponse = await fetch(`${apiUrl}/api/files/${attachment.id}`, {
        headers: { Authorization: `Bearer ${token}` },
      })

      if (!downloadResponse.ok) {
        throw new Error('Failed to get image download URL')
      }

      const downloadData = await downloadResponse.json() as { download_url: string }
      toast.dismiss(toastId)
      return { url: downloadData.download_url, attachmentId: attachment.id }
    } catch (err) {
      toast.dismiss(toastId)
      toast.error('Failed to upload image. Please try again.')
      console.error('[useImageUpload] Failed to upload image:', err)
      return null
    }
  }, [token, documentId])
}
