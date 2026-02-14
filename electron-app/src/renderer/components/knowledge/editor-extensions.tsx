/**
 * Knowledge Base Editor Extensions
 *
 * Single factory function that configures ALL TipTap extensions upfront.
 * Later plans (03-02 through 03-04) only add toolbar UI sections --
 * the extensions themselves are already registered here.
 */

import { Extension, RawCommands } from '@tiptap/core'
import { ReactNodeViewRenderer, NodeViewWrapper } from '@tiptap/react'
import type { NodeViewProps } from '@tiptap/react'
import Image from '@tiptap/extension-image'
import type { Transaction, EditorState } from '@tiptap/pm/state'
import type { Node as ProseMirrorNode } from '@tiptap/pm/model'
import StarterKit from '@tiptap/starter-kit'
import Underline from '@tiptap/extension-underline'
import TextStyle from '@tiptap/extension-text-style'
import FontFamily from '@tiptap/extension-font-family'
import Color from '@tiptap/extension-color'
import Highlight from '@tiptap/extension-highlight'
import TextAlign from '@tiptap/extension-text-align'
import Link from '@tiptap/extension-link'
import Table from '@tiptap/extension-table'
import TableRow from '@tiptap/extension-table-row'
import TableCell from '@tiptap/extension-table-cell'
import TableHeader from '@tiptap/extension-table-header'
import TaskList from '@tiptap/extension-task-list'
import TaskItem from '@tiptap/extension-task-item'
import CodeBlockLowlight from '@tiptap/extension-code-block-lowlight'
import CharacterCount from '@tiptap/extension-character-count'
import Placeholder from '@tiptap/extension-placeholder'
import { SearchHighlight } from './search-highlight-extension'
import { common, createLowlight } from 'lowlight'
import { useState, useRef, useCallback, useEffect } from 'react'
import { useGetDownloadUrls } from '@/hooks/use-attachments'
import { cn } from '@/lib/utils'

// ============================================================================
// Batch URL Resolution
// ============================================================================

// Collects attachment IDs from concurrently mounting ResizableImageView
// instances and resolves them in a single batch API call.
let pendingIds = new Set<string>()
let pendingResolvers: Array<{ resolve: (urls: Record<string, string>) => void }> = []
let batchTimer: ReturnType<typeof setTimeout> | null = null

function requestBatchUrl(
  attachmentId: string,
  fetchBatch: (ids: string[]) => Promise<Record<string, string>>
): Promise<string | null> {
  return new Promise<string | null>((resolve) => {
    pendingIds.add(attachmentId)

    const wrappedResolve = (urls: Record<string, string>) => {
      resolve(urls[attachmentId] || null)
    }
    pendingResolvers.push({ resolve: wrappedResolve })

    if (batchTimer) clearTimeout(batchTimer)
    batchTimer = setTimeout(async () => {
      const ids = [...pendingIds]
      const resolvers = pendingResolvers
      pendingIds = new Set()
      pendingResolvers = []
      batchTimer = null

      try {
        const urls = await fetchBatch(ids)
        for (const r of resolvers) {
          r.resolve(urls)
        }
      } catch (err) {
        console.error('[ResizableImageView] Batch URL fetch failed:', err)
        for (const r of resolvers) {
          r.resolve({})
        }
      }
    }, 50) // 50ms debounce to collect all mounting NodeViews
  })
}

// ============================================================================
// Type Helpers
// ============================================================================

/** Type helper for setImage with extra attributes (attachmentId, width).
 *  Use with a type assertion at the call site:
 *    editor.chain().focus().setImage({ src, attachmentId } as SetImageAttrs).run()
 */
export type SetImageAttrs = {
  src: string
  alt?: string
  title?: string
  attachmentId?: string
  width?: number
}

// ============================================================================
// Custom Extensions (copied from RichTextEditor.tsx)
// ============================================================================

