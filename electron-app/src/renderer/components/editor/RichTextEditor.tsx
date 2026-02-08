/**
 * RichTextEditor Component
 *
 * Full-featured rich text editor for task descriptions.
 * Features:
 * - Bold, italic, underline, strikethrough
 * - Text alignment (left, center, right, justify)
 * - Text colors and highlights
 * - Font families and sizes
 * - Bullet and numbered lists
 * - Tables with resizable columns
 * - Images with skeleton loading
 * - Code blocks
 * - Read-only mode for Done/archived tasks
 */

import { useEditor, EditorContent, Editor, Extension, NodeViewWrapper, NodeViewProps, ReactNodeViewRenderer } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Underline from '@tiptap/extension-underline'
import TextAlign from '@tiptap/extension-text-align'
import Highlight from '@tiptap/extension-highlight'
import Image from '@tiptap/extension-image'
import Link from '@tiptap/extension-link'
import Table from '@tiptap/extension-table'
import TableRow from '@tiptap/extension-table-row'
import TableCell from '@tiptap/extension-table-cell'
import TableHeader from '@tiptap/extension-table-header'
import TextStyle from '@tiptap/extension-text-style'
import Color from '@tiptap/extension-color'
import FontFamily from '@tiptap/extension-font-family'
import Placeholder from '@tiptap/extension-placeholder'

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
      indent: () => ({ tr, state, dispatch }) => {
        const { selection } = state
        const { from, to } = selection
        let changed = false
        state.doc.nodesBetween(from, to, (node, pos) => {
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
      outdent: () => ({ tr, state, dispatch }) => {
        const { selection } = state
        const { from, to } = selection
        let changed = false
        state.doc.nodesBetween(from, to, (node, pos) => {
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
    }
  },
})

// ============================================================================
// Resizable Image Node View
// ============================================================================

function ResizableImageView({ node, updateAttributes, selected }: NodeViewProps) {
  const [isResizing, setIsResizing] = useState(false)
  const imageRef = useRef<HTMLImageElement>(null)
  const startXRef = useRef(0)
  const startWidthRef = useRef(0)

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsResizing(true)
    startXRef.current = e.clientX
    startWidthRef.current = imageRef.current?.offsetWidth || 0

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const diff = moveEvent.clientX - startXRef.current
      const newWidth = Math.max(50, startWidthRef.current + diff)
      updateAttributes({ width: newWidth })
    }

    const handleMouseUp = () => {
      setIsResizing(false)
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
  }, [updateAttributes])

  return (
    <NodeViewWrapper className="inline-block relative" data-drag-handle>
      <div className={cn('inline-block relative group', selected && 'ring-2 ring-primary/50 rounded')}>
        <img
          ref={imageRef}
          src={node.attrs.src}
          alt={node.attrs.alt || ''}
          title={node.attrs.title || ''}
          width={node.attrs.width || undefined}
          className="max-w-full h-auto rounded-md block"
          style={node.attrs.width ? { width: `${node.attrs.width}px` } : undefined}
          draggable={false}
        />
        {/* Resize handle - bottom right corner */}
        <div
          onMouseDown={handleMouseDown}
          className={cn(
            'absolute bottom-0 right-0 w-4 h-4 cursor-se-resize',
            'bg-primary/60 rounded-tl-sm opacity-0 group-hover:opacity-100 transition-opacity',
            isResizing && 'opacity-100'
          )}
          title="Drag to resize"
        />
      </div>
    </NodeViewWrapper>
  )
}

// Custom resizable Image extension
const ResizableImage = Image.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      width: {
        default: null,
        parseHTML: element => {
          const width = element.getAttribute('width') || element.style.width
          return width ? parseInt(String(width), 10) : null
        },
        renderHTML: attributes => {
          if (!attributes.width) return {}
          return { width: attributes.width, style: `width: ${attributes.width}px` }
        },
      },
    }
  },

  addNodeView() {
    return ReactNodeViewRenderer(ResizableImageView)
  },
})

// Helper function to set font size
function setFontSize(editor: Editor, fontSize: string) {
  editor.chain().focus().setMark('textStyle', { fontSize }).run()
}

