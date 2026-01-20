/**
 * WebSocket Hooks
 *
 * React hooks for using the WebSocket client in components.
 * Provides automatic connection management, state tracking, and cleanup.
 *
 * Features:
 * - Automatic connection on mount with auth token
 * - Automatic cleanup on unmount
 * - Room subscription management
 * - Type-safe event listeners
 * - Connection state tracking
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useAuthStore } from '@/stores/auth-store'
import { useNotificationsStore } from '@/stores/notifications-store'
import { useProjectsStore, type ProjectStatusChangedEventData } from '@/stores/projects-store'
import { useProjectMembersStore } from '@/stores/project-members-store'
import {
  wsClient,
  WebSocketClient,
  WebSocketState,
  MessageType,
  type WebSocketMessage,
  type WebSocketConfig,
  type WebSocketEventListener,
  type Unsubscribe,
  type TaskUpdateEventData,
  type TaskMovedEventData,
  type NoteUpdateEventData,
  type UserPresenceEventData,
  type RoomJoinedEventData,
  type ConnectedEventData,
  type InvitationReceivedEventData,
  type InvitationResponseEventData,
  type MemberAddedEventData,
  type MemberRemovedEventData,
  type RoleUpdatedEventData,
  type NotificationReadEventData,
} from '@/lib/websocket'

/**
 * Project status update event data
 */
export interface ProjectStatusUpdateEventData {
  project_id: string
  application_id: string
  action: 'created' | 'updated' | 'deleted' | 'status_changed'
  project: Record<string, unknown>
  timestamp: string
  changed_by?: string
  old_status?: string
  new_status?: string
}

// ============================================================================
// Utilities
// ============================================================================

/**
 * Creates a debounced version of a function
 */
function debounce<T extends (...args: Parameters<T>) => void>(
  func: T,
  wait: number
): { (...args: Parameters<T>): void; cancel: () => void } {
  let timeoutId: ReturnType<typeof setTimeout> | null = null

  const debounced = (...args: Parameters<T>) => {
    if (timeoutId) {
      clearTimeout(timeoutId)
    }
    timeoutId = setTimeout(() => {
      func(...args)
      timeoutId = null
    }, wait)
  }

  debounced.cancel = () => {
    if (timeoutId) {
      clearTimeout(timeoutId)
      timeoutId = null
    }
  }

  return debounced
}

// ============================================================================
// Types
// ============================================================================

/**
 * WebSocket connection status
 */
export interface WebSocketStatus {
  state: WebSocketState
  isConnected: boolean
  isConnecting: boolean
  isReconnecting: boolean
  rooms: string[]
}

/**
 * Options for useWebSocket hook
 */
export interface UseWebSocketOptions {
  /** Auto-connect on mount (default: true) */
  autoConnect?: boolean
  /** Rooms to auto-join on connect */
  initialRooms?: string[]
  /** Custom WebSocket client instance */
  client?: WebSocketClient
}

/**
 * Return type for useWebSocket hook
 */
export interface UseWebSocketReturn {
  /** Current connection status */
  status: WebSocketStatus
  /** Connect to WebSocket server */
  connect: () => void
  /** Disconnect from WebSocket server */
  disconnect: () => void
  /** Join a room */
  joinRoom: (roomId: string) => void
  /** Leave a room */
  leaveRoom: (roomId: string) => void
  /** Send a message */
  send: <T = unknown>(type: MessageType | string, data: T) => boolean
  /** Send typing indicator */
  sendTyping: (roomId: string, isTyping: boolean) => void
  /** Send viewing indicator */
  sendViewing: (roomId: string, entityType: string, entityId: string) => void
  /** Subscribe to a message type */
  subscribe: <T = unknown>(type: MessageType | string, listener: WebSocketEventListener<T>) => Unsubscribe
  /** WebSocket client instance */
  client: WebSocketClient
}

// ============================================================================
// Main Hook
// ============================================================================

/**
 * Main WebSocket hook for managing connection and subscriptions
 *
 * @example
 * ```tsx
 * function TaskBoard({ projectId }) {
 *   const { status, joinRoom, leaveRoom, subscribe } = useWebSocket({
 *     initialRooms: [WebSocketClient.getProjectRoom(projectId)]
 *   })
 *
 *   useEffect(() => {
 *     const unsubscribe = subscribe(MessageType.TASK_UPDATED, (data) => {
 *       // Handle task update
 *     })
 *     return unsubscribe
 *   }, [subscribe])
 *
 *   return <div>Connected: {status.isConnected.toString()}</div>
 * }
 * ```
 */
