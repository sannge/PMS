/**
 * Note Editor Component
 *
 * Rich text editor for note content using TipTap.
 *
 * Features:
 * - Formatting toolbar (bold, italic, underline, strikethrough)
 * - Headings (H1, H2, H3)
 * - Lists (bullet, numbered, task lists)
 * - Code blocks and inline code
 * - Links and images
 * - Text alignment
 * - Highlight text
 * - Keyboard shortcuts
 * - Auto-save support via onChange callback
 */

import { useCallback, useEffect } from 'react'
import { useEditor, EditorContent, type Editor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Underline from '@tiptap/extension-underline'
import Link from '@tiptap/extension-link'
import Placeholder from '@tiptap/extension-placeholder'
import Image from '@tiptap/extension-image'
import TextAlign from '@tiptap/extension-text-align'
import Highlight from '@tiptap/extension-highlight'
import TaskList from '@tiptap/extension-task-list'
import TaskItem from '@tiptap/extension-task-item'
import { cn } from '@/lib/utils'
import {
  Bold,
  Italic,
  Underline as UnderlineIcon,
  Strikethrough,
  Code,
  Heading1,
  Heading2,
  Heading3,
  List,
  ListOrdered,
  ListTodo,
  Quote,
  Minus,
  Link as LinkIcon,
  Image as ImageIcon,
  AlignLeft,
  AlignCenter,
  AlignRight,
  AlignJustify,
  Highlighter,
  Undo2,
  Redo2,
  RemoveFormatting,
  Pilcrow,
} from 'lucide-react'

// ============================================================================
// Types
// ============================================================================

export interface NoteEditorProps {
  /**
   * Initial content (HTML string)
   */
  content?: string | null
  /**
   * Placeholder text when editor is empty
   */
  placeholder?: string
  /**
   * Whether the editor is editable
   */
  editable?: boolean
  /**
   * Callback when content changes
   */
  onChange?: (content: string) => void
  /**
   * Callback when focus changes
   */
  onFocus?: () => void
  /**
   * Callback when blur happens
   */
  onBlur?: () => void
  /**
   * Optional className for the container
   */
  className?: string
  /**
   * Whether to show the toolbar
   */
  showToolbar?: boolean
  /**
   * Auto focus on mount
   */
  autoFocus?: boolean
}

interface ToolbarButtonProps {
  onClick: () => void
  isActive?: boolean
  disabled?: boolean
  title: string
  children: React.ReactNode
}

interface ToolbarDividerProps {
  className?: string
}

// ============================================================================
// Toolbar Button Component
// ============================================================================

function ToolbarButton({
  onClick,
  isActive = false,
  disabled = false,
  title,
  children,
}: ToolbarButtonProps): JSX.Element {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={cn(
        'flex h-8 w-8 items-center justify-center rounded-md transition-colors',
        'text-muted-foreground hover:bg-accent hover:text-foreground',
        'focus:outline-none focus:ring-1 focus:ring-ring',
        'disabled:opacity-50 disabled:cursor-not-allowed',
        isActive && 'bg-accent text-foreground'
      )}
    >
      {children}
    </button>
  )
}

// ============================================================================
// Toolbar Divider Component
// ============================================================================

function ToolbarDivider({ className }: ToolbarDividerProps): JSX.Element {
  return <div className={cn('mx-1 h-6 w-px bg-border', className)} />
}

// ============================================================================
// Editor Toolbar Component
// ============================================================================

interface EditorToolbarProps {
  editor: Editor | null
  onAddImage?: () => void
  onAddLink?: () => void
}

