/**
 * TanStack Query Hooks for Notifications
 *
 * Provides React Query hooks for notification management with:
 * - Optimistic mark-as-read updates
 * - Unread count polling
 * - Automatic refetch on window focus
 *
 * @see https://tanstack.com/query/latest
 */

import {
  useQuery,
  useMutation,
  useQueryClient,
  UseQueryResult,
  UseMutationResult,
} from '@tanstack/react-query'
import { useAuthStore } from '@/stores/auth-store'
import { queryKeys } from '@/lib/query-client'

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

export interface Notification {
  id: string
  user_id: string
  notification_type: NotificationType
  title: string
  body: string | null
  is_read: boolean
  data: Record<string, unknown> | null
  created_at: string
  read_at: string | null
}

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

function getAuthHeaders(token: string | null): Record<string, string> {
  if (!token) return {}
  return { Authorization: `Bearer ${token}` }
}

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
// Notification Queries
// ============================================================================

/**
 * Fetch notifications for the current user.
 * Uses 1 min stale time and 30 sec refetch interval for near real-time updates.
 */
export function useNotifications(): UseQueryResult<NotificationListResponse, Error> {
  const token = useAuthStore((s) => s.token)

  return useQuery({
    queryKey: queryKeys.notifications,
    queryFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.get<NotificationListResponse>(
        '/api/notifications',
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return (
        response.data || {
          items: [],
          total: 0,
          unread_count: 0,
        }
      )
    },
    enabled: !!token,
    staleTime: 60 * 1000, // 1 minute
    gcTime: 24 * 60 * 60 * 1000,
    refetchInterval: 60 * 1000, // Poll every minute as backup to WebSocket
  })
}

/**
 * Fetch just the unread count (lightweight query).
 * Polls more frequently than full notification list.
 */
export function useUnreadCount(): UseQueryResult<number, Error> {
  const token = useAuthStore((s) => s.token)

  return useQuery({
    queryKey: queryKeys.unreadCount,
    queryFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.get<{ unread_count: number }>(
        '/api/notifications/unread-count',
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data?.unread_count || 0
    },
    enabled: !!token,
    staleTime: 30 * 1000, // 30 seconds
    gcTime: 24 * 60 * 60 * 1000,
    refetchInterval: 30 * 1000, // Poll every 30 seconds
  })
}

// ============================================================================
// Notification Mutations
// ============================================================================

/**
 * Mark a notification as read with optimistic update.
 */
export function useMarkAsRead(): UseMutationResult<
  void,
  Error,
  string,
  { previousNotifications?: NotificationListResponse; previousCount?: number }
> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (notificationId: string) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.post<void>(
        `/api/notifications/${notificationId}/read`,
        {},
        getAuthHeaders(token)
      )

      if (response.status !== 200 && response.status !== 204) {
        throw new Error(parseApiError(response.status, response.data).message)
      }
    },
    // Optimistic update
    onMutate: async (notificationId) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.notifications })
      await queryClient.cancelQueries({ queryKey: queryKeys.unreadCount })

      const previousNotifications = queryClient.getQueryData<NotificationListResponse>(
        queryKeys.notifications
      )
      const previousCount = queryClient.getQueryData<number>(queryKeys.unreadCount)

      // Optimistically update notification
      queryClient.setQueryData<NotificationListResponse>(queryKeys.notifications, (old) => {
        if (!old) return old
        const wasUnread = old.items.find((n) => n.id === notificationId && !n.is_read)
        return {
          ...old,
          items: old.items.map((n) =>
            n.id === notificationId
              ? { ...n, is_read: true, read_at: new Date().toISOString() }
              : n
          ),
          unread_count: wasUnread ? Math.max(0, old.unread_count - 1) : old.unread_count,
        }
      })

      // Optimistically update count
      queryClient.setQueryData<number>(queryKeys.unreadCount, (old) =>
        Math.max(0, (old || 0) - 1)
      )

      return { previousNotifications, previousCount }
    },
    onError: (_err, _vars, context) => {
      if (context?.previousNotifications) {
        queryClient.setQueryData(queryKeys.notifications, context.previousNotifications)
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

/**
 * Mark all notifications as read.
 */
export function useMarkAllAsRead(): UseMutationResult<
  void,
  Error,
  void,
  { previousNotifications?: NotificationListResponse; previousCount?: number }
> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.post<void>(
        '/api/notifications/read-all',
        {},
        getAuthHeaders(token)
      )

      if (response.status !== 200 && response.status !== 204) {
        throw new Error(parseApiError(response.status, response.data).message)
      }
    },
    // Optimistic update
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: queryKeys.notifications })
      await queryClient.cancelQueries({ queryKey: queryKeys.unreadCount })

      const previousNotifications = queryClient.getQueryData<NotificationListResponse>(
        queryKeys.notifications
      )
      const previousCount = queryClient.getQueryData<number>(queryKeys.unreadCount)

      // Mark all as read
      queryClient.setQueryData<NotificationListResponse>(queryKeys.notifications, (old) => {
        if (!old) return old
        const now = new Date().toISOString()
        return {
          ...old,
          items: old.items.map((n) => ({ ...n, is_read: true, read_at: n.read_at || now })),
          unread_count: 0,
        }
      })

      queryClient.setQueryData<number>(queryKeys.unreadCount, 0)

      return { previousNotifications, previousCount }
    },
    onError: (_err, _vars, context) => {
      if (context?.previousNotifications) {
        queryClient.setQueryData(queryKeys.notifications, context.previousNotifications)
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

/**
 * Delete a notification.
 */
export function useDeleteNotification(): UseMutationResult<
  void,
  Error,
  string,
  { previousNotifications?: NotificationListResponse }
> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (notificationId: string) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.delete<void>(
        `/api/notifications/${notificationId}`,
        getAuthHeaders(token)
      )

      if (response.status !== 204 && response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }
    },
    // Optimistic delete
    onMutate: async (notificationId) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.notifications })

      const previousNotifications = queryClient.getQueryData<NotificationListResponse>(
        queryKeys.notifications
      )

      queryClient.setQueryData<NotificationListResponse>(queryKeys.notifications, (old) => {
        if (!old) return old
        const removed = old.items.find((n) => n.id === notificationId)
        const wasUnread = removed && !removed.is_read
        return {
          ...old,
          items: old.items.filter((n) => n.id !== notificationId),
          total: old.total - 1,
          unread_count: wasUnread ? Math.max(0, old.unread_count - 1) : old.unread_count,
        }
      })

      return { previousNotifications }
    },
    onError: (_err, _vars, context) => {
      if (context?.previousNotifications) {
        queryClient.setQueryData(queryKeys.notifications, context.previousNotifications)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.notifications })
      queryClient.invalidateQueries({ queryKey: queryKeys.unreadCount })
    },
  })
}
