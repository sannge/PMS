/**
 * TanStack Query Hooks for Notifications
 *
 * Provides React Query hooks for notification management with:
 * - Optimistic mark-as-read updates
 * - Unread count polling
 * - Automatic refetch on window focus
 * - Browser notification alerts
 * - IndexedDB persistence for offline access
 *
 * @see https://tanstack.com/query/latest
 */

import { useCallback, useMemo } from 'react'
import {
  useQuery,
  useInfiniteQuery,
  useMutation,
  useQueryClient,
  UseQueryResult,
  UseInfiniteQueryResult,
  UseMutationResult,
  InfiniteData,
} from '@tanstack/react-query'
import { useAuthToken } from '@/contexts/auth-context'
import { authGet, authPost, authPut, authDelete } from '@/lib/api-client'
import { queryKeys } from '@/lib/query-client'
import { useWebSocketStatus } from '@/hooks/use-websocket'

// ============================================================================
// Constants
// ============================================================================

const NOTIFICATION_SOUND_URL = '/notification.mp3'
const NOTIFICATIONS_PAGE_SIZE = 20

// ============================================================================
// Types
// ============================================================================

export type NotificationType =
  | 'task_assigned'
  | 'task_status_changed'
  | 'comment_mention'
  | 'comment_added'
  | 'member_added'
  | 'member_removed'
  | 'role_changed'
  | 'project_member_added'
  | 'project_member_removed'
  | 'project_role_changed'
  | 'invitation_received'
  | 'invitation_accepted'
  | 'invitation_rejected'
  | 'application_invite'  // Backend notification type for app invitations

// Raw notification from API (matches backend schema)
interface NotificationApiResponse {
  id: string
  user_id: string
  type: NotificationType
  title: string
  message: string | null
  is_read: boolean
  entity_type: string | null
  entity_id: string | null
  entity_status: string | null
  created_at: string
}

// Notification with aliases for frontend compatibility
export interface Notification {
  id: string
  user_id: string
  type: NotificationType
  title: string
  message: string | null
  is_read: boolean
  entity_type: string | null
  entity_id: string | null
  entity_status: string | null
  created_at: string
  // Aliases for frontend components using old field names
  notification_type: NotificationType
  body: string | null
  data: Record<string, unknown> | null
}

// Single page of notifications
export interface NotificationPage {
  items: Notification[]
  nextCursor: number | null  // skip value for next page, null if no more
  hasMore: boolean
}

// Flattened view for components (data only, no functions)
export interface NotificationListResponse {
  items: Notification[]
  total: number
  unread_count: number
}

export interface ApiError {
  message: string
  code?: string
  field?: string
}

// ============================================================================
// Helper Functions
// ============================================================================

function parseApiError(status: number, data: unknown): ApiError {
  if (typeof data === 'object' && data !== null) {
    const errorData = data as Record<string, unknown>
    if (typeof errorData.detail === 'string') {
      return { message: errorData.detail }
    }
  }

  switch (status) {
    case 401:
      return { message: 'Authentication required.' }
    case 404:
      return { message: 'Notification not found.' }
    case 500:
      return { message: 'Server error. Please try again later.' }
    default:
      return { message: 'An unexpected error occurred.' }
  }
}

// ============================================================================
// Helper: Transform API response to Notification
// ============================================================================

function transformNotification(n: NotificationApiResponse): Notification {
  return {
    ...n,
    notification_type: n.type,  // Alias for components using old field name
    body: n.message,            // Alias for components using old field name
    data: n.entity_id ? { invitation_id: n.entity_id, status: n.entity_status } : null,
  }
}

// ============================================================================
// Notification Queries
// ============================================================================

/**
 * Fetch notifications with infinite scroll pagination.
 * Loads 20 notifications per page, persisted to IndexedDB automatically.
 */
