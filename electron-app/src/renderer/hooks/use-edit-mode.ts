/**
 * useEditMode Hook
 *
 * View/edit state machine for document editing. Encapsulates:
 * - Lock acquire/release on mode transitions
 * - Manual save with optimistic concurrency (row_version)
 * - Dirty detection (localContent vs savedContent)
 * - Discard confirmation dialog
 * - 5-minute inactivity dialog
 * - Navigation guard (blocks selectDocument/setActiveTab if dirty)
 * - Screen navigation guard (blocks sidebar navigation if dirty)
 * - App close guard (auto-saves dirty content on quit)
 * - Force-taken detection (toast + exit to view)
 *
 * Used by both EditorPanel (Notes page) and InnerPanel (KnowledgePanel).
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { useDocumentLock, INACTIVITY_TIMEOUT_MS } from './use-document-lock'
import { useSaveDocumentContent } from './use-queries'
import { useDocument } from './use-documents'
import type { Document } from './use-documents'
import { useKnowledgeBase } from '@/contexts/knowledge-base-context'
import { useAuthState } from '@/contexts/auth-context'
import { useQueryClient } from '@tanstack/react-query'
import { queryKeys } from '@/lib/query-client'
import {
  registerScreenGuard,
  unregisterScreenGuard,
} from '@/lib/screen-navigation-guard'
import { saveDraft, deleteDraft } from '@/lib/draft-db'
import type { SaveStatus } from '@/components/knowledge/editor-types'

// ============================================================================
// Constants
// ============================================================================

const AUTO_SAVE_TIMEOUT_MS = 60_000           // 60 seconds
const INACTIVITY_CHECK_MS = 30_000           // 30 seconds
const DRAFT_DEBOUNCE_MS = 2_000              // 2 seconds — auto-buffer to IndexedDB

export interface UseEditModeOptions {
  documentId: string | null
  canEdit: boolean
  /** Whether the current user is an application owner (for force-take locks) */
  isOwner?: boolean
}

export interface UseEditModeReturn {
  mode: 'view' | 'edit'
  saveStatus: SaveStatus
  isDirty: boolean
  isSaving: boolean
  /** True while entering edit mode (refetch + lock acquire in progress) */
  isEntering: boolean
  /** True while exiting edit mode (lock release in progress) */
  isExiting: boolean
  showDiscardDialog: boolean
  showInactivityDialog: boolean
  showQuitDialog: boolean
  lockHolder: ReturnType<typeof useDocumentLock>['lockHolder']
  isLockedByOther: boolean
  canForceTake: boolean
  /** Whether the current user has edit permission for this scope */
  canEdit: boolean
  /** Document data from the internal useDocument query */
  document: ReturnType<typeof useDocument>['data']
  /** Whether document query errored (e.g. 404) */
  isDocError: boolean
  enterEditMode: () => Promise<void>
  handleContentChange: (json: object) => void
  handleBaselineSync: (json: object) => void
  save: () => Promise<void>
  cancel: () => void
  confirmDiscard: () => void
  cancelDiscard: () => void
  inactivitySave: () => Promise<void>
  inactivityDiscard: () => void
  inactivityKeepEditing: () => void
  forceTake: () => Promise<void>
  quitSave: () => void
  quitDiscard: () => void
  quitCancel: () => void
  /** Call on any user interaction (scroll, click, selection) to reset inactivity timer */
  resetActivity: () => void
}

// ============================================================================
// Hook
// ============================================================================

