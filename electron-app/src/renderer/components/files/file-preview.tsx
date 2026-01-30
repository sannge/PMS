/**
 * File Preview Component
 *
 * Modal dialog for previewing file attachments.
 *
 * Features:
 * - Image preview with zoom
 * - PDF preview via iframe
 * - Video and audio player
 * - Download button
 * - Navigation between files
 * - Keyboard navigation (Escape to close, arrows for navigation)
 */

import { useState, useCallback, useEffect } from 'react'
import { cn } from '@/lib/utils'
import {
  X,
  Download,
  ExternalLink,
  ChevronLeft,
  ChevronRight,
  Loader2,
  FileText,
  File,
  FileImage,
  FileVideo,
  FileAudio,
  FileCode,
  FileArchive,
  ZoomIn,
  ZoomOut,
  RotateCw,
  Maximize2,
} from 'lucide-react'
import { type Attachment, useGetDownloadUrl } from '@/hooks/use-attachments'
import {
  formatFileSize,
  isImageFile,
  isPdfFile,
  isVideoFile,
  isAudioFile,
  getFileIconType,
} from '@/lib/file-utils'

// ============================================================================
// Types
// ============================================================================

export interface FilePreviewProps {
  /**
   * Attachment to preview
   */
  attachment: Attachment | null
  /**
   * Whether the preview is open
   */
  isOpen: boolean
  /**
   * All attachments for navigation
   */
  attachments?: Attachment[]
  /**
   * Callback to close the preview
   */
  onClose: () => void
  /**
   * Callback when navigating to previous/next
   */
  onNavigate?: (attachment: Attachment) => void
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Get preview icon for non-previewable files
 */
function getPreviewIcon(fileType: string | null, fileName: string): JSX.Element {
  const iconType = getFileIconType(fileType, fileName)

  switch (iconType) {
    case 'image':
      return <FileImage className="h-24 w-24 text-blue-500" />
    case 'video':
      return <FileVideo className="h-24 w-24 text-purple-500" />
    case 'audio':
      return <FileAudio className="h-24 w-24 text-green-500" />
    case 'pdf':
      return <FileText className="h-24 w-24 text-red-500" />
    case 'word':
    case 'text':
      return <FileText className="h-24 w-24 text-blue-600" />
    case 'archive':
      return <FileArchive className="h-24 w-24 text-yellow-600" />
    case 'code':
      return <FileCode className="h-24 w-24 text-slate-600" />
    default:
      return <File className="h-24 w-24 text-muted-foreground" />
  }
}

/**
 * Check if file type is previewable
 */
function isPreviewable(fileType: string | null): boolean {
  return isImageFile(fileType) || isPdfFile(fileType) || isVideoFile(fileType) || isAudioFile(fileType)
}

// ============================================================================
// Sub-Components
// ============================================================================

interface ImagePreviewProps {
  url: string
  alt: string
}

function ImagePreview({ url, alt }: ImagePreviewProps): JSX.Element {
  const [zoom, setZoom] = useState(1)
  const [rotation, setRotation] = useState(0)
  const [isLoading, setIsLoading] = useState(true)

  const handleZoomIn = useCallback(() => {
    setZoom((z) => Math.min(z + 0.25, 3))
  }, [])

  const handleZoomOut = useCallback(() => {
    setZoom((z) => Math.max(z - 0.25, 0.5))
  }, [])

  const handleRotate = useCallback(() => {
    setRotation((r) => (r + 90) % 360)
  }, [])

  const handleReset = useCallback(() => {
    setZoom(1)
    setRotation(0)
  }, [])

  return (
    <div className="relative flex flex-1 flex-col items-center justify-center">
      {/* Image Controls */}
      <div className="absolute top-4 left-1/2 -translate-x-1/2 z-10 flex items-center gap-1 rounded-lg border border-border bg-background/90 backdrop-blur-sm p-1 shadow-lg">
        <button
          onClick={handleZoomOut}
          className="rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
          title="Zoom out"
        >
          <ZoomOut className="h-4 w-4" />
        </button>
        <span className="px-2 text-sm text-muted-foreground">{Math.round(zoom * 100)}%</span>
        <button
          onClick={handleZoomIn}
          className="rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
          title="Zoom in"
        >
          <ZoomIn className="h-4 w-4" />
        </button>
        <div className="mx-1 h-5 w-px bg-border" />
        <button
          onClick={handleRotate}
          className="rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
          title="Rotate"
        >
          <RotateCw className="h-4 w-4" />
        </button>
        <button
          onClick={handleReset}
          className="rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
          title="Reset"
        >
          <Maximize2 className="h-4 w-4" />
        </button>
      </div>

      {/* Image */}
      <div className="relative flex-1 flex items-center justify-center overflow-auto w-full">
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-background/50">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        )}
        <img
          src={url}
          alt={alt}
          onLoad={() => setIsLoading(false)}
          className="max-h-full object-contain transition-transform duration-200"
          style={{
            transform: `scale(${zoom}) rotate(${rotation}deg)`,
          }}
        />
      </div>
    </div>
  )
}

interface VideoPreviewProps {
  url: string
}

function VideoPreview({ url }: VideoPreviewProps): JSX.Element {
  return (
    <div className="flex flex-1 items-center justify-center">
      <video
        src={url}
        controls
        autoPlay={false}
        className="max-h-full max-w-full rounded-lg"
      >
        Your browser does not support video playback.
      </video>
    </div>
  )
}

interface AudioPreviewProps {
  url: string
}

function AudioPreview({ url }: AudioPreviewProps): JSX.Element {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4">
      <FileAudio className="h-24 w-24 text-green-500" />
      <audio src={url} controls autoPlay={false} className="w-full max-w-md">
        Your browser does not support audio playback.
      </audio>
    </div>
  )
}