export function useNotificationsInfinite(options?: { enabled?: boolean }): UseInfiniteQueryResult<InfiniteData<NotificationPage>, Error> {
  const token = useAuthToken()
  const optionEnabled = options?.enabled ?? true

  return useInfiniteQuery({
    queryKey: queryKeys.notifications,
    queryFn: async ({ pageParam = 0 }) => {
      const response = await authGet<NotificationApiResponse[]>(
        `/api/notifications?skip=${pageParam}&limit=${NOTIFICATIONS_PAGE_SIZE}`
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      const rawItems = Array.isArray(response.data) ? response.data : []
      const items = rawItems.map(transformNotification)
      const hasMore = items.length === NOTIFICATIONS_PAGE_SIZE

      return {
        items,
        nextCursor: hasMore ? pageParam + NOTIFICATIONS_PAGE_SIZE : null,
        hasMore,
      }
    },
    initialPageParam: 0,
    getNextPageParam: (lastPage) => lastPage.nextCursor,
    enabled: !!token && optionEnabled,
    staleTime: 60 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
    refetchOnWindowFocus: false, // WS real-time invalidation handles freshness
  })
}

/**
 * Convenience hook that flattens infinite query pages into a single list.
 * Memoized to prevent unnecessary recomputation on every render.
 */
export function useNotifications(options?: { enabled?: boolean }): {
  data: NotificationListResponse | undefined
  isLoading: boolean
  isError: boolean
  error: Error | null
  refetch: () => void
  fetchNextPage: () => void
  hasNextPage: boolean
  isFetchingNextPage: boolean
} {
  const infiniteQuery = useNotificationsInfinite(options)

  // Memoize the expensive data computation in a single pass.
  // Deduplicates by ID to handle page boundary overlap after WS prepends + refetch.
  const data = useMemo((): NotificationListResponse | undefined => {
    if (!infiniteQuery.data) return undefined

    const items: Notification[] = []
    const seen = new Set<string>()
    let unreadCount = 0

    for (const page of infiniteQuery.data.pages) {
      for (const item of page.items) {
        if (seen.has(item.id)) continue
        seen.add(item.id)
        items.push(item)
        if (!item.is_read) unreadCount++
      }
    }

    return {
      items,
      total: items.length,
      unread_count: unreadCount,
    }
  }, [infiniteQuery.data])

  return {
    data,
    isLoading: infiniteQuery.isLoading,
    isError: infiniteQuery.isError,
    error: infiniteQuery.error,
    refetch: infiniteQuery.refetch,
    fetchNextPage: infiniteQuery.fetchNextPage,
    hasNextPage: infiniteQuery.hasNextPage ?? false,
    isFetchingNextPage: infiniteQuery.isFetchingNextPage,
  }
}

/**
 * Fetch just the unread count (lightweight query).
 * Polls more frequently than full notification list.
 */
export function useUnreadCount(): UseQueryResult<number, Error> {
  const token = useAuthToken()
  const wsStatus = useWebSocketStatus()

  return useQuery({
    queryKey: queryKeys.unreadCount,
    queryFn: async () => {
      const response = await authGet<{ total: number; unread: number }>(
        '/api/notifications/count'
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data?.unread || 0
    },
    enabled: !!token,
    staleTime: 30 * 1000, // 30 seconds
    gcTime: 24 * 60 * 60 * 1000,
    // Only poll when WebSocket is disconnected; WS pushes invalidation events
    refetchInterval: wsStatus.isConnected ? false : 30 * 1000,
    refetchOnWindowFocus: false, // WS real-time invalidation handles freshness
  })
}

// ============================================================================
// Notification Mutations (with infinite query optimistic updates)
// ============================================================================

type InfiniteNotificationData = InfiniteData<NotificationPage>

/**
 * Mark a notification as read with optimistic update across pages.
 */
export function useMarkAsRead(): UseMutationResult<
  void,
  Error,
  string,
  { previousData?: InfiniteNotificationData; previousCount?: number }
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (notificationId: string) => {
      const response = await authPut<void>(
        `/api/notifications/${notificationId}`,
        { is_read: true }
      )

      if (response.status !== 200 && response.status !== 204) {
        throw new Error(parseApiError(response.status, response.data).message)
      }
    },
    onMutate: async (notificationId) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.notifications })
      await queryClient.cancelQueries({ queryKey: queryKeys.unreadCount })

      const previousData = queryClient.getQueryData<InfiniteNotificationData>(queryKeys.notifications)
      const previousCount = queryClient.getQueryData<number>(queryKeys.unreadCount)

      // Check if notification was unread before updating (early return on find)
      let wasUnread = false
      if (previousData) {
        outer: for (const page of previousData.pages) {
          for (const item of page.items) {
            if (item.id === notificationId) {
              wasUnread = !item.is_read
              break outer
            }
          }
        }
      }

      // Optimistically update across all pages
      queryClient.setQueryData<InfiniteNotificationData>(queryKeys.notifications, (old) => {
        if (!old) return old
        return {
          ...old,
          pages: old.pages.map((page) => ({
            ...page,
            items: page.items.map((n) =>
              n.id === notificationId ? { ...n, is_read: true } : n
            ),
          })),
        }
      })

      // Optimistically update count if it was unread
      if (wasUnread) {
        queryClient.setQueryData<number>(queryKeys.unreadCount, (old) =>
          Math.max(0, (old || 0) - 1)
        )
      }

      return { previousData, previousCount }
    },
    onError: (_err, _vars, context) => {
      if (context?.previousData) {
        queryClient.setQueryData(queryKeys.notifications, context.previousData)
      }
      if (context?.previousCount !== undefined) {
        queryClient.setQueryData(queryKeys.unreadCount, context.previousCount)
      }
    },
    onSettled: () => {
      // Only invalidate unread count, not full list (optimistic update is sufficient)
      queryClient.invalidateQueries({ queryKey: queryKeys.unreadCount })
    },
  })
}

