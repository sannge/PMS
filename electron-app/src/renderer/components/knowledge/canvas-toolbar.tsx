/**
 * CanvasToolbar
 *
 * Wraps the existing EditorToolbar and adds canvas-specific controls:
 * zoom in/out/reset and "New Container" button.
 */

import { useCallback } from 'react'
import { ZoomIn, ZoomOut, RotateCcw, PlusSquare } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Editor } from '@tiptap/core'
import { EditorToolbar } from './editor-toolbar'

interface CanvasToolbarProps {
  activeEditor: Editor | null
  editable: boolean
  onImageUpload?: (file: File) => void
  zoom: number
  onZoomChange: (zoom: number) => void
  onAddContainer: () => void
}

const ZOOM_LEVELS = [0.75, 1, 1.25]

export function CanvasToolbar({
  activeEditor,
  editable,
  onImageUpload,
  zoom,
  onZoomChange,
  onAddContainer,
}: CanvasToolbarProps) {
  const handleZoomIn = useCallback(() => {
    // Find next zoom level above current (handles non-preset values)
    const next = ZOOM_LEVELS.find((l) => l > zoom + 0.001)
    if (next !== undefined) onZoomChange(next)
  }, [zoom, onZoomChange])

  const handleZoomOut = useCallback(() => {
    // Find previous zoom level below current
    const prev = [...ZOOM_LEVELS].reverse().find((l) => l < zoom - 0.001)
    if (prev !== undefined) onZoomChange(prev)
  }, [zoom, onZoomChange])

  const handleZoomReset = useCallback(() => {
    onZoomChange(1)
  }, [onZoomChange])

  // Hide toolbar entirely in read-only mode — action bar already handles view state
  if (!editable) return null

  return (
    <div role="toolbar" aria-label="Canvas toolbar" className="flex items-center border-b bg-muted/20 min-h-[40px]">
      <div className="flex-1 min-w-0">
        {activeEditor ? (
          <EditorToolbar editor={activeEditor} onImageUpload={onImageUpload} />
        ) : (
          <div className="flex items-center px-3 py-1.5 text-sm text-muted-foreground">
            Click a container to edit
          </div>
        )}
      </div>

      <div className="flex items-center gap-0.5 px-2 border-l shrink-0">
        <button
          type="button"
          onClick={onAddContainer}
          title="New container"
          aria-label="Add new text container"
          className="p-1.5 rounded hover:bg-muted transition-colors"
        >
          <PlusSquare className="h-4 w-4" aria-hidden="true" />
        </button>

        <div className="w-px h-6 bg-border mx-1" aria-hidden="true" />

        <button
          type="button"
          onClick={handleZoomOut}
          disabled={zoom <= ZOOM_LEVELS[0]}
          title="Zoom out"
          aria-label="Zoom out"
          className={cn(
            'p-1.5 rounded hover:bg-muted transition-colors',
            zoom <= ZOOM_LEVELS[0] && 'opacity-50 cursor-not-allowed',
          )}
        >
          <ZoomOut className="h-4 w-4" aria-hidden="true" />
        </button>

        <span className="text-xs text-muted-foreground min-w-[40px] text-center tabular-nums" aria-label={`Zoom level ${Math.round(zoom * 100)} percent`}>
          {Math.round(zoom * 100)}%
        </span>

        <button
          type="button"
          onClick={handleZoomIn}
          disabled={zoom >= ZOOM_LEVELS[ZOOM_LEVELS.length - 1]}
          title="Zoom in"
          aria-label="Zoom in"
          className={cn(
            'p-1.5 rounded hover:bg-muted transition-colors',
            zoom >= ZOOM_LEVELS[ZOOM_LEVELS.length - 1] && 'opacity-50 cursor-not-allowed',
          )}
        >
          <ZoomIn className="h-4 w-4" aria-hidden="true" />
        </button>

        <button
          type="button"
          onClick={handleZoomReset}
          disabled={zoom === 1}
          title="Reset zoom"
          aria-label="Reset zoom to 100%"
          className={cn(
            'p-1.5 rounded hover:bg-muted transition-colors',
            zoom === 1 && 'opacity-50 cursor-not-allowed',
          )}
        >
          <RotateCcw className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
    </div>
  )
}