// Custom FontSize extension - extends TextStyle to support font-size
const FontSize = Extension.create({
  name: 'fontSize',

  addOptions() {
    return {
      types: ['textStyle'],
    }
  },

  addGlobalAttributes() {
    return [
      {
        types: this.options.types,
        attributes: {
          fontSize: {
            default: null,
            parseHTML: element => element.style.fontSize?.replace(/['"]+/g, '') || null,
            renderHTML: attributes => {
              if (!attributes.fontSize) {
                return {}
              }
              return {
                style: `font-size: ${attributes.fontSize}`,
              }
            },
          },
        },
      },
    ]
  },
})

// Custom Indent extension - adds margin-left based indentation for paragraph/heading nodes
const INDENT_STEP = 40
const MAX_INDENT_LEVEL = 8

const Indent = Extension.create({
  name: 'indent',

  addGlobalAttributes() {
    return [
      {
        types: ['paragraph', 'heading'],
        attributes: {
          indent: {
            default: 0,
            parseHTML: element => {
              const marginLeft = element.style.marginLeft
              if (!marginLeft) return 0
              return Math.round(parseInt(marginLeft, 10) / INDENT_STEP) || 0
            },
            renderHTML: attributes => {
              if (!attributes.indent || attributes.indent <= 0) return {}
              return {
                style: `margin-left: ${attributes.indent * INDENT_STEP}px`,
              }
            },
          },
        },
      },
    ]
  },

  addCommands() {
    return {
      indent: () => ({ tr, state, dispatch }: { tr: Transaction; state: EditorState; dispatch?: (tr: Transaction) => void }) => {
        const { selection } = state
        const { from, to } = selection
        let changed = false
        state.doc.nodesBetween(from, to, (node: ProseMirrorNode, pos: number) => {
          if (node.type.name === 'paragraph' || node.type.name === 'heading') {
            const currentIndent = node.attrs.indent || 0
            if (currentIndent < MAX_INDENT_LEVEL) {
              if (dispatch) {
                tr.setNodeMarkup(pos, undefined, {
                  ...node.attrs,
                  indent: currentIndent + 1,
                })
              }
              changed = true
            }
          }
        })
        return changed
      },
      outdent: () => ({ tr, state, dispatch }: { tr: Transaction; state: EditorState; dispatch?: (tr: Transaction) => void }) => {
        const { selection } = state
        const { from, to } = selection
        let changed = false
        state.doc.nodesBetween(from, to, (node: ProseMirrorNode, pos: number) => {
          if (node.type.name === 'paragraph' || node.type.name === 'heading') {
            const currentIndent = node.attrs.indent || 0
            if (currentIndent > 0) {
              if (dispatch) {
                tr.setNodeMarkup(pos, undefined, {
                  ...node.attrs,
                  indent: currentIndent - 1,
                })
              }
              changed = true
            }
          }
        })
        return changed
      },
    } as Partial<RawCommands>
  },
})

// ============================================================================
// Resizable Image Node View
// ============================================================================

function ResizableImageView({ node, updateAttributes, selected, editor }: NodeViewProps) {
  const [isResizing, setIsResizing] = useState(false)
  const [resolvedSrc, setResolvedSrc] = useState<string>(node.attrs.src || '')
  const imageRef = useRef<HTMLImageElement>(null)
  const startXRef = useRef(0)
  const startWidthRef = useRef(0)
  const getDownloadUrls = useGetDownloadUrls()

  // Refresh presigned URL on mount when attachmentId is present.
  // Uses batch collector to coalesce concurrent mounts into a single API call.
  // Only updates local display state -- does NOT call updateAttributes to avoid
  // marking the document as dirty when the user has made no edits.
  useEffect(() => {
    const attachmentId = node.attrs.attachmentId
    if (!attachmentId) return

    let cancelled = false
    requestBatchUrl(attachmentId, getDownloadUrls).then((freshUrl) => {
      if (cancelled || !freshUrl) return
      setResolvedSrc(freshUrl)
    })

    return () => { cancelled = true }
  }, [node.attrs.attachmentId, getDownloadUrls])

  const currentWidthRef = useRef(0)

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsResizing(true)
    startXRef.current = e.clientX
    startWidthRef.current = imageRef.current?.offsetWidth || 0
    currentWidthRef.current = startWidthRef.current

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const diff = moveEvent.clientX - startXRef.current
      const newWidth = Math.max(50, startWidthRef.current + diff)
      currentWidthRef.current = newWidth
      // Visual feedback only -- no ProseMirror transaction
      if (imageRef.current) {
        imageRef.current.style.width = `${newWidth}px`
      }
    }

    const handleMouseUp = () => {
      setIsResizing(false)
      // Single ProseMirror transaction = single undo step
      updateAttributes({ width: currentWidthRef.current })
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
  }, [updateAttributes])

  return (
    <NodeViewWrapper className="inline-block relative" data-drag-handle>
      <div className={cn('inline-block relative group', selected && editor.isEditable && 'ring-2 ring-primary/50 rounded')}>
        <img
          ref={imageRef}
          src={resolvedSrc}
          alt={node.attrs.alt || ''}
          title={node.attrs.title || ''}
          width={node.attrs.width || undefined}
          className="max-w-full h-auto rounded-md block"
          style={node.attrs.width ? { width: `${node.attrs.width}px` } : undefined}
          draggable={false}
        />
        {/* Resize handle - only in edit mode */}
        {editor.isEditable && (
          <div
            onMouseDown={handleMouseDown}
            className={cn(
              'absolute bottom-0 right-0 w-4 h-4 cursor-se-resize',
              'bg-primary/60 rounded-tl-sm opacity-0 group-hover:opacity-100 transition-opacity',
              isResizing && 'opacity-100'
            )}
            title="Drag to resize"
          />
        )}
      </div>
    </NodeViewWrapper>
  )
}