/**
 * Mark all notifications as read across all pages.
 */
export function useMarkAllAsRead(): UseMutationResult<
  void,
  Error,
  void,
  { previousData?: InfiniteNotificationData; previousCount?: number }
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async () => {
      const response = await authPost<void>(
        '/api/notifications/mark-all-read',
        {}
      )

      if (response.status !== 200 && response.status !== 204) {
        throw new Error(parseApiError(response.status, response.data).message)
      }
    },
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: queryKeys.notifications })
      await queryClient.cancelQueries({ queryKey: queryKeys.unreadCount })

      const previousData = queryClient.getQueryData<InfiniteNotificationData>(queryKeys.notifications)
      const previousCount = queryClient.getQueryData<number>(queryKeys.unreadCount)

      // Mark all as read across all pages
      queryClient.setQueryData<InfiniteNotificationData>(queryKeys.notifications, (old) => {
        if (!old) return old
        return {
          ...old,
          pages: old.pages.map((page) => ({
            ...page,
            items: page.items.map((n) => ({ ...n, is_read: true })),
          })),
        }
      })

      queryClient.setQueryData<number>(queryKeys.unreadCount, 0)

      return { previousData, previousCount }
    },
    onError: (_err, _vars, context) => {
      if (context?.previousData) {
        queryClient.setQueryData(queryKeys.notifications, context.previousData)
      }
      if (context?.previousCount !== undefined) {
        queryClient.setQueryData(queryKeys.unreadCount, context.previousCount)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.unreadCount })
    },
  })
}

/**
 * Delete a notification from any page.
 */
export function useDeleteNotification(): UseMutationResult<
  void,
  Error,
  string,
  { previousData?: InfiniteNotificationData; previousCount?: number }
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (notificationId: string) => {
      const response = await authDelete<void>(
        `/api/notifications/${notificationId}`
      )

      if (response.status !== 204 && response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }
    },
    onMutate: async (notificationId) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.notifications })
      await queryClient.cancelQueries({ queryKey: queryKeys.unreadCount })

      const previousData = queryClient.getQueryData<InfiniteNotificationData>(queryKeys.notifications)
      const previousCount = queryClient.getQueryData<number>(queryKeys.unreadCount)

      // Find if notification was unread before removing (early return on find)
      let wasUnread = false
      if (previousData) {
        outer: for (const page of previousData.pages) {
          for (const item of page.items) {
            if (item.id === notificationId) {
              wasUnread = !item.is_read
              break outer
            }
          }
        }
      }

      // Remove from pages
      queryClient.setQueryData<InfiniteNotificationData>(queryKeys.notifications, (old) => {
        if (!old) return old
        return {
          ...old,
          pages: old.pages.map((page) => ({
            ...page,
            items: page.items.filter((n) => n.id !== notificationId),
          })),
        }
      })

      // Update count if was unread
      if (wasUnread) {
        queryClient.setQueryData<number>(queryKeys.unreadCount, (old) =>
          Math.max(0, (old || 0) - 1)
        )
      }

      return { previousData, previousCount }
    },
    onError: (_err, _vars, context) => {
      if (context?.previousData) {
        queryClient.setQueryData(queryKeys.notifications, context.previousData)
      }
      if (context?.previousCount !== undefined) {
        queryClient.setQueryData(queryKeys.unreadCount, context.previousCount)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.unreadCount })
    },
  })
}

