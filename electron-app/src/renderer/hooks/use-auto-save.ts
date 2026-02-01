/**
 * Auto-save hook for document content.
 *
 * Provides debounced auto-save (10s inactivity), dirty tracking,
 * imperative saveNow(), and save status for UI display.
 * Uses optimistic concurrency via row_version.
 *
 * @module use-auto-save
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import type { Editor } from '@tiptap/react'
import { useSaveDocumentContent } from './use-queries'

// ============================================================================
// Types
// ============================================================================

/** Save status union for UI display */
export type SaveStatus =
  | { state: 'idle' }
  | { state: 'saving' }
  | { state: 'saved'; at: number }
  | { state: 'error'; message: string }

/** Options for the useAutoSave hook */
export interface UseAutoSaveOptions {
  /** Document ID to save */
  documentId: string
  /** TipTap editor instance (null while loading) */
  editor: Editor | null
  /** Current server row_version */
  rowVersion: number
}

/** Return value of the useAutoSave hook */
export interface UseAutoSaveReturn {
  /** Check if editor content differs from last saved content */
  isDirty: () => boolean
  /** Imperatively save now (cancels pending debounce) */
  saveNow: () => Promise<void>
  /** Current save status for UI display */
  saveStatus: SaveStatus
  /** Manually set save status (e.g., to clear errors) */
  setSaveStatus: React.Dispatch<React.SetStateAction<SaveStatus>>
}

// ============================================================================
// Constants
// ============================================================================

/** Debounce delay in milliseconds (10 seconds of inactivity) */
const DEBOUNCE_MS = 10_000

// ============================================================================
// Hook
// ============================================================================

/**
 * Auto-save hook that debounces editor changes and saves after 10s of inactivity.
 *
 * Features:
 * - 10-second debounce on editor updates
 * - Dirty check comparing JSON content against last save
 * - Concurrent save prevention via mutex ref
 * - Imperative saveNow() for save-on-navigate/close
 * - row_version tracking for optimistic concurrency
 *
 * @example
 * ```tsx
 * const { isDirty, saveNow, saveStatus } = useAutoSave({
 *   documentId: doc.id,
 *   editor,
 *   rowVersion: doc.row_version,
 * })
 * ```
 */
export function useAutoSave({
  documentId,
  editor,
  rowVersion,
}: UseAutoSaveOptions): UseAutoSaveReturn {
  // Save mutation
  const saveMutation = useSaveDocumentContent()

  // Refs (no re-renders)
  const lastSavedRef = useRef<string>('')
  const timerRef = useRef<ReturnType<typeof setTimeout>>()
  const savingRef = useRef(false)
  const rowVersionRef = useRef(rowVersion)

  // Save status state (for UI)
  const [saveStatus, setSaveStatus] = useState<SaveStatus>({ state: 'idle' })

  // Sync rowVersionRef when prop changes (e.g., after external refresh)
  useEffect(() => {
    rowVersionRef.current = rowVersion
  }, [rowVersion])

  // Initialize lastSavedRef when document loads or changes
  useEffect(() => {
    if (editor && documentId) {
      lastSavedRef.current = JSON.stringify(editor.getJSON())
    }
  }, [editor, documentId])

  // Dirty check: compare current editor JSON to last saved
  const isDirty = useCallback((): boolean => {
    if (!editor) return false
    return JSON.stringify(editor.getJSON()) !== lastSavedRef.current
  }, [editor])

  // Imperative save function
  const saveNow = useCallback(async (): Promise<void> => {
    // Guards: no editor, not dirty, or already saving
    if (!editor || savingRef.current) return

    const jsonStr = JSON.stringify(editor.getJSON())
    if (jsonStr === lastSavedRef.current) return

    savingRef.current = true

    // Cancel any pending debounce timer
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = undefined
    }

    setSaveStatus({ state: 'saving' })

    try {
      const result = await saveMutation.mutateAsync({
        documentId,
        content_json: jsonStr,
        row_version: rowVersionRef.current,
      })

      // Update tracking refs on success
      lastSavedRef.current = jsonStr
      rowVersionRef.current = result.row_version
      setSaveStatus({ state: 'saved', at: Date.now() })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Save failed'
      setSaveStatus({ state: 'error', message })
    } finally {
      savingRef.current = false
    }
  }, [editor, documentId, saveMutation])

  // Editor update listener: debounce saves at 10s inactivity
  useEffect(() => {
    if (!editor) return

    const handler = () => {
      // Reset debounce timer on each editor update
      if (timerRef.current) {
        clearTimeout(timerRef.current)
      }
      timerRef.current = setTimeout(() => {
        void saveNow()
      }, DEBOUNCE_MS)
    }

    editor.on('update', handler)

    return () => {
      editor.off('update', handler)
      if (timerRef.current) {
        clearTimeout(timerRef.current)
        timerRef.current = undefined
      }
    }
  }, [editor, saveNow])

  return {
    isDirty,
    saveNow,
    saveStatus,
    setSaveStatus,
  }
}
