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

import { useCallback, useEffect, useRef, useState } from 'react'
import { useAuthStore } from '@/stores/auth-store'
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
  type NoteUpdateEventData,
  type UserPresenceEventData,
  type RoomJoinedEventData,
  type ConnectedEventData,
} from '@/lib/websocket'

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

// ============================================================================
// Exports
// ============================================================================

export {
  wsClient,
  WebSocketClient,
  WebSocketState,
  MessageType,
  type WebSocketMessage,
  type WebSocketConfig,
  type WebSocketEventListener,
  type Unsubscribe,
  type TaskUpdateEventData,
  type NoteUpdateEventData,
  type UserPresenceEventData,
  type ConnectedEventData,
  type RoomJoinedEventData,
}
