/**
 * useDocumentLock Hook
 *
 * Manages document lock lifecycle: acquire, release, force-take, heartbeat,
 * inactivity auto-release, and real-time WebSocket updates.
 *
 * Features:
 * - Lock status query with 30s fallback poll
 * - Acquire/release/force-take mutations
 * - 10s heartbeat interval while lock is held
 * - 30s inactivity auto-release (calls onBeforeRelease first)
 * - WebSocket subscription for real-time lock state updates
 * - Unmount cleanup with fire-and-forget release
 *
 * Also exports useDocumentLockStatus for read-only lock status display
 * (e.g., showing lock icons in the folder tree).
 *
 * @module use-document-lock
 */

import { useCallback, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '@/contexts/auth-context'
import { useWebSocket } from './use-websocket'
import { MessageType } from '@/lib/websocket'
import { queryKeys } from '@/lib/query-client'

// ============================================================================
// Types
// ============================================================================

export interface LockHolder {
  user_id: string
  user_name: string
  acquired_at: number | null
}

export interface LockStatusResponse {
  is_locked: boolean
  lock_holder: LockHolder | null
}

export interface UseDocumentLockOptions {
  documentId: string | null
  userId: string
  userName: string
  userRole: string | null // 'owner' | 'editor' | 'viewer' | null
  onBeforeRelease?: () => Promise<void> // Save callback (Phase 4's saveNow)
}

export interface UseDocumentLockReturn {
  lockHolder: LockHolder | null
  isLockedByMe: boolean
  isLockedByOther: boolean
  acquireLock: () => Promise<boolean>
  releaseLock: () => Promise<void>
  forceTakeLock: () => Promise<boolean>
  canForceTake: boolean
  isLoading: boolean
}

// ============================================================================
// Constants
// ============================================================================

const HEARTBEAT_INTERVAL_MS = 10_000 // 10 seconds
const INACTIVITY_CHECK_INTERVAL_MS = 5_000 // 5 seconds
const INACTIVITY_THRESHOLD_MS = 30_000 // 30 seconds
const LOCK_POLL_INTERVAL_MS = 30_000 // 30 seconds fallback poll

// ============================================================================
// Helpers
// ============================================================================

function getAuthHeaders(token: string | null): Record<string, string> {
  if (!token) return {}
  return { Authorization: `Bearer ${token}` }
}

// ============================================================================
// Hook
// ============================================================================

export function useDocumentLock({
  documentId,
  userId,
  userName: _userName,
  userRole,
  onBeforeRelease,
}: UseDocumentLockOptions): UseDocumentLockReturn {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()
  const { subscribe, status: wsStatus } = useWebSocket()

  // Refs to avoid re-renders and stale closures
  const lockReleasedRef = useRef(false)
  const heartbeatTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const inactivityTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const lastActivityRef = useRef<number>(Date.now())
  const onBeforeReleaseRef = useRef(onBeforeRelease)
  const documentIdRef = useRef(documentId)
  const tokenRef = useRef(token)
  const userIdRef = useRef(userId)

  // Keep refs current
  useEffect(() => {
    onBeforeReleaseRef.current = onBeforeRelease
    documentIdRef.current = documentId
    tokenRef.current = token
    userIdRef.current = userId
  })

  // ============================================================================
  // Lock Status Query
  // ============================================================================

  const lockQuery = useQuery({
    queryKey: queryKeys.documentLock(documentId || ''),
    queryFn: async (): Promise<LockStatusResponse> => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.get<LockStatusResponse>(
        `/api/documents/${documentId}/lock`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error('Failed to fetch lock status')
      }

      return response.data
    },
    enabled: !!token && !!documentId,
    refetchInterval: LOCK_POLL_INTERVAL_MS,
    staleTime: 10_000,
    gcTime: 60_000,
  })

  // Derived state
  const lockHolder = lockQuery.data?.lock_holder ?? null
  const isLockedByMe = lockHolder?.user_id === userId && !!userId
  const isLockedByOther = lockHolder != null && lockHolder.user_id !== userId
  const canForceTake = isLockedByOther && userRole === 'owner'

  // Store isLockedByMe in ref for cleanup
  const isLockedByMeRef = useRef(isLockedByMe)
  useEffect(() => {
    isLockedByMeRef.current = isLockedByMe
  }, [isLockedByMe])

  // ============================================================================
  // Acquire Mutation
  // ============================================================================

  const acquireMutation = useMutation({
    mutationFn: async (): Promise<boolean> => {
      if (!window.electronAPI || !documentId) return false

      const response = await window.electronAPI.post<LockStatusResponse>(
        `/api/documents/${documentId}/lock`,
        {},
        getAuthHeaders(token)
      )

      if (response.status === 200) {
        lockReleasedRef.current = false
        return true
      }

      // 409 = locked by someone else
      if (response.status === 409) {
        queryClient.invalidateQueries({ queryKey: queryKeys.documentLock(documentId) })
        return false
      }

      throw new Error('Failed to acquire lock')
    },
    onSuccess: (acquired) => {
      if (acquired && documentId) {
        queryClient.invalidateQueries({ queryKey: queryKeys.documentLock(documentId) })
      }
    },
  })

  // ============================================================================
  // Release Mutation
  // ============================================================================

  const releaseMutation = useMutation({
    mutationFn: async (): Promise<void> => {
      if (!window.electronAPI || !documentId || lockReleasedRef.current) return

      lockReleasedRef.current = true

      // Save before release
      try {
        await onBeforeReleaseRef.current?.()
      } catch {
        // Best effort save
      }

      const response = await window.electronAPI.delete<void>(
        `/api/documents/${documentId}/lock`,
        getAuthHeaders(token)
      )

      if (response.status !== 200 && response.status !== 204) {
        // Reset flag if release failed
        lockReleasedRef.current = false
      }
    },
    onSuccess: () => {
      if (documentId) {
        queryClient.invalidateQueries({ queryKey: queryKeys.documentLock(documentId) })
      }
    },
  })

  // ============================================================================
  // Force-Take Mutation
  // ============================================================================

  const forceTakeMutation = useMutation({
    mutationFn: async (): Promise<boolean> => {
      if (!window.electronAPI || !documentId) return false

      const response = await window.electronAPI.post<LockStatusResponse>(
        `/api/documents/${documentId}/lock/force-take`,
        {},
        getAuthHeaders(token)
      )

      if (response.status === 200) {
        lockReleasedRef.current = false
        return true
      }

      return false
    },
    onSuccess: (taken) => {
      if (taken && documentId) {
        queryClient.invalidateQueries({ queryKey: queryKeys.documentLock(documentId) })
      }
    },
  })

  // ============================================================================
  // Stable callbacks
  // ============================================================================

  const acquireLock = useCallback(async (): Promise<boolean> => {
    try {
      return await acquireMutation.mutateAsync()
    } catch {
      return false
    }
  }, [acquireMutation])

  const releaseLock = useCallback(async (): Promise<void> => {
    try {
      await releaseMutation.mutateAsync()
    } catch {
      // Best effort release
    }
  }, [releaseMutation])

  const forceTakeLock = useCallback(async (): Promise<boolean> => {
    try {
      return await forceTakeMutation.mutateAsync()
    } catch {
      return false
    }
  }, [forceTakeMutation])

  // ============================================================================
  // Heartbeat
  // ============================================================================

  useEffect(() => {
    if (!isLockedByMe || !documentId) {
      if (heartbeatTimerRef.current) {
        clearInterval(heartbeatTimerRef.current)
        heartbeatTimerRef.current = null
      }
      return
    }

    const sendHeartbeat = async () => {
      if (!window.electronAPI || !documentIdRef.current) return

      try {
        const response = await window.electronAPI.post<void>(
          `/api/documents/${documentIdRef.current}/lock/heartbeat`,
          {},
          getAuthHeaders(tokenRef.current)
        )

        // 409 = lock lost (expired or taken)
        if (response.status === 409) {
          queryClient.invalidateQueries({
            queryKey: queryKeys.documentLock(documentIdRef.current),
          })
        }
      } catch {
        // Heartbeat failure - invalidate to check status
        if (documentIdRef.current) {
          queryClient.invalidateQueries({
            queryKey: queryKeys.documentLock(documentIdRef.current),
          })
        }
      }
    }

    heartbeatTimerRef.current = setInterval(sendHeartbeat, HEARTBEAT_INTERVAL_MS)

    return () => {
      if (heartbeatTimerRef.current) {
        clearInterval(heartbeatTimerRef.current)
        heartbeatTimerRef.current = null
      }
    }
  }, [isLockedByMe, documentId, queryClient])

  // ============================================================================
  // Inactivity Timer
  // ============================================================================

  useEffect(() => {
    if (!isLockedByMe || !documentId) {
      if (inactivityTimerRef.current) {
        clearInterval(inactivityTimerRef.current)
        inactivityTimerRef.current = null
      }
      return
    }

    // Reset activity on lock acquire
    lastActivityRef.current = Date.now()

    // Activity tracking
    const trackActivity = () => {
      lastActivityRef.current = Date.now()
    }

    // Listen for activity events
    window.addEventListener('keydown', trackActivity)
    window.addEventListener('mousemove', trackActivity)
    window.addEventListener('click', trackActivity)

    // Check inactivity periodically
    inactivityTimerRef.current = setInterval(async () => {
      const elapsed = Date.now() - lastActivityRef.current
      if (elapsed > INACTIVITY_THRESHOLD_MS) {
        // Auto-release: save first, then release
        try {
          await onBeforeReleaseRef.current?.()
        } catch {
          // Best effort save
        }

        if (
          documentIdRef.current &&
          !lockReleasedRef.current &&
          window.electronAPI
        ) {
          lockReleasedRef.current = true
          await window.electronAPI.delete<void>(
            `/api/documents/${documentIdRef.current}/lock`,
            getAuthHeaders(tokenRef.current)
          )
          queryClient.invalidateQueries({
            queryKey: queryKeys.documentLock(documentIdRef.current),
          })
        }
      }
    }, INACTIVITY_CHECK_INTERVAL_MS)

    return () => {
      window.removeEventListener('keydown', trackActivity)
      window.removeEventListener('mousemove', trackActivity)
      window.removeEventListener('click', trackActivity)
      if (inactivityTimerRef.current) {
        clearInterval(inactivityTimerRef.current)
        inactivityTimerRef.current = null
      }
    }
  }, [isLockedByMe, documentId, queryClient])

  // ============================================================================
  // WebSocket Subscription
  // ============================================================================

  useEffect(() => {
    if (!documentId || !wsStatus.isConnected) return

    const handleLocked = (data: { document_id: string; lock_holder: LockHolder }) => {
      if (data.document_id !== documentId) return
      queryClient.setQueryData<LockStatusResponse>(
        queryKeys.documentLock(documentId),
        { is_locked: true, lock_holder: data.lock_holder }
      )
    }

    const handleUnlocked = (data: { document_id: string }) => {
      if (data.document_id !== documentId) return
      queryClient.setQueryData<LockStatusResponse>(
        queryKeys.documentLock(documentId),
        { is_locked: false, lock_holder: null }
      )
    }

    const handleForceTaken = (data: { document_id: string; lock_holder: LockHolder }) => {
      if (data.document_id !== documentId) return

      // If I lost the lock, save before updating state
      if (data.lock_holder.user_id !== userIdRef.current) {
        void onBeforeReleaseRef.current?.()
        lockReleasedRef.current = true
      } else {
        // I now hold the lock
        lockReleasedRef.current = false
      }

      queryClient.setQueryData<LockStatusResponse>(
        queryKeys.documentLock(documentId),
        { is_locked: true, lock_holder: data.lock_holder }
      )
    }

    const unsubLocked = subscribe<{ document_id: string; lock_holder: LockHolder }>(
      MessageType.DOCUMENT_LOCKED,
      handleLocked
    )
    const unsubUnlocked = subscribe<{ document_id: string }>(
      MessageType.DOCUMENT_UNLOCKED,
      handleUnlocked
    )
    const unsubForceTaken = subscribe<{ document_id: string; lock_holder: LockHolder }>(
      MessageType.DOCUMENT_FORCE_TAKEN,
      handleForceTaken
    )

    return () => {
      unsubLocked()
      unsubUnlocked()
      unsubForceTaken()
    }
  }, [documentId, wsStatus.isConnected, subscribe, queryClient])

  // ============================================================================
  // Cleanup on Unmount
  // ============================================================================

  useEffect(() => {
    return () => {
      // Fire-and-forget release if we hold the lock
      if (
        isLockedByMeRef.current &&
        !lockReleasedRef.current &&
        documentIdRef.current &&
        window.electronAPI
      ) {
        lockReleasedRef.current = true
        void window.electronAPI.delete<void>(
          `/api/documents/${documentIdRef.current}/lock`,
          getAuthHeaders(tokenRef.current)
        )
      }

      // Clear timers
      if (heartbeatTimerRef.current) {
        clearInterval(heartbeatTimerRef.current)
        heartbeatTimerRef.current = null
      }
      if (inactivityTimerRef.current) {
        clearInterval(inactivityTimerRef.current)
        inactivityTimerRef.current = null
      }
    }
  }, [])

  // ============================================================================
  // Return
  // ============================================================================

  return {
    lockHolder,
    isLockedByMe,
    isLockedByOther,
    acquireLock,
    releaseLock,
    forceTakeLock,
    canForceTake,
    isLoading: lockQuery.isLoading || acquireMutation.isPending || releaseMutation.isPending,
  }
}

