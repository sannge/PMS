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
import { useKnowledgeBase } from '@/contexts/knowledge-base-context'
import { useAuthStore } from '@/contexts/auth-context'
import { useQueryClient } from '@tanstack/react-query'
import { queryKeys } from '@/lib/query-client'
import {
  registerScreenGuard,
  unregisterScreenGuard,
} from '@/lib/screen-navigation-guard'
import type { SaveStatus } from '@/components/knowledge/editor-types'

// ============================================================================
// Constants
// ============================================================================

const AUTO_SAVE_TIMEOUT_MS = 60_000           // 60 seconds
const INACTIVITY_CHECK_MS = 30_000           // 30 seconds

export interface UseEditModeOptions {
  documentId: string | null
  userRole: string | null
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
}

// ============================================================================
// Hook
// ============================================================================

export function useEditMode({
  documentId,
  userRole,
}: UseEditModeOptions): UseEditModeReturn {
  const token = useAuthStore((s) => s.token)
  const userId = useAuthStore((s) => s.user?.id ?? '')
  const userName = useAuthStore((s) => s.user?.display_name ?? s.user?.email ?? '')
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
    userRole,
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
    if (!documentId) return

    setIsEntering(true)
    try {
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
    }
  }, [documentId, refetchDoc, lock])

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
  // Save
  // ============================================================================

  const save = useCallback(async () => {
    if (!documentId || !localContentRef.current) return

    setSaveStatus({ state: 'saving' })
    setIsExiting(true)

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

      // Set flag to prevent automatic lock re-acquisition during intentional exit
      isIntentionallyExitingRef.current = true

      // Release lock and go back to view mode
      await lock.releaseLock()
      setMode('view')
      setSaveStatus({ state: 'idle' })

      // Invalidate to refetch latest
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
    void exitEditMode()
  }, [exitEditMode])

  const inactivityKeepEditing = useCallback(() => {
    setShowInactivityDialog(false)
    lastEditRef.current = Date.now()
  }, [])

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
      if (idleMs >= INACTIVITY_TIMEOUT_MS && !showInactivityDialog) {
        setShowInactivityDialog(true)
      }
    }, INACTIVITY_CHECK_MS)

    return () => clearInterval(checkInterval)
  }, [mode, showInactivityDialog])

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
      window.electronAPI?.confirmQuitSave()
      return
    }
    const docId = documentIdRef.current
    const headers = { Authorization: `Bearer ${tokenRef.current}` }
    // Save → release lock → quit
    void window.electronAPI
      .put(
        `/api/documents/${docId}/content`,
        {
          content_json: localContentRef.current,
          row_version: rowVersionRef.current,
        },
        headers
      )
      .then(() => window.electronAPI?.delete<void>(`/api/documents/${docId}/lock`, headers))
      .then(() => window.electronAPI?.confirmQuitSave())
      .catch(() => window.electronAPI?.confirmQuitSave())
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
        toast.warning(`Editing was taken over by ${takerName}`)
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
        void acquireLockRef.current().then((acquired) => {
          if (acquired) {
            // Silently recovered — reset activity timestamp
            lastEditRef.current = Date.now()
          } else if (isDirtyRef.current) {
            setShowInactivityDialog(true)
          } else {
            toast.info('Editing session ended due to inactivity')
            void exitEditMode()
          }
        }).catch(() => {
          if (isDirtyRef.current) {
            setShowInactivityDialog(true)
          } else {
            toast.info('Editing session ended due to inactivity')
            void exitEditMode()
          }
        })
      }
    }
    prevLockedByMeRef.current = lock.isLockedByMe
  }, [lock.isLockedByMe, lock.lockHolder, queryClient, exitEditMode, setMode])

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
    setIsEntering(true)
    try {
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
    }
  }, [lock, refetchDoc])

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
    canForceTake: lock.canForceTake,
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
  }
}