function EditorToolbar({ editor, onAddImage, onAddLink }: EditorToolbarProps): JSX.Element | null {
  if (!editor) return null

  const handleAddLink = useCallback(() => {
    if (onAddLink) {
      onAddLink()
      return
    }

    const previousUrl = editor.getAttributes('link').href
    const url = window.prompt('Enter URL', previousUrl || 'https://')

    // Cancelled
    if (url === null) return

    // Empty
    if (url === '') {
      editor.chain().focus().extendMarkRange('link').unsetLink().run()
      return
    }

    // Update or set link
    editor.chain().focus().extendMarkRange('link').setLink({ href: url }).run()
  }, [editor, onAddLink])

  const handleAddImage = useCallback(() => {
    if (onAddImage) {
      onAddImage()
      return
    }

    const url = window.prompt('Enter image URL', 'https://')

    if (url) {
      editor.chain().focus().setImage({ src: url }).run()
    }
  }, [editor, onAddImage])

  return (
    <div className="flex flex-wrap items-center gap-0.5 border-b border-border bg-muted/30 p-1">
      {/* Undo/Redo */}
      <ToolbarButton
        onClick={() => editor.chain().focus().undo().run()}
        disabled={!editor.can().undo()}
        title="Undo (Ctrl+Z)"
      >
        <Undo2 className="h-4 w-4" />
      </ToolbarButton>
      <ToolbarButton
        onClick={() => editor.chain().focus().redo().run()}
        disabled={!editor.can().redo()}
        title="Redo (Ctrl+Shift+Z)"
      >
        <Redo2 className="h-4 w-4" />
      </ToolbarButton>

      <ToolbarDivider />

      {/* Text Style */}
      <ToolbarButton
        onClick={() => editor.chain().focus().setParagraph().run()}
        isActive={editor.isActive('paragraph')}
        title="Paragraph"
      >
        <Pilcrow className="h-4 w-4" />
      </ToolbarButton>
      <ToolbarButton
        onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
        isActive={editor.isActive('heading', { level: 1 })}
        title="Heading 1"
      >
        <Heading1 className="h-4 w-4" />
      </ToolbarButton>
      <ToolbarButton
        onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
        isActive={editor.isActive('heading', { level: 2 })}
        title="Heading 2"
      >
        <Heading2 className="h-4 w-4" />
      </ToolbarButton>
      <ToolbarButton
        onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
        isActive={editor.isActive('heading', { level: 3 })}
        title="Heading 3"
      >
        <Heading3 className="h-4 w-4" />
      </ToolbarButton>

      <ToolbarDivider />

      {/* Basic Formatting */}
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
        onClick={() => editor.chain().focus().toggleHighlight().run()}
        isActive={editor.isActive('highlight')}
        title="Highlight"
      >
        <Highlighter className="h-4 w-4" />
      </ToolbarButton>
      <ToolbarButton
        onClick={() => editor.chain().focus().toggleCode().run()}
        isActive={editor.isActive('code')}
        title="Inline Code"
      >
        <Code className="h-4 w-4" />
      </ToolbarButton>

      <ToolbarDivider />

      {/* Lists */}
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
        onClick={() => editor.chain().focus().toggleTaskList().run()}
        isActive={editor.isActive('taskList')}
        title="Task List"
      >
        <ListTodo className="h-4 w-4" />
      </ToolbarButton>

      <ToolbarDivider />

      {/* Blocks */}
      <ToolbarButton
        onClick={() => editor.chain().focus().toggleBlockquote().run()}
        isActive={editor.isActive('blockquote')}
        title="Quote"
      >
        <Quote className="h-4 w-4" />
      </ToolbarButton>
      <ToolbarButton
        onClick={() => editor.chain().focus().toggleCodeBlock().run()}
        isActive={editor.isActive('codeBlock')}
        title="Code Block"
      >
        <Code className="h-4 w-4 rotate-180" />
      </ToolbarButton>
      <ToolbarButton
        onClick={() => editor.chain().focus().setHorizontalRule().run()}
        title="Horizontal Rule"
      >
        <Minus className="h-4 w-4" />
      </ToolbarButton>

      <ToolbarDivider />

      {/* Text Alignment */}
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

      <ToolbarDivider />

      {/* Media & Links */}
      <ToolbarButton
        onClick={handleAddLink}
        isActive={editor.isActive('link')}
        title="Add Link"
      >
        <LinkIcon className="h-4 w-4" />
      </ToolbarButton>
      <ToolbarButton onClick={handleAddImage} title="Add Image">
        <ImageIcon className="h-4 w-4" />
      </ToolbarButton>

      <ToolbarDivider />

      {/* Clear Formatting */}
      <ToolbarButton
        onClick={() => editor.chain().focus().unsetAllMarks().clearNodes().run()}
        title="Clear Formatting"
      >
        <RemoveFormatting className="h-4 w-4" />
      </ToolbarButton>
    </div>
  )
}

// ============================================================================
// Note Editor Component
// ============================================================================

