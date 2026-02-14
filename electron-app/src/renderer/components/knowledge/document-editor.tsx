/**
 * DocumentEditor Component
 *
 * Pure rich text editor for the knowledge base.
 * Composes the EditorToolbar + TipTap EditorContent + status bar.
 * Content is persisted as TipTap JSON (not HTML).
 *
 * When `editable=false`, shows read-only content without toolbar.
 * When `editable=true`, shows toolbar and allows editing.
 * Content sync: always syncs in view mode; only on initial load in edit mode.
 */

import { useEditor, EditorContent, useEditorState } from '@tiptap/react'
import type { Editor } from '@tiptap/core'
import { DOMParser } from '@tiptap/pm/model'
import { useCallback, useEffect, useRef } from 'react'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'
import { useAuthStore } from '@/contexts/auth-context'
import { createDocumentExtensions, type SetImageAttrs } from './editor-extensions'
import { EditorToolbar } from './editor-toolbar'
import { DocumentTimestamp } from './document-header'
import type { DocumentEditorProps } from './editor-types'
import './editor-styles.css'

/** Allowed image MIME types for client-side validation */
const ALLOWED_IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/gif', 'image/webp']

/** Escape HTML special characters for safe insertion */
function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

// ============================================================================
// EditorStatusBar -- reactive word + character count
// ============================================================================

function EditorStatusBar({ editor }: { editor: Editor }) {
  const { wordCount, charCount } = useEditorState({
    editor,
    selector: (ctx) => ({
      wordCount: ctx.editor?.storage.characterCount?.words() ?? 0,
      charCount: ctx.editor?.storage.characterCount?.characters() ?? 0,
    }),
  }) ?? { wordCount: 0, charCount: 0 }

  return (
    <div className="flex items-center justify-between px-3 py-1.5 border-t text-xs text-muted-foreground">
      <span>{wordCount} words</span>
      <span>{charCount} characters</span>
    </div>
  )
}

// ============================================================================
// DocumentEditor
// ============================================================================

