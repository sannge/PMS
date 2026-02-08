/**
 * useDocumentLock Hook
 *
 * Manages document lock lifecycle: acquire, release, force-take, heartbeat,
 * and real-time WebSocket updates.
 *
 * Features:
 * - Lock status query with 30s fallback poll
 * - Acquire/release/force-take mutations
 * - 60s heartbeat interval while lock is held
 * - WebSocket subscription for real-time lock state updates
 * - Unmount cleanup with fire-and-forget release
 *
 * Also exports useDocumentLockStatus for read-only lock status display
 * (e.g., showing lock icons in the folder tree).
 *
 * @module use-document-lock
 */

import React, { useCallback, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuthStore } from "@/contexts/auth-context";
import { useWebSocket } from "./use-websocket";
import { MessageType } from "@/lib/websocket";
import { queryKeys } from "@/lib/query-client";
import { isTempId } from "./use-documents";

// ============================================================================
// Types
// ============================================================================

export interface LockHolder {
  user_id: string;
  user_name: string;
  acquired_at: number | null;
}

export interface LockStatusResponse {
  is_locked: boolean;
  lock_holder: LockHolder | null;
}

export interface UseDocumentLockOptions {
  documentId: string | null;
  userId: string;
  userName: string;
  userRole: string | null; // 'owner' | 'editor' | 'viewer' | null
  lastActivityRef?: React.RefObject<number>;
}

export interface UseDocumentLockReturn {
  lockHolder: LockHolder | null;
  isLockedByMe: boolean;
  isLockedByOther: boolean;
  acquireLock: () => Promise<boolean>;
  releaseLock: () => Promise<void>;
  forceTakeLock: () => Promise<boolean>;
  canForceTake: boolean;
  isLoading: boolean;
}

// ============================================================================
// Constants
// ============================================================================

const HEARTBEAT_INTERVAL_MS = 60_000; // 60 seconds
const LOCK_POLL_INTERVAL_MS = 30_000; // 30 seconds fallback poll
/** After this idle duration, heartbeats stop and the proactive inactivity dialog fires. */
export const INACTIVITY_TIMEOUT_MS = 1 * 60 * 1000; // 5 minutes
// isTempId imported from use-documents.ts

// ============================================================================
// Helpers
// ============================================================================

