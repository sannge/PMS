/**
 * useDraft Hook - Draft Persistence and Crash Recovery
 *
 * Auto-buffers unsaved editor content to IndexedDB every 2 seconds of
 * inactivity. On document open, checks for drafts newer than the server
 * version and exposes a restore/discard prompt.
 *
 * Usage:
 *   const { pendingDraft, restoreDraft, discardDraft, clearDraftAfterSave } = useDraft({
 *     documentId,
 *     editor,
 *     serverUpdatedAt,
 *     documentTitle,
 *   })
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import type { Editor } from '@tiptap/core'
import { getDraft, saveDraft, deleteDraft, type DraftEntry } from '@/lib/draft-db'

// ============================================================================
// Types
// ============================================================================

interface UseDraftParams {
  documentId: string
  editor: Editor | null
  /** Server's updated_at for the loaded document (epoch ms) */
  serverUpdatedAt: number
  documentTitle: string
}

interface UseDraftReturn {
  /** Non-null when a recoverable draft exists that is newer than the server version */
  pendingDraft: DraftEntry | null
  /** Returns parsed JSON content from the pending draft for the editor to load */
  restoreDraft: () => unknown | null
  /** Deletes the pending draft from IndexedDB */
  discardDraft: () => Promise<void>
  /** Deletes the draft from IndexedDB after a successful server save */
  clearDraftAfterSave: () => Promise<void>
}

// ============================================================================
// Constants
// ============================================================================

/** Debounce interval for auto-buffering drafts (ms) */
const DRAFT_DEBOUNCE_MS = 2_000

// ============================================================================
// Hook
// ============================================================================

export function useDraft({
  documentId,
  editor,
  serverUpdatedAt,
  documentTitle,
}: UseDraftParams): UseDraftReturn {
  const [pendingDraft, setPendingDraft] = useState<DraftEntry | null>(null)
  const draftTimerRef = useRef<ReturnType<typeof setTimeout>>()

  // Stable refs for values used in callbacks
  const documentTitleRef = useRef(documentTitle)
  documentTitleRef.current = documentTitle
  const serverUpdatedAtRef = useRef(serverUpdatedAt)
  serverUpdatedAtRef.current = serverUpdatedAt

  // --------------------------------------------------------------------------
  // On-mount draft check
  // --------------------------------------------------------------------------
  useEffect(() => {
    if (!documentId || !serverUpdatedAt) return

    let cancelled = false

    async function checkForDraft() {
      const draft = await getDraft(documentId)
      if (cancelled) return

      if (!draft) return

      if (draft.draftedAt > serverUpdatedAt) {
        // Draft is newer than server -- check if content differs
        if (editor) {
          const currentContent = JSON.stringify(editor.getJSON())
          if (currentContent === draft.contentJson) {
            // Draft matches current editor content, silently delete
            await deleteDraft(documentId)
            return
          }
        }
        // Content differs (or editor not loaded yet) -- prompt user
        setPendingDraft(draft)
      } else {
        // Draft is older than server version, silently delete
        await deleteDraft(documentId)
      }
    }

    checkForDraft()

    return () => {
      cancelled = true
    }
  }, [documentId, serverUpdatedAt, editor])

  // --------------------------------------------------------------------------
  // Auto-buffer on editor changes
  // --------------------------------------------------------------------------
  useEffect(() => {
    if (!editor || !documentId) return

    const handler = () => {
      if (draftTimerRef.current) {
        clearTimeout(draftTimerRef.current)
      }

      draftTimerRef.current = setTimeout(() => {
        saveDraft({
          documentId,
          contentJson: JSON.stringify(editor.getJSON()),
          title: documentTitleRef.current,
          serverUpdatedAt: serverUpdatedAtRef.current,
          draftedAt: Date.now(),
        })
      }, DRAFT_DEBOUNCE_MS)
    }

    editor.on('update', handler)

    return () => {
      editor.off('update', handler)
      if (draftTimerRef.current) {
        clearTimeout(draftTimerRef.current)
      }
    }
  }, [editor, documentId])

  // --------------------------------------------------------------------------
  // restoreDraft - return parsed JSON content from pending draft
  // --------------------------------------------------------------------------
  const restoreDraft = useCallback((): unknown | null => {
    if (!pendingDraft) return null

    try {
      const content = JSON.parse(pendingDraft.contentJson) as unknown
      setPendingDraft(null)
      // Do NOT delete from IndexedDB yet -- will be deleted on next successful server save
      return content
    } catch {
      setPendingDraft(null)
      return null
    }
  }, [pendingDraft])

  // --------------------------------------------------------------------------
  // discardDraft - delete from IndexedDB and clear pending state
  // --------------------------------------------------------------------------
  const discardDraft = useCallback(async () => {
    await deleteDraft(documentId)
    setPendingDraft(null)
  }, [documentId])

  // --------------------------------------------------------------------------
  // clearDraftAfterSave - called by auto-save hook after successful server save
  // --------------------------------------------------------------------------
  const clearDraftAfterSave = useCallback(async () => {
    await deleteDraft(documentId)
  }, [documentId])

  return {
    pendingDraft,
    restoreDraft,
    discardDraft,
    clearDraftAfterSave,
  }
}