export function useWebSocket(options: UseWebSocketOptions = {}): UseWebSocketReturn {
  const { autoConnect = true, initialRooms = [], client = wsClient } = options

  const token = useAuthStore((state) => state.token)
  const initialRoomsRef = useRef(initialRooms)

  const [status, setStatus] = useState<WebSocketStatus>({
    state: client.getState(),
    isConnected: client.isConnected(),
    isConnecting: client.getState() === WebSocketState.CONNECTING,
    isReconnecting: client.getState() === WebSocketState.RECONNECTING,
    rooms: client.getRooms(),
  })

  // Update status when state changes
  useEffect(() => {
    const unsubscribe = client.onStateChange((state) => {
      setStatus({
        state,
        isConnected: state === WebSocketState.CONNECTED,
        isConnecting: state === WebSocketState.CONNECTING,
        isReconnecting: state === WebSocketState.RECONNECTING,
        rooms: client.getRooms(),
      })
    })

    return unsubscribe
  }, [client])

  // Connect when token is available
  useEffect(() => {
    if (!autoConnect || !token) {
      return
    }

    client.setToken(token)
    client.connect()

    return () => {
      // Don't disconnect on unmount - connection is shared
    }
  }, [autoConnect, token, client])

  // Join initial rooms when connected
  useEffect(() => {
    if (!status.isConnected || initialRoomsRef.current.length === 0) {
      return
    }

    initialRoomsRef.current.forEach((roomId) => {
      client.joinRoom(roomId)
    })
  }, [status.isConnected, client])

  // Callbacks
  const connect = useCallback(() => {
    client.connect(token || undefined)
  }, [client, token])

  const disconnect = useCallback(() => {
    client.disconnect()
  }, [client])

  const joinRoom = useCallback(
    (roomId: string) => {
      client.joinRoom(roomId)
    },
    [client]
  )

  const leaveRoom = useCallback(
    (roomId: string) => {
      client.leaveRoom(roomId)
    },
    [client]
  )

  const send = useCallback(
    <T = unknown>(type: MessageType | string, data: T): boolean => {
      return client.send(type, data)
    },
    [client]
  )

  const sendTyping = useCallback(
    (roomId: string, isTyping: boolean) => {
      client.sendTypingIndicator(roomId, isTyping)
    },
    [client]
  )

  const sendViewing = useCallback(
    (roomId: string, entityType: string, entityId: string) => {
      client.sendViewingIndicator(roomId, entityType, entityId)
    },
    [client]
  )

  const subscribe = useCallback(
    <T = unknown>(type: MessageType | string, listener: WebSocketEventListener<T>): Unsubscribe => {
      return client.on(type, listener)
    },
    [client]
  )

  return {
    status,
    connect,
    disconnect,
    joinRoom,
    leaveRoom,
    send,
    sendTyping,
    sendViewing,
    subscribe,
    client,
  }
}

// ============================================================================
// Specialized Hooks
// ============================================================================

/**
 * Hook for subscribing to task updates in a project
 *
 * @example
 * ```tsx
 * function TaskBoard({ projectId }) {
 *   const { tasks } = useTaskStore()
 *
 *   useTaskUpdates(projectId, (update) => {
 *     if (update.action === 'created') {
 *       // Add new task
 *     } else if (update.action === 'updated') {
 *       // Update existing task
 *     } else if (update.action === 'deleted') {
 *       // Remove task
 *     }
 *   })
 * }
 * ```
 */
