/**
 * File Utility Functions
 *
 * Helper functions for file handling, formatting, and type detection.
 */

// ============================================================================
// File Size Formatting
// ============================================================================

/**
 * Format file size for display
 */
export function formatFileSize(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return 'Unknown size'
  if (bytes === 0) return '0 B'

  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))

  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}

// ============================================================================
// File Extension
// ============================================================================

/**
 * Get file extension from filename
 */
export function getFileExtension(fileName: string): string {
  const parts = fileName.split('.')
  return parts.length > 1 ? parts[parts.length - 1].toLowerCase() : ''
}

// ============================================================================
// File Type Detection
// ============================================================================

/**
 * Check if file is an image
 */
export function isImageFile(fileType: string | null | undefined): boolean {
  if (!fileType) return false
  return fileType.startsWith('image/')
}

/**
 * Check if file is a PDF
 */
export function isPdfFile(fileType: string | null | undefined): boolean {
  return fileType === 'application/pdf'
}

/**
 * Check if file is a video
 */
export function isVideoFile(fileType: string | null | undefined): boolean {
  if (!fileType) return false
  return fileType.startsWith('video/')
}

/**
 * Check if file is an audio
 */
export function isAudioFile(fileType: string | null | undefined): boolean {
  if (!fileType) return false
  return fileType.startsWith('audio/')
}

/**
 * Get file icon type based on MIME type and filename
 */
export function getFileIconType(fileType: string | null | undefined, fileName: string): string {
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
// File Validation
// ============================================================================

/**
 * Check if file size is within limit
 */
export function isFileSizeValid(fileSize: number, maxSize: number): boolean {
  return fileSize <= maxSize
}

/**
 * Check if file type is allowed
 */
export function isFileTypeAllowed(fileType: string, allowedTypes: string[]): boolean {
  if (allowedTypes.length === 0) return true

  for (const allowed of allowedTypes) {
    if (allowed.endsWith('/*')) {
      // Wildcard match (e.g., "image/*")
      const prefix = allowed.slice(0, -1)
      if (fileType.startsWith(prefix)) return true
    } else if (allowed.startsWith('.')) {
      // Extension match
      // This would need filename, skip for now
      continue
    } else if (fileType === allowed) {
      return true
    }
  }

  return false
}