// ============================================================================
// Read-Only Lock Status Hook (for tree display)
// ============================================================================

/**
 * Return type for useDocumentLockStatus hook
 */
export interface UseDocumentLockStatusReturn {
  /** Whether the document is currently locked */
  isLocked: boolean
  /** Info about who holds the lock (null if not locked) */
  lockHolder: { userId: string; userName: string } | null
  /** Whether the lock status is being loaded */
  isLoading: boolean
}

/**
 * Query lock status for a document (read-only, for display).
 *
 * This is a SEPARATE hook from useDocumentLock which is for acquiring locks.
 * Use this hook to display lock indicators in the folder tree or document list.
 *
 * Features:
 * - Queries lock status from API
 * - Subscribes to WebSocket for real-time updates
 * - 30s polling fallback
 * - Disabled when documentId is null
 *
 * @param documentId - Document ID to query lock status for (null to disable)
 * @returns Lock status info for display
 *
 * @example
 * ```tsx
 * function DocumentItem({ doc }) {
 *   const { isLocked, lockHolder } = useDocumentLockStatus(doc.id)
 *
 *   return (
 *     <div>
 *       <span>{doc.title}</span>
 *       {isLocked && <Lock title={`Editing: ${lockHolder?.userName}`} />}
 *     </div>
 *   )
 * }
 * ```
 */