export function useTaskUpdates(
  projectId: string | null,
  onUpdate: (data: TaskUpdateEventData) => void
): void {
  const { subscribe, joinRoom, leaveRoom, status } = useWebSocket()
  const callbackRef = useRef(onUpdate)

  // Keep callback ref up to date
  useEffect(() => {
    callbackRef.current = onUpdate
  }, [onUpdate])

  // Join project room and subscribe to task events
  useEffect(() => {
    if (!projectId || !status.isConnected) {
      return
    }

    const roomId = WebSocketClient.getProjectRoom(projectId)
    joinRoom(roomId)

    const unsubscribeCreated = subscribe<TaskUpdateEventData>(
      MessageType.TASK_CREATED,
      (data) => callbackRef.current(data)
    )

    const unsubscribeUpdated = subscribe<TaskUpdateEventData>(
      MessageType.TASK_UPDATED,
      (data) => callbackRef.current(data)
    )

    const unsubscribeDeleted = subscribe<TaskUpdateEventData>(
      MessageType.TASK_DELETED,
      (data) => callbackRef.current(data)
    )

    const unsubscribeStatus = subscribe<TaskUpdateEventData>(
      MessageType.TASK_STATUS_CHANGED,
      (data) => callbackRef.current(data)
    )

    return () => {
      unsubscribeCreated()
      unsubscribeUpdated()
      unsubscribeDeleted()
      unsubscribeStatus()
      leaveRoom(roomId)
    }
  }, [projectId, status.isConnected, subscribe, joinRoom, leaveRoom])
}

/**
 * Hook for subscribing to task moved events (Kanban drag-and-drop)
 *
 * Listens for task_moved WebSocket events and calls the callback with
 * the task's new position and status information.
 *
 * @example
 * ```tsx
 * function KanbanBoard({ projectId }) {
 *   useTaskMoved(projectId, (data) => {
 *     // Update task position in local state
 *     updateTaskPosition(data.task_id, data.new_status_id, data.new_rank)
 *   })
 * }
 * ```
 */
export function useTaskMoved(
  projectId: string | null,
  onMoved: (data: TaskMovedEventData) => void
): void {
  const { subscribe, status } = useWebSocket()
  const callbackRef = useRef(onMoved)

  // Keep callback ref up to date
  useEffect(() => {
    callbackRef.current = onMoved
  }, [onMoved])

  // Subscribe to task_moved events (room is already joined by useTaskUpdates)
  useEffect(() => {
    if (!projectId || !status.isConnected) {
      return
    }

    const unsubscribeMoved = subscribe<TaskMovedEventData>(
      MessageType.TASK_MOVED,
      (data) => {
        // Only process events for this project
        if (data.project_id === projectId) {
          callbackRef.current(data)
        }
      }
    )

    return () => {
      unsubscribeMoved()
      // Don't leave room here - useTaskUpdates manages the room lifecycle
    }
  }, [projectId, status.isConnected, subscribe])
}

/**
 * Hook for subscribing to project status updates in an application
 *
 * @example
 * ```tsx
 * function ProjectList({ applicationId }) {
 *   const { projects } = useProjectStore()
 *
 *   useProjectStatusUpdates(applicationId, (update) => {
 *     if (update.action === 'created') {
 *       // Add new project
 *     } else if (update.action === 'updated') {
 *       // Update existing project
 *     } else if (update.action === 'deleted') {
 *       // Remove project
 *     } else if (update.action === 'status_changed') {
 *       // Handle status change
 *     }
 *   })
 * }
 * ```
 */
export function useProjectStatusUpdates(
  applicationId: string | null,
  onUpdate: (data: ProjectStatusUpdateEventData) => void
): void {
  const { subscribe, joinRoom, leaveRoom, status } = useWebSocket()
  const callbackRef = useRef(onUpdate)

  // Keep callback ref up to date
  useEffect(() => {
    callbackRef.current = onUpdate
  }, [onUpdate])

  // Join application room and subscribe to project events
  useEffect(() => {
    if (!applicationId || !status.isConnected) {
      return
    }

    const roomId = WebSocketClient.getApplicationRoom(applicationId)
    joinRoom(roomId)

    const unsubscribeCreated = subscribe<ProjectStatusUpdateEventData>(
      MessageType.PROJECT_CREATED,
      (data) => callbackRef.current(data)
    )

    const unsubscribeUpdated = subscribe<ProjectStatusUpdateEventData>(
      MessageType.PROJECT_UPDATED,
      (data) => callbackRef.current(data)
    )

    const unsubscribeDeleted = subscribe<ProjectStatusUpdateEventData>(
      MessageType.PROJECT_DELETED,
      (data) => callbackRef.current(data)
    )

    const unsubscribeStatus = subscribe<ProjectStatusUpdateEventData>(
      MessageType.PROJECT_STATUS_CHANGED,
      (data) => callbackRef.current(data)
    )

    return () => {
      unsubscribeCreated()
      unsubscribeUpdated()
      unsubscribeDeleted()
      unsubscribeStatus()
      leaveRoom(roomId)
    }
  }, [applicationId, status.isConnected, subscribe, joinRoom, leaveRoom])
}