// Custom resizable Image extension with persistent attachmentId
const ResizableImage = Image.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      width: {
        default: null,
        parseHTML: element => {
          const width = element.getAttribute('width') || element.style.width
          if (!width) return null
          const parsed = parseInt(String(width), 10)
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
    }
  },

  addNodeView() {
    return ReactNodeViewRenderer(ResizableImageView)
  },
})

// ============================================================================
// Constants
// ============================================================================

export const COLORS = [
  // Grays
  '#000000', '#1f2937', '#374151', '#6b7280', '#9ca3af', '#d1d5db',
  // Reds
  '#7f1d1d', '#991b1b', '#dc2626', '#ef4444', '#f87171', '#fca5a5',
  // Oranges
  '#7c2d12', '#c2410c', '#ea580c', '#f97316', '#fb923c', '#fdba74',
  // Yellows
  '#713f12', '#a16207', '#ca8a04', '#eab308', '#facc15', '#fde047',
  // Greens
  '#14532d', '#166534', '#16a34a', '#22c55e', '#4ade80', '#86efac',
  // Teals
  '#134e4a', '#115e59', '#0d9488', '#14b8a6', '#2dd4bf', '#5eead4',
  // Blues
  '#1e3a5f', '#1e40af', '#2563eb', '#3b82f6', '#60a5fa', '#93c5fd',
  // Indigos
  '#312e81', '#3730a3', '#4f46e5', '#6366f1', '#818cf8', '#a5b4fc',
  // Purples
  '#581c87', '#7e22ce', '#9333ea', '#a855f7', '#c084fc', '#d8b4fe',
  // Pinks
  '#831843', '#be185d', '#ec4899', '#f472b6', '#f9a8d4', '#fbcfe8',
]

