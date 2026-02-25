/**
 * Draw.io Modal Editor
 *
 * Near-full-screen modal wrapping the draw.io embed iframe via react-drawio.
 * Uses draw.io's native Save & Exit button (not a custom export call) because
 * the ref-based exportDiagram doesn't work reliably in Electron's sandboxed iframe.
 *
 * Flow:
 *   Save & Exit → draw.io exports PNG (exportFormat="png") → onExport fires →
 *   cropPngWhitespace trims empty space → saves data
 *   Exit / Cancel → onClose fires → closes modal without saving
 */

import { useCallback, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { DrawIoEmbed } from 'react-drawio'
import type { EventExport, EventExit } from 'react-drawio'

interface DrawioModalProps {
  open: boolean
  initialXml: string
  onSave: (xml: string, previewPng: string) => void
  onClose: () => void
}

/** Max pixel width for the stored preview — keeps base64 size reasonable */
const MAX_PREVIEW_WIDTH = 1200

/**
 * Crop whitespace from a PNG data URL and resize to a sane max width.
 *
 * Draw.io exports the full page canvas, which often includes large empty
 * margins around the actual diagram shapes. This:
 * 1. Scans pixel data to find the content bounding box
 * 2. Crops tightly (+ 20px padding)
 * 3. Scales down to MAX_PREVIEW_WIDTH if wider (preserving aspect ratio)
 */
function cropAndResizePng(dataUrl: string): Promise<string> {
  return new Promise((resolve) => {
    const img = new Image()
    img.onload = () => {
      const canvas = document.createElement('canvas')
      const ctx = canvas.getContext('2d')
      if (!ctx) { resolve(dataUrl); return }

      canvas.width = img.width
      canvas.height = img.height
      ctx.drawImage(img, 0, 0)

      const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height)
      const { data, width, height } = imageData

      let top = height, left = width, right = 0, bottom = 0

      for (let y = 0; y < height; y++) {
        for (let x = 0; x < width; x++) {
          const idx = (y * width + x) * 4
          const r = data[idx], g = data[idx + 1], b = data[idx + 2], a = data[idx + 3]
          // Non-white and non-transparent pixel = content
          if (a > 10 && (r < 245 || g < 245 || b < 245)) {
            if (x < left) left = x
            if (x > right) right = x
            if (y < top) top = y
            if (y > bottom) bottom = y
          }
        }
      }

      // All white or empty — return as-is
      if (right <= left || bottom <= top) {
        resolve(dataUrl)
        return
      }

      // Add padding around content
      const pad = 20
      left = Math.max(0, left - pad)
      top = Math.max(0, top - pad)
      right = Math.min(width - 1, right + pad)
      bottom = Math.min(height - 1, bottom + pad)

      const cropW = right - left + 1
      const cropH = bottom - top + 1

      // Scale down if wider than MAX_PREVIEW_WIDTH (preserves aspect ratio)
      let outW = cropW
      let outH = cropH
      if (cropW > MAX_PREVIEW_WIDTH) {
        const scale = MAX_PREVIEW_WIDTH / cropW
        outW = MAX_PREVIEW_WIDTH
        outH = Math.round(cropH * scale)
      }

      const outCanvas = document.createElement('canvas')
      outCanvas.width = outW
      outCanvas.height = outH
      const outCtx = outCanvas.getContext('2d')
      if (!outCtx) { resolve(dataUrl); return }

      // High-quality downscale + white background
      outCtx.imageSmoothingEnabled = true
      outCtx.imageSmoothingQuality = 'high'
      outCtx.fillStyle = '#ffffff'
      outCtx.fillRect(0, 0, outW, outH)
      outCtx.drawImage(canvas, left, top, cropW, cropH, 0, 0, outW, outH)

      resolve(outCanvas.toDataURL('image/png'))
    }
    img.onerror = () => resolve(dataUrl)
    img.src = dataUrl
  })
}

export function DrawioModal({ open, initialXml, onSave, onClose }: DrawioModalProps) {
  // Block Escape from propagating to TipTap
  useEffect(() => {
    if (!open) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        e.stopPropagation()
        onClose()
      }
    }
    window.addEventListener('keydown', handleKeyDown, true)
    return () => window.removeEventListener('keydown', handleKeyDown, true)
  }, [open, onClose])

  // Fires when draw.io's Save & Exit exports the diagram as PNG
  const handleExport = useCallback((data: EventExport) => {
    if (!data.data) return

    // draw.io returns PNG as data URL (with prefix) or raw base64
    const pngDataUrl = data.data.startsWith('data:')
      ? data.data
      : `data:image/png;base64,${data.data}`

    // Crop whitespace + resize, then save
    cropAndResizePng(pngDataUrl).then((croppedPng) => {
      onSave(data.xml, croppedPng)
    })
  }, [onSave])

  // Fires when user clicks Exit (without saving) or after Save & Exit completes
  const handleDrawioExit = useCallback((_data: EventExit) => {
    // If onExport already called onSave (Save & Exit), modal is already closing.
    // If user clicked Exit (without saving), close without saving.
    onClose()
  }, [onClose])

  if (!open) return null

  return createPortal(
    <div
      className="fixed inset-0 z-50"
      role="dialog"
      aria-modal="true"
      aria-label="Edit Diagram"
      onKeyDown={e => e.stopPropagation()}
    >
      {/* Overlay */}
      <div className="absolute inset-0 bg-black/80" aria-hidden="true" />

      {/* Modal */}
      <div className="absolute inset-4 bg-background border rounded-lg flex flex-col overflow-hidden z-10">
        {/* Minimal header — draw.io provides its own Save & Exit / Exit buttons */}
        <div className="px-4 py-2 border-b flex items-center justify-between shrink-0">
          <h2 className="text-lg font-semibold leading-none">Edit Diagram</h2>
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-sm rounded-md border border-border hover:bg-muted transition-colors"
          >
            Cancel
          </button>
        </div>

        {/* Draw.io iframe */}
        <div style={{ flex: '1 1 0%', minHeight: 0 }}>
          <DrawIoEmbed
            xml={initialXml || undefined}
            exportFormat="png"
            onExport={handleExport}
            onClose={handleDrawioExit}
            urlParameters={{
              ui: 'dark',
              dark: false,
              spin: true,
              noSaveBtn: true,
              noExitBtn: true,
              libraries: true,
              grid: true,
            }}
          />
        </div>
      </div>
    </div>,
    document.body
  )
}