/**
 * Hook for subscribing to note updates in an application
 */
export function useNoteUpdates(
  applicationId: string | null,
  onUpdate: (data: NoteUpdateEventData) => void
): void {
  const { subscribe, joinRoom, leaveRoom, status } = useWebSocket()
  const callbackRef = useRef(onUpdate)

  useEffect(() => {
    callbackRef.current = onUpdate
  }, [onUpdate])

  useEffect(() => {
    if (!applicationId || !status.isConnected) {
      return
    }

    const roomId = WebSocketClient.getApplicationRoom(applicationId)
    joinRoom(roomId)

    const unsubscribeCreated = subscribe<NoteUpdateEventData>(
      MessageType.NOTE_CREATED,
      (data) => callbackRef.current(data)
    )

    const unsubscribeUpdated = subscribe<NoteUpdateEventData>(
      MessageType.NOTE_UPDATED,
      (data) => callbackRef.current(data)
    )

    const unsubscribeDeleted = subscribe<NoteUpdateEventData>(
      MessageType.NOTE_DELETED,
      (data) => callbackRef.current(data)
    )

    const unsubscribeContent = subscribe<NoteUpdateEventData>(
      MessageType.NOTE_CONTENT_CHANGED,
      (data) => callbackRef.current(data)
    )

    return () => {
      unsubscribeCreated()
      unsubscribeUpdated()
      unsubscribeDeleted()
      unsubscribeContent()
      leaveRoom(roomId)
    }
  }, [applicationId, status.isConnected, subscribe, joinRoom, leaveRoom])
}

/**
 * Hook for tracking user presence in a room
 */
export function useUserPresence(
  roomId: string | null,
  onPresenceChange?: (data: UserPresenceEventData) => void
): { users: string[]; userCount: number } {
  const { subscribe, joinRoom, leaveRoom, status } = useWebSocket()
  const [users, setUsers] = useState<string[]>([])
  const [userCount, setUserCount] = useState(0)
  const callbackRef = useRef(onPresenceChange)

  useEffect(() => {
    callbackRef.current = onPresenceChange
  }, [onPresenceChange])

  useEffect(() => {
    if (!roomId || !status.isConnected) {
      return
    }

    joinRoom(roomId)

    // Listen for room joined to get initial user count
    const unsubscribeJoined = subscribe<RoomJoinedEventData>(
      MessageType.ROOM_JOINED,
      (data) => {
        if (data.room_id === roomId) {
          setUserCount(data.user_count)
        }
      }
    )

    // Listen for presence updates
    const unsubscribePresence = subscribe<UserPresenceEventData>(
      MessageType.USER_PRESENCE,
      (data) => {
        if (data.room_id === roomId) {
          setUserCount(data.user_count)

          if (data.action === 'joined') {
            setUsers((prev) => [...new Set([...prev, data.user_id])])
          } else if (data.action === 'left') {
            setUsers((prev) => prev.filter((id) => id !== data.user_id))
          }

          callbackRef.current?.(data)
        }
      }
    )

    return () => {
      unsubscribeJoined()
      unsubscribePresence()
      leaveRoom(roomId)
    }
  }, [roomId, status.isConnected, subscribe, joinRoom, leaveRoom])

  return { users, userCount }
}

/**
 * Hook for subscribing to notifications
 */
export function useNotifications(
  onNotification: (data: Record<string, unknown>) => void
): void {
  const { subscribe, status } = useWebSocket()
  const callbackRef = useRef(onNotification)

  useEffect(() => {
    callbackRef.current = onNotification
  }, [onNotification])

  useEffect(() => {
    if (!status.isConnected) {
      return
    }

    const unsubscribe = subscribe<Record<string, unknown>>(
      MessageType.NOTIFICATION,
      (data) => callbackRef.current(data)
    )

    return unsubscribe
  }, [status.isConnected, subscribe])
}

/**
 * Hook for tracking connection status
 */
