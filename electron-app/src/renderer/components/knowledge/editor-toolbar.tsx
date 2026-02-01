/**
 * EditorToolbar Component
 *
 * Toolbar for the knowledge base DocumentEditor.
 * Plan 03-01: Basic text formatting (bold/italic/underline/strikethrough) + undo/redo
 * Plans 03-02 through 03-04 add remaining toolbar sections.
 */

import {
  Bold,
  Italic,
  Underline,
  Strikethrough,
  Undo2,
  Redo2,
} from 'lucide-react'
import { cn } from '@/lib/utils'
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

      {/* Heading dropdown - Plan 03-02 */}
      {/* List buttons - Plan 03-02 */}
      {/* Table controls - Plan 03-03 */}
      {/* Link, Font, Color controls - Plan 03-04 */}
    </div>
  )
}