// Helper function to set font family
function setFontFamilyHelper(editor: Editor, fontFamily: string) {
  editor.chain().focus().setFontFamily(fontFamily).run()
}
import { useState, useCallback, useEffect, useRef } from 'react'
import {
  Bold,
  Italic,
  Underline as UnderlineIcon,
  Strikethrough,
  AlignLeft,
  AlignCenter,
  AlignRight,
  AlignJustify,
  List,
  ListOrdered,
  Code,
  Highlighter,
  Image as ImageIcon,
  Table as TableIcon,
  Link as LinkIcon,
  Undo,
  Redo,
  ChevronDown,
  Palette,
  Type,
  Plus,
  Trash2,
  IndentIncrease,
  IndentDecrease,
  AlertCircle,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { useAuthStore } from '@/contexts/auth-context'

// ============================================================================
// Types
// ============================================================================

export interface RichTextEditorProps {
  value?: string
  onChange?: (value: string) => void
  placeholder?: string
  readOnly?: boolean
  className?: string
  /** Max content length in bytes (default 500KB) */
  maxLength?: number
  /** Max height of the editor content area (default '600px') */
  maxHeight?: string
  /** Callback when image is uploaded */
  onImageUpload?: (file: File) => Promise<string>
  /** Callback when an error occurs (e.g. image upload failure) */
  onError?: (message: string) => void
}

interface ToolbarButtonProps {
  onClick: () => void
  isActive?: boolean
  disabled?: boolean
  title: string
  children: React.ReactNode
}

// ============================================================================
// Constants
// ============================================================================

const COLORS = [
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

const HIGHLIGHT_COLORS = [
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

const FONT_SIZES = [
  { label: 'Small', value: '0.875rem' },
  { label: 'Normal', value: '1rem' },
  { label: 'Large', value: '1.25rem' },
  { label: 'Heading', value: '1.5rem' },
]

const FONT_FAMILIES = [
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

const DEFAULT_FONT_FAMILY = 'Arial, sans-serif'

// ============================================================================
// Toolbar Button Component
// ============================================================================

function ToolbarButton({
  onClick,
  isActive,
  disabled,
  title,
  children,
}: ToolbarButtonProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={cn(
        'p-1.5 rounded hover:bg-muted transition-colors',
        isActive && 'bg-muted text-primary',
        disabled && 'opacity-50 cursor-not-allowed'
      )}
    >
      {children}
    </button>
  )
}

// ============================================================================
// Toolbar Component
// ============================================================================

interface ToolbarProps {
  editor: Editor
  uploadImage: (file: File) => Promise<string | null>
}

function Toolbar({ editor, uploadImage }: ToolbarProps) {
  const [isUploading, setIsUploading] = useState(false)
  const [linkDialogOpen, setLinkDialogOpen] = useState(false)
  const [linkUrl, setLinkUrl] = useState('')
  const linkInputRef = useRef<HTMLInputElement>(null)

  // Image upload handler - opens file picker
  const handleImageUpload = useCallback(async () => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'image/*'
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0]
      if (!file) return

      setIsUploading(true)
      try {
        const url = await uploadImage(file)
        if (url) {
          editor.chain().focus().setImage({ src: url }).run()
        }
      } catch (err) {
        console.error('Failed to upload image:', err)
      } finally {
        setIsUploading(false)
      }
    }
    input.click()
  }, [editor, uploadImage])

  // Table insert handler
  const handleInsertTable = useCallback(() => {
    editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()
  }, [editor])

  // Link handler - opens inline dialog
  const handleLink = useCallback(() => {
    const previousUrl = editor.getAttributes('link').href || ''
    setLinkUrl(previousUrl)
    setLinkDialogOpen(true)
    setTimeout(() => linkInputRef.current?.focus(), 50)
  }, [editor])

  const applyLink = useCallback(() => {
    let url = linkUrl.trim()
    if (url === '') {
      editor.chain().focus().extendMarkRange('link').unsetLink().run()
    } else {
      // Auto-prepend https:// if no protocol
      if (url && !/^https?:\/\//i.test(url)) {
        url = 'https://' + url
      }
      editor.chain().focus().extendMarkRange('link').setLink({ href: url }).run()
    }
    setLinkDialogOpen(false)
    setLinkUrl('')
  }, [editor, linkUrl])

  const removeLink = useCallback(() => {
    editor.chain().focus().extendMarkRange('link').unsetLink().run()
    setLinkDialogOpen(false)
    setLinkUrl('')
  }, [editor])

  return (
    <div className="relative flex flex-wrap items-center gap-1 p-2 border-b bg-muted/30">
      {/* Undo/Redo */}
      <div className="flex items-center gap-0.5 pr-2 border-r">
        <ToolbarButton
          onClick={() => editor.chain().focus().undo().run()}
          disabled={!editor.can().undo()}
          title="Undo"
        >
          <Undo className="h-4 w-4" />
        </ToolbarButton>
        <ToolbarButton
          onClick={() => editor.chain().focus().redo().run()}
          disabled={!editor.can().redo()}
          title="Redo"
        >
          <Redo className="h-4 w-4" />
        </ToolbarButton>
      </div>

      {/* Text Formatting */}
      <div className="flex items-center gap-0.5 pr-2 border-r">
        <ToolbarButton
          onClick={() => editor.chain().focus().toggleBold().run()}
          isActive={editor.isActive('bold')}
          title="Bold (Ctrl+B)"
        >
          <Bold className="h-4 w-4" />
        </ToolbarButton>
        <ToolbarButton
          onClick={() => editor.chain().focus().toggleItalic().run()}
          isActive={editor.isActive('italic')}
          title="Italic (Ctrl+I)"
        >
          <Italic className="h-4 w-4" />
        </ToolbarButton>
        <ToolbarButton
          onClick={() => editor.chain().focus().toggleUnderline().run()}
          isActive={editor.isActive('underline')}
          title="Underline (Ctrl+U)"
        >
          <UnderlineIcon className="h-4 w-4" />
        </ToolbarButton>
        <ToolbarButton
          onClick={() => editor.chain().focus().toggleStrike().run()}
          isActive={editor.isActive('strike')}
          title="Strikethrough"
        >
          <Strikethrough className="h-4 w-4" />
        </ToolbarButton>
        <ToolbarButton
          onClick={() => editor.chain().focus().toggleCode().run()}
          isActive={editor.isActive('code')}
          title="Code"
        >
          <Code className="h-4 w-4" />
        </ToolbarButton>
      </div>

      {/* Text Color */}
      <div className="flex items-center gap-0.5 pr-2 border-r">
        <Popover>
          <PopoverTrigger asChild>
            <button
              type="button"
              className="flex items-center gap-1 p-1.5 rounded hover:bg-muted transition-colors"
              title="Text Color"
            >
              <Palette className="h-4 w-4" />
              <ChevronDown className="h-3 w-3" />
            </button>
          </PopoverTrigger>
          <PopoverContent className="w-auto p-2">
            <div className="grid grid-cols-6 gap-1">
              {COLORS.map((color) => (
                <button
                  key={color}
                  type="button"
                  onClick={() => editor.chain().focus().setColor(color).run()}
                  className="w-6 h-6 rounded border border-border hover:scale-110 transition-transform"
                  style={{ backgroundColor: color }}
                  title={color}
                />
              ))}
            </div>
            <button
              type="button"
              onClick={() => editor.chain().focus().unsetColor().run()}
              className="mt-2 w-full text-xs text-center py-1 rounded hover:bg-muted text-muted-foreground transition-colors"
            >
              Reset color
            </button>
          </PopoverContent>
        </Popover>

        <Popover>
          <PopoverTrigger asChild>
            <button
              type="button"
              className={cn(
                'flex items-center gap-1 p-1.5 rounded hover:bg-muted transition-colors',
                editor.isActive('highlight') && 'bg-muted text-primary'
              )}
              title="Highlight"
            >
              <Highlighter className="h-4 w-4" />
              <ChevronDown className="h-3 w-3" />
            </button>
          </PopoverTrigger>
          <PopoverContent className="w-auto p-2">
            <div className="grid grid-cols-4 gap-1">
              {HIGHLIGHT_COLORS.map((color) => (
                <button
                  key={color}
                  type="button"
                  onClick={() => editor.chain().focus().toggleHighlight({ color }).run()}
                  className="w-6 h-6 rounded border border-border hover:scale-110 transition-transform"
                  style={{ backgroundColor: color }}
                  title={color}
                />
              ))}
            </div>
            <button
              type="button"
              onClick={() => editor.chain().focus().unsetHighlight().run()}
              className="mt-2 w-full text-xs text-center py-1 rounded hover:bg-muted text-muted-foreground transition-colors"
            >
              Remove highlight
            </button>
          </PopoverContent>
        </Popover>
      </div>

      {/* Alignment */}
      <div className="flex items-center gap-0.5 pr-2 border-r">
        <ToolbarButton
          onClick={() => editor.chain().focus().setTextAlign('left').run()}
          isActive={editor.isActive({ textAlign: 'left' })}
          title="Align Left"
        >
          <AlignLeft className="h-4 w-4" />
        </ToolbarButton>
        <ToolbarButton
          onClick={() => editor.chain().focus().setTextAlign('center').run()}
          isActive={editor.isActive({ textAlign: 'center' })}
          title="Align Center"
        >
          <AlignCenter className="h-4 w-4" />
        </ToolbarButton>
        <ToolbarButton
          onClick={() => editor.chain().focus().setTextAlign('right').run()}
          isActive={editor.isActive({ textAlign: 'right' })}
          title="Align Right"
        >
          <AlignRight className="h-4 w-4" />
        </ToolbarButton>
        <ToolbarButton
          onClick={() => editor.chain().focus().setTextAlign('justify').run()}
          isActive={editor.isActive({ textAlign: 'justify' })}
          title="Justify"
        >
          <AlignJustify className="h-4 w-4" />
        </ToolbarButton>
      </div>

      {/* Lists & Indentation */}
      <div className="flex items-center gap-0.5 pr-2 border-r">
        <ToolbarButton
          onClick={() => editor.chain().focus().toggleBulletList().run()}
          isActive={editor.isActive('bulletList')}
          title="Bullet List"
        >
          <List className="h-4 w-4" />
        </ToolbarButton>
        <ToolbarButton
          onClick={() => editor.chain().focus().toggleOrderedList().run()}
          isActive={editor.isActive('orderedList')}
          title="Numbered List"
        >
          <ListOrdered className="h-4 w-4" />
        </ToolbarButton>
        <ToolbarButton
          onClick={() => {
            if (editor.can().liftListItem('listItem')) {
              editor.chain().focus().liftListItem('listItem').run()
            } else {
              (editor.chain().focus() as any).outdent().run()
            }
          }}
          title="Decrease Indent"
        >
          <IndentDecrease className="h-4 w-4" />
        </ToolbarButton>
        <ToolbarButton
          onClick={() => {
            if (editor.can().sinkListItem('listItem')) {
              editor.chain().focus().sinkListItem('listItem').run()
            } else {
              (editor.chain().focus() as any).indent().run()
            }
          }}
          title="Increase Indent"
        >
          <IndentIncrease className="h-4 w-4" />
        </ToolbarButton>
      </div>

      {/* Font Size & Font Family */}
      <div className="flex items-center gap-0.5 pr-2 border-r">
        {/* Font Size */}
        <Popover>
          <PopoverTrigger asChild>
            <button
              type="button"
              className="flex items-center gap-1 px-2 py-1.5 rounded hover:bg-muted transition-colors text-xs min-w-[55px]"
              title="Font Size"
            >
              <Type className="h-3.5 w-3.5" />
              <span className="text-xs truncate">
                {(() => {
                  const currentFontSize = editor.getAttributes('textStyle').fontSize
                  const match = FONT_SIZES.find(f => f.value === currentFontSize)
                  return match?.label || 'Normal'
                })()}
              </span>
              <ChevronDown className="h-3 w-3 ml-auto" />
            </button>
          </PopoverTrigger>
          <PopoverContent className="w-auto p-2">
            <div className="flex flex-col gap-1">
              {FONT_SIZES.map(({ label, value }) => {
                const currentFontSize = editor.getAttributes('textStyle').fontSize
                const isActive = currentFontSize === value || (!currentFontSize && value === '1rem')
                return (
                  <button
                    key={value}
                    type="button"
                    onClick={() => {
                      setFontSize(editor, value)
                    }}
                    className={cn(
                      'px-3 py-1.5 text-left rounded hover:bg-muted transition-colors',
                      'text-sm',
                      isActive && 'bg-primary/10 text-primary font-medium'
                    )}
                    style={{ fontSize: value }}
                  >
                    {label}
                    {value === '1rem' && ' (Default)'}
                  </button>
                )
              })}
            </div>
          </PopoverContent>
        </Popover>

        {/* Font Family */}
        <Popover>
          <PopoverTrigger asChild>
            <button
              type="button"
              className="flex items-center gap-1 px-2 py-1.5 rounded hover:bg-muted transition-colors text-xs min-w-[55px]"
              title="Font Family"
            >
              <span className="text-xs truncate">
                {(() => {
                  const currentFontFamily = editor.getAttributes('textStyle').fontFamily
                  const match = FONT_FAMILIES.find(f => f.value === currentFontFamily)
                  return match?.label.replace(' (Default)', '') || 'Arial'
                })()}
              </span>
              <ChevronDown className="h-3 w-3 ml-auto" />
            </button>
          </PopoverTrigger>
          <PopoverContent className="w-auto p-2">
            <div className="flex flex-col gap-1 max-h-48 overflow-y-auto">
              {FONT_FAMILIES.map(({ label, value }) => {
                const currentFontFamily = editor.getAttributes('textStyle').fontFamily
                const isActive = currentFontFamily === value || (!currentFontFamily && value === DEFAULT_FONT_FAMILY)
                return (
                  <button
                    key={value}
                    type="button"
                    onClick={() => {
                      if (value === 'inherit') {
                        editor.chain().focus().unsetFontFamily().run()
                      } else {
                        setFontFamilyHelper(editor, value)
                      }
                    }}
                    className={cn(
                      'px-3 py-1.5 text-left rounded hover:bg-muted transition-colors',
                      'text-sm whitespace-nowrap',
                      isActive && 'bg-primary/10 text-primary font-medium'
                    )}
                    style={{ fontFamily: value }}
                  >
                    {label}
                  </button>
                )
              })}
            </div>
          </PopoverContent>
        </Popover>
      </div>

      {/* Insert */}
      <div className="flex items-center gap-0.5">
        <ToolbarButton
          onClick={handleLink}
          isActive={editor.isActive('link')}
          title="Insert Link"
        >
          <LinkIcon className="h-4 w-4" />
        </ToolbarButton>
        <ToolbarButton
          onClick={handleInsertTable}
          isActive={editor.isActive('table')}
          title="Insert Table"
        >
          <TableIcon className="h-4 w-4" />
        </ToolbarButton>
      </div>

      {/* Table controls when inside a table */}
      {editor.isActive('table') && (
        <div className="flex items-center gap-0.5 pl-2 border-l">
          <ToolbarButton
            onClick={() => editor.chain().focus().addColumnAfter().run()}
            title="Add Column"
          >
            <Plus className="h-4 w-4" />
          </ToolbarButton>
          <ToolbarButton
            onClick={() => editor.chain().focus().addRowAfter().run()}
            title="Add Row"
          >
            <Plus className="h-4 w-4 rotate-90" />
          </ToolbarButton>
          <ToolbarButton
            onClick={() => editor.chain().focus().deleteColumn().run()}
            title="Delete Column"
          >
            <Trash2 className="h-4 w-4 text-destructive" />
          </ToolbarButton>
          <ToolbarButton
            onClick={() => editor.chain().focus().deleteRow().run()}
            title="Delete Row"
          >
            <Trash2 className="h-4 w-4 text-destructive rotate-90" />
          </ToolbarButton>
          <ToolbarButton
            onClick={() => editor.chain().focus().deleteTable().run()}
            title="Delete Table"
          >
            <TableIcon className="h-4 w-4 text-destructive" />
          </ToolbarButton>
        </div>
      )}

      {/* Link Dialog */}
      {linkDialogOpen && (
        <div className="absolute left-0 right-0 top-full z-50 border-b bg-background shadow-md p-3">
          <div className="flex items-center gap-2">
            <LinkIcon className="h-4 w-4 text-muted-foreground flex-shrink-0" />
            <input
              ref={linkInputRef}
              type="url"
              value={linkUrl}
              onChange={(e) => setLinkUrl(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  applyLink()
                } else if (e.key === 'Escape') {
                  setLinkDialogOpen(false)
                  setLinkUrl('')
                }
              }}
              placeholder="https://example.com"
              className="flex-1 rounded-md border border-input bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary/30"
            />
            <button
              type="button"
              onClick={applyLink}
              className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              Apply
            </button>
            {editor.isActive('link') && (
              <button
                type="button"
                onClick={removeLink}
                className="rounded-md border border-input px-3 py-1.5 text-xs font-medium text-destructive hover:bg-destructive/10 transition-colors"
              >
                Remove
              </button>
            )}
            <button
              type="button"
              onClick={() => { setLinkDialogOpen(false); setLinkUrl('') }}
              className="rounded-md border border-input px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Main Component
// ============================================================================

export function RichTextEditor({
  value = '',
  onChange,
  placeholder = 'Write something...',
  readOnly = false,
  className,
  maxLength = 512000,
  maxHeight = '600px',
  onImageUpload,
  onError,
}: RichTextEditorProps) {
  // Ref to track if we're updating from props (prevent infinite loop)
  const isUpdatingFromProps = useRef(false)
  // Ref to track the last known value to avoid unnecessary updates
  const lastValueRef = useRef(value)
  // Debounce timer ref
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null)
  // Ref to hold pending external value when editor is focused
  const pendingExternalValueRef = useRef<string | null>(null)
  // Whether content exceeds max length
  const [isOverLimit, setIsOverLimit] = useState(false)
  // Token for image upload
  const token = useAuthStore((s) => s.token)

  // Image upload function for paste and drop
  const uploadImage = useCallback(async (file: File): Promise<string | null> => {
    if (file.size > 5 * 1024 * 1024) {
      const msg = 'Image size must be less than 5MB'
      onError?.(msg)
      return null
    }

    try {
      if (onImageUpload) {
        return await onImageUpload(file)
      }

      const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8001'

      // Use native fetch for FormData - the Electron IPC bridge
      // JSON-stringifies bodies which destroys multipart/form-data
      const formData = new FormData()
      formData.append('file', file)

      const uploadResponse = await fetch(`${apiUrl}/api/files/upload`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: formData,
      })

      if (!uploadResponse.ok) {
        const errorData = await uploadResponse.json().catch(() => ({}))
        throw new Error((errorData as { detail?: string }).detail || 'Failed to upload image')
      }

      const attachment = await uploadResponse.json() as { id: string }

      // Fetch presigned download URL for the uploaded attachment
      const downloadResponse = await fetch(`${apiUrl}/api/files/${attachment.id}`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      })

      if (!downloadResponse.ok) {
        throw new Error('Failed to get image download URL')
      }

      const downloadData = await downloadResponse.json() as { download_url: string }
      return downloadData.download_url
    } catch (err) {
      console.error('Failed to upload image:', err)
      onError?.(err instanceof Error ? err.message : 'Failed to upload image. Please try again.')
      return null
    }
  }, [token, onImageUpload, onError])

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: {
          levels: [1, 2, 3],
        },
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
        HTMLAttributes: {
          class: 'text-primary underline cursor-pointer',
        },
      }),
      ResizableImage.configure({
        HTMLAttributes: {
          class: 'max-w-full h-auto rounded-md',
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
      Placeholder.configure({
        placeholder,
      }),
    ],
    content: value,
    editable: !readOnly,
    editorProps: {
      attributes: {
        class: cn(
          'prose prose-sm max-w-none focus:outline-none min-h-[120px] overflow-y-auto p-3',
          'prose-headings:font-semibold prose-p:my-2',
          'prose-ul:my-2 prose-ol:my-2 prose-li:my-1',
          '[&_table]:border-collapse [&_table]:w-full',
          '[&_th]:border [&_th]:border-border [&_th]:p-2 [&_th]:bg-muted',
          '[&_td]:border [&_td]:border-border [&_td]:p-2',
          // Table resize cursor styles
          '[&_.tableWrapper]:relative [&_.tableWrapper]:overflow-x-auto',
          '[&_.resize-cursor]:absolute [&_.resize-cursor]:right-[-2px] [&_.resize-cursor]:top-0',
          '[&_.resize-cursor]:bottom-0 [&_.resize-cursor]:w-1.5 [&_.resize-cursor]:cursor-col-resize',
          '[&_.resize-cursor]:bg-border/40 [&_.resize-cursor:hover]:bg-primary/60',
          '[&_.column-resize-handle]:absolute [&_.column-resize-handle]:right-[-2px]',
          '[&_.column-resize-handle]:top-0 [&_.column-resize-handle]:bottom-[-2px]',
          '[&_.column-resize-handle]:w-1.5 [&_.column-resize-handle]:cursor-col-resize',
          '[&_.column-resize-handle]:bg-primary/60',
          '[&_.selectedCell]:bg-primary/10',
        ),
        style: `font-family: ${DEFAULT_FONT_FAMILY}; max-height: ${maxHeight};`,
      },
      // Handle paste for images (Ctrl+V with image in clipboard)
      handlePaste: (view, event) => {
        const items = event.clipboardData?.items
        if (!items) return false

        for (const item of items) {
          if (item.type.startsWith('image/')) {
            event.preventDefault()
            const file = item.getAsFile()
            if (file) {
              // Show a placeholder while uploading
              uploadImage(file).then((url) => {
                if (url) {
                  // Insert image at current cursor position
                  const node = view.state.schema.nodes.image?.create({ src: url })
                  if (node) {
                    const tr = view.state.tr.replaceSelectionWith(node)
                    view.dispatch(tr)
                  }
                }
              }).catch((err) => {
                console.error('Failed to paste image:', err)
                onError?.('Failed to paste image. Please try again.')
              })
            }
            return true
          }
        }
        return false
      },
      // Handle drop for images
      handleDrop: (view, event) => {
        const files = event.dataTransfer?.files
        if (!files || files.length === 0) return false

        const file = files[0]
        if (file.type.startsWith('image/')) {
          event.preventDefault()
          uploadImage(file).then((url) => {
            if (url) {
              const coordinates = view.posAtCoords({
                left: event.clientX,
                top: event.clientY,
              })
              if (coordinates) {
                const node = view.state.schema.nodes.image?.create({ src: url })
                if (node) {
                  const tr = view.state.tr.insert(coordinates.pos, node)
                  view.dispatch(tr)
                }
              }
            }
          })
          return true
        }
        return false
      },
    },
    onUpdate: ({ editor }) => {
      // Don't trigger onChange if we're updating from props
      if (isUpdatingFromProps.current) {
        return
      }

      const html = editor.getHTML()
      const contentSize = new Blob([html]).size
      const overLimit = contentSize > maxLength
      setIsOverLimit(overLimit)

      // Skip onChange if over limit
      if (overLimit) {
        return
      }

      if (onChange) {
        // Debounce the onChange callback to prevent rapid updates
        if (debounceTimerRef.current) {
          clearTimeout(debounceTimerRef.current)
        }

        debounceTimerRef.current = setTimeout(() => {
          // Only call onChange if the value actually changed
          if (html !== lastValueRef.current) {
            lastValueRef.current = html
            onChange(html)
          }
        }, 500) // 500ms debounce
      }
    },
  })

  // Cleanup debounce timer on unmount
  useEffect(() => {
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current)
      }
    }
  }, [])

  // Update editor content when value prop changes (from external source)
  useEffect(() => {
    if (editor && value !== lastValueRef.current) {
      // If editor is focused, defer the update to avoid cursor jump
      if (editor.isFocused) {
        pendingExternalValueRef.current = value
        lastValueRef.current = value
        return
      }
      // Mark that we're updating from props to prevent onChange loop
      isUpdatingFromProps.current = true
      lastValueRef.current = value
      editor.commands.setContent(value)
      // Reset flag after the update is processed
      setTimeout(() => {
        isUpdatingFromProps.current = false
      }, 0)
    }
  }, [value, editor])

  // Apply pending external value on blur
  useEffect(() => {
    if (!editor) return
    const handleBlur = () => {
      const pending = pendingExternalValueRef.current
      if (pending !== null) {
        pendingExternalValueRef.current = null
        isUpdatingFromProps.current = true
        editor.commands.setContent(pending)
        setTimeout(() => {
          isUpdatingFromProps.current = false
        }, 0)
      }
    }
    editor.on('blur', handleBlur)
    return () => {
      editor.off('blur', handleBlur)
    }
  }, [editor])

  // Update editable state when readOnly changes
  useEffect(() => {
    if (editor) {
      editor.setEditable(!readOnly)
    }
  }, [editor, readOnly])

  if (!editor) {
    return (
      <div className={cn('border border-input rounded-lg bg-muted/20 animate-pulse', className)}>
        <div className="h-10 border-b border-input" />
        <div className="h-32" />
      </div>
    )
  }

  return (
    <div className={cn('border border-input rounded-lg overflow-hidden bg-background', className)}>
      {/* Toolbar - hidden when read-only */}
      {!readOnly && <Toolbar editor={editor} uploadImage={uploadImage} />}

      {/* Over limit warning */}
      {isOverLimit && (
        <div className="flex items-center gap-2 px-3 py-2 bg-amber-500/10 border-b border-amber-500/30 text-amber-700 dark:text-amber-400 text-xs">
          <AlertCircle className="h-3.5 w-3.5 flex-shrink-0" />
          Content exceeds the maximum size limit ({Math.round(maxLength / 1024)}KB). Changes will not be saved until content is reduced.
        </div>
      )}

      {/* Editor Content */}
      <EditorContent editor={editor} />
    </div>
  )
}

export default RichTextEditor