export const HIGHLIGHT_COLORS = [
  // Yellows
  '#fef9c3', '#fef3c7', '#fde68a', '#fcd34d',
  // Pinks
  '#fce7f3', '#fbcfe8', '#f9a8d4', '#f472b6',
  // Blues
  '#dbeafe', '#bfdbfe', '#93c5fd', '#60a5fa',
  // Greens
  '#d1fae5', '#a7f3d0', '#6ee7b7', '#34d399',
  // Purples
  '#f3e8ff', '#e9d5ff', '#d8b4fe', '#c084fc',
  // Teals
  '#ccfbf1', '#99f6e4', '#5eead4', '#2dd4bf',
  // Reds
  '#fee2e2', '#fecaca', '#fca5a5', '#f87171',
  // Indigos
  '#e0e7ff', '#c7d2fe', '#a5b4fc', '#818cf8',
  // Oranges
  '#ffedd5', '#fed7aa', '#fdba74', '#fb923c',
  // Grays
  '#f3f4f6', '#e5e7eb', '#d1d5db', '#9ca3af',
]

export const FONT_SIZES = [
  { label: 'Small', value: '0.875rem' },
  { label: 'Normal', value: '1rem' },
  { label: 'Large', value: '1.25rem' },
  { label: 'Heading', value: '1.5rem' },
]

export const FONT_FAMILIES = [
  { label: 'Arial (Default)', value: 'Arial, sans-serif' },
  { label: 'Sans Serif', value: 'ui-sans-serif, system-ui, sans-serif' },
  { label: 'Serif', value: 'ui-serif, Georgia, serif' },
  { label: 'Mono', value: 'ui-monospace, monospace' },
  { label: 'Times New Roman', value: 'Times New Roman, serif' },
  { label: 'Georgia', value: 'Georgia, serif' },
  { label: 'Verdana', value: 'Verdana, sans-serif' },
  { label: 'Tahoma', value: 'Tahoma, sans-serif' },
  { label: 'Trebuchet MS', value: 'Trebuchet MS, sans-serif' },
  { label: 'Courier New', value: 'Courier New, monospace' },
]

export const DEFAULT_FONT_FAMILY = 'Arial, sans-serif'

// ============================================================================
// Extension Factory
// ============================================================================

/**
 * Creates the complete set of TipTap extensions for the knowledge base editor.
 * All extensions are configured upfront; subsequent plans only add toolbar UI.
 */
export function createDocumentExtensions(options?: { placeholder?: string }) {
  const lowlight = createLowlight(common)

  return [
    StarterKit.configure({
      heading: { levels: [1, 2, 3, 4, 5, 6] },
      codeBlock: false, // Use CodeBlockLowlight instead
    }),
    Underline,
    TextStyle,
    FontFamily,
    FontSize,
    Indent,
    Color,
    Highlight.configure({
      multicolor: true,
    }),
    TextAlign.configure({
      types: ['heading', 'paragraph'],
    }),
    Link.configure({
      openOnClick: false,
      autolink: true,
      linkOnPaste: true,
      defaultProtocol: 'https',
      HTMLAttributes: {
        class: 'text-primary underline cursor-pointer',
        rel: 'noopener noreferrer',
      },
    }),
    Table.configure({
      resizable: true,
      HTMLAttributes: {
        class: 'border-collapse border border-border w-full',
      },
    }),
    TableRow,
    TableCell.configure({
      HTMLAttributes: {
        class: 'border border-border p-2',
      },
    }),
    TableHeader.configure({
      HTMLAttributes: {
        class: 'border border-border p-2 bg-muted font-semibold',
      },
    }),
    TaskList.configure({
      HTMLAttributes: {
        class: 'not-prose',
      },
    }),
    TaskItem.configure({
      nested: true,
    }),
    CodeBlockLowlight.configure({
      lowlight,
      defaultLanguage: 'plaintext',
      HTMLAttributes: {
        class: 'rounded-md bg-muted p-4 font-mono text-sm overflow-x-auto',
      },
    }),
    ResizableImage.configure({
      inline: true,
      HTMLAttributes: {
        class: 'max-w-full h-auto rounded-md',
      },
    }),
    CharacterCount,
    Placeholder.configure({
      placeholder: options?.placeholder || 'Start writing...',
    }),
    SearchHighlight,
  ]
}