interface PdfPreviewProps {
  url: string
}

function PdfPreview({ url }: PdfPreviewProps): JSX.Element {
  const [isLoading, setIsLoading] = useState(true)

  return (
    <div className="relative flex flex-1 flex-col">
      {isLoading && (
        <div className="absolute inset-0 flex items-center justify-center bg-background/50">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      )}
      <iframe
        src={url}
        onLoad={() => setIsLoading(false)}
        className="flex-1 border-0 rounded-lg"
        title="PDF Preview"
      />
    </div>
  )
}

interface NoPreviewProps {
  attachment: Attachment
}

function NoPreview({ attachment }: NoPreviewProps): JSX.Element {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4">
      {getPreviewIcon(attachment.file_type, attachment.file_name)}
      <div className="text-center">
        <p className="text-lg font-medium text-foreground">{attachment.file_name}</p>
        <p className="text-sm text-muted-foreground">
          {attachment.file_type || 'Unknown type'} &bull; {formatFileSize(attachment.file_size)}
        </p>
        <p className="mt-4 text-sm text-muted-foreground">
          Preview not available for this file type.
        </p>
      </div>
    </div>
  )
}

// ============================================================================
// Main Component
// ============================================================================

export function FilePreview({
  attachment,
  isOpen,
  attachments = [],
  onClose,
  onNavigate,
}: FilePreviewProps): JSX.Element | null {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [isLoadingUrl, setIsLoadingUrl] = useState(false)
  const getDownloadUrl = useGetDownloadUrl()

  // Find current index for navigation
  const currentIndex = attachment
    ? attachments.findIndex((a) => a.id === attachment.id)
    : -1
  const hasPrev = currentIndex > 0
  const hasNext = currentIndex >= 0 && currentIndex < attachments.length - 1

  // Load preview URL when attachment changes
  useEffect(() => {
    if (!attachment || !isOpen) {
      setPreviewUrl(null)
      return
    }

    setIsLoadingUrl(true)
    getDownloadUrl(attachment.id)
      .then((url) => {
        setPreviewUrl(url)
      })
      .finally(() => {
        setIsLoadingUrl(false)
      })
  }, [attachment?.id, isOpen, getDownloadUrl])

  // Keyboard navigation
  useEffect(() => {
    if (!isOpen) return

    function handleKeyDown(e: KeyboardEvent) {
      switch (e.key) {
        case 'Escape':
          onClose()
          break
        case 'ArrowLeft':
          if (hasPrev && onNavigate) {
            onNavigate(attachments[currentIndex - 1])
          }
          break
        case 'ArrowRight':
          if (hasNext && onNavigate) {
            onNavigate(attachments[currentIndex + 1])
          }
          break
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, hasPrev, hasNext, currentIndex, attachments, onClose, onNavigate])

  // Handle download
  const handleDownload = useCallback(async () => {
    if (!previewUrl) return

    try {
      const link = document.createElement('a')
      link.href = previewUrl
      link.download = attachment?.file_name || 'download'
      link.target = '_blank'
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
    } catch {
      // Fallback: open in new tab
      window.electronAPI.openExternal(previewUrl)
    }
  }, [previewUrl, attachment?.file_name])

  // Handle open external
  const handleOpenExternal = useCallback(() => {
    if (previewUrl) {
      window.electronAPI.openExternal(previewUrl)
    }
  }, [previewUrl])

  if (!isOpen || !attachment) {
    return null
  }

  const canPreview = isPreviewable(attachment.file_type)

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="fixed inset-0 z-50 flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between bg-background/90 backdrop-blur-sm border-b border-border px-4 py-3">
          <div className="flex items-center gap-3 min-w-0">
            <h3 className="font-medium text-foreground truncate">{attachment.file_name}</h3>
            <span className="text-sm text-muted-foreground">
              {formatFileSize(attachment.file_size)}
            </span>
            {attachments.length > 1 && (
              <span className="text-sm text-muted-foreground">
                ({currentIndex + 1} of {attachments.length})
              </span>
            )}
          </div>

          <div className="flex items-center gap-1">
            <button
              onClick={handleDownload}
              disabled={!previewUrl}
              className={cn(
                'rounded-md p-2 text-muted-foreground transition-colors',
                'hover:bg-accent hover:text-foreground',
                'disabled:opacity-50 disabled:cursor-not-allowed'
              )}
              title="Download"
            >
              <Download className="h-5 w-5" />
            </button>
            <button
              onClick={handleOpenExternal}
              disabled={!previewUrl}
              className={cn(
                'rounded-md p-2 text-muted-foreground transition-colors',
                'hover:bg-accent hover:text-foreground',
                'disabled:opacity-50 disabled:cursor-not-allowed'
              )}
              title="Open in browser"
            >
              <ExternalLink className="h-5 w-5" />
            </button>
            <button
              onClick={onClose}
              className="rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
              title="Close (Esc)"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 flex items-center justify-center p-4 overflow-hidden">
          {isLoadingUrl ? (
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          ) : !previewUrl ? (
            <div className="text-center">
              <p className="text-muted-foreground">Failed to load preview</p>
            </div>
          ) : canPreview ? (
            <>
              {isImageFile(attachment.file_type) && (
                <ImagePreview url={previewUrl} alt={attachment.file_name} />
              )}
              {isPdfFile(attachment.file_type) && <PdfPreview url={previewUrl} />}
              {isVideoFile(attachment.file_type) && <VideoPreview url={previewUrl} />}
              {isAudioFile(attachment.file_type) && <AudioPreview url={previewUrl} />}
            </>
          ) : (
            <NoPreview attachment={attachment} />
          )}
        </div>

        {/* Navigation Arrows */}
        {attachments.length > 1 && (
          <>
            {hasPrev && (
              <button
                onClick={() => onNavigate?.(attachments[currentIndex - 1])}
                className={cn(
                  'fixed left-4 top-1/2 -translate-y-1/2 z-50',
                  'rounded-full p-3 bg-background/90 backdrop-blur-sm border border-border',
                  'text-muted-foreground hover:text-foreground hover:bg-accent',
                  'transition-all shadow-lg'
                )}
                title="Previous (←)"
              >
                <ChevronLeft className="h-6 w-6" />
              </button>
            )}
            {hasNext && (
              <button
                onClick={() => onNavigate?.(attachments[currentIndex + 1])}
                className={cn(
                  'fixed right-4 top-1/2 -translate-y-1/2 z-50',
                  'rounded-full p-3 bg-background/90 backdrop-blur-sm border border-border',
                  'text-muted-foreground hover:text-foreground hover:bg-accent',
                  'transition-all shadow-lg'
                )}
                title="Next (→)"
              >
                <ChevronRight className="h-6 w-6" />
              </button>
            )}
          </>
        )}
      </div>
    </>
  )
}

export default FilePreview
