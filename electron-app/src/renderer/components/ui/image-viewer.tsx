/**
 * ImageViewer Component
 *
 * A lightbox-style image viewer modal for viewing images within the application.
 * Features:
 * - Full-screen overlay with image
 * - Zoom in/out controls
 * - Download button
 * - Close on backdrop click or Escape key
 * - Smooth animations
 */

import { useCallback, useEffect, useState } from 'react'
import { cn } from '@/lib/utils'
import { X, ZoomIn, ZoomOut, Download, RotateCw } from 'lucide-react'

// ============================================================================
// Types
// ============================================================================

export interface ImageViewerProps {
  /** Image URL to display */
  src: string
  /** Alt text for the image */
  alt?: string
  /** File name for download */
  fileName?: string
  /** Whether the viewer is open */
  isOpen: boolean
  /** Callback when the viewer should close */
  onClose: () => void
  /** Optional class name for the overlay */
  className?: string
}

// ============================================================================
// Constants
// ============================================================================

const ZOOM_LEVELS = [0.5, 0.75, 1, 1.25, 1.5, 2, 3]
const DEFAULT_ZOOM_INDEX = 2 // 100%

// ============================================================================
// Component
// ============================================================================

export function ImageViewer({
  src,
  alt = 'Image',
  fileName,
  isOpen,
  onClose,
  className,
}: ImageViewerProps): JSX.Element | null {
  const [zoomIndex, setZoomIndex] = useState(DEFAULT_ZOOM_INDEX)
  const [rotation, setRotation] = useState(0)
  const [isLoading, setIsLoading] = useState(true)

  const zoom = ZOOM_LEVELS[zoomIndex]

  // Reset state when opening
  useEffect(() => {
    if (isOpen) {
      setZoomIndex(DEFAULT_ZOOM_INDEX)
      setRotation(0)
      setIsLoading(true)
    }
  }, [isOpen])

  // Handle keyboard shortcuts
  useEffect(() => {
    if (!isOpen) return

    const handleKeyDown = (e: KeyboardEvent) => {
      switch (e.key) {
        case 'Escape':
          onClose()
          break
        case '+':
        case '=':
          handleZoomIn()
          break
        case '-':
          handleZoomOut()
          break
        case 'r':
        case 'R':
          handleRotate()
          break
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose, zoomIndex])

  const handleZoomIn = useCallback(() => {
    setZoomIndex((i) => Math.min(i + 1, ZOOM_LEVELS.length - 1))
  }, [])

  const handleZoomOut = useCallback(() => {
    setZoomIndex((i) => Math.max(i - 1, 0))
  }, [])

  const handleRotate = useCallback(() => {
    setRotation((r) => (r + 90) % 360)
  }, [])

  const handleDownload = useCallback(() => {
    // Open in new tab for download (browser will handle it)
    window.open(src, '_blank')
  }, [src])

  const handleBackdropClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === e.currentTarget) {
        onClose()
      }
    },
    [onClose]
  )

  if (!isOpen) return null

  return (
    <div
      className={cn(
        'fixed inset-0 z-50 flex items-center justify-center',
        'bg-black/90 backdrop-blur-sm',
        'animate-in fade-in duration-200',
        className
      )}
      onClick={handleBackdropClick}
    >
      {/* Toolbar */}
      <div
        className={cn(
          'absolute top-4 left-1/2 -translate-x-1/2 z-10',
          'flex items-center gap-1 px-2 py-1.5 rounded-lg',
          'bg-black/60 border border-white/10 backdrop-blur-md',
          'shadow-lg'
        )}
      >
        {/* Zoom out */}
        <button
          onClick={handleZoomOut}
          disabled={zoomIndex === 0}
          className={cn(
            'flex h-8 w-8 items-center justify-center rounded-md',
            'text-white/80 hover:text-white hover:bg-white/10',
            'disabled:opacity-40 disabled:cursor-not-allowed',
            'transition-colors'
          )}
          title="Zoom out (-)"
        >
          <ZoomOut className="h-4 w-4" />
        </button>

        {/* Zoom level indicator */}
        <span className="px-2 text-xs text-white/70 font-mono min-w-[3rem] text-center">
          {Math.round(zoom * 100)}%
        </span>

        {/* Zoom in */}
        <button
          onClick={handleZoomIn}
          disabled={zoomIndex === ZOOM_LEVELS.length - 1}
          className={cn(
            'flex h-8 w-8 items-center justify-center rounded-md',
            'text-white/80 hover:text-white hover:bg-white/10',
            'disabled:opacity-40 disabled:cursor-not-allowed',
            'transition-colors'
          )}
          title="Zoom in (+)"
        >
          <ZoomIn className="h-4 w-4" />
        </button>

        {/* Divider */}
        <div className="w-px h-5 bg-white/20 mx-1" />

        {/* Rotate */}
        <button
          onClick={handleRotate}
          className={cn(
            'flex h-8 w-8 items-center justify-center rounded-md',
            'text-white/80 hover:text-white hover:bg-white/10',
            'transition-colors'
          )}
          title="Rotate (R)"
        >
          <RotateCw className="h-4 w-4" />
        </button>

        {/* Download */}
        <button
          onClick={handleDownload}
          className={cn(
            'flex h-8 w-8 items-center justify-center rounded-md',
            'text-white/80 hover:text-white hover:bg-white/10',
            'transition-colors'
          )}
          title="Download"
        >
          <Download className="h-4 w-4" />
        </button>

        {/* Divider */}
        <div className="w-px h-5 bg-white/20 mx-1" />

        {/* Close */}
        <button
          onClick={onClose}
          className={cn(
            'flex h-8 w-8 items-center justify-center rounded-md',
            'text-white/80 hover:text-white hover:bg-white/10',
            'transition-colors'
          )}
          title="Close (Esc)"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* File name */}
      {fileName && (
        <div
          className={cn(
            'absolute bottom-4 left-1/2 -translate-x-1/2 z-10',
            'px-3 py-1.5 rounded-lg',
            'bg-black/60 border border-white/10 backdrop-blur-md',
            'text-xs text-white/70'
          )}
        >
          {fileName}
        </div>
      )}

      {/* Image container */}
      <div
        className={cn(
          'relative max-w-[90vw] max-h-[85vh] overflow-auto',
          'flex items-center justify-center'
        )}
        onClick={(e) => e.stopPropagation()}
      >
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="h-8 w-8 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          </div>
        )}
        <img
          src={src}
          alt={alt}
          className={cn(
            'max-w-none transition-transform duration-200 ease-out',
            isLoading && 'opacity-0'
          )}
          style={{
            transform: `scale(${zoom}) rotate(${rotation}deg)`,
          }}
          onLoad={() => setIsLoading(false)}
          draggable={false}
        />
      </div>
    </div>
  )
}

// ============================================================================
// Exports
// ============================================================================

export default ImageViewer
