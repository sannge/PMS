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
 * Also exports useActiveLocks for batch lock status in tree views
 * (replaces per-document queries with a single batch request).
 *
 * @module use-document-lock
 */

import React, { useCallback, useEffect, useMemo, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuthStore } from "@/contexts/auth-context";
import { useWebSocket } from "./use-websocket";
import { MessageType, WebSocketClient } from "@/lib/websocket";
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
export const INACTIVITY_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes
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
// Batch Active Locks Hook (for tree display)
// ============================================================================

/**
 * API response shape for the active-locks endpoint.
 */
interface ActiveLockApiItem {
  document_id: string;
  lock_holder: {
    user_id: string;
    user_name: string;
    acquired_at: number | null;
  };
}

interface ActiveLocksApiResponse {
  locks: ActiveLockApiItem[];
}

/**
 * Lock info for a single document, as exposed to tree components.
 */
export interface ActiveLockInfo {
  userId: string;
  userName: string;
}

/**
 * Fetch all active locks for a scope in a single request.
 *
 * Replaces per-document useDocumentLockStatus calls in tree views.
 * Returns a Map<documentId, ActiveLockInfo> for O(1) lookups.
 *
 * - staleTime: 0 (locks are transient; always refetch on mount)
 * - refetchOnWindowFocus: false (WS handles this while component is mounted)
 * - Joins scope WS room so lock broadcast events are received
 *
 * Also subscribes to DOCUMENT_LOCKED/UNLOCKED/FORCE_TAKEN WS events to
 * update the cache in-place without refetching.
 *
 * @param scope - 'application' | 'project' | 'personal'
 * @param scopeId - UUID of the scope entity (null to disable)
 * @returns Map of documentId -> lock info for currently locked documents
 */
export function useActiveLocks(
  scope: string,
  scopeId: string | null,
): Map<string, ActiveLockInfo> {
  const token = useAuthStore((s) => s.token);
  const userId = useAuthStore((s) => s.user?.id ?? null);
  const queryClient = useQueryClient();
  const { subscribe, joinRoom, leaveRoom, status: wsStatus } = useWebSocket();

  // For personal scope, use userId as scope_id (same as useDocuments pattern)
  const effectiveScopeId =
    scope === "personal" ? (userId ?? "") : (scopeId ?? "");

  const queryKey = queryKeys.activeLocks(scope, effectiveScopeId);

  const { data } = useQuery({
    queryKey,
    queryFn: async (): Promise<ActiveLocksApiResponse> => {
      if (!window.electronAPI) {
        throw new Error("Electron API not available");
      }

      const apiScopeId = scope === "personal" ? userId : scopeId;
      if (!apiScopeId) {
        return { locks: [] };
      }

      const params = new URLSearchParams();
      params.set("scope", scope);
      params.set("scope_id", apiScopeId);

      const response =
        await window.electronAPI.get<ActiveLocksApiResponse>(
          `/api/documents/active-locks?${params.toString()}`,
          token ? { Authorization: `Bearer ${token}` } : {},
        );

      if (response.status !== 200) {
        return { locks: [] };
      }

      return response.data;
    },
    enabled: !!token && !!scope && (scope === "personal" || !!scopeId),
    staleTime: 0, // Always stale — locks are transient, refetch on every mount
    refetchOnWindowFocus: false, // WS keeps it fresh while mounted
    gcTime: 5 * 60 * 1000,
  });

  // Join the appropriate WS room so lock broadcast events are received.
  // The backend broadcasts lock events to scope rooms (project/application/user).
  useEffect(() => {
    if (!wsStatus.isConnected || !effectiveScopeId) return;

    let roomId: string;
    if (scope === "personal") {
      roomId = WebSocketClient.getUserRoom(effectiveScopeId);
    } else if (scope === "project") {
      roomId = WebSocketClient.getProjectRoom(effectiveScopeId);
    } else {
      roomId = WebSocketClient.getApplicationRoom(effectiveScopeId);
    }

    joinRoom(roomId);
    return () => leaveRoom(roomId);
  }, [scope, effectiveScopeId, wsStatus.isConnected, joinRoom, leaveRoom]);

  // Invalidate on WS reconnect to catch events missed during disconnect.
  // Track the previous connected state with a ref to detect false→true transitions.
  const wasConnectedRef = useRef(wsStatus.isConnected);
  useEffect(() => {
    const wasConnected = wasConnectedRef.current;
    wasConnectedRef.current = wsStatus.isConnected;

    if (wsStatus.isConnected && !wasConnected && effectiveScopeId) {
      queryClient.invalidateQueries({ queryKey });
    }
  }, [wsStatus.isConnected, queryClient, queryKey, effectiveScopeId]);

  // Subscribe to lock events and update cache in-place
  useEffect(() => {
    if (!wsStatus.isConnected || !effectiveScopeId) return;

    const handleLocked = (eventData: {
      document_id: string;
      lock_holder: LockHolder;
    }) => {
      queryClient.setQueryData<ActiveLocksApiResponse>(queryKey, (old) => {
        if (!old) return old;
        // Remove existing entry for this doc (if any), then add
        const filtered = old.locks.filter(
          (l) => l.document_id !== eventData.document_id,
        );
        return {
          locks: [
            ...filtered,
            {
              document_id: eventData.document_id,
              lock_holder: eventData.lock_holder,
            },
          ],
        };
      });
    };

    const handleUnlocked = (eventData: { document_id: string }) => {
      queryClient.setQueryData<ActiveLocksApiResponse>(queryKey, (old) => {
        if (!old) return old;
        return {
          locks: old.locks.filter(
            (l) => l.document_id !== eventData.document_id,
          ),
        };
      });
    };

    const handleForceTaken = (eventData: {
      document_id: string;
      lock_holder: LockHolder;
    }) => {
      queryClient.setQueryData<ActiveLocksApiResponse>(queryKey, (old) => {
        if (!old) return old;
        const filtered = old.locks.filter(
          (l) => l.document_id !== eventData.document_id,
        );
        return {
          locks: [
            ...filtered,
            {
              document_id: eventData.document_id,
              lock_holder: eventData.lock_holder,
            },
          ],
        };
      });
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
  }, [wsStatus.isConnected, subscribe, queryClient, queryKey, effectiveScopeId]);

  // Convert to Map for O(1) lookups in tree rendering
  return useMemo(() => {
    const map = new Map<string, ActiveLockInfo>();
    if (!data?.locks) return map;

    for (const lock of data.locks) {
      map.set(lock.document_id, {
        userId: lock.lock_holder.user_id,
        userName: lock.lock_holder.user_name,
      });
    }
    return map;
  }, [data]);
}
