/**
 * EditorToolbar Component
 *
 * Toolbar for the knowledge base DocumentEditor.
 * Plan 03-01: Basic text formatting (bold/italic/underline/strikethrough) + undo/redo
 * Plan 03-02: Heading dropdown, list buttons, code block, indent/outdent
 * Plan 03-03: Table insert + contextual table controls
 * Plan 03-04: Link dialog, font family/size dropdowns, text color/highlight pickers
 */

import { useState, useRef, useCallback } from 'react'
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
  Table2,
  Columns3,
  Rows3,
  Plus,
  Minus,
  Trash2,
  Link2,
  Unlink,
  Palette,
  Highlighter,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  Popover,
  PopoverTrigger,
  PopoverContent,
} from '@/components/ui/popover'
import { Input } from '@/components/ui/input'
import type { Editor } from '@tiptap/react'
import type { EditorToolbarProps } from './editor-types'
import {
  FONT_FAMILIES,
  FONT_SIZES,
  COLORS,
  HIGHLIGHT_COLORS,
  DEFAULT_FONT_FAMILY,
} from './editor-extensions'

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
// LinkPopover
// ============================================================================

function LinkPopover({ editor }: { editor: Editor }) {
  const [open, setOpen] = useState(false)
  const [url, setUrl] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const handleOpen = useCallback(
    (isOpen: boolean) => {
      if (isOpen) {
        const currentHref = editor.getAttributes('link').href || ''
        setUrl(currentHref)
        setTimeout(() => inputRef.current?.focus(), 50)
      }
      setOpen(isOpen)
    },
    [editor]
  )

  const applyLink = useCallback(() => {
    let href = url.trim()
    if (href === '') {
      editor.chain().focus().extendMarkRange('link').unsetLink().run()
    } else {
      if (!/^https?:\/\//i.test(href)) {
        href = 'https://' + href
      }
      editor.chain().focus().extendMarkRange('link').setLink({ href }).run()
    }
    setOpen(false)
    setUrl('')
  }, [editor, url])

  const removeLink = useCallback(() => {
    editor.chain().focus().extendMarkRange('link').unsetLink().run()
    setOpen(false)
    setUrl('')
  }, [editor])

  return (
    <Popover open={open} onOpenChange={handleOpen}>
      <PopoverTrigger asChild>
        <button
          title="Insert/Edit link"
          className={cn(
            'p-1.5 rounded hover:bg-muted transition-colors',
            editor.isActive('link') && 'bg-muted text-primary'
          )}
        >
          <Link2 className="h-4 w-4" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-72 p-3">
        <div className="flex flex-col gap-2">
          <label className="text-xs font-medium text-muted-foreground">URL</label>
          <Input
            ref={inputRef}
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                applyLink()
              } else if (e.key === 'Escape') {
                setOpen(false)
                setUrl('')
              }
            }}
            placeholder="https://example.com"
            className="text-sm"
          />
          <div className="flex items-center gap-2">
            <button
              onClick={applyLink}
              className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              Apply
            </button>
            {editor.isActive('link') && (
              <button
                onClick={removeLink}
                className="flex items-center gap-1 rounded-md border border-input px-3 py-1.5 text-xs font-medium text-destructive hover:bg-destructive/10 transition-colors"
              >
                <Unlink className="h-3 w-3" />
                Remove link
              </button>
            )}
          </div>
        </div>
      </PopoverContent>
    </Popover>
  )
}

// ============================================================================
// FontFamilyDropdown
// ============================================================================