export function useWebSocketStatus(): WebSocketStatus {
  const { status } = useWebSocket({ autoConnect: false })
  return status
}

/**
 * Hook for debounced typing indicator
 *
 * Sends typing indicator with debouncing to reduce message frequency.
 * Automatically sends isTyping=false after the debounce delay.
 *
 * @example
 * ```tsx
 * function NoteEditor({ roomId }) {
 *   const { setTyping } = useDebouncedTyping(roomId, 300)
 *
 *   return (
 *     <textarea
 *       onChange={() => setTyping(true)}
 *       onBlur={() => setTyping(false)}
 *     />
 *   )
 * }
 * ```
 */
export function useDebouncedTyping(
  roomId: string | null,
  delay: number = 300
): { setTyping: (isTyping: boolean) => void } {
  const { sendTyping, status } = useWebSocket()
  const lastSentRef = useRef<boolean | null>(null)

  // Debounced function to send "stopped typing" after delay
  const debouncedStopTyping = useMemo(
    () =>
      debounce(() => {
        if (roomId && status.isConnected && lastSentRef.current !== false) {
          sendTyping(roomId, false)
          lastSentRef.current = false
        }
      }, delay + 1000), // Extra delay before sending "stopped"
    [roomId, status.isConnected, sendTyping, delay]
  )

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      debouncedStopTyping.cancel()
      // Send final "stopped typing" on unmount
      if (roomId && lastSentRef.current === true) {
        sendTyping(roomId, false)
      }
    }
  }, [roomId, sendTyping, debouncedStopTyping])

  const setTyping = useCallback(
    (isTyping: boolean) => {
      if (!roomId || !status.isConnected) return

      if (isTyping) {
        // Only send "typing" if we haven't already
        if (lastSentRef.current !== true) {
          sendTyping(roomId, true)
          lastSentRef.current = true
        }
        // Reset the stop-typing timer
        debouncedStopTyping()
      } else {
        // Immediately send "stopped typing"
        debouncedStopTyping.cancel()
        if (lastSentRef.current !== false) {
          sendTyping(roomId, false)
          lastSentRef.current = false
        }
      }
    },
    [roomId, status.isConnected, sendTyping, debouncedStopTyping]
  )

  return { setTyping }
}

/**
 * Hook for subscribing to all WebSocket messages (debugging)
 */
export function useWebSocketDebug(
  enabled: boolean = false,
  onMessage?: (message: WebSocketMessage) => void
): void {
  const { subscribe, status } = useWebSocket()
  const callbackRef = useRef(onMessage)

  useEffect(() => {
    callbackRef.current = onMessage
  }, [onMessage])

  useEffect(() => {
    if (!enabled || !status.isConnected) {
      return
    }

    const unsubscribe = subscribe<WebSocketMessage>('*', (message) => {
      callbackRef.current?.(message)
    })

    return unsubscribe
  }, [enabled, status.isConnected, subscribe])
}

/**
 * Hook for subscribing to invitation notifications
 *
 * This hook listens for all invitation-related WebSocket events:
 * - invitation_received: When someone invites you to an application
 * - invitation_response: When someone accepts/rejects your invitation
 * - member_added: When a new member joins an application
 * - member_removed: When a member leaves/is removed from an application
 * - role_updated: When a member's role is changed
 *
 * @example
 * ```tsx
 * function App() {
 *   useInvitationNotifications({
 *     onInvitationReceived: (data) => {
 *       toast.info(`${data.inviter_name} invited you to ${data.application_name}`)
 *     },
 *     onInvitationResponse: (data) => {
 *       toast.info(`${data.invitee_name} ${data.status} your invitation`)
 *     }
 *   })
 * }
 * ```
 */
export interface UseInvitationNotificationsOptions {
  onInvitationReceived?: (data: InvitationReceivedEventData) => void
  onInvitationResponse?: (data: InvitationResponseEventData) => void
  onMemberAdded?: (data: MemberAddedEventData) => void
  onMemberRemoved?: (data: MemberRemovedEventData) => void
  onRoleUpdated?: (data: RoleUpdatedEventData) => void
}

