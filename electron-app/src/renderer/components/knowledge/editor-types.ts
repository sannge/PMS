/**
 * Knowledge Base Editor Types
 *
 * TypeScript interfaces for the DocumentEditor and EditorToolbar components.
 */

import type { Editor } from '@tiptap/react'

/** Props for the main DocumentEditor component */
export interface DocumentEditorProps {
  /** TipTap JSON content to render */
  content?: object
  /** Callback fired with TipTap JSON when content changes (debounced 300ms) */
  onChange?: (json: object) => void
  /** Whether the editor is editable (default: true) */
  editable?: boolean
  /** Placeholder text shown when editor is empty */
  placeholder?: string
  /** Additional CSS classes for the outer container */
  className?: string
}

/** Props for the EditorToolbar component */
export interface EditorToolbarProps {
  /** TipTap Editor instance */
  editor: Editor
}

/** A toolbar section groups related buttons with a separator */
export type ToolbarSection = {
  /** Unique key for the section */
  key: string
  /** Display label (used for accessibility) */
  label: string
}