export function useDocumentLockStatus(documentId: string | null): UseDocumentLockStatusReturn {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()
  const { subscribe, status: wsStatus } = useWebSocket()

  // Query lock status
  const { data, isLoading } = useQuery({
    queryKey: queryKeys.documentLock(documentId ?? ''),
    queryFn: async (): Promise<LockStatusResponse> => {
      if (!window.electronAPI || !documentId) {
        return { is_locked: false, lock_holder: null }
      }

      const response = await window.electronAPI.get<LockStatusResponse>(
        `/api/documents/${documentId}/lock`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        // Return unlocked state on error
        return { is_locked: false, lock_holder: null }
      }

      return response.data
    },
    enabled: !!token && !!documentId,
    staleTime: 10_000, // 10 seconds
    refetchInterval: 30_000, // 30s fallback poll
    gcTime: 60_000,
  })

  // Subscribe to WebSocket for real-time lock updates
  useEffect(() => {
    if (!documentId || !wsStatus.isConnected) return

    const handleLocked = (eventData: { document_id: string; lock_holder: LockHolder }) => {
      if (eventData.document_id !== documentId) return
      queryClient.setQueryData<LockStatusResponse>(
        queryKeys.documentLock(documentId),
        { is_locked: true, lock_holder: eventData.lock_holder }
      )
    }

    const handleUnlocked = (eventData: { document_id: string }) => {
      if (eventData.document_id !== documentId) return
      queryClient.setQueryData<LockStatusResponse>(
        queryKeys.documentLock(documentId),
        { is_locked: false, lock_holder: null }
      )
    }

    const handleForceTaken = (eventData: { document_id: string; lock_holder: LockHolder }) => {
      if (eventData.document_id !== documentId) return
      queryClient.setQueryData<LockStatusResponse>(
        queryKeys.documentLock(documentId),
        { is_locked: true, lock_holder: eventData.lock_holder }
      )
    }

    const unsubLocked = subscribe<{ document_id: string; lock_holder: LockHolder }>(
      MessageType.DOCUMENT_LOCKED,
      handleLocked
    )
    const unsubUnlocked = subscribe<{ document_id: string }>(
      MessageType.DOCUMENT_UNLOCKED,
      handleUnlocked
    )
    const unsubForceTaken = subscribe<{ document_id: string; lock_holder: LockHolder }>(
      MessageType.DOCUMENT_FORCE_TAKEN,
      handleForceTaken
    )

    return () => {
      unsubLocked()
      unsubUnlocked()
      unsubForceTaken()
    }
  }, [documentId, wsStatus.isConnected, subscribe, queryClient])

  // Derive return values
  const isLocked = !!data?.is_locked && !!data?.lock_holder
  const lockHolder = data?.lock_holder
    ? { userId: data.lock_holder.user_id, userName: data.lock_holder.user_name }
    : null

  return {
    isLocked,
    lockHolder,
    isLoading,
  }
}
