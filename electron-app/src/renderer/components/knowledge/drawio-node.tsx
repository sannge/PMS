/**
 * Draw.io Diagram Node for TipTap Editor
 *
 * Renders diagrams as inline PNG previews. Clicking opens a modal
 * with the full draw.io editor (drawio-modal.tsx). Diagram XML is
 * stored in TipTap node attrs; the PNG preview is uploaded to MinIO
 * and referenced via attachmentId (presigned URL resolution).
 * Legacy base64 previewPng attrs are read but never re-serialized.
 */

import { Node, mergeAttributes } from '@tiptap/core'
import { ReactNodeViewRenderer, NodeViewWrapper } from '@tiptap/react'
import type { NodeViewProps } from '@tiptap/react'
import { useState, useCallback, useEffect, useRef } from 'react'
import { cn } from '@/lib/utils'
import { DrawioModal } from './drawio-modal'
import { useGetDownloadUrls } from '@/hooks/use-attachments'
import { requestBatchUrl } from './editor-extensions'
import { useAuthStore } from '@/contexts/auth-context'
import { toast } from 'sonner'

// ============================================================================
// Module Augmentation
// ============================================================================

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    drawio: {
      insertDrawio: () => ReturnType
    }
  }
}

// ============================================================================
// NodeView Component
// ============================================================================

/** Max diagram preview PNG size (10 MB, matching image upload limit) */
const MAX_DRAWIO_PNG_SIZE = 10 * 1024 * 1024

/** Convert a base64 data URL to a Blob without using fetch() (avoids CSP/SSRF concerns). */
function dataUrlToBlob(dataUrl: string): Blob {
  const commaIdx = dataUrl.indexOf(',')
  const meta = dataUrl.slice(0, commaIdx)
  const base64 = dataUrl.slice(commaIdx + 1)
  const mime = meta.match(/:(.*?);/)?.[1] || 'image/png'
  const byteString = atob(base64)
  const ab = new ArrayBuffer(byteString.length)
  const ia = new Uint8Array(ab)
  for (let i = 0; i < byteString.length; i++) ia[i] = byteString.charCodeAt(i)
  return new Blob([ab], { type: mime })
}

