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
  /** Document ID for lock operations (optional - enables locking when provided) */
  documentId?: string | null
  /** Current user ID for lock ownership check */
  userId?: string
  /** Current user display name */
  userName?: string
  /** User's role in the document's application scope (owner/editor/viewer) */
  userRole?: string | null
  /** Imperative save callback for onBeforeRelease (auto-save's saveNow) */
  onSaveNow?: () => Promise<void>
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
