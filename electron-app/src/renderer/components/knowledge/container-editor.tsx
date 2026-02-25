/**
 * ContainerEditor
 *
 * Lazy TipTap editor inside each canvas container. Renders static HTML
 * when inactive, mounts a full TipTap editor when active. Only one
 * TipTap instance exists across the entire canvas at any time.
 */

import { useEditor, EditorContent } from '@tiptap/react'
import type { Editor } from '@tiptap/core'
import { DOMParser } from '@tiptap/pm/model'
import { useEffect, useRef, useMemo, useCallback } from 'react'
import { toast } from 'sonner'
import { createDocumentExtensions, createStaticExtensions, updateImagePlaceholder, removeImagePlaceholder } from './editor-extensions'
import { generateStaticHTML, escapeHtml } from './canvas-utils'
import './editor-styles.css'
import './canvas-styles.css'

interface ContainerEditorProps {
  content: object
  isActive: boolean
  editable: boolean
  onChange: (json: object) => void
  onEditorReady: (editor: Editor | null) => void
  onOverflow?: (width: number) => void
  onImageUpload?: (file: File) => Promise<{ url: string; attachmentId: string } | null>
  documentId?: string
}

const staticExtensions = createStaticExtensions()

export function ContainerEditor({
  content,
  isActive,
  editable,
  onChange,
  onEditorReady,
  onOverflow,
  onImageUpload,
  documentId,
}: ContainerEditorProps) {
  const onChangeRef = useRef(onChange)
  useEffect(() => { onChangeRef.current = onChange }, [onChange])

  const onEditorReadyRef = useRef(onEditorReady)
  useEffect(() => { onEditorReadyRef.current = onEditorReady }, [onEditorReady])

  const onOverflowRef = useRef(onOverflow)
  useEffect(() => { onOverflowRef.current = onOverflow }, [onOverflow])

  const contentRef = useRef(content)
  contentRef.current = content

  const editorRef = useRef<Editor | null>(null)
  const isSyncingRef = useRef(false)
  const editorWrapperRef = useRef<HTMLDivElement>(null)
  const staticWrapperRef = useRef<HTMLDivElement>(null)
  const overflowRafRef = useRef<number | null>(null)

  const onImageUploadRef = useRef(onImageUpload)
  useEffect(() => { onImageUploadRef.current = onImageUpload }, [onImageUpload])

  /** Check if content overflows the wrapper element and notify parent */
  const checkOverflow = useCallback((el: HTMLElement | null) => {
    if (!el || !onOverflowRef.current) return
    if (el.clientWidth === 0) return  // element not yet laid out
    if (el.scrollWidth > el.clientWidth + 5) {
      onOverflowRef.current(el.scrollWidth)
    }
  }, [])

  // Memoize extensions to avoid recreating on each useEditor invocation
  // eslint-disable-next-line react-hooks/exhaustive-deps -- documentId is stable for the container's lifetime
  const extensions = useMemo(
    () => createDocumentExtensions({ placeholder: 'Type here...', documentId }),
    [documentId],
  )

  const editor = useEditor({
    extensions,
    content: content || undefined,
    editable,
    immediatelyRender: false,
    onUpdate: ({ editor: ed }) => {
      if (isSyncingRef.current) return
      onChangeRef.current(ed.getJSON())
      // Check for content overflow after DOM update (debounced)
      if (overflowRafRef.current !== null) cancelAnimationFrame(overflowRafRef.current)
      overflowRafRef.current = requestAnimationFrame(() => {
        checkOverflow(editorWrapperRef.current)
        overflowRafRef.current = null
      })
    },
    editorProps: {
      // Clean Excel/Google Sheets HTML on paste
      transformPastedHTML: (html: string) => {
        if (!html.includes('xmlns:x="urn:schemas-microsoft-com:office:excel"') &&
            !html.includes('ProgId="Excel') &&
            !html.includes('google-sheets-html-origin')) {
          return html
        }
        const tableMatch = html.match(/<table[\s\S]*<\/table>/i)
        if (!tableMatch) return html
        return tableMatch[0]
          .replace(/<!--[\s\S]*?-->/g, '')
          .replace(/<col[^>]*\/?>/gi, '')
          .replace(/<colgroup[^>]*>[\s\S]*?<\/colgroup>/gi, '')
          .replace(/<\/?(?:font|span)[^>]*>/gi, '')
          .replace(/\s*class="[^"]*"/gi, '')
          .replace(/\s*style="[^"]*"/gi, '')
          .replace(/\s*(?:width|height|border|cellpadding|cellspacing|align|valign)="[^"]*"/gi, '')
          .replace(/\s*xmlns:[a-z]+="[^"]*"/gi, '')
      },
      // Handle paste for spreadsheet TSV and images
      handlePaste: (view, event) => {
        // TSV fallback for spreadsheet data
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
            const parser = DOMParser.fromSchema(view.state.schema)
            const doc = document.implementation.createHTMLDocument()
            doc.body.innerHTML = tableHtml
            const slice = parser.parseSlice(doc.body)
            const tr = view.state.tr.replaceSelection(slice)
            view.dispatch(tr)
            return true
          }
        }

        // Image paste
        const uploadFn = onImageUploadRef.current
        if (!uploadFn) return false

        // When clipboard contains HTML (e.g. Excel/Sheets table), let TipTap's
        // transformPastedHTML handle it instead of intercepting the image.
        // Windows puts both HTML table data AND a PNG screenshot on the clipboard
        // when copying from Excel — we want the table, not the screenshot.
        const hasHtml = !!htmlData
        const items = event.clipboardData?.items
        if (items) {
          for (const item of items) {
            if (item.type.startsWith('image/') && !hasHtml) {
              event.preventDefault()
              const file = item.getAsFile()
              if (file) {
                const placeholderId = crypto.randomUUID()
                const placeholderNode = view.state.schema.nodes.image?.create({
                  src: '',
                  loading: true,
                  placeholderId,
                })
                if (placeholderNode) {
                  const pos = Math.min(view.state.selection.from, view.state.doc.content.size)
                  view.dispatch(view.state.tr.insert(pos, placeholderNode))
                }
                uploadFn(file).then((result) => {
                  if (view.isDestroyed) return
                  if (!result) {
                    removeImagePlaceholder(view, placeholderId)
                    return
                  }
                  updateImagePlaceholder(view, placeholderId, {
                    src: result.url,
                    attachmentId: result.attachmentId,
                  })
                }).catch(() => {
                  if (!view.isDestroyed) removeImagePlaceholder(view, placeholderId)
                  toast.error('Failed to paste image')
                })
              }
              return true
            }
          }
        }

        // Fallback: clipboardData.files (File Explorer paste)
        // Also skip when HTML is present (same Excel/Sheets guard as above)
        const clipFiles = event.clipboardData?.files
        if (clipFiles && clipFiles.length > 0 && !hasHtml) {
          const clipFile = clipFiles[0]
          if (clipFile.type.startsWith('image/')) {
            event.preventDefault()
            const placeholderId = crypto.randomUUID()
            const placeholderNode = view.state.schema.nodes.image?.create({
              src: '',
              loading: true,
              placeholderId,
            })
            if (placeholderNode) {
              const pos = Math.min(view.state.selection.from, view.state.doc.content.size)
              view.dispatch(view.state.tr.insert(pos, placeholderNode))
            }
            uploadFn(clipFile).then((result) => {
              if (view.isDestroyed) return
              if (!result) {
                removeImagePlaceholder(view, placeholderId)
                return
              }
              updateImagePlaceholder(view, placeholderId, {
                src: result.url,
                attachmentId: result.attachmentId,
              })
            }).catch(() => {
              if (!view.isDestroyed) removeImagePlaceholder(view, placeholderId)
              toast.error('Failed to paste image')
            })
            return true
          }
        }

        return false
      },
      // Handle image drop
      handleDrop: (view, event) => {
        const uploadFn = onImageUploadRef.current
        if (!uploadFn) return false

        const files = event.dataTransfer?.files
        if (!files || files.length === 0) return false

        const imageFiles = Array.from(files).filter(f => f.type.startsWith('image/'))
        if (imageFiles.length === 0) return false

        event.preventDefault()
        const dropCoords = view.posAtCoords({ left: event.clientX, top: event.clientY })
        if (!dropCoords) return true

        let tr = view.state.tr
        let offset = 0
        const placeholders: Array<{ file: File; id: string }> = []
        for (const file of imageFiles) {
          const placeholderId = crypto.randomUUID()
          const node = view.state.schema.nodes.image?.create({
            src: '',
            loading: true,
            placeholderId,
          })
          if (node) {
            const pos = Math.min(dropCoords.pos + offset, tr.doc.content.size)
            tr = tr.insert(pos, node)
            offset += node.nodeSize
          }
          placeholders.push({ file, id: placeholderId })
        }
        view.dispatch(tr)

        for (const { file, id } of placeholders) {
          uploadFn(file).then((result) => {
            if (view.isDestroyed) return
            if (!result) {
              removeImagePlaceholder(view, id)
              return
            }
            updateImagePlaceholder(view, id, {
              src: result.url,
              attachmentId: result.attachmentId,
            })
          }).catch(() => {
            if (!view.isDestroyed) removeImagePlaceholder(view, id)
            toast.error('Failed to upload image')
          })
        }
        return true
      },
    },
  }, [isActive])

  // Cleanup overflow RAF on unmount
  useEffect(() => {
    return () => {
      if (overflowRafRef.current !== null) cancelAnimationFrame(overflowRafRef.current)
    }
  }, [])

  // Keep editorRef in sync for cleanup
  useEffect(() => {
    editorRef.current = editor ?? null
  }, [editor])

  // When becoming active: set content and notify parent; on deactivation: clean up
  // eslint-disable-next-line react-hooks/exhaustive-deps -- content is intentionally excluded: TipTap manages its own state once active, and including content would reset the editor on every parent re-render
  useEffect(() => {
    if (!isActive) return
    if (!editor) return

    isSyncingRef.current = true
    editor.commands.setContent(content)
    queueMicrotask(() => { isSyncingRef.current = false })
    onEditorReadyRef.current(editor)

    // Check for overflow after editor content is set
    requestAnimationFrame(() => {
      checkOverflow(editorWrapperRef.current)
    })

    return () => {
      // Don't unconditionally push content back - the onUpdate handler
      // already keeps state in sync during active editing.
      // Pushing here causes cancel/discard to fail because it writes
      // dirty content into canvas state right as we're trying to revert.
      onEditorReadyRef.current(null)
    }
  }, [editor, isActive, checkOverflow])

  useEffect(() => {
    if (editor && !editor.isDestroyed) {
      editor.setEditable(editable, false)
    }
  }, [editor, editable])

  const staticHTML = useMemo(() => {
    if (isActive) return ''
    return generateStaticHTML(content, staticExtensions)
  }, [content, isActive])

  // Check for overflow in static preview after render (RAF avoids forced reflow)
  useEffect(() => {
    if (isActive) return
    const id = requestAnimationFrame(() => {
      checkOverflow(staticWrapperRef.current)
    })
    return () => cancelAnimationFrame(id)
  }, [isActive, staticHTML, checkOverflow])

  // Active state: show editor or loading skeleton while it mounts
  if (isActive) {
    if (editor) {
      return (
        <div ref={editorWrapperRef} className="canvas-editor-content">
          <EditorContent editor={editor} className="max-w-none" />
        </div>
      )
    }
    return (
      <div className="canvas-static-preview max-w-none">
        <div className="h-4 w-3/4 rounded bg-muted animate-pulse mt-1" />
        <div className="h-4 w-1/2 rounded bg-muted animate-pulse mt-1.5" />
      </div>
    )
  }

  return (
    <div ref={staticWrapperRef} className="canvas-static-preview max-w-none">
      <div
        className="ProseMirror"
        dangerouslySetInnerHTML={{ __html: staticHTML }}
      />
    </div>
  )
}
