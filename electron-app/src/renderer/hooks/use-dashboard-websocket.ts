/**
 * Dashboard WebSocket Invalidation Hook
 *
 * Subscribes to WS events that affect dashboard stats.
 * Only active while the dashboard component is mounted.
 * Debounces rapid-fire events (2s window) to coalesce into a single refetch.
 */

import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { wsClient, MessageType } from '@/lib/websocket'
import { queryKeys } from '@/lib/query-client'

export function useDashboardWebSocket(): void {
  const queryClient = useQueryClient()

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | null = null

    const invalidate = () => {
      if (timer) clearTimeout(timer)
      timer = setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: queryKeys.dashboard })
        timer = null
      }, 2000)
    }

    const unsubs = [
      wsClient.on(MessageType.TASK_CREATED, invalidate),
      wsClient.on(MessageType.TASK_UPDATED, invalidate),
      wsClient.on(MessageType.TASK_DELETED, invalidate),
      wsClient.on(MessageType.TASK_STATUS_CHANGED, invalidate),
      wsClient.on(MessageType.TASK_MOVED, invalidate),
      wsClient.on(MessageType.PROJECT_CREATED, invalidate),
      wsClient.on(MessageType.PROJECT_UPDATED, invalidate),
      wsClient.on(MessageType.PROJECT_DELETED, invalidate),
      wsClient.on(MessageType.PROJECT_STATUS_CHANGED, invalidate),
      wsClient.on(MessageType.MEMBER_ADDED, invalidate),
      wsClient.on(MessageType.MEMBER_REMOVED, invalidate),
    ]

    return () => {
      if (timer) clearTimeout(timer)
      unsubs.forEach(fn => fn())
    }
  }, [queryClient])
}
