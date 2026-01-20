/**
 * Notifications Store
 *
 * Zustand store for managing notifications with full backend sync.
 *
 * Features:
 * - Fetches persisted notifications from backend on load
 * - Handles real-time WebSocket notifications
 * - Deduplication to prevent duplicate notifications
 * - Syncs read/unread state with backend
 * - Audio alerts for new notifications
 * - Automatic fetch on WebSocket reconnect
 */

import { create } from 'zustand'
import { getAuthHeaders } from './auth-store'

// ============================================================================
// Types
// ============================================================================

export type NotificationType =
  | 'application_invite'
  | 'invitation_accepted'
  | 'invitation_rejected'
  | 'task_assigned'
  | 'task_mentioned'
  | 'note_mentioned'
  | 'project_added'
  | 'member_joined'
  | 'member_left'
  | 'role_changed'
  // Project member notification types
  | 'project_member_added'
  | 'project_member_removed'
  | 'project_role_changed'
  | 'task_reassignment_needed'
  // UI-only types (not persisted)
  | 'invitation_received'
  | 'member_added'
  | 'member_removed'
  | 'role_updated'
  | 'info'
  | 'success'
  | 'warning'
  | 'error'

export type EntityType =
  | 'application'
  | 'project'
  | 'task'
  | 'note'
  | 'invitation'
  | 'user'

/**
 * Backend notification model
 */
export interface BackendNotification {
  id: string
  user_id: string
  type: string
  title: string
  message: string
  entity_type: string | null
  entity_id: string | null
  entity_status: string | null
  is_read: boolean
  created_at: string
  updated_at: string
}

/**
 * Unified notification for display
 */
export interface InAppNotification {
  id: string
  type: NotificationType
  title: string
  message: string
  timestamp: Date
  read: boolean
  entityType?: EntityType
  entityId?: string
  entityStatus?: string
  // Source tracking
  source: 'backend' | 'realtime'
  // Additional data for the notification
  data?: Record<string, unknown>
  // Optional action button
  action?: {
    label: string
    onClick: () => void
  }
}

interface NotificationsState {
  notifications: InAppNotification[]
  unreadCount: number
  isOpen: boolean
  isLoading: boolean
  isLoadingMore: boolean
  isFetched: boolean
  lastFetchTime: number | null
  hasMore: boolean
  currentSkip: number
  error: string | null
}

interface NotificationsActions {
  // Core actions
  addNotification: (notification: Omit<InAppNotification, 'id' | 'timestamp' | 'read' | 'source'> & { source?: 'backend' | 'realtime' }) => void
  markAsRead: (id: string, token?: string | null) => Promise<void>
  markAllAsRead: (token?: string | null) => Promise<void>
  removeNotification: (id: string, token?: string | null) => Promise<void>
  clearAll: (token?: string | null) => Promise<void>

  // UI actions
  setOpen: (open: boolean) => void
  toggleOpen: () => void

  // Backend sync
  fetchNotifications: (token: string | null) => Promise<void>
  loadMoreNotifications: (token: string | null) => Promise<void>
  fetchUnreadCount: (token: string | null) => Promise<number>
  syncWithBackend: (backendNotifications: BackendNotification[], isLoadMore?: boolean) => void

  // Utility
  clearError: () => void
  reset: () => void
}

type NotificationsStore = NotificationsState & NotificationsActions

// ============================================================================
// Constants
// ============================================================================

const MAX_NOTIFICATIONS = 100
const NOTIFICATION_SOUND_URL = '/notification.mp3' // Optional: add sound file

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Generate unique ID for real-time notifications
 */