/**
 * Clear all notifications (resets infinite query).
 */
export function useClearAllNotifications(): UseMutationResult<
  void,
  Error,
  void,
  { previousData?: InfiniteNotificationData; previousCount?: number }
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async () => {
      const response = await authDelete<void>(
        '/api/notifications'
      )

      if (response.status !== 204 && response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }
    },
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: queryKeys.notifications })
      await queryClient.cancelQueries({ queryKey: queryKeys.unreadCount })

      const previousData = queryClient.getQueryData<InfiniteNotificationData>(queryKeys.notifications)
      const previousCount = queryClient.getQueryData<number>(queryKeys.unreadCount)

      // Clear all pages
      queryClient.setQueryData<InfiniteNotificationData>(queryKeys.notifications, {
        pages: [{ items: [], nextCursor: null, hasMore: false }],
        pageParams: [0],
      })
      queryClient.setQueryData<number>(queryKeys.unreadCount, 0)

      return { previousData, previousCount }
    },
    onError: (_err, _vars, context) => {
      if (context?.previousData) {
        queryClient.setQueryData(queryKeys.notifications, context.previousData)
      }
      if (context?.previousCount !== undefined) {
        queryClient.setQueryData(queryKeys.unreadCount, context.previousCount)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.notifications })
      queryClient.invalidateQueries({ queryKey: queryKeys.unreadCount })
    },
  })
}

// ============================================================================
// Desktop Notification Helpers
// ============================================================================

/**
 * Play notification sound
 */
function playNotificationSound(): void {
  try {
    const audio = new Audio(NOTIFICATION_SOUND_URL)
    audio.volume = 0.5
    audio.play().catch(() => {
      // Ignore errors (user hasn't interacted with page yet)
    })
  } catch {
    // Ignore audio errors
  }
}

/**
 * Show desktop notification using Electron's native notification system
 */
function showDesktopNotification(title: string, message: string): void {
  if (!title || !message) return

  // Use Electron's notification API via preload
  if (window.electronAPI?.showNotification) {
    window.electronAPI.showNotification({
      title,
      body: message,
      type: 'info',
    }).catch(() => {
      // Ignore notification errors
    })
  }
}

/**
 * Request notification permission (no-op in Electron)
 */
export function requestNotificationPermission(): void {
  // Electron notifications don't require permission prompts
}

/**
 * Hook to add a real-time notification (from WebSocket).
 * Handles both raw API format and transformed format.
 * Prepends to first page and shows browser notification.
 */
export function useAddNotification(): (rawNotification: NotificationApiResponse | Notification) => void {
  const queryClient = useQueryClient()

  return useCallback(
    (rawNotification: NotificationApiResponse | Notification) => {
      // Transform if needed (WebSocket might send raw API format)
      const notification: Notification = 'notification_type' in rawNotification
        ? rawNotification as Notification
        : transformNotification(rawNotification as NotificationApiResponse)

      // Play sound and show browser notification
      playNotificationSound()
      showDesktopNotification(notification.title, notification.body || notification.message || '')

      // Prepend to first page of infinite query
      queryClient.setQueryData<InfiniteNotificationData>(queryKeys.notifications, (old) => {
        if (!old || old.pages.length === 0) {
          return {
            pages: [{ items: [notification], nextCursor: null, hasMore: false }],
            pageParams: [0],
          }
        }

        // Check for duplicates across all pages (early return on find)
        for (const page of old.pages) {
          for (const item of page.items) {
            if (item.id === notification.id) {
              return old // Duplicate found, no change
            }
          }
        }

        // Prepend to first page
        return {
          ...old,
          pages: [
            { ...old.pages[0], items: [notification, ...old.pages[0].items] },
            ...old.pages.slice(1),
          ],
        }
      })

      // Increment unread count
      if (!notification.is_read) {
        queryClient.setQueryData<number>(queryKeys.unreadCount, (old) => (old || 0) + 1)
      }
    },
    [queryClient]
  )
}