function DrawioNodeView({ node, updateAttributes, selected, editor }: NodeViewProps) {
  const [modalOpen, setModalOpen] = useState(false)
  const [isEditable, setIsEditable] = useState(editor.isEditable)
  const [isResizing, setIsResizing] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [localPreviewUrl, setLocalPreviewUrl] = useState<string | null>(null)
  const [freshUrl, setFreshUrl] = useState<string | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const startXRef = useRef(0)
  const startWidthRef = useRef(0)
  const currentWidthRef = useRef(0)
  // Suppresses the click-to-open-modal that fires right after a resize drag ends
  const justResizedRef = useRef(false)
  // Tracks the latest save generation to prevent stale upload callbacks
  const saveGenerationRef = useRef(0)
  // Abort controller for cancelling in-flight uploads on re-save or unmount
  const abortControllerRef = useRef<AbortController | null>(null)
  // Tracks active document listeners for cleanup on unmount (prevents leak during mid-drag unmount)
  const resizeCleanupRef = useRef<(() => void) | null>(null)
  const getDownloadUrls = useGetDownloadUrls()
  const token = useAuthStore((s) => s.token)

  // Revoke object URL on cleanup / when localPreviewUrl changes
  useEffect(() => {
    return () => {
      if (localPreviewUrl) URL.revokeObjectURL(localPreviewUrl)
    }
  }, [localPreviewUrl])

  // Abort in-flight upload and clean up resize listeners on unmount
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort()
      resizeCleanupRef.current?.()
    }
  }, [])

  // Reactively track editor editability — NodeViews don't re-render
  // automatically when editor.setEditable() is called because the
  // editor object reference stays the same.
  useEffect(() => {
    const handler = () => setIsEditable(editor.isEditable)
    editor.on('transaction', handler)
    handler() // sync initial state
    return () => { editor.off('transaction', handler) }
  }, [editor])

  // Refresh presigned URL on mount when attachmentId is present.
  // Uses batch collector to coalesce concurrent mounts into a single API call.
  // Also clears localPreviewUrl once a presigned URL is available (prevents
  // flash of "preview unavailable" between object URL revocation and presigned URL).
  useEffect(() => {
    setFreshUrl(null)
    const attachmentId = node.attrs.attachmentId
    if (!attachmentId) return
    let cancelled = false
    requestBatchUrl(attachmentId, getDownloadUrls).then((url) => {
      if (cancelled || !url) return
      setFreshUrl(url)
      setLocalPreviewUrl(null) // presigned URL is ready, release object URL
    })
    return () => { cancelled = true }
  }, [node.attrs.attachmentId, getDownloadUrls])

  const { data, width } = node.attrs

  // Priority: fresh presigned URL > optimistic local preview > legacy base64 (only if no attachmentId)
  const resolvedPreviewUrl =
    freshUrl ||
    localPreviewUrl ||
    (!node.attrs.attachmentId ? node.attrs.previewPng : null) ||
    null

  const uploadDrawioPng = useCallback(async (blob: Blob, signal: AbortSignal): Promise<{ attachmentId: string } | null> => {
    const documentId = editor.extensionManager.extensions.find(ext => ext.name === 'drawio')?.options?.documentId
    if (!documentId || !token) return null

    try {
      // Validate file size
      if (blob.size > MAX_DRAWIO_PNG_SIZE) {
        toast.error(`Diagram preview too large (${(blob.size / 1024 / 1024).toFixed(1)} MB). Max is 10 MB.`)
        return null
      }

      const file = new File([blob], 'diagram.png', { type: 'image/png' })

      const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8001'
      const params = new URLSearchParams({
        entity_type: 'document',
        entity_id: documentId,
      })

      const formData = new FormData()
      formData.append('file', file)

      const uploadResponse = await fetch(`${apiUrl}/api/files/upload?${params.toString()}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
        signal,
      })

      if (!uploadResponse.ok) {
        const errorData = await uploadResponse.json().catch(() => ({}))
        throw new Error((errorData as { detail?: string }).detail || 'Failed to upload diagram preview')
      }

      const attachment = await uploadResponse.json() as { id: string }
      return { attachmentId: attachment.id }
    } catch (err) {
      if ((err as Error).name === 'AbortError') return null
      console.error('[DrawioNodeView] Failed to upload diagram preview:', err)
      toast.error('Failed to save diagram preview')
      return null
    }
  }, [editor, token])

  const handleSave = useCallback(async (xml: string, png: string) => {
    setModalOpen(false)

    // Defense-in-depth: only accept data: URLs
    if (!png.startsWith('data:')) {
      console.error('[DrawioNodeView] Unexpected non-data URL, aborting save')
      toast.error('Failed to process diagram preview')
      return
    }

    // Decode base64 once — reuse blob for both optimistic preview and upload
    let blob: Blob
    try {
      blob = dataUrlToBlob(png)
    } catch (err) {
      console.error('[DrawioNodeView] Failed to decode diagram preview:', err)
      toast.error('Failed to process diagram preview')
      return
    }

    // Create object URL for optimistic preview (lightweight reference to blob)
    const objectUrl = URL.createObjectURL(blob)
    setLocalPreviewUrl(objectUrl)

    // Update XML data immediately but keep old previewPng/attachmentId as
    // fallback for collaborators — only clear after upload succeeds.
    updateAttributes({ data: xml })

    // Abort any previous in-flight upload, then create a new controller
    abortControllerRef.current?.abort()
    const abortController = new AbortController()
    abortControllerRef.current = abortController

    // Track generation to ignore stale upload completions on rapid re-saves
    const generation = ++saveGenerationRef.current

    setIsUploading(true)
    const result = await uploadDrawioPng(blob, abortController.signal)

    // Guard: component may have unmounted or a newer save may have started
    if (editor.isDestroyed || generation !== saveGenerationRef.current) return

    setIsUploading(false)

    if (result) {
      // Single transaction: set attachmentId and clear legacy previewPng together.
      // localPreviewUrl is kept alive until the presigned URL effect resolves
      // (cleared inside the requestBatchUrl .then() callback to prevent flicker).
      updateAttributes({ attachmentId: result.attachmentId, previewPng: null })
    }
    // On failure: localPreviewUrl stays as fallback, old previewPng/attachmentId preserved
  }, [updateAttributes, uploadDrawioPng, editor])

  const handleContainerClick = useCallback(() => {
    if (justResizedRef.current) return
    setModalOpen(true)
  }, [])

  // Width-only resize — height follows aspect ratio
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsResizing(true)
    startXRef.current = e.clientX
    startWidthRef.current = containerRef.current?.offsetWidth || 0
    currentWidthRef.current = startWidthRef.current

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const diff = moveEvent.clientX - startXRef.current
      const newWidth = Math.max(100, startWidthRef.current + diff)
      currentWidthRef.current = newWidth
      if (containerRef.current) {
        containerRef.current.style.width = `${newWidth}px`
      }
    }

    const cleanup = () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
      resizeCleanupRef.current = null
    }

    const handleMouseUp = () => {
      setIsResizing(false)
      updateAttributes({ width: currentWidthRef.current })
      cleanup()
      // Suppress the click event that fires after mouseup
      justResizedRef.current = true
      setTimeout(() => { justResizedRef.current = false }, 200)
    }

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
    resizeCleanupRef.current = cleanup
  }, [updateAttributes])

  // Empty state — no diagram data yet
  if (!data) {
    return (
      <NodeViewWrapper className="node-drawio" data-drag-handle contentEditable={false}>
        <div
          className={cn(
            'relative group flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed border-muted-foreground/30 bg-muted/30 text-muted-foreground',
            isEditable && 'cursor-pointer hover:border-primary/50 hover:bg-muted/50 transition-colors',
            selected && isEditable && 'ring-2 ring-primary/50'
          )}
          style={{ minHeight: 120 }}
          onClick={isEditable ? handleContainerClick : undefined}
        >
          <svg className="h-8 w-8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="7" height="7" rx="1" />
            <rect x="14" y="3" width="7" height="7" rx="1" />
            <rect x="8.5" y="14" width="7" height="7" rx="1" />
            <path d="M10 7h4" />
            <path d="M7 10v2.5a1.5 1.5 0 001.5 1.5" />
            <path d="M17 10v2.5a1.5 1.5 0 01-1.5 1.5" />
          </svg>
          <span className="text-sm font-medium">
            {isEditable ? 'Click to create diagram' : 'Empty diagram'}
          </span>
        </div>
        {isEditable && (
          <DrawioModal
            open={modalOpen}
            initialXml=""
            onSave={handleSave}
            onClose={() => setModalOpen(false)}
          />
        )}
      </NodeViewWrapper>
    )
  }

  // Has data — show PNG preview
  return (
    <NodeViewWrapper className="node-drawio" data-drag-handle contentEditable={false}>
      <div
        ref={containerRef}
        className={cn(
          'relative group',
          !width && 'w-fit',
          isEditable && 'cursor-pointer',
          selected && isEditable && 'ring-2 ring-primary/50 rounded'
        )}
        style={{ width: width || undefined, maxWidth: '100%' }}
        onClick={isEditable ? handleContainerClick : undefined}
      >
        {resolvedPreviewUrl ? (
          <img
            src={resolvedPreviewUrl}
            alt="Diagram"
            className={cn('block h-auto rounded-md bg-white', width ? 'w-full' : 'max-w-full')}
            draggable={false}
          />
        ) : (
          <div className="flex items-center justify-center rounded-md border border-border bg-muted/30 text-muted-foreground" style={{ minHeight: 120 }}>
            <span className="text-sm">Diagram (preview unavailable)</span>
          </div>
        )}

        {/* Hover overlay — pointer-events-none so resize handle stays interactive */}
        {isEditable && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/0 group-hover:bg-black/20 transition-colors rounded-md pointer-events-none">
            <span className="text-sm font-medium text-white opacity-0 group-hover:opacity-100 transition-opacity bg-black/60 px-3 py-1.5 rounded-md">
              Click to edit diagram
            </span>
          </div>
        )}

        {/* Upload overlay */}
        {isUploading && (
          <div className="absolute inset-0 flex items-center justify-center bg-white/60 rounded-md z-20">
            <span className="text-xs text-muted-foreground">Saving preview...</span>
          </div>
        )}

        {/* Resize handle — edit mode only */}
        {isEditable && (
          <div
            onMouseDown={handleMouseDown}
            onClick={e => e.stopPropagation()}
            className={cn(
              'absolute bottom-0 right-0 w-5 h-5 cursor-se-resize z-10',
              'bg-primary/60 rounded-tl-sm opacity-0 group-hover:opacity-100 transition-opacity',
              isResizing && 'opacity-100'
            )}
            role="separator"
            aria-label="Drag to resize diagram"
            title="Drag to resize"
          />
        )}
      </div>

      {isEditable && (
        <DrawioModal
          open={modalOpen}
          initialXml={data}
          onSave={handleSave}
          onClose={() => setModalOpen(false)}
        />
      )}
    </NodeViewWrapper>
  )
}

// ============================================================================
// TipTap Node Extension
// ============================================================================

export const DrawioNode = Node.create({
  name: 'drawio',
  group: 'block',
  atom: true,
  draggable: true,

  addOptions() {
    return { documentId: null as string | null }
  },

  addAttributes() {
    return {
      data: {
        default: null,
        parseHTML: element => element.getAttribute('data-drawio-xml'),
        renderHTML: attributes => {
          if (!attributes.data) return {}
          return { 'data-drawio-xml': attributes.data }
        },
      },
      width: {
        default: null,
        parseHTML: element => {
          const w = element.getAttribute('width') || element.style.width
          if (!w) return null
          const parsed = parseInt(String(w), 10)
          return Number.isNaN(parsed) ? null : parsed
        },
        renderHTML: attributes => {
          if (!attributes.width) return {}
          return { width: attributes.width, style: `width: ${attributes.width}px` }
        },
      },
      attachmentId: {
        default: null,
        parseHTML: element => element.getAttribute('data-attachment-id'),
        renderHTML: attributes => {
          if (!attributes.attachmentId) return {}
          return { 'data-attachment-id': attributes.attachmentId }
        },
      },
      previewPng: {
        default: null,
        parseHTML: element => element.getAttribute('data-preview-png'),
        renderHTML: () => ({}),  // Legacy read-only; never re-serialize base64
      },
    }
  },

  parseHTML() {
    return [{ tag: 'div[data-type="drawio"]' }]
  },

  renderHTML({ HTMLAttributes }) {
    return ['div', mergeAttributes({ 'data-type': 'drawio' }, HTMLAttributes)]
  },

  addNodeView() {
    return ReactNodeViewRenderer(DrawioNodeView)
  },

  addCommands() {
    return {
      insertDrawio: () => ({ commands }) => {
        return commands.insertContent({ type: this.name, attrs: {} })
      },
    }
  },
})