function getAuthHeaders(token: string | null): Record<string, string> {
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

/** Normalize API response (field is `locked`) to frontend shape (`is_locked`). */
function normalizeLockResponse(
  raw: Record<string, unknown>,
): LockStatusResponse {
  return {
    is_locked: (raw.is_locked ?? raw.locked ?? false) as boolean,
    lock_holder: (raw.lock_holder as LockHolder | null) ?? null,
  };
}

// ============================================================================
// Hook
// ============================================================================

export function useDocumentLock({
  documentId,
  userId,
  userName: _userName,
  userRole,
  lastActivityRef,
}: UseDocumentLockOptions): UseDocumentLockReturn {
  const token = useAuthStore((s) => s.token);
  const queryClient = useQueryClient();
  const { subscribe, status: wsStatus } = useWebSocket();

  // Refs to avoid re-renders and stale closures
  const lockReleasedRef = useRef(false);
  const heartbeatTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const documentIdRef = useRef(documentId);
  const tokenRef = useRef(token);
  const userIdRef = useRef(userId);

  // Keep refs current
  useEffect(() => {
    documentIdRef.current = documentId;
    tokenRef.current = token;
    userIdRef.current = userId;
  });

  // Reset lockReleasedRef when switching documents
  useEffect(() => {
    lockReleasedRef.current = false;
  }, [documentId]);

  // ============================================================================
  // Lock Status Query
  // ============================================================================

  const lockQuery = useQuery({
    queryKey: queryKeys.documentLock(documentId || ""),
    queryFn: async (): Promise<LockStatusResponse> => {
      if (!window.electronAPI) {
        throw new Error("Electron API not available");
      }

      const response = await window.electronAPI.get<Record<string, unknown>>(
        `/api/documents/${documentId}/lock`,
        getAuthHeaders(token),
      );

      if (response.status !== 200) {
        throw new Error("Failed to fetch lock status");
      }

      return normalizeLockResponse(response.data);
    },
    // Skip temp IDs from optimistic updates - they don't exist on the server yet
    enabled: !!token && !!documentId && !isTempId(documentId),
    refetchInterval: LOCK_POLL_INTERVAL_MS,
    staleTime: 10_000,
    gcTime: 60_000,
  });

  // Derived state
  const lockHolder = lockQuery.data?.lock_holder ?? null;
  const isLockedByMe = lockHolder?.user_id === userId && !!userId;
  const isLockedByOther = lockHolder != null && lockHolder.user_id !== userId;
  const canForceTake = isLockedByOther && userRole === "owner";

  // Store isLockedByMe in ref for cleanup
  const isLockedByMeRef = useRef(isLockedByMe);
  useEffect(() => {
    isLockedByMeRef.current = isLockedByMe;
  }, [isLockedByMe]);

  // ============================================================================
  // Acquire Mutation
  // ============================================================================

  const acquireMutation = useMutation({
    mutationFn: async (): Promise<boolean> => {
      if (!window.electronAPI || !documentId) return false;

      const response = await window.electronAPI.post<LockStatusResponse>(
        `/api/documents/${documentId}/lock`,
        {},
        getAuthHeaders(token),
      );

      if (response.status === 200) {
        lockReleasedRef.current = false;
        return true;
      }

      // 409 = locked by someone else
      if (response.status === 409) {
        queryClient.invalidateQueries({
          queryKey: queryKeys.documentLock(documentId),
        });
        return false;
      }

      throw new Error("Failed to acquire lock");
    },
    onSuccess: (acquired) => {
      if (acquired && documentId) {
        queryClient.invalidateQueries({
          queryKey: queryKeys.documentLock(documentId),
        });
      }
    },
  });

  // ============================================================================
  // Release Mutation
  // ============================================================================

  const releaseMutation = useMutation({
    mutationFn: async (docId: string): Promise<void> => {
      if (!window.electronAPI || lockReleasedRef.current) return;

      lockReleasedRef.current = true;

      try {
        const response = await window.electronAPI.delete<void>(
          `/api/documents/${docId}/lock`,
          getAuthHeaders(tokenRef.current),
        );

        if (response.status !== 200 && response.status !== 204) {
          lockReleasedRef.current = false;
        }
      } catch {
        // Network error — reset flag so release can be retried
        lockReleasedRef.current = false;
      }
    },
    onSuccess: (_data, docId) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.documentLock(docId),
      });
    },
  });

  // ============================================================================
  // Force-Take Mutation
  // ============================================================================

  const forceTakeMutation = useMutation({
    mutationFn: async (): Promise<boolean> => {
      if (!window.electronAPI || !documentId) return false;

      const response = await window.electronAPI.post<LockStatusResponse>(
        `/api/documents/${documentId}/lock/force-take`,
        {},
        getAuthHeaders(token),
      );

      if (response.status === 200) {
        lockReleasedRef.current = false;
        return true;
      }

      return false;
    },
    onSuccess: (taken) => {
      if (taken && documentId) {
        queryClient.invalidateQueries({
          queryKey: queryKeys.documentLock(documentId),
        });
      }
    },
  });

  // ============================================================================
  // Stable callbacks
  // ============================================================================

  const acquireLock = useCallback(async (): Promise<boolean> => {
    try {
      return await acquireMutation.mutateAsync();
    } catch {
      return false;
    }
  }, [acquireMutation]);

  const releaseLock = useCallback(async (): Promise<void> => {
    const docId = documentIdRef.current;
    if (!docId) return;
    try {
      await releaseMutation.mutateAsync(docId);
    } catch {
      // Best effort release
    }
  }, [releaseMutation]);

  const forceTakeLock = useCallback(async (): Promise<boolean> => {
    try {
      return await forceTakeMutation.mutateAsync();
    } catch {
      return false;
    }
  }, [forceTakeMutation]);

  // ============================================================================
  // Heartbeat
  // ============================================================================

  useEffect(() => {
    if (!isLockedByMe || !documentId) {
      if (heartbeatTimerRef.current) {
        clearInterval(heartbeatTimerRef.current);
        heartbeatTimerRef.current = null;
      }
      return;
    }

    const sendHeartbeat = async () => {
      if (!window.electronAPI || !documentIdRef.current) return;

      // Activity gate: if lastActivityRef is provided and user has been idle
      // longer than the inactivity timeout, skip the heartbeat so the server
      // TTL expires and the lock is released automatically.
      if (lastActivityRef?.current != null) {
        const idleMs = Date.now() - lastActivityRef.current;
        if (idleMs > INACTIVITY_TIMEOUT_MS) {
          return; // Skip heartbeat — let server TTL expire as backup
        }
      }

      try {
        const response = await window.electronAPI.post<void>(
          `/api/documents/${documentIdRef.current}/lock/heartbeat`,
          {},
          getAuthHeaders(tokenRef.current),
        );

        // 409 = lock lost (expired or taken)
        if (response.status === 409) {
          queryClient.invalidateQueries({
            queryKey: queryKeys.documentLock(documentIdRef.current),
          });
        }
      } catch {
        // Heartbeat failure - invalidate to check status
        if (documentIdRef.current) {
          queryClient.invalidateQueries({
            queryKey: queryKeys.documentLock(documentIdRef.current),
          });
        }
      }
    };

    heartbeatTimerRef.current = setInterval(
      sendHeartbeat,
      HEARTBEAT_INTERVAL_MS,
    );

    return () => {
      if (heartbeatTimerRef.current) {
        clearInterval(heartbeatTimerRef.current);
        heartbeatTimerRef.current = null;
      }
    };
  }, [isLockedByMe, documentId, queryClient]);

  // ============================================================================
  // WebSocket Subscription
  // ============================================================================

  useEffect(() => {
    if (!documentId || !wsStatus.isConnected) return;

    const handleLocked = (data: {
      document_id: string;
      lock_holder: LockHolder;
    }) => {
      if (data.document_id !== documentId) return;
      queryClient.setQueryData<LockStatusResponse>(
        queryKeys.documentLock(documentId),
        { is_locked: true, lock_holder: data.lock_holder },
      );
    };

    const handleUnlocked = (data: { document_id: string }) => {
      if (data.document_id !== documentId) return;
      queryClient.setQueryData<LockStatusResponse>(
        queryKeys.documentLock(documentId),
        { is_locked: false, lock_holder: null },
      );
    };

    const handleForceTaken = (data: {
      document_id: string;
      lock_holder: LockHolder;
    }) => {
      if (data.document_id !== documentId) return;

      if (data.lock_holder.user_id !== userIdRef.current) {
        // I lost the lock — useEditMode detects this via isLockedByMe transition
        lockReleasedRef.current = true;
      } else {
        // I now hold the lock
        lockReleasedRef.current = false;
      }

      queryClient.setQueryData<LockStatusResponse>(
        queryKeys.documentLock(documentId),
        { is_locked: true, lock_holder: data.lock_holder },
      );
    };

    const unsubLocked = subscribe<{
      document_id: string;
      lock_holder: LockHolder;
    }>(MessageType.DOCUMENT_LOCKED, handleLocked);
    const unsubUnlocked = subscribe<{ document_id: string }>(
      MessageType.DOCUMENT_UNLOCKED,
      handleUnlocked,
    );
    const unsubForceTaken = subscribe<{
      document_id: string;
      lock_holder: LockHolder;
    }>(MessageType.DOCUMENT_FORCE_TAKEN, handleForceTaken);

    return () => {
      unsubLocked();
      unsubUnlocked();
      unsubForceTaken();
    };
  }, [documentId, wsStatus.isConnected, subscribe, queryClient]);

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
        lockReleasedRef.current = true;
        void window.electronAPI.delete<void>(
          `/api/documents/${documentIdRef.current}/lock`,
          getAuthHeaders(tokenRef.current),
        );
      }

      // Clear timers
      if (heartbeatTimerRef.current) {
        clearInterval(heartbeatTimerRef.current);
        heartbeatTimerRef.current = null;
      }
    };
  }, []);

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
    isLoading:
      lockQuery.isLoading ||
      acquireMutation.isPending ||
      releaseMutation.isPending,
  };
}

