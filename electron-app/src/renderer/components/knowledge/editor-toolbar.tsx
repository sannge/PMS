/**
 * EditorToolbar Component
 *
 * Toolbar for the knowledge base DocumentEditor.
 * Plan 03-01: Basic text formatting (bold/italic/underline/strikethrough) + undo/redo
 * Plan 03-02: Heading dropdown, list buttons, code block, indent/outdent
 * Plans 03-03 through 03-04 add remaining toolbar sections.
 */

import { useState } from 'react'
import {
  Bold,
  Italic,
  Underline,
  Strikethrough,
  Undo2,
  Redo2,
  Heading,
  ChevronDown,
  Pilcrow,
  List,
  ListOrdered,
  ListChecks,
  Code2,
  IndentIncrease,
  IndentDecrease,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  Popover,
  PopoverTrigger,
  PopoverContent,
} from '@/components/ui/popover'
import type { Editor } from '@tiptap/react'
import type { EditorToolbarProps } from './editor-types'

// ============================================================================
// ToolbarButton Helper
// ============================================================================

interface ToolbarButtonProps {
  onClick: () => void
  isActive?: boolean
  disabled?: boolean
  title: string
  children: React.ReactNode
}

function ToolbarButton({
  onClick,
  isActive,
  disabled,
  title,
  children,
}: ToolbarButtonProps) {
  return (
    <button
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
// Toolbar Separator
// ============================================================================

function ToolbarSeparator() {
  return <div className="w-px h-6 bg-border mx-1" />
}

// ============================================================================
// Heading Dropdown Helpers
// ============================================================================

type HeadingLevel = 1 | 2 | 3 | 4 | 5 | 6

interface HeadingOption {
  label: string
  level: HeadingLevel | null // null = paragraph
  className: string
}

const HEADING_OPTIONS: HeadingOption[] = [
  { label: 'Paragraph', level: null, className: 'text-sm' },
  { label: 'Heading 1', level: 1, className: 'text-xl font-bold' },
  { label: 'Heading 2', level: 2, className: 'text-lg font-bold' },
  { label: 'Heading 3', level: 3, className: 'text-base font-semibold' },
  { label: 'Heading 4', level: 4, className: 'text-sm font-semibold' },
  { label: 'Heading 5', level: 5, className: 'text-xs font-semibold' },
  { label: 'Heading 6', level: 6, className: 'text-xs font-medium' },
]

function getCurrentHeadingLabel(editor: Editor): string {
  for (let level = 1; level <= 6; level++) {
    if (editor.isActive('heading', { level })) {
      return `Heading ${level}`
    }
  }
  return 'Paragraph'
}

function isHeadingActive(editor: Editor): boolean {
  for (let level = 1; level <= 6; level++) {
    if (editor.isActive('heading', { level })) {
      return true
    }
  }
  return false
}

// ============================================================================
// HeadingDropdown
// ============================================================================

function HeadingDropdown({ editor }: { editor: Editor }) {
  const [open, setOpen] = useState(false)
  const currentLabel = getCurrentHeadingLabel(editor)
  const hasActiveHeading = isHeadingActive(editor)

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          title="Text style"
          className={cn(
            'flex items-center gap-1 px-2 py-1.5 rounded hover:bg-muted transition-colors text-sm',
            hasActiveHeading && 'bg-muted text-primary'
          )}
        >
          {hasActiveHeading ? (
            <Heading className="h-4 w-4" />
          ) : (
            <Pilcrow className="h-4 w-4" />
          )}
          <span className="max-w-[80px] truncate">{currentLabel}</span>
          <ChevronDown className="h-3 w-3 opacity-60" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-48 p-1">
        {HEADING_OPTIONS.map((option) => {
          const isActive =
            option.level === null
              ? !isHeadingActive(editor)
              : editor.isActive('heading', { level: option.level })

          return (
            <button
              key={option.label}
              onClick={() => {
                if (option.level === null) {
                  editor.chain().focus().setParagraph().run()
                } else {
                  editor
                    .chain()
                    .focus()
                    .toggleHeading({ level: option.level })
                    .run()
                }
                setOpen(false)
              }}
              className={cn(
                'w-full text-left px-2 py-1.5 rounded hover:bg-muted transition-colors',
                isActive && 'bg-primary/10',
                option.className
              )}
            >
              {option.label}
            </button>
          )
        })}
      </PopoverContent>
    </Popover>
  )
}

// ============================================================================
// EditorToolbar
// ============================================================================

export function EditorToolbar({ editor }: EditorToolbarProps) {
  return (
    <div className="flex flex-wrap items-center gap-0.5 p-2 border-b bg-muted/30">
      {/* Undo / Redo */}
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
        title="Redo (Ctrl+Y)"
      >
        <Redo2 className="h-4 w-4" />
      </ToolbarButton>

      <ToolbarSeparator />

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
        <Underline className="h-4 w-4" />
      </ToolbarButton>
      <ToolbarButton
        onClick={() => editor.chain().focus().toggleStrike().run()}
        isActive={editor.isActive('strike')}
        title="Strikethrough"
      >
        <Strikethrough className="h-4 w-4" />
      </ToolbarButton>

      <ToolbarSeparator />

      {/* Heading Dropdown */}
      <HeadingDropdown editor={editor} />

      <ToolbarSeparator />

      {/* List + Checklist */}
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
        title="Checklist"
      >
        <ListChecks className="h-4 w-4" />
      </ToolbarButton>

      <ToolbarSeparator />

      {/* Code Block */}
      <ToolbarButton
        onClick={() => editor.chain().focus().toggleCodeBlock().run()}
        isActive={editor.isActive('codeBlock')}
        title="Code Block"
      >
        <Code2 className="h-4 w-4" />
      </ToolbarButton>

      <ToolbarSeparator />

      {/* Indent / Outdent */}
      <ToolbarButton
        onClick={() => (editor.chain().focus() as any).indent().run()}
        title="Indent"
      >
        <IndentIncrease className="h-4 w-4" />
      </ToolbarButton>
      <ToolbarButton
        onClick={() => (editor.chain().focus() as any).outdent().run()}
        title="Outdent"
      >
        <IndentDecrease className="h-4 w-4" />
      </ToolbarButton>

      {/* Table controls - Plan 03-03 */}
      {/* Link, Font, Color controls - Plan 03-04 */}
    </div>
  )
}