export function NoteEditor({
  content,
  placeholder = 'Start writing your note...',
  editable = true,
  onChange,
  onFocus,
  onBlur,
  className,
  showToolbar = true,
  autoFocus = false,
}: NoteEditorProps): JSX.Element {
  // Initialize editor with extensions
  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: {
          levels: [1, 2, 3],
        },
        codeBlock: {
          HTMLAttributes: {
            class: 'rounded-md bg-muted p-4 font-mono text-sm',
          },
        },
        code: {
          HTMLAttributes: {
            class: 'rounded-md bg-muted px-1.5 py-0.5 font-mono text-sm',
          },
        },
        blockquote: {
          HTMLAttributes: {
            class: 'border-l-4 border-border pl-4 italic text-muted-foreground',
          },
        },
      }),
      Underline,
      Link.configure({
        openOnClick: false,
        HTMLAttributes: {
          class: 'text-primary underline underline-offset-4 cursor-pointer hover:text-primary/80',
        },
      }),
      Placeholder.configure({
        placeholder,
        emptyEditorClass:
          'before:content-[attr(data-placeholder)] before:float-left before:text-muted-foreground before:pointer-events-none before:h-0',
      }),
      Image.configure({
        HTMLAttributes: {
          class: 'rounded-md max-w-full h-auto',
        },
      }),
      TextAlign.configure({
        types: ['heading', 'paragraph'],
      }),
      Highlight.configure({
        HTMLAttributes: {
          class: 'bg-yellow-200 dark:bg-yellow-800 rounded-sm px-0.5',
        },
      }),
      TaskList.configure({
        HTMLAttributes: {
          class: 'not-prose',
        },
      }),
      TaskItem.configure({
        HTMLAttributes: {
          class: 'flex items-start gap-2',
        },
        nested: true,
      }),
    ],
    content: content || '',
    editable,
    autofocus: autoFocus,
    onUpdate: ({ editor }) => {
      if (onChange) {
        onChange(editor.getHTML())
      }
    },
    onFocus: () => {
      if (onFocus) {
        onFocus()
      }
    },
    onBlur: () => {
      if (onBlur) {
        onBlur()
      }
    },
    editorProps: {
      attributes: {
        class: cn(
          'prose prose-sm dark:prose-invert max-w-none',
          'min-h-[200px] p-4 outline-none',
          'prose-headings:font-semibold',
          'prose-h1:text-2xl prose-h2:text-xl prose-h3:text-lg',
          'prose-p:my-2 prose-ul:my-2 prose-ol:my-2',
          'prose-li:my-0.5',
          'prose-pre:bg-muted prose-pre:rounded-md',
          'prose-code:before:content-none prose-code:after:content-none',
          'focus:outline-none'
        ),
      },
    },
  })

  // Update content when prop changes
  useEffect(() => {
    if (editor && content !== undefined && editor.getHTML() !== content) {
      editor.commands.setContent(content || '')
    }
  }, [editor, content])

  // Update editable state
  useEffect(() => {
    if (editor) {
      editor.setEditable(editable)
    }
  }, [editor, editable])

  return (
    <div
      className={cn(
        'flex flex-col rounded-md border border-input bg-background',
        'focus-within:ring-1 focus-within:ring-ring focus-within:border-ring',
        !editable && 'opacity-70',
        className
      )}
    >
      {/* Toolbar */}
      {showToolbar && editable && <EditorToolbar editor={editor} />}

      {/* Editor Content */}
      <EditorContent
        editor={editor}
        className={cn(
          'flex-1 overflow-auto',
          '[&_.ProseMirror]:outline-none',
          // Task list styles
          '[&_ul[data-type=taskList]]:list-none [&_ul[data-type=taskList]]:pl-0',
          '[&_ul[data-type=taskList]_li]:flex [&_ul[data-type=taskList]_li]:items-start [&_ul[data-type=taskList]_li]:gap-2',
          '[&_ul[data-type=taskList]_input]:mt-1 [&_ul[data-type=taskList]_input]:h-4 [&_ul[data-type=taskList]_input]:w-4',
          '[&_ul[data-type=taskList]_input]:accent-primary'
        )}
      />

      {/* Word Count (optional, can be added if needed) */}
      {editor && (
        <div className="border-t border-border px-4 py-1.5 text-xs text-muted-foreground">
          {editor.storage.characterCount?.characters() || 0} characters
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Utility: Get Editor Content as HTML
// ============================================================================

export function getEditorContent(editor: Editor | null): string {
  if (!editor) return ''
  return editor.getHTML()
}

// ============================================================================
// Utility: Get Editor Content as Plain Text
// ============================================================================

export function getEditorPlainText(editor: Editor | null): string {
  if (!editor) return ''
  return editor.getText()
}

export default NoteEditor