// ============================================================================
// Read-Only Lock Status Hook (for tree display)
// ============================================================================

/**
 * Return type for useDocumentLockStatus hook
 */
export interface UseDocumentLockStatusReturn {
  /** Whether the document is currently locked */
  isLocked: boolean;
  /** Info about who holds the lock (null if not locked) */
  lockHolder: { userId: string; userName: string } | null;
  /** Whether the lock status is being loaded */
  isLoading: boolean;
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
export function useDocumentLockStatus(
  documentId: string | null,
): UseDocumentLockStatusReturn {
  const token = useAuthStore((s) => s.token);
  const queryClient = useQueryClient();
  const { subscribe, status: wsStatus } = useWebSocket();

  // Query lock status
  const { data, isLoading } = useQuery({
    queryKey: queryKeys.documentLock(documentId ?? ""),
    queryFn: async (): Promise<LockStatusResponse> => {
      if (!window.electronAPI || !documentId) {
        return { is_locked: false, lock_holder: null };
      }

      const response = await window.electronAPI.get<Record<string, unknown>>(
        `/api/documents/${documentId}/lock`,
        getAuthHeaders(token),
      );

      if (response.status !== 200) {
        // Return unlocked state on error
        return { is_locked: false, lock_holder: null };
      }

      return normalizeLockResponse(response.data);
    },
    // Skip temp IDs from optimistic updates - they don't exist on the server yet
    enabled: !!token && !!documentId && !isTempId(documentId),
    staleTime: 10_000, // 10 seconds
    refetchInterval: 30_000, // 30s fallback poll
    gcTime: 60_000,
  });

  // Subscribe to WebSocket for real-time lock updates
  useEffect(() => {
    if (!documentId || !wsStatus.isConnected) return;

    const handleLocked = (eventData: {
      document_id: string;
      lock_holder: LockHolder;
    }) => {
      if (eventData.document_id !== documentId) return;
      queryClient.setQueryData<LockStatusResponse>(
        queryKeys.documentLock(documentId),
        { is_locked: true, lock_holder: eventData.lock_holder },
      );
    };

    const handleUnlocked = (eventData: { document_id: string }) => {
      if (eventData.document_id !== documentId) return;
      queryClient.setQueryData<LockStatusResponse>(
        queryKeys.documentLock(documentId),
        { is_locked: false, lock_holder: null },
      );
    };

    const handleForceTaken = (eventData: {
      document_id: string;
      lock_holder: LockHolder;
    }) => {
      if (eventData.document_id !== documentId) return;
      queryClient.setQueryData<LockStatusResponse>(
        queryKeys.documentLock(documentId),
        { is_locked: true, lock_holder: eventData.lock_holder },
      );
    };

    const unsubLocked = subscribe<{
      document_id: string;
      lock_holder: LockHolder;
    }>(MessageType.DOCUMENT_LOCKED, handleLocked);
    const unsubUnlocked = subscribe<{ document_id: string }>(
      MessageType.DOCUMENT_UNLOCKED,
      handleUnlocked,
    );
    const unsubForceTaken = subscribe<{
      document_id: string;
      lock_holder: LockHolder;
    }>(MessageType.DOCUMENT_FORCE_TAKEN, handleForceTaken);

    return () => {
      unsubLocked();
      unsubUnlocked();
      unsubForceTaken();
    };
  }, [documentId, wsStatus.isConnected, subscribe, queryClient]);

  // Derive return values
  const isLocked = !!data?.is_locked && !!data?.lock_holder;
  const lockHolder = data?.lock_holder
    ? { userId: data.lock_holder.user_id, userName: data.lock_holder.user_name }
    : null;

  return {
    isLocked,
    lockHolder,
    isLoading,
  };
}