export function DocumentEditor({
  content,
  onChange,
  editable = true,
  placeholder,
  className,
  updatedAt,
  onBaselineSync,
  documentId,
  searchTerms,
  scrollToOccurrence,
}: DocumentEditorProps) {
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const onChangeRef = useRef(onChange)
  const editableRef = useRef(editable)
  const onBaselineSyncRef = useRef(onBaselineSync)
  const token = useAuthStore((s) => s.token)

  // Keep refs current
  useEffect(() => {
    onChangeRef.current = onChange
  }, [onChange])

  useEffect(() => {
    editableRef.current = editable
  }, [editable])

  useEffect(() => {
    onBaselineSyncRef.current = onBaselineSync
  }, [onBaselineSync])

  // Image upload: POST to /api/files/upload, return presigned URL + attachmentId
  const uploadImage = useCallback(async (file: File): Promise<{ url: string; attachmentId: string } | null> => {
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

      // Fetch presigned download URL
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
      console.error('[DocumentEditor] Failed to upload image:', err)
      return null
    }
  }, [token, documentId])

  // Stable onUpdate handler using ref-based debounce
  const handleUpdate = useCallback(({ editor: ed }: { editor: ReturnType<typeof useEditor> extends infer E ? NonNullable<E> : never }) => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current)
    }
    debounceRef.current = setTimeout(() => {
      onChangeRef.current?.(ed.getJSON())
    }, 300)
  }, [])

  // Ref to hold uploadImage for use in editorProps closures
  const uploadImageRef = useRef(uploadImage)
  useEffect(() => { uploadImageRef.current = uploadImage }, [uploadImage])

  const editor = useEditor({
    extensions: createDocumentExtensions({ placeholder }),
    content: content || undefined,
    editable,
    onUpdate: handleUpdate,
    editorProps: {
      // Clean Excel/Google Sheets HTML on paste
      transformPastedHTML: (html: string) => {
        // Only clean spreadsheet HTML
        if (!html.includes('xmlns:x="urn:schemas-microsoft-com:office:excel"') &&
            !html.includes('ProgId="Excel') &&
            !html.includes('google-sheets-html-origin')) {
          return html
        }
        return html
          .replace(/<!--[\s\S]*?-->/g, '')
          .replace(/mso-[^;:"]+:[^;:"]+;?/gi, '')
          .replace(/class="[^"]*"/gi, '')
          .replace(/<col[^>]*>/gi, '')
          .replace(/<colgroup[^>]*>[\s\S]*?<\/colgroup>/gi, '')
          .replace(/width:\s*[\d.]+pt;?/gi, '')
          .replace(/height:\s*[\d.]+pt;?/gi, '')
      },
      handleClick: (_view, _pos, event) => {
        // In view mode, allow link clicks to open in new tab
        if (!editable) {
          // Find closest anchor tag (handles nested elements like <a><strong>text</strong></a>)
          const anchor = (event.target as HTMLElement).closest('a')
          if (anchor && anchor.hasAttribute('href')) {
            const href = anchor.getAttribute('href')
            // Security: Only allow safe URL schemes
            if (href && /^(https?:\/\/|mailto:|tel:)/.test(href)) {
              window.open(href, '_blank', 'noopener,noreferrer')
              event.preventDefault()
              return true
            }
          }
        }
        return false
      },
      // Handle paste for spreadsheet data and images
      handlePaste: (view, event) => {
        // TSV fallback for spreadsheet data (when no HTML is available)
        const htmlData = event.clipboardData?.getData('text/html') || ''
        const textData = event.clipboardData?.getData('text/plain') || ''
        if (!htmlData && textData && textData.includes('\t') && textData.includes('\n')) {
          const MAX_ROWS = 100
          const MAX_COLS = 50
          const allRows = textData.trim().split('\n')
          const rows = allRows.slice(0, MAX_ROWS).map(row => row.split('\t').slice(0, MAX_COLS))
          if (rows.length > 1 || (rows[0] && rows[0].length > 1)) {
            const rowsTruncated = allRows.length > MAX_ROWS
            const colsTruncated = allRows.some(row => row.split('\t').length > MAX_COLS)
            if (rowsTruncated || colsTruncated) {
              toast.info(`Table truncated to ${MAX_ROWS} rows × ${MAX_COLS} columns`)
            }
            event.preventDefault()
            const tableHtml = '<table>' +
              rows.map((row, i) =>
                '<tr>' + row.map(cell =>
                  `<${i === 0 ? 'th' : 'td'}>${escapeHtml(cell.trim())}</${i === 0 ? 'th' : 'td'}>`
                ).join('') + '</tr>'
              ).join('') + '</table>'
            // Use the schema to parse and insert the table
            const parser = DOMParser.fromSchema(view.state.schema)
            const doc = document.implementation.createHTMLDocument()
            doc.body.innerHTML = tableHtml
            const slice = parser.parseSlice(doc.body)
            const tr = view.state.tr.replaceSelection(slice)
            view.dispatch(tr)
            return true
          }
        }

        const items = event.clipboardData?.items
        if (!items) return false

        for (const item of items) {
          if (item.type.startsWith('image/')) {
            event.preventDefault()
            const file = item.getAsFile()
            if (file) {
              const insertPos = view.state.selection.from
              uploadImageRef.current(file).then((result) => {
                if (!result || view.isDestroyed) return
                const node = view.state.schema.nodes.image?.create({
                  src: result.url,
                  attachmentId: result.attachmentId,
                })
                if (node) {
                  const pos = Math.min(insertPos, view.state.doc.content.size)
                  const tr = view.state.tr.insert(pos, node)
                  view.dispatch(tr)
                }
              }).catch((err) => {
                toast.error('Failed to paste image')
                console.error('[DocumentEditor] Failed to paste image:', err)
              })
            }
            return true
          }
        }

        // Fallback: check clipboardData.files (File Explorer paste)
        const clipFiles = event.clipboardData?.files
        if (clipFiles && clipFiles.length > 0) {
          const clipFile = clipFiles[0]
          if (clipFile.type.startsWith('image/')) {
            event.preventDefault()
            const insertPos = view.state.selection.from
            uploadImageRef.current(clipFile).then((result) => {
              if (!result || view.isDestroyed) return
              const node = view.state.schema.nodes.image?.create({
                src: result.url,
                attachmentId: result.attachmentId,
              })
              if (node) {
                const pos = Math.min(insertPos, view.state.doc.content.size)
                const tr = view.state.tr.insert(pos, node)
                view.dispatch(tr)
              }
            }).catch((err) => {
              toast.error('Failed to paste image')
              console.error('[DocumentEditor] File explorer paste failed:', err)
            })
            return true
          }
        }

        return false
      },
      // Handle drop for images (supports multi-file drops)
      handleDrop: (view, event) => {
        const files = event.dataTransfer?.files
        if (!files || files.length === 0) return false

        const imageFiles = Array.from(files).filter(f => f.type.startsWith('image/'))
        if (imageFiles.length === 0) return false

        event.preventDefault()
        const dropCoords = view.posAtCoords({ left: event.clientX, top: event.clientY })
        if (!dropCoords) return true

        let nextPos = dropCoords.pos
        let chain = Promise.resolve()
        for (const file of imageFiles) {
          chain = chain.then(() =>
            uploadImageRef.current(file).then((result) => {
              if (!result || view.isDestroyed) return
              const node = view.state.schema.nodes.image?.create({
                src: result.url,
                attachmentId: result.attachmentId,
              })
              if (node) {
                const pos = Math.min(nextPos, view.state.doc.content.size)
                const tr = view.state.tr.insert(pos, node)
                view.dispatch(tr)
                nextPos = pos + node.nodeSize
              }
            }).catch((err) => {
              toast.error('Failed to upload image')
              console.error('[DocumentEditor] Drop image failed:', err)
            })
          )
        }
        return true
      },
    },
  })

  // Cleanup debounce timer on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current)
      }
    }
  }, [])

  // Sync editable state — emitUpdate: false prevents onUpdate from firing
  // during the view→edit transition, which would otherwise cause a false
  // dirty-detection (onUpdate fires with stale content before setContent runs).
  useEffect(() => {
    if (editor) {
      editor.setEditable(editable, false)
    }
  }, [editor, editable])

  // Sync content prop:
  // - In view mode (not editable): always sync to reflect latest server data
  // - In edit mode (editable): only sync if editor is not focused (initial load)
  // - When switching from edit to view: always sync to discard unsaved changes
  useEffect(() => {
    if (!editor || !content) return
    if (!editableRef.current || !editor.isFocused) {
      editor.commands.setContent(content)
      // After setContent in edit mode, sync TipTap-normalized JSON back to
      // parent for dirty-detection baseline (TipTap adds default attrs like
      // textAlign/indent that our raw JSON builders don't include).
      if (editableRef.current && onBaselineSyncRef.current) {
        onBaselineSyncRef.current(editor.getJSON())
      }
    }
  }, [editor, content, editable])

  // Apply search highlight decorations when searchTerms change, then scroll to target occurrence
  useEffect(() => {
    if (!editor || editor.isDestroyed) return
    if (searchTerms && searchTerms.length > 0) {
      editor.commands.setSearchHighlights(searchTerms)
      // Scroll to the target occurrence after decorations are rendered
      let rafId: number | undefined
      let timerId: ReturnType<typeof setTimeout> | undefined
      if (scrollToOccurrence != null && scrollToOccurrence >= 0) {
        rafId = requestAnimationFrame(() => {
          const scrollContainer = editor.view.dom.parentElement?.closest('.overflow-y-auto')
          const editorEl = scrollContainer ?? editor.view.dom.parentElement
          if (!editorEl) return
          const highlights = editorEl.querySelectorAll('.search-highlight')
          const target = highlights[scrollToOccurrence]
          if (target) {
            target.scrollIntoView({ behavior: 'smooth', block: 'center' })
            target.classList.add('search-highlight-active')
            timerId = setTimeout(() => target.classList.remove('search-highlight-active'), 2000)
          }
        })
      }
      return () => {
        if (rafId != null) cancelAnimationFrame(rafId)
        if (timerId != null) clearTimeout(timerId)
      }
    } else {
      editor.commands.clearSearchHighlights()
    }
  }, [editor, searchTerms, scrollToOccurrence])

  // Handle image upload from toolbar button (must be above early return for hooks rules)
  const handleToolbarImageUpload = useCallback((file: File) => {
    if (!editor || editor.isDestroyed) return
    uploadImage(file).then((result) => {
      if (!result || !editor || editor.isDestroyed) return
      editor.chain().focus().setImage({
        src: result.url,
        attachmentId: result.attachmentId,
      } as SetImageAttrs).run()
    }).catch((err) => {
      toast.error('Failed to upload image')
      console.error('[DocumentEditor] Toolbar image upload failed:', err)
    })
  }, [uploadImage, editor])

  if (!editor) {
    return null
  }

  return (
    <div className={cn('overflow-hidden bg-background flex flex-col min-h-0', className)}>
      {editable && <EditorToolbar editor={editor} onImageUpload={handleToolbarImageUpload} />}
      <div className="flex-1 overflow-y-auto min-h-0">
        {updatedAt && <DocumentTimestamp updatedAt={updatedAt} />}
        <EditorContent editor={editor} className="prose prose-sm max-w-none" />
      </div>
      <EditorStatusBar editor={editor} />
    </div>
  )
}
