/**
 * Knowledge Base Editor Types
 *
 * TypeScript interfaces for the DocumentEditor, EditorToolbar, and save status.
 */

import type { Editor } from '@tiptap/react'

/** Save status union for UI display */
export type SaveStatus =
  | { state: 'idle' }
  | { state: 'saving' }
  | { state: 'saved'; at: number }
  | { state: 'error'; message: string }

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
  /** ISO timestamp for display above the editor content */
  updatedAt?: string
  /**
   * Called once after setContent in edit mode with TipTap-normalized JSON.
   * Use this to sync dirty-detection baselines — TipTap adds default attrs
   * (textAlign, indent) that our raw JSON builders don't include.
   */
  onBaselineSync?: (json: object) => void
  /** Document ID for image upload association */
  documentId?: string
  /** Search terms to highlight in the editor via ProseMirror decorations */
  searchTerms?: string[]
  /** Which occurrence (0-based) to scroll to after highlights are applied. -1 = no scroll. */
  scrollToOccurrence?: number
}

/** Props for the EditorToolbar component */
export interface EditorToolbarProps {
  /** TipTap Editor instance */
  editor: Editor
  /** Callback to upload an image file, returns the inserted image src URL */
  onImageUpload?: (file: File) => void
}