function FontFamilyDropdown({ editor }: { editor: Editor }) {
  const [open, setOpen] = useState(false)

  const currentFontFamily = editor.getAttributes('textStyle').fontFamily
  const currentLabel = (() => {
    const match = FONT_FAMILIES.find((f) => f.value === currentFontFamily)
    return match ? match.label.replace(' (Default)', '') : 'Arial'
  })()

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          title="Font family"
          className="flex items-center gap-1 px-2 py-1.5 rounded hover:bg-muted transition-colors text-xs min-w-[55px]"
        >
          <span className="text-xs truncate">{currentLabel}</span>
          <ChevronDown className="h-3 w-3 ml-auto opacity-60" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-auto p-2">
        <div className="flex flex-col gap-1 max-h-48 overflow-y-auto">
          {FONT_FAMILIES.map(({ label, value }) => {
            const isActive =
              currentFontFamily === value ||
              (!currentFontFamily && value === DEFAULT_FONT_FAMILY)
            return (
              <button
                key={value}
                onClick={() => {
                  editor.chain().focus().setFontFamily(value).run()
                  setOpen(false)
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
  )
}

// ============================================================================
// FontSizeDropdown
// ============================================================================

function FontSizeDropdown({ editor }: { editor: Editor }) {
  const [open, setOpen] = useState(false)

  const currentFontSize = editor.getAttributes('textStyle').fontSize
  const currentLabel = (() => {
    const match = FONT_SIZES.find((f) => f.value === currentFontSize)
    return match?.label || 'Normal'
  })()

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          title="Font size"
          className="flex items-center gap-1 px-2 py-1.5 rounded hover:bg-muted transition-colors text-xs min-w-[55px]"
        >
          <span className="text-xs truncate">{currentLabel}</span>
          <ChevronDown className="h-3 w-3 ml-auto opacity-60" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-auto p-2">
        <div className="flex flex-col gap-1">
          {FONT_SIZES.map(({ label, value }) => {
            const isActive =
              currentFontSize === value ||
              (!currentFontSize && value === '1rem')
            return (
              <button
                key={value}
                onClick={() => {
                  editor.chain().focus().setMark('textStyle', { fontSize: value }).run()
                  setOpen(false)
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
  )
}

// ============================================================================
// TextColorPicker
// ============================================================================

function TextColorPicker({ editor }: { editor: Editor }) {
  const currentColor = editor.getAttributes('textStyle').color || '#000000'

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          className="flex flex-col items-center p-1.5 rounded hover:bg-muted transition-colors"
          title="Text color"
        >
          <Palette className="h-4 w-4" />
          <div
            className="w-4 h-0.5 rounded-full mt-0.5"
            style={{ backgroundColor: currentColor }}
          />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-2">
        <div className="grid grid-cols-6 gap-1">
          {COLORS.map((color) => (
            <button
              key={color}
              onClick={() => editor.chain().focus().setColor(color).run()}
              className="w-6 h-6 rounded border border-border hover:scale-110 transition-transform"
              style={{ backgroundColor: color }}
              title={color}
            />
          ))}
        </div>
        <button
          onClick={() => editor.chain().focus().unsetColor().run()}
          className="mt-2 w-full text-xs text-center py-1 rounded hover:bg-muted text-muted-foreground transition-colors"
        >
          Reset color
        </button>
      </PopoverContent>
    </Popover>
  )
}

// ============================================================================
// HighlightColorPicker
// ============================================================================

function HighlightColorPicker({ editor }: { editor: Editor }) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          className={cn(
            'flex items-center p-1.5 rounded hover:bg-muted transition-colors',
            editor.isActive('highlight') && 'bg-muted text-primary'
          )}
          title="Highlight color"
        >
          <Highlighter className="h-4 w-4" />
          <ChevronDown className="h-3 w-3 opacity-60" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-2">
        <div className="grid grid-cols-4 gap-1">
          {HIGHLIGHT_COLORS.map((color) => (
            <button
              key={color}
              onClick={() => editor.chain().focus().toggleHighlight({ color }).run()}
              className="w-6 h-6 rounded border border-border hover:scale-110 transition-transform"
              style={{ backgroundColor: color }}
              title={color}
            />
          ))}
        </div>
        <button
          onClick={() => editor.chain().focus().unsetHighlight().run()}
          className="mt-2 w-full text-xs text-center py-1 rounded hover:bg-muted text-muted-foreground transition-colors"
        >
          Remove highlight
        </button>
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

      <ToolbarSeparator />

      {/* Table Insert */}
      <ToolbarButton
        onClick={() =>
          editor
            .chain()
            .focus()
            .insertTable({ rows: 3, cols: 3, withHeaderRow: true })
            .run()
        }
        title="Insert table (3x3)"
      >
        <Table2 className="h-4 w-4" />
      </ToolbarButton>

      {/* Contextual Table Controls -- only visible when cursor is inside a table */}
      {editor.isActive('table') && (
        <>
          <ToolbarSeparator />

          <ToolbarButton
            onClick={() => editor.chain().focus().addColumnAfter().run()}
            title="Add column after"
          >
            <span className="relative inline-flex items-center">
              <Columns3 className="h-4 w-4" />
              <Plus className="h-2.5 w-2.5 absolute -right-1 -top-1" />
            </span>
          </ToolbarButton>
          <ToolbarButton
            onClick={() => editor.chain().focus().deleteColumn().run()}
            title="Delete column"
          >
            <span className="relative inline-flex items-center">
              <Columns3 className="h-4 w-4" />
              <Minus className="h-2.5 w-2.5 absolute -right-1 -top-1" />
            </span>
          </ToolbarButton>
          <ToolbarButton
            onClick={() => editor.chain().focus().addRowAfter().run()}
            title="Add row after"
          >
            <span className="relative inline-flex items-center">
              <Rows3 className="h-4 w-4" />
              <Plus className="h-2.5 w-2.5 absolute -right-1 -top-1" />
            </span>
          </ToolbarButton>
          <ToolbarButton
            onClick={() => editor.chain().focus().deleteRow().run()}
            title="Delete row"
          >
            <span className="relative inline-flex items-center">
              <Rows3 className="h-4 w-4" />
              <Minus className="h-2.5 w-2.5 absolute -right-1 -top-1" />
            </span>
          </ToolbarButton>
          <ToolbarButton
            onClick={() => editor.chain().focus().toggleHeaderRow().run()}
            title="Toggle header row"
          >
            <span className="relative inline-flex items-center">
              <Table2 className="h-4 w-4" />
              <Heading className="h-2.5 w-2.5 absolute -right-1 -top-1" />
            </span>
          </ToolbarButton>
          <ToolbarButton
            onClick={() => editor.chain().focus().deleteTable().run()}
            title="Delete table"
          >
            <Trash2 className="h-4 w-4" />
          </ToolbarButton>
        </>
      )}

      <ToolbarSeparator />

      {/* Link Insert/Edit */}
      <LinkPopover editor={editor} />

      <ToolbarSeparator />

      {/* Font Family Dropdown */}
      <FontFamilyDropdown editor={editor} />

      {/* Font Size Dropdown */}
      <FontSizeDropdown editor={editor} />

      <ToolbarSeparator />

      {/* Text Color Picker */}
      <TextColorPicker editor={editor} />

      {/* Highlight Color Picker */}
      <HighlightColorPicker editor={editor} />
    </div>
  )
}
