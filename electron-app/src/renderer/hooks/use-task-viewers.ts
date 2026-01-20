/**
 * useTaskViewers Hook
 *
 * Tracks which users are currently viewing specific tasks within a project.
 * This enables showing viewer indicators on task cards.
 *
 * Features:
 * - Track viewers per task ID
 * - Subscribe to viewing events from WebSocket
 * - Send viewing indicator when opening a task
 * - Auto-cleanup when users leave
 */

import { useEffect, useCallback, useState, useRef } from 'react'
import { useWebSocket, MessageType } from './use-websocket'
import { useAuthStore } from '@/stores/auth-store'

// ============================================================================
// Types
// ============================================================================

export interface TaskViewer {
  user_id: string
  user_name: string
  avatar_url: string | null
  started_at: number
}

export interface TaskViewersState {
  /** Map of task_id -> array of viewers */
  viewers: Record<string, TaskViewer[]>
}

export interface UseTaskViewersOptions {
  /** Project ID to track viewers for */
  projectId: string | null
  /** Whether the hook is enabled */
  enabled?: boolean
}

export interface UseTaskViewersReturn {
  /** Get viewers for a specific task */
  getViewers: (taskId: string) => TaskViewer[]
  /** Get viewer count for a specific task */
  getViewerCount: (taskId: string) => number
  /** Send viewing indicator for a task */
  setViewing: (taskId: string | null) => void
  /** Current task being viewed by this user */
  currentTaskId: string | null
}

// ============================================================================
// Constants
// ============================================================================

const VIEWER_EXPIRY_MS = 60000 // 1 minute without update = expired
const CLEANUP_INTERVAL_MS = 30000 // Cleanup stale viewers every 30s

// ============================================================================
// Hook
// ============================================================================

export function useTaskViewers({
  projectId,
  enabled = true,
}: UseTaskViewersOptions): UseTaskViewersReturn {
  const { send, subscribe, status } = useWebSocket()
  const user = useAuthStore((state) => state.user)

  const [viewers, setViewers] = useState<Record<string, TaskViewer[]>>({})
  const [currentTaskId, setCurrentTaskId] = useState<string | null>(null)
  const viewingIntervalRef = useRef<NodeJS.Timeout | null>(null)

  // Get viewers for a task
  const getViewers = useCallback(
    (taskId: string): TaskViewer[] => {
      return viewers[taskId] || []
    },
    [viewers]
  )

  // Get viewer count
  const getViewerCount = useCallback(
    (taskId: string): number => {
      return (viewers[taskId] || []).length
    },
    [viewers]
  )

  // Send viewing indicator
  const setViewing = useCallback(
    (taskId: string | null) => {
      if (!projectId || !user || !status.isConnected) return

      // Clear previous viewing interval
      if (viewingIntervalRef.current) {
        clearInterval(viewingIntervalRef.current)
        viewingIntervalRef.current = null
      }

      // Clear previous task viewing
      if (currentTaskId && currentTaskId !== taskId) {
        send(MessageType.USER_VIEWING, {
          project_id: projectId,
          task_id: null,
          user_id: user.id,
          user_name: user.name || user.email,
          avatar_url: null,
        })
      }

      setCurrentTaskId(taskId)

      if (taskId) {
        // Send initial viewing indicator
        const sendViewingUpdate = () => {
          send(MessageType.USER_VIEWING, {
            project_id: projectId,
            task_id: taskId,
            user_id: user.id,
            user_name: user.name || user.email,
            avatar_url: null,
          })
        }

        sendViewingUpdate()

        // Send periodic updates to maintain presence
        viewingIntervalRef.current = setInterval(sendViewingUpdate, 30000)
      }
    },
    [projectId, user, status.isConnected, currentTaskId, send]
  )

  // Handle viewing updates from other users
  useEffect(() => {
    if (!enabled || !projectId || !status.isConnected) return

    const handleViewingUpdate = (data: {
      project_id: string
      task_id: string | null
      user_id: string
      user_name: string
      avatar_url: string | null
    }) => {
      // Ignore our own updates
      if (data.user_id === user?.id) return
      // Ignore updates for other projects
      if (data.project_id !== projectId) return

      setViewers((prev) => {
        const updated = { ...prev }

        // Remove user from all tasks first
        for (const taskId of Object.keys(updated)) {
          updated[taskId] = updated[taskId].filter((v) => v.user_id !== data.user_id)
          if (updated[taskId].length === 0) {
            delete updated[taskId]
          }
        }

        // Add user to new task if specified
        if (data.task_id) {
          const viewer: TaskViewer = {
            user_id: data.user_id,
            user_name: data.user_name,
            avatar_url: data.avatar_url,
            started_at: Date.now(),
          }

          if (!updated[data.task_id]) {
            updated[data.task_id] = []
          }
          updated[data.task_id].push(viewer)
        }

        return updated
      })
    }

    const unsubscribe = subscribe(MessageType.USER_VIEWING, handleViewingUpdate)

    return () => {
      unsubscribe()
    }
  }, [enabled, projectId, status.isConnected, user?.id, subscribe])

  // Cleanup stale viewers periodically
  useEffect(() => {
    const cleanup = setInterval(() => {
      const now = Date.now()
      setViewers((prev) => {
        const updated = { ...prev }
        let changed = false

        for (const taskId of Object.keys(updated)) {
          const filtered = updated[taskId].filter(
            (v) => now - v.started_at < VIEWER_EXPIRY_MS
          )
          if (filtered.length !== updated[taskId].length) {
            changed = true
            if (filtered.length === 0) {
              delete updated[taskId]
            } else {
              updated[taskId] = filtered
            }
          }
        }

        return changed ? updated : prev
      })
    }, CLEANUP_INTERVAL_MS)

    return () => {
      clearInterval(cleanup)
    }
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (viewingIntervalRef.current) {
        clearInterval(viewingIntervalRef.current)
      }
      // Clear viewing state when unmounting
      if (currentTaskId && projectId && user && status.isConnected) {
        send(MessageType.USER_VIEWING, {
          project_id: projectId,
          task_id: null,
          user_id: user.id,
          user_name: user.name || user.email,
          avatar_url: null,
        })
      }
    }
  }, [currentTaskId, projectId, user, status.isConnected, send])

  return {
    getViewers,
    getViewerCount,
    setViewing,
    currentTaskId,
  }
}

export default useTaskViewers