export function useEditMode({
  documentId,
  canEdit,
  isOwner = false,
}: UseEditModeOptions): UseEditModeReturn {
  const authState = useAuthState()
  const token = authState.token
  const userId = authState.user?.id ?? ''
  const userName = authState.user?.display_name ?? authState.user?.email ?? ''
  const queryClient = useQueryClient()
  const {
    registerNavigationGuard,
    unregisterNavigationGuard,
  } = useKnowledgeBase()

  // State
  const [mode, setModeState] = useState<'view' | 'edit'>('view')
  const [saveStatus, setSaveStatus] = useState<SaveStatus>({ state: 'idle' })
  const [showDiscardDialog, setShowDiscardDialog] = useState(false)
  const [showInactivityDialog, setShowInactivityDialog] = useState(false)
  const showInactivityDialogRef = useRef(false)
  const [isDirty, setIsDirtyState] = useState(false)
  const [isEntering, setIsEntering] = useState(false)
  const [isExiting, setIsExiting] = useState(false)
  const [showQuitDialog, setShowQuitDialog] = useState(false)

  // Refs — modeRef and isDirtyRef are kept in sync SYNCHRONOUSLY
  // to avoid race conditions in the navigation guard and confirmDiscard flow.
  const localContentRef = useRef<string | null>(null)
  const savedContentRef = useRef<string | null>(null)
  const rowVersionRef = useRef(1)
  const deferredActionRef = useRef<(() => void) | null>(null)
  const lastEditRef = useRef<number>(Date.now())
  const modeRef = useRef(mode)
  const isDirtyRef = useRef(isDirty)
  const documentIdRef = useRef(documentId)
  const tokenRef = useRef(token)
  const isIntentionallyExitingRef = useRef(false)
  const quitSaveAttemptsRef = useRef(0)
  const prevCanEditRef = useRef(canEdit)
  const enteringGuardRef = useRef(false)

  // Wrappers that update both state and ref synchronously
  const setMode = useCallback((m: 'view' | 'edit') => {
    modeRef.current = m
    setModeState(m)
  }, [])

  const setIsDirty = useCallback((d: boolean) => {
    isDirtyRef.current = d
    setIsDirtyState(d)
  }, [])

  // Keep refs in sync (via effect is fine — these change less frequently)
  useEffect(() => { documentIdRef.current = documentId }, [documentId])
  useEffect(() => { tokenRef.current = token }, [token])
  useEffect(() => { showInactivityDialogRef.current = showInactivityDialog }, [showInactivityDialog])

  // Document data — single source of truth, exposed to consumers
  const { data: doc, refetch: refetchDoc, isError: isDocError } = useDocument(documentId)

  // Sync row version from document
  useEffect(() => {
    if (doc?.row_version) {
      rowVersionRef.current = doc.row_version
    }
  }, [doc?.row_version])

  // Lock (no onBeforeRelease — we manage saves explicitly now)
  const lock = useDocumentLock({
    documentId,
    userId,
    userName,
    userRole: isOwner ? 'owner' : null,
    lastActivityRef: lastEditRef,
  })

  // Ref for acquireLock to avoid stale closures in effects
  const acquireLockRef = useRef(lock.acquireLock)
  useEffect(() => { acquireLockRef.current = lock.acquireLock }, [lock.acquireLock])

  // Save mutation
  const saveMutation = useSaveDocumentContent()

  // ============================================================================
  // Reset on document change
  // ============================================================================

  useEffect(() => {
    setMode('view')
    setSaveStatus({ state: 'idle' })
    setIsDirty(false)
    setShowDiscardDialog(false)
    setShowInactivityDialog(false)
    setIsEntering(false)
    setIsExiting(false)
    setShowQuitDialog(false)
    localContentRef.current = null
    savedContentRef.current = null
    deferredActionRef.current = null
  }, [documentId])

  // ============================================================================
  // Exit edit mode helper
  // ============================================================================

  const exitEditMode = useCallback(async () => {
    setIsExiting(true)
    // Set flag to prevent automatic lock re-acquisition during intentional exit
    isIntentionallyExitingRef.current = true
    try {
      await lock.releaseLock()
    } finally {
      setMode('view')
      setSaveStatus({ state: 'idle' })
      setIsDirty(false)
      setShowDiscardDialog(false)
      setShowInactivityDialog(false)
      setIsExiting(false)
      isIntentionallyExitingRef.current = false
      localContentRef.current = null
      // Clear draft from IndexedDB (user discarded or saved elsewhere)
      if (documentIdRef.current) {
        void deleteDraft(documentIdRef.current)
      }
      // Refetch to get latest server content
      if (documentIdRef.current) {
        queryClient.invalidateQueries({ queryKey: queryKeys.document(documentIdRef.current) })
      }
    }
  }, [lock, queryClient, setMode])

  // ============================================================================
  // Enter edit mode
  // ============================================================================

  const enterEditMode = useCallback(async () => {
    if (enteringGuardRef.current) return
    enteringGuardRef.current = true
    try {
      if (!documentId) return
      if (!canEdit) {
        toast.error("You don't have edit permission")
        return
      }

      setIsEntering(true)
      // Refetch document to get latest content
      const { data: freshDoc } = await refetchDoc()
      if (!freshDoc) return

      const acquired = await lock.acquireLock()
      if (!acquired) {
        // Read fresh lock status from cache (acquireLock invalidates on 409)
        const cachedLock = queryClient.getQueryData<{ lock_holder: { user_name: string } | null }>(
          queryKeys.documentLock(documentId)
        )
        const holderName = cachedLock?.lock_holder?.user_name
        toast.error(
          holderName
            ? `Being edited by ${holderName}`
            : 'Could not acquire editing lock'
        )
        return
      }

      // Store raw content as preliminary baseline — the editor's
      // onBaselineSync callback will overwrite this with TipTap-normalized
      // JSON once setContent runs (adds default attrs like textAlign/indent).
      savedContentRef.current = freshDoc.content_json ?? null
      localContentRef.current = freshDoc.content_json ?? null
      rowVersionRef.current = freshDoc.row_version
      lastEditRef.current = Date.now()
      setIsDirty(false)
      setSaveStatus({ state: 'idle' })
      setMode('edit')
    } finally {
      setIsEntering(false)
      enteringGuardRef.current = false
    }
  }, [documentId, canEdit, refetchDoc, lock, queryClient])

  // ============================================================================
  // Baseline sync (called by editor after setContent normalizes content)
  // ============================================================================

  const handleBaselineSync = useCallback((json: object) => {
    if (modeRef.current !== 'edit') return
    const normalized = JSON.stringify(json)
    savedContentRef.current = normalized
    localContentRef.current = normalized
  }, [])

  // ============================================================================
  // Content change handler
  // ============================================================================

  const handleContentChange = useCallback((json: object) => {
    // Ignore content change events in view mode — TipTap fires onUpdate
    // even for programmatic setContent calls (e.g. syncing server data).
    if (modeRef.current !== 'edit') return
    const jsonStr = JSON.stringify(json)
    localContentRef.current = jsonStr
    lastEditRef.current = Date.now()
    const dirty = jsonStr !== savedContentRef.current
    setIsDirty(dirty)
  }, [])

  // ============================================================================
  // Draft auto-buffer (crash recovery)
  // ============================================================================

  const lastDraftWriteRef = useRef(0)

  useEffect(() => {
    if (mode !== 'edit' || !documentId) return

    // Poll every 2s: if dirty and enough time has passed since last write,
    // buffer content to IndexedDB for crash recovery.
    const interval = setInterval(() => {
      if (!isDirtyRef.current || !localContentRef.current || !documentIdRef.current) return
      const now = Date.now()
      // Only write if at least DRAFT_DEBOUNCE_MS since last draft write
      if (now - lastDraftWriteRef.current < DRAFT_DEBOUNCE_MS) return
      lastDraftWriteRef.current = now
      const serverTs = doc?.updated_at ? new Date(doc.updated_at).getTime() : 0
      void saveDraft({
        documentId: documentIdRef.current,
        contentJson: localContentRef.current,
        title: doc?.title ?? '',
        serverUpdatedAt: serverTs,
        draftedAt: now,
      })
    }, DRAFT_DEBOUNCE_MS)

    return () => clearInterval(interval)
  }, [mode, documentId, doc?.updated_at, doc?.title])

  // ============================================================================
  // Save
  // ============================================================================

  const save = useCallback(async () => {
    if (!documentId || !localContentRef.current) return

    setSaveStatus({ state: 'saving' })
    setIsExiting(true)
    isIntentionallyExitingRef.current = true

    try {
      const result = await saveMutation.mutateAsync({
        documentId,
        content_json: localContentRef.current,
        row_version: rowVersionRef.current,
      })

      rowVersionRef.current = result.row_version
      savedContentRef.current = localContentRef.current
      setSaveStatus({ state: 'saved', at: Date.now() })
      setIsDirty(false)

      // Optimistically update cached document with saved content so that
      // switching to view mode shows the just-saved content immediately
      // instead of flashing stale pre-edit content from the query cache.
      queryClient.setQueryData<Document>(queryKeys.document(documentId), (old) => {
        if (!old) return old
        return {
          ...old,
          content_json: localContentRef.current,
          row_version: result.row_version,
        }
      })

      // Release lock (best-effort — don't block view transition on release failure)
      try {
        await lock.releaseLock()
      } catch {
        toast.warning('Saved, but could not release lock — it will expire automatically.')
      }

      setMode('view')
      setSaveStatus({ state: 'idle' })

      // Clear draft from IndexedDB after successful save
      void deleteDraft(documentId)

      // Background refetch to sync server-generated fields (updated_at, etc.)
      // This won't cause flicker because setQueryData above already set content_json.
      queryClient.invalidateQueries({ queryKey: queryKeys.document(documentId) })
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Save failed'
      setSaveStatus({ state: 'error', message })
      toast.error(`Save failed: ${message}`)
    } finally {
      setIsExiting(false)
      isIntentionallyExitingRef.current = false
    }
  }, [documentId, saveMutation, lock, queryClient, setMode])

  // ============================================================================
  // Cancel
  // ============================================================================

  const cancel = useCallback(() => {
    if (isDirtyRef.current) {
      deferredActionRef.current = null
      setShowDiscardDialog(true)
    } else {
      void exitEditMode()
    }
  }, [exitEditMode])

  const confirmDiscard = useCallback(() => {
    setShowDiscardDialog(false)
    const deferred = deferredActionRef.current
    deferredActionRef.current = null
    void exitEditMode().then(() => {
      deferred?.()
    }).catch(() => {
      // exitEditMode or deferred navigation failed — UI already reset
    })
  }, [exitEditMode])

  const cancelDiscard = useCallback(() => {
    setShowDiscardDialog(false)
    deferredActionRef.current = null
  }, [])

  // ============================================================================
  // Inactivity dialog actions
  // ============================================================================

  const inactivitySave = useCallback(async () => {
    setShowInactivityDialog(false)
    await save()
  }, [save])

  const inactivityDiscard = useCallback(() => {
    setShowInactivityDialog(false)
    void exitEditMode().catch(() => {
      // Best effort — lock release may fail during inactivity exit
    })
  }, [exitEditMode])

  const inactivityKeepEditing = useCallback(() => {
    setShowInactivityDialog(false)
    lastEditRef.current = Date.now()
  }, [])

  /** Call on any user interaction (scroll, click, selection) to reset inactivity timer */
  const resetActivity = useCallback(() => { lastEditRef.current = Date.now() }, [])

  // Refs for callbacks to avoid stale closures in timer effects
  const saveRef = useRef(save)
  useEffect(() => { saveRef.current = save }, [save])
  const cancelRef = useRef(cancel)
  useEffect(() => { cancelRef.current = cancel }, [cancel])
  const exitEditModeRef = useRef(exitEditMode)
  useEffect(() => { exitEditModeRef.current = exitEditMode }, [exitEditMode])

  // ============================================================================
  // Proactive inactivity timer (30s check interval)
  // ============================================================================

  useEffect(() => {
    if (mode !== 'edit') return

    const checkInterval = setInterval(() => {
      const idleMs = Date.now() - lastEditRef.current
      if (idleMs >= INACTIVITY_TIMEOUT_MS && !showInactivityDialogRef.current) {
        setShowInactivityDialog(true)
      }
    }, INACTIVITY_CHECK_MS)

    return () => clearInterval(checkInterval)
  }, [mode])

  // ============================================================================
  // Auto-save trigger (fires once after 60s of dialog being open)
  // ============================================================================

  useEffect(() => {
    if (!showInactivityDialog) return

    const timeout = setTimeout(() => {
      setShowInactivityDialog(false)
      if (isDirtyRef.current) {
        void saveRef.current()
      } else {
        void exitEditModeRef.current()
      }
    }, AUTO_SAVE_TIMEOUT_MS)

    return () => clearTimeout(timeout)
  }, [showInactivityDialog])

  // ============================================================================
  // Quit dialog actions
  // ============================================================================

  const quitSave = useCallback(() => {
    setShowQuitDialog(false)
    // Prevent the lock-expired effect from re-acquiring during quit
    isIntentionallyExitingRef.current = true
    if (!documentIdRef.current || !localContentRef.current || !window.electronAPI) {
      isIntentionallyExitingRef.current = false
      window.electronAPI?.confirmQuitSave()
      return
    }
    const docId = documentIdRef.current
    const headers = { Authorization: `Bearer ${tokenRef.current}` }
    // Save → release lock (best effort) → quit
    void window.electronAPI
      .put(
        `/api/documents/${docId}/content`,
        {
          content_json: localContentRef.current,
          row_version: rowVersionRef.current,
        },
        headers
      )
      .then(() => {
        // Save succeeded — clear draft and release lock (best-effort, don't block quit)
        void deleteDraft(docId)
        void window.electronAPI?.delete<void>(`/api/documents/${docId}/lock`, headers).catch(() => {})
        window.electronAPI?.confirmQuitSave()
      })
      .catch(() => {
        quitSaveAttemptsRef.current++
        if (quitSaveAttemptsRef.current >= 3) {
          // Max retries exceeded — save draft and quit
          if (localContentRef.current && documentIdRef.current) {
            void saveDraft({
              documentId: documentIdRef.current,
              contentJson: localContentRef.current,
              title: 'Quit recovery',
              serverUpdatedAt: 0,
              draftedAt: Date.now(),
            })
          }
          toast.error('Could not save after multiple attempts. Your changes were saved as a local draft.')
          window.electronAPI?.confirmQuitSave()
          return
        }
        // Save failed — don't quit, let user retry
        isIntentionallyExitingRef.current = false
        toast.error('Save failed during quit. Your changes are still in the editor.')
        setShowQuitDialog(true)
      })
  }, [])

  const quitDiscard = useCallback(() => {
    setShowQuitDialog(false)
    // Prevent the lock-expired effect from re-acquiring during quit
    isIntentionallyExitingRef.current = true
    const docId = documentIdRef.current
    if (docId && window.electronAPI) {
      const headers = { Authorization: `Bearer ${tokenRef.current}` }
      // Release lock → quit
      void window.electronAPI
        .delete<void>(`/api/documents/${docId}/lock`, headers)
        .then(() => window.electronAPI?.confirmQuitSave())
        .catch(() => window.electronAPI?.confirmQuitSave())
    } else {
      window.electronAPI?.confirmQuitSave()
    }
  }, [])

  const quitCancel = useCallback(() => {
    setShowQuitDialog(false)
    window.electronAPI?.cancelQuit()
  }, [])

  // ============================================================================
  // Navigation guard
  // ============================================================================

  useEffect(() => {
    const guard = (targetDocId: string | null, proceed: () => void): boolean => {
      // Not in edit mode — allow
      if (modeRef.current !== 'edit') return true

      // Same document — allow
      if (targetDocId === documentIdRef.current) return true

      // In edit mode + clean — exit silently and allow
      if (!isDirtyRef.current) {
        void exitEditMode()
        return true
      }

      // In edit mode + dirty — block and show dialog
      deferredActionRef.current = proceed
      setShowDiscardDialog(true)
      return false
    }

    registerNavigationGuard(guard)
    return () => unregisterNavigationGuard()
  }, [registerNavigationGuard, unregisterNavigationGuard, exitEditMode])

  // ============================================================================
  // Screen navigation guard (sidebar clicks to other screens)
  // ============================================================================

  useEffect(() => {
    const guard = (proceed: () => void): boolean => {
      // Not in edit mode — allow
      if (modeRef.current !== 'edit') return true

      // In edit mode + clean — exit silently and allow
      if (!isDirtyRef.current) {
        void exitEditMode()
        return true
      }

      // In edit mode + dirty — block and show dialog
      deferredActionRef.current = proceed
      setShowDiscardDialog(true)
      return false
    }

    registerScreenGuard(guard)
    return () => unregisterScreenGuard()
  }, [exitEditMode])

  // ============================================================================
  // App close guard (show quit dialog if unsaved changes)
  // ============================================================================

  useEffect(() => {
    if (!window.electronAPI) return

    const cleanup = window.electronAPI.onBeforeQuit(() => {
      if (
        isDirtyRef.current &&
        localContentRef.current &&
        documentIdRef.current &&
        window.electronAPI
      ) {
        // Show in-app quit dialog
        quitSaveAttemptsRef.current = 0
        setShowQuitDialog(true)
      } else {
        // No unsaved changes — quit immediately
        window.electronAPI.confirmQuitSave()
      }
    })

    return cleanup
  }, [])

  // ============================================================================
  // Force-taken / lock-expired detection
  // ============================================================================

  const prevLockedByMeRef = useRef(lock.isLockedByMe)

  useEffect(() => {
    // Detect transition: was locked by me → no longer locked by me, while in edit mode
    if (prevLockedByMeRef.current && !lock.isLockedByMe && modeRef.current === 'edit') {
      // Ignore lock loss if we're intentionally exiting (prevents automatic re-acquisition)
      if (isIntentionallyExitingRef.current) {
        prevLockedByMeRef.current = lock.isLockedByMe
        return
      }

      if (lock.lockHolder !== null) {
        // Lock was force-taken by another user
        const takerName = lock.lockHolder?.user_name ?? 'another user'

        if (isDirtyRef.current && localContentRef.current && documentIdRef.current) {
          const serverTs = doc?.updated_at ? new Date(doc.updated_at).getTime() : 0
          saveDraft({
            documentId: documentIdRef.current,
            contentJson: localContentRef.current,
            title: doc?.title ?? 'Force-taken recovery',
            serverUpdatedAt: serverTs,
            draftedAt: Date.now(),
          }).then(() => {
            toast.warning(`Editing was taken over by ${takerName}. Your unsaved changes were saved as a draft.`)
          }).catch(() => {
            toast.error(`Editing was taken over by ${takerName}. Warning: draft save failed — your unsaved changes may be lost.`)
          })
        } else {
          toast.warning(`Editing was taken over by ${takerName}`)
        }

        setMode('view')
        setSaveStatus({ state: 'idle' })
        setIsDirty(false)
        setShowDiscardDialog(false)
        setShowInactivityDialog(false)
        if (documentIdRef.current) {
          queryClient.invalidateQueries({ queryKey: queryKeys.document(documentIdRef.current) })
        }
      } else {
        // Lock expired (inactivity — server TTL ran out)
        // Try to silently re-acquire before interrupting the user
        void (async () => {
          let acquired = false
          try {
            acquired = await acquireLockRef.current()
          } catch {
            // Acquire failed — fall through to handle as not-acquired
          }

          if (acquired) {
            // Re-acquired lock — check if content changed while lock was expired
            lastEditRef.current = Date.now()
            try {
              const { data: freshDoc } = await refetchDoc()
              if (freshDoc) {
                const serverContent = freshDoc.content_json ?? null
                // Update row_version regardless — server is source of truth
                rowVersionRef.current = freshDoc.row_version
                if (serverContent !== savedContentRef.current) {
                  // Content changed on server while lock was expired
                  if (isDirtyRef.current) {
                    // User has local edits + server changed — conflict
                    // Save draft of user's local edits for safety, then reset to server content
                    const localDraftContent = localContentRef.current
                    const draftDocId = documentIdRef.current
                    savedContentRef.current = serverContent
                    localContentRef.current = serverContent
                    setIsDirty(false)
                    if (localDraftContent && draftDocId) {
                      const serverTs = freshDoc.updated_at
                        ? new Date(freshDoc.updated_at).getTime()
                        : 0
                      saveDraft({
                        documentId: draftDocId,
                        contentJson: localDraftContent,
                        title: freshDoc.title ?? 'Conflict recovery',
                        serverUpdatedAt: serverTs,
                        draftedAt: Date.now(),
                      }).then(() => {
                        lastDraftWriteRef.current = Date.now()
                        toast.warning(
                          'Document was modified while you were away. Your changes were saved as a draft.'
                        )
                        void exitEditMode()
                      }).catch(() => {
                        toast.error(
                          'Document was modified while you were away. Warning: draft save failed — your unsaved changes may be lost.'
                        )
                        void exitEditMode()
                      })
                    } else {
                      toast.warning(
                        'Document was modified while you were away.'
                      )
                      void exitEditMode()
                    }
                  } else {
                    // No local edits — just update baseline to server content
                    savedContentRef.current = serverContent
                    localContentRef.current = serverContent
                  }
                }
                // else: server content unchanged — silently continue editing
              }
            } catch {
              // Refetch failed — continue with existing content
              // (row_version will catch conflicts on save)
            }
          } else if (isDirtyRef.current) {
            setShowInactivityDialog(true)
          } else {
            toast.info('Editing session ended due to inactivity')
            void exitEditMode()
          }
        })()
      }
    }
    prevLockedByMeRef.current = lock.isLockedByMe
  }, [lock.isLockedByMe, lock.lockHolder, queryClient, exitEditMode, setMode, refetchDoc])

  // ============================================================================
  // Auto-eject from edit mode when permissions are revoked mid-edit
  // ============================================================================

  useEffect(() => {
    const wasCanEdit = prevCanEditRef.current
    prevCanEditRef.current = canEdit

    // Only trigger on true→false transition while in edit mode
    if (wasCanEdit === true && canEdit === false && modeRef.current === 'edit') {
      // Force-exit regardless of dirty state — user no longer has permission.
      // Unlike voluntary cancel (which shows a discard dialog), permission
      // revocation is non-negotiable: the backend will reject any save attempt.
      toast.warning('Your edit permission was revoked. Unsaved changes were discarded.')
      void exitEditModeRef.current()
    }
  }, [canEdit])

  // ============================================================================
  // Keyboard shortcuts (Ctrl+S → save, Ctrl+W → cancel)
  // ============================================================================

  useEffect(() => {
    if (mode !== 'edit') return

    const handler = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey
      if (!mod) return

      if (e.key === 's') {
        e.preventDefault()
        // Guard against double-save while save+release is in progress
        if (isIntentionallyExitingRef.current) return
        void saveRef.current()
      } else if (e.key === 'w') {
        e.preventDefault()
        cancelRef.current()
      }
    }

    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [mode])

  // ============================================================================
  // Force-take (owner)
  // ============================================================================

  const forceTake = useCallback(async () => {
    if (enteringGuardRef.current) return
    enteringGuardRef.current = true
    try {
      if (!canEdit) {
        toast.error("You don't have edit permission")
        return
      }
      setIsEntering(true)
      const taken = await lock.forceTakeLock()
      if (taken) {
        // Refetch and enter edit mode
        const { data: freshDoc } = await refetchDoc()
        if (freshDoc) {
          savedContentRef.current = freshDoc.content_json ?? null
          localContentRef.current = freshDoc.content_json ?? null
          rowVersionRef.current = freshDoc.row_version
          lastEditRef.current = Date.now()
          setIsDirty(false)
          setSaveStatus({ state: 'idle' })
          setMode('edit')
        }
      }
    } finally {
      setIsEntering(false)
      enteringGuardRef.current = false
    }
  }, [canEdit, lock, refetchDoc])

  return {
    mode,
    saveStatus,
    isDirty,
    isSaving: saveMutation.isPending,
    isEntering,
    isExiting,
    showDiscardDialog,
    showInactivityDialog,
    showQuitDialog,
    lockHolder: lock.lockHolder,
    isLockedByOther: lock.isLockedByOther,
    canForceTake: lock.canForceTake && canEdit,
    canEdit,
    document: doc,
    isDocError,
    enterEditMode,
    handleContentChange,
    handleBaselineSync,
    save,
    cancel,
    confirmDiscard,
    cancelDiscard,
    inactivitySave,
    inactivityDiscard,
    inactivityKeepEditing,
    forceTake,
    quitSave,
    quitDiscard,
    quitCancel,
    resetActivity,
  }
}