function generateId(): string {
  return `notif-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

/**
 * Convert backend notification to app format
 */
function convertBackendNotification(backend: BackendNotification): InAppNotification {
  return {
    id: backend.id,
    type: backend.type as NotificationType,
    title: backend.title,
    message: backend.message,
    timestamp: new Date(backend.created_at),
    read: backend.is_read,
    entityType: backend.entity_type as EntityType | undefined,
    entityId: backend.entity_id || undefined,
    entityStatus: backend.entity_status || undefined,
    source: 'backend',
  }
}

/**
 * Play notification sound
 */
function playNotificationSound(): void {
  try {
    // Create audio element dynamically
    const audio = new Audio(NOTIFICATION_SOUND_URL)
    audio.volume = 0.5
    audio.play().catch(() => {
      // Ignore errors (user hasn't interacted with page yet, file not found, etc.)
    })
  } catch {
    // Ignore audio errors
  }
}

/**
 * Show browser notification if permitted
 */
function showBrowserNotification(title: string, message: string): void {
  if (typeof Notification === 'undefined') return
  if (Notification.permission !== 'granted') return

  try {
    new Notification(title, {
      body: message,
      icon: '/icon.png',
      tag: 'pm-notification',
    })
  } catch {
    // Ignore notification errors
  }
}

// ============================================================================
// Store
// ============================================================================

const NOTIFICATIONS_LIMIT = 20

export const useNotificationsStore = create<NotificationsStore>((set, get) => ({
  // State
  notifications: [],
  unreadCount: 0,
  isOpen: false,
  isLoading: false,
  isLoadingMore: false,
  isFetched: false,
  lastFetchTime: null,
  hasMore: true,
  currentSkip: 0,
  error: null,

  // ============================================================================
  // Core Actions
  // ============================================================================

  addNotification: (notification) => {
    const { notifications } = get()

    // Generate ID for real-time notifications
    const id = notification.source === 'backend'
      ? generateId()
      : generateId()

    // Check for duplicates by comparing content (for real-time) or ID (for backend)
    const isDuplicate = notifications.some((n) => {
      // Same backend ID
      if (notification.source === 'backend' && n.id === id) return true
      // Same content within last 5 seconds (real-time dedup)
      if (notification.source !== 'backend') {
        const timeDiff = Date.now() - n.timestamp.getTime()
        if (timeDiff < 5000 && n.title === notification.title && n.message === notification.message) {
          return true
        }
      }
      return false
    })

    if (isDuplicate) return

    const newNotification: InAppNotification = {
      ...notification,
      id,
      timestamp: new Date(),
      read: false,
      source: notification.source || 'realtime',
    }

    // Play sound and show browser notification for real-time notifications
    if (notification.source !== 'backend') {
      playNotificationSound()
      showBrowserNotification(notification.title, notification.message)
    }

    set((state) => {
      const updated = [newNotification, ...state.notifications].slice(0, MAX_NOTIFICATIONS)
      return {
        notifications: updated,
        unreadCount: updated.filter((n) => !n.read).length,
      }
    })
  },

  markAsRead: async (id, token) => {
    const notification = get().notifications.find((n) => n.id === id)
    if (!notification || notification.read) return

    // Optimistic update
    set((state) => ({
      notifications: state.notifications.map((n) =>
        n.id === id ? { ...n, read: true } : n
      ),
      unreadCount: Math.max(0, state.unreadCount - 1),
    }))

    // Sync with backend if it's a backend notification
    if (notification.source === 'backend' && token && window.electronAPI) {
      try {
        await window.electronAPI.put(
          `/api/notifications/${id}`,
          { is_read: true },
          getAuthHeaders(token)
        )
      } catch {
        // Revert on error
        set((state) => ({
          notifications: state.notifications.map((n) =>
            n.id === id ? { ...n, read: false } : n
          ),
          unreadCount: state.unreadCount + 1,
        }))
      }
    }
  },

  markAllAsRead: async (token) => {
    const { notifications } = get()
    const unreadIds = notifications.filter((n) => !n.read && n.source === 'backend').map((n) => n.id)

    // Optimistic update
    set((state) => ({
      notifications: state.notifications.map((n) => ({ ...n, read: true })),
      unreadCount: 0,
    }))

    // Sync with backend
    if (token && window.electronAPI && unreadIds.length > 0) {
      try {
        await window.electronAPI.post(
          '/api/notifications/mark-all-read',
          {},
          getAuthHeaders(token)
        )
      } catch {
        // Don't revert - user already saw notification, just log error
        console.error('Failed to sync mark-all-read with backend')
      }
    }
  },

  removeNotification: async (id, token) => {
    const notification = get().notifications.find((n) => n.id === id)
    if (!notification) return

    const wasUnread = !notification.read

    // Optimistic update
    set((state) => ({
      notifications: state.notifications.filter((n) => n.id !== id),
      unreadCount: wasUnread ? Math.max(0, state.unreadCount - 1) : state.unreadCount,
    }))

    // Delete from backend if it's a backend notification
    if (notification.source === 'backend' && token && window.electronAPI) {
      try {
        await window.electronAPI.delete(
          `/api/notifications/${id}`,
          getAuthHeaders(token)
        )
      } catch {
        // Don't restore - notification is dismissed in UI
        console.error('Failed to delete notification from backend')
      }
    }
  },

  clearAll: async (token) => {
    const hasBackendNotifications = get().notifications.some((n) => n.source === 'backend')

    // Optimistic update
    set({ notifications: [], unreadCount: 0 })

    // Clear from backend
    if (hasBackendNotifications && token && window.electronAPI) {
      try {
        await window.electronAPI.delete(
          '/api/notifications',
          getAuthHeaders(token)
        )
      } catch {
        console.error('Failed to clear notifications from backend')
      }
    }
  },

  // ============================================================================
  // UI Actions
  // ============================================================================

  setOpen: (open) => {
    set({ isOpen: open })
  },

  toggleOpen: () => {
    set((state) => ({ isOpen: !state.isOpen }))
  },

  // ============================================================================
  // Backend Sync
  // ============================================================================

  fetchNotifications: async (token) => {
    if (!token || !window.electronAPI) return

    set({ isLoading: true, error: null })

    try {
      const response = await window.electronAPI.get<BackendNotification[]>(
        `/api/notifications?limit=${NOTIFICATIONS_LIMIT}&skip=0`,
        getAuthHeaders(token)
      )

      if (response.status === 200 && response.data) {
        get().syncWithBackend(response.data, false)
        set({
          isFetched: true,
          lastFetchTime: Date.now(),
          currentSkip: response.data.length,
          hasMore: response.data.length === NOTIFICATIONS_LIMIT,
        })
      } else {
        set({ error: 'Failed to fetch notifications' })
      }
    } catch (err) {
      set({ error: err instanceof Error ? err.message : 'Failed to fetch notifications' })
    } finally {
      set({ isLoading: false })
    }
  },

  loadMoreNotifications: async (token) => {
    const { isLoadingMore, hasMore, currentSkip } = get()
    if (!token || !window.electronAPI || isLoadingMore || !hasMore) return

    set({ isLoadingMore: true, error: null })

    try {
      const response = await window.electronAPI.get<BackendNotification[]>(
        `/api/notifications?limit=${NOTIFICATIONS_LIMIT}&skip=${currentSkip}`,
        getAuthHeaders(token)
      )

      if (response.status === 200 && response.data) {
        get().syncWithBackend(response.data, true)
        set({
          currentSkip: currentSkip + response.data.length,
          hasMore: response.data.length === NOTIFICATIONS_LIMIT,
        })
      } else {
        set({ error: 'Failed to load more notifications' })
      }
    } catch (err) {
      set({ error: err instanceof Error ? err.message : 'Failed to load more notifications' })
    } finally {
      set({ isLoadingMore: false })
    }
  },

  fetchUnreadCount: async (token) => {
    if (!token || !window.electronAPI) return 0

    try {
      const response = await window.electronAPI.get<{ total: number; unread: number }>(
        '/api/notifications/count',
        getAuthHeaders(token)
      )

      if (response.status === 200 && response.data) {
        return response.data.unread
      }
    } catch {
      // Ignore errors
    }

    return 0
  },

  syncWithBackend: (backendNotifications, isLoadMore = false) => {
    const { notifications: existingNotifications } = get()

    // Convert backend notifications
    const converted = backendNotifications.map(convertBackendNotification)

    if (isLoadMore) {
      // For load more, append to existing notifications (avoiding duplicates)
      const existingIds = new Set(existingNotifications.map(n => n.id))
      const newNotifications = converted.filter(n => !existingIds.has(n.id))

      const merged = [...existingNotifications, ...newNotifications]
        .sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime())

      set({
        notifications: merged,
        unreadCount: merged.filter((n) => !n.read).length,
      })
    } else {
      // For initial fetch/refresh, detect new unread notifications for alerts
      const existingIds = new Set(existingNotifications.map(n => n.id))
      const newUnreadNotifications = converted.filter(
        n => !existingIds.has(n.id) && !n.read
      )

      // Play sound and show browser notification for new unread notifications
      if (newUnreadNotifications.length > 0 && existingNotifications.length > 0) {
        // Only alert if this isn't the initial load (existingNotifications.length > 0)
        playNotificationSound()
        const latest = newUnreadNotifications[0]
        showBrowserNotification(latest.title, latest.message)
      }

      // Keep real-time notifications that aren't in backend yet
      const realtimeNotifications = existingNotifications.filter((n) => n.source === 'realtime')

      // Merge: backend notifications + real-time (deduped by similar content)
      const uniqueRealtime = realtimeNotifications.filter((rt) => {
        return !converted.some(
          (bn) => bn.title === rt.title && bn.message === rt.message
        )
      })

      const merged = [...converted, ...uniqueRealtime]
        .sort((a, b) => b.timestamp.getTime() - a.timestamp.getTime())
        .slice(0, MAX_NOTIFICATIONS)

      set({
        notifications: merged,
        unreadCount: merged.filter((n) => !n.read).length,
      })
    }
  },

  // ============================================================================
  // Utility
  // ============================================================================

  clearError: () => {
    set({ error: null })
  },

  reset: () => {
    set({
      notifications: [],
      unreadCount: 0,
      isOpen: false,
      isLoading: false,
      isLoadingMore: false,
      isFetched: false,
      lastFetchTime: null,
      hasMore: true,
      currentSkip: 0,
      error: null,
    })
  },
}))

// ============================================================================
// Selectors
// ============================================================================

export const selectUnreadCount = (state: NotificationsStore) => state.unreadCount
export const selectNotifications = (state: NotificationsStore) => state.notifications
export const selectIsOpen = (state: NotificationsStore) => state.isOpen
export const selectIsLoading = (state: NotificationsStore) => state.isLoading
export const selectIsLoadingMore = (state: NotificationsStore) => state.isLoadingMore
export const selectIsFetched = (state: NotificationsStore) => state.isFetched
export const selectHasMore = (state: NotificationsStore) => state.hasMore

// ============================================================================
// Request browser notification permission
// ============================================================================

export function requestNotificationPermission(): void {
  if (typeof Notification !== 'undefined' && Notification.permission === 'default') {
    Notification.requestPermission()
  }
}