export function useInvitationNotifications(
  options: UseInvitationNotificationsOptions = {}
): void {
  const { subscribe, status } = useWebSocket()
  const optionsRef = useRef(options)

  useEffect(() => {
    optionsRef.current = options
  }, [options])

  useEffect(() => {
    if (!status.isConnected) {
      return
    }

    const unsubscribes: Unsubscribe[] = []

    // Listen for invitation received
    unsubscribes.push(
      subscribe<InvitationReceivedEventData>(
        MessageType.INVITATION_RECEIVED,
        (data) => optionsRef.current.onInvitationReceived?.(data)
      )
    )

    // Listen for invitation response (accept/reject)
    unsubscribes.push(
      subscribe<InvitationResponseEventData>(
        MessageType.INVITATION_RESPONSE,
        (data) => optionsRef.current.onInvitationResponse?.(data)
      )
    )

    // Listen for member added
    unsubscribes.push(
      subscribe<MemberAddedEventData>(
        MessageType.MEMBER_ADDED,
        (data) => optionsRef.current.onMemberAdded?.(data)
      )
    )

    // Listen for member removed
    unsubscribes.push(
      subscribe<MemberRemovedEventData>(
        MessageType.MEMBER_REMOVED,
        (data) => optionsRef.current.onMemberRemoved?.(data)
      )
    )

    // Listen for role updated
    unsubscribes.push(
      subscribe<RoleUpdatedEventData>(
        MessageType.ROLE_UPDATED,
        (data) => optionsRef.current.onRoleUpdated?.(data)
      )
    )

    return () => {
      unsubscribes.forEach((unsubscribe) => unsubscribe())
    }
  }, [status.isConnected, subscribe])
}

/**
 * Hook for syncing notification read status across tabs/devices
 *
 * When a notification is marked as read on one device/tab, this hook
 * receives the event via WebSocket and updates the local store.
 *
 * @example
 * ```tsx
 * function App() {
 *   useNotificationReadSync()
 *   // Now notification read status syncs across all open tabs
 * }
 * ```
 */
export function useNotificationReadSync(): void {
  const { subscribe, status } = useWebSocket()

  useEffect(() => {
    if (!status.isConnected) {
      return
    }

    const unsubscribe = subscribe<NotificationReadEventData>(
      MessageType.NOTIFICATION_READ,
      (data) => {
        // Update the notification in local store (optimistic, no backend call)
        const store = useNotificationsStore.getState()
        const notification = store.notifications.find(
          (n: { id: string }) => n.id === data.notification_id
        )
        if (notification && !notification.read) {
          // Directly update state without calling markAsRead (which would trigger another backend call)
          useNotificationsStore.setState((state) => ({
            ...state,
            notifications: state.notifications.map((n) =>
              n.id === data.notification_id ? { ...n, read: true } : n
            ),
            unreadCount: Math.max(0, state.unreadCount - 1),
          }))
        }
      }
    )

    return unsubscribe
  }, [status.isConnected, subscribe])
}

/**
 * Event data for project update
 */
export interface ProjectUpdatedEventData {
  project_id: string
  name: string
  description: string | null
  project_type: string
  project_key: string
  updated_at: string | null
  updated_by: string
}

/**
 * Event data for project member added
 */
export interface ProjectMemberAddedEventData {
  project_id: string
  member_id: string
  user_id: string
  role: string
  user: {
    id: string
    email: string
    display_name: string | null
    avatar_url: string | null
  }
  added_by: string
}

/**
 * Event data for project member removed
 */
export interface ProjectMemberRemovedEventData {
  project_id: string
  user_id: string
  removed_by: string
  tasks_unassigned: number
}

/**
 * Event data for project role changed
 */
export interface ProjectRoleChangedEventData {
  project_id: string
  user_id: string
  old_role: string
  new_role: string
  changed_by: string
}

/**
 * Hook to sync project updates (name, description, type, derived status) across tabs/windows.
 *
 * When a project is updated or its derived status changes (due to task changes),
 * this hook receives the event via WebSocket and updates the local projects store.
 *
 * @param projectId - The project ID to sync updates for
 */
export function useProjectUpdatedSync(projectId: string | undefined): void {
  const { subscribe, status, joinRoom, leaveRoom } = useWebSocket()

  useEffect(() => {
    if (!status.isConnected || !projectId) {
      return
    }

    const roomId = WebSocketClient.getProjectRoom(projectId)
    joinRoom(roomId)

    // Subscribe to project property updates (name, description, type)
    const unsubscribeUpdated = subscribe<ProjectUpdatedEventData>(
      MessageType.PROJECT_UPDATED,
      (data) => {
        if (data.project_id === projectId) {
          useProjectsStore.getState().handleProjectUpdated(data)
        }
      }
    )

    // Subscribe to project status changes (derived status from task distribution)
    const unsubscribeStatusChanged = subscribe<ProjectStatusChangedEventData>(
      MessageType.PROJECT_STATUS_CHANGED,
      (data) => {
        if (data.project_id === projectId) {
          useProjectsStore.getState().handleProjectStatusChanged(data)
        }
      }
    )

    return () => {
      unsubscribeUpdated()
      unsubscribeStatusChanged()
      leaveRoom(roomId)
    }
  }, [status.isConnected, projectId, subscribe, joinRoom, leaveRoom])
}

/**
 * Hook to sync project member changes across tabs/windows.
 *
 * When project members are added, removed, or their roles change,
 * this hook receives the events via WebSocket and updates the local store.
 *
 * @param projectId - The project ID to sync member changes for
 */
export function useProjectMemberSync(projectId: string | undefined): void {
  const { subscribe, status, joinRoom, leaveRoom } = useWebSocket()

  useEffect(() => {
    if (!status.isConnected || !projectId) {
      return
    }

    const roomId = WebSocketClient.getProjectRoom(projectId)
    joinRoom(roomId)

    // Subscribe to member added
    const unsubscribeMemberAdded = subscribe<ProjectMemberAddedEventData>(
      MessageType.PROJECT_MEMBER_ADDED,
      (data) => {
        if (data.project_id === projectId) {
          useProjectMembersStore.getState().handleMemberAdded(data)
        }
      }
    )

    // Subscribe to member removed
    const unsubscribeMemberRemoved = subscribe<ProjectMemberRemovedEventData>(
      MessageType.PROJECT_MEMBER_REMOVED,
      (data) => {
        if (data.project_id === projectId) {
          useProjectMembersStore.getState().handleMemberRemoved(data)
        }
      }
    )

    // Subscribe to role changed
    const unsubscribeRoleChanged = subscribe<ProjectRoleChangedEventData>(
      MessageType.PROJECT_ROLE_CHANGED,
      (data) => {
        if (data.project_id === projectId) {
          useProjectMembersStore.getState().handleRoleChanged(data)
        }
      }
    )

    return () => {
      unsubscribeMemberAdded()
      unsubscribeMemberRemoved()
      unsubscribeRoleChanged()
      leaveRoom(roomId)
    }
  }, [status.isConnected, projectId, subscribe, joinRoom, leaveRoom])
}

/**
 * Hook for syncing project deletion across tabs/devices
 *
 * When a project is deleted, this hook receives the event via WebSocket
 * and updates the local projects store. The event is sent directly to
 * affected users (project members and application owners).
 *
 * @example
 * ```tsx
 * function App() {
 *   useProjectDeletedSync()
 *   // Now project deletions sync across all open tabs
 * }
 * ```
 */
export function useProjectDeletedSync(): void {
  const { subscribe, status } = useWebSocket()

  useEffect(() => {
    if (!status.isConnected) {
      return
    }

    const unsubscribe = subscribe<{
      project_id: string
      application_id: string
      project_name: string
      project_key: string
      deleted_by: string
    }>(
      MessageType.PROJECT_DELETED,
      (data) => {
        useProjectsStore.getState().handleProjectDeleted(data)
      }
    )

    return unsubscribe
  }, [status.isConnected, subscribe])
}

// ============================================================================
// Exports
// ============================================================================

export {
  wsClient,
  WebSocketClient,
  WebSocketState,
  MessageType,
  debounce,
  type WebSocketMessage,
  type WebSocketConfig,
  type WebSocketEventListener,
  type Unsubscribe,
  type TaskUpdateEventData,
  type TaskMovedEventData,
  type NoteUpdateEventData,
  type UserPresenceEventData,
  type ConnectedEventData,
  type RoomJoinedEventData,
  type InvitationReceivedEventData,
  type InvitationResponseEventData,
  type MemberAddedEventData,
  type MemberRemovedEventData,
  type RoleUpdatedEventData,
  type NotificationReadEventData,
}
