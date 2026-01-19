/**
 * WebSocket Client
 *
 * A robust WebSocket client with automatic reconnection, message queuing,
 * and room-based subscription support.
 *
 * Features:
 * - Automatic reconnection with exponential backoff
 * - Message queuing while disconnected
 * - Ping/pong keepalive support
 * - Room-based subscriptions
 * - Event-driven architecture
 * - TypeScript type safety
 */

// ============================================================================
// Types
// ============================================================================

/**
 * WebSocket connection states
 */
export enum WebSocketState {
  CONNECTING = 'connecting',
  CONNECTED = 'connected',
  DISCONNECTED = 'disconnected',
  RECONNECTING = 'reconnecting',
  CLOSED = 'closed',
}

/**
 * Message types matching the backend MessageType enum
 */
export enum MessageType {
  // Connection events
  CONNECTED = 'connected',
  DISCONNECTED = 'disconnected',
  ERROR = 'error',

  // Room events
  JOIN_ROOM = 'join_room',
  LEAVE_ROOM = 'leave_room',
  ROOM_JOINED = 'room_joined',
  ROOM_LEFT = 'room_left',

  // Task events
  TASK_CREATED = 'task_created',
  TASK_UPDATED = 'task_updated',
  TASK_DELETED = 'task_deleted',
  TASK_STATUS_CHANGED = 'task_status_changed',

  // Note events
  NOTE_CREATED = 'note_created',
  NOTE_UPDATED = 'note_updated',
  NOTE_DELETED = 'note_deleted',
  NOTE_CONTENT_CHANGED = 'note_content_changed',

  // Project events
  PROJECT_CREATED = 'project_created',
  PROJECT_UPDATED = 'project_updated',
  PROJECT_DELETED = 'project_deleted',
  PROJECT_STATUS_CHANGED = 'project_status_changed',

  // Application events
  APPLICATION_CREATED = 'application_created',
  APPLICATION_UPDATED = 'application_updated',
  APPLICATION_DELETED = 'application_deleted',

  // Collaboration events
  USER_PRESENCE = 'user_presence',
  USER_TYPING = 'user_typing',
  USER_VIEWING = 'user_viewing',

  // Notification events
  NOTIFICATION = 'notification',
  NOTIFICATION_READ = 'notification_read',

  // Invitation/member events
  INVITATION_RECEIVED = 'invitation_received',
  INVITATION_RESPONSE = 'invitation_response',
  MEMBER_ADDED = 'member_added',
  MEMBER_REMOVED = 'member_removed',
  ROLE_UPDATED = 'role_updated',

  // Keepalive
  PING = 'ping',
  PONG = 'pong',
}

/**
 * WebSocket message structure
 */
export interface WebSocketMessage<T = unknown> {
  type: MessageType | string
  data: T
}

/**
 * Connection event data
 */
export interface ConnectedEventData {
  user_id: string
  connected_at: string
  rooms: string[]
}

/**
 * Room joined event data
 */
export interface RoomJoinedEventData {
  room_id: string
  user_count: number
}

/**
 * Room left event data
 */
export interface RoomLeftEventData {
  room_id: string
}

/**
 * User presence event data
 */
export interface UserPresenceEventData {
  room_id: string
  user_id: string
  action: 'joined' | 'left'
  user_count: number
}

/**
 * Entity update event data base
 */
export interface EntityUpdateEventData<T = unknown> {
  action: 'created' | 'updated' | 'deleted' | 'status_changed' | 'content_changed'
  timestamp: string
  changed_by?: string
  [key: string]: unknown
  entity?: T
}

/**
 * Task update event data
 */
export interface TaskUpdateEventData {
  task_id: string
  project_id: string
  action: string
  task: Record<string, unknown>
  timestamp: string
  changed_by?: string
  old_status?: string
  new_status?: string
}

/**
 * Note update event data
 */
export interface NoteUpdateEventData {
  note_id: string
  application_id: string
  action: string
  note: Record<string, unknown>
  timestamp: string
  changed_by?: string
  content_delta?: Record<string, unknown>
}

/**
 * Invitation received event data
 */
export interface InvitationReceivedEventData {
  invitation_id: string
  application_id: string
  application_name: string
  inviter_id: string
  inviter_name: string
  inviter_email?: string
  role: string
  timestamp: string
}

/**
 * Invitation response event data
 */
export interface InvitationResponseEventData {
  invitation_id: string
  application_id: string
  invitee_id?: string
  invitee_name?: string
  invitee_email?: string
  inviter_id?: string
  inviter_name?: string
  status: 'accepted' | 'rejected' | 'cancelled'
  role: string
  timestamp: string
}

/**
 * Member added event data
 */
export interface MemberAddedEventData {
  application_id: string
  user_id: string
  user_name: string
  user_email?: string
  role: string
  is_manager: boolean
  added_by: string
  timestamp: string
}

/**
 * Member removed event data
 */
export interface MemberRemovedEventData {
  application_id: string
  user_id: string
  user_name: string
  removed_by: string
  reason?: string
  timestamp: string
}

/**
 * Role updated event data
 */
export interface RoleUpdatedEventData {
  application_id: string
  user_id: string
  user_name: string
  old_role: string
  new_role: string
  is_manager: boolean
  updated_by: string
  timestamp: string
}

/**
 * Notification read event data (for cross-tab sync)
 */
export interface NotificationReadEventData {
  notification_id: string
  user_id: string
  timestamp: string
}

/**
 * WebSocket client configuration
 */
export interface WebSocketConfig {
  /** WebSocket server URL (default: ws://localhost:8000/ws) */
  url?: string
  /** JWT token for authentication */
  token?: string
  /** Enable automatic reconnection (default: true) */
  autoReconnect?: boolean
  /** Maximum reconnection attempts (default: 10) */
  maxReconnectAttempts?: number
  /** Initial reconnection delay in ms (default: 1000) */
  reconnectDelay?: number
  /** Maximum reconnection delay in ms (default: 30000) */
  maxReconnectDelay?: number
  /** Ping interval in ms for keepalive (default: 30000) */
  pingInterval?: number
  /** Pong timeout in ms (default: 5000) */
  pongTimeout?: number
  /** Message queue max size (default: 100) */
  maxQueueSize?: number
}

/**
 * Event listener callback
 */
export type WebSocketEventListener<T = unknown> = (data: T) => void

/**
 * Event listener unsubscribe function
 */
export type Unsubscribe = () => void

// ============================================================================
// Constants
// ============================================================================

const DEFAULT_CONFIG: Required<WebSocketConfig> = {
  url: 'ws://localhost:8000/ws',
  token: '',
  autoReconnect: true,
  maxReconnectAttempts: 10,
  reconnectDelay: 1000,
  maxReconnectDelay: 30000,
  pingInterval: 30000,
  pongTimeout: 5000,
  maxQueueSize: 100,
}

// ============================================================================
// WebSocket Client Class
// ============================================================================

/**
 * WebSocket client with reconnection and message queuing support
 */
export class WebSocketClient {
  private ws: WebSocket | null = null
  private config: Required<WebSocketConfig>
  private state: WebSocketState = WebSocketState.DISCONNECTED
  private reconnectAttempts = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private pingTimer: ReturnType<typeof setInterval> | null = null
  private pongTimer: ReturnType<typeof setTimeout> | null = null
  private messageQueue: WebSocketMessage[] = []
  private rooms: Set<string> = new Set()
  private listeners: Map<string, Set<WebSocketEventListener>> = new Map()
  private stateListeners: Set<WebSocketEventListener<WebSocketState>> = new Set()

  constructor(config: WebSocketConfig = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config }
  }

  // ============================================================================
  // Public API
  // ============================================================================

  /**
   * Get current connection state
   */
  getState(): WebSocketState {
    return this.state
  }

  /**
   * Check if connected
   */
  isConnected(): boolean {
    return this.state === WebSocketState.CONNECTED
  }

  /**
   * Get list of joined rooms
   */
  getRooms(): string[] {
    return Array.from(this.rooms)
  }

  /**
   * Update configuration
   */
  updateConfig(config: Partial<WebSocketConfig>): void {
    this.config = { ...this.config, ...config }
  }

  /**
   * Set authentication token
   */
  setToken(token: string | null): void {
    this.config.token = token || ''
  }

  /**
   * Connect to WebSocket server
   */
  connect(token?: string): void {
    // Update token if provided
    if (token !== undefined) {
      this.config.token = token || ''
    }

    // Don't connect without token
    if (!this.config.token) {
      this.setState(WebSocketState.DISCONNECTED)
      return
    }

    // Don't connect if already connecting or connected
    if (this.state === WebSocketState.CONNECTING || this.state === WebSocketState.CONNECTED) {
      return
    }

    this.setState(WebSocketState.CONNECTING)

    try {
      // Build URL with token as query parameter
      const url = new URL(this.config.url)
      url.searchParams.set('token', this.config.token)

      this.ws = new WebSocket(url.toString())

      // Set up event handlers
      this.ws.onopen = this.handleOpen.bind(this)
      this.ws.onclose = this.handleClose.bind(this)
      this.ws.onerror = this.handleError.bind(this)
      this.ws.onmessage = this.handleMessage.bind(this)
    } catch (error) {
      this.handleError(error as Event)
    }
  }

  /**
   * Disconnect from WebSocket server
   */
  disconnect(): void {
    this.clearTimers()
    this.reconnectAttempts = 0

    if (this.ws) {
      // Prevent reconnection on intentional close
      this.config.autoReconnect = false
      this.ws.close(1000, 'Client disconnected')
      this.ws = null
    }

    this.setState(WebSocketState.CLOSED)
    this.rooms.clear()
  }

  /**
   * Send a message to the server
   */
  send<T = unknown>(type: MessageType | string, data: T): boolean {
    const message: WebSocketMessage<T> = { type, data }

    if (this.isConnected() && this.ws) {
      try {
        this.ws.send(JSON.stringify(message))
        return true
      } catch {
        // Queue message if send fails
        this.queueMessage(message)
        return false
      }
    } else {
      // Queue message if not connected
      this.queueMessage(message)
      return false
    }
  }

  /**
   * Join a room for targeted updates
   */
  joinRoom(roomId: string): void {
    if (this.rooms.has(roomId)) {
      console.log('[WebSocket] Already in room:', roomId)
      return
    }

    console.log('[WebSocket] Joining room:', roomId)
    this.rooms.add(roomId)
    this.send(MessageType.JOIN_ROOM, { room_id: roomId })
  }

  /**
   * Leave a room
   */
  leaveRoom(roomId: string): void {
    if (!this.rooms.has(roomId)) {
      return
    }

    this.rooms.delete(roomId)
    this.send(MessageType.LEAVE_ROOM, { room_id: roomId })
  }

  /**
   * Send typing indicator
   */
  sendTypingIndicator(roomId: string, isTyping: boolean): void {
    this.send(MessageType.USER_TYPING, {
      room_id: roomId,
      is_typing: isTyping,
    })
  }

  /**
   * Send viewing indicator
   */
  sendViewingIndicator(roomId: string, entityType: string, entityId: string): void {
    this.send(MessageType.USER_VIEWING, {
      room_id: roomId,
      entity_type: entityType,
      entity_id: entityId,
    })
  }

  /**
   * Subscribe to a message type
   */
  on<T = unknown>(type: MessageType | string, listener: WebSocketEventListener<T>): Unsubscribe {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, new Set())
    }
    this.listeners.get(type)!.add(listener as WebSocketEventListener)

    return () => {
      this.listeners.get(type)?.delete(listener as WebSocketEventListener)
    }
  }

  /**
   * Unsubscribe from a message type
   */
  off<T = unknown>(type: MessageType | string, listener: WebSocketEventListener<T>): void {
    this.listeners.get(type)?.delete(listener as WebSocketEventListener)
  }

  /**
   * Subscribe to all messages
   */
  onMessage<T = unknown>(listener: WebSocketEventListener<WebSocketMessage<T>>): Unsubscribe {
    return this.on('*', listener as WebSocketEventListener)
  }

  /**
   * Subscribe to connection state changes
   */
  onStateChange(listener: WebSocketEventListener<WebSocketState>): Unsubscribe {
    this.stateListeners.add(listener)
    return () => {
      this.stateListeners.delete(listener)
    }
  }

  /**
   * Remove all listeners
   */
  removeAllListeners(): void {
    this.listeners.clear()
    this.stateListeners.clear()
  }

  // ============================================================================
  // Room Helper Methods
  // ============================================================================

  /**
   * Get project room ID
   */
  static getProjectRoom(projectId: string): string {
    return `project:${projectId}`
  }

  /**
   * Get application room ID
   */
  static getApplicationRoom(applicationId: string): string {
    return `application:${applicationId}`
  }

  /**
   * Get task room ID
   */
  static getTaskRoom(taskId: string): string {
    return `task:${taskId}`
  }

  /**
   * Get note room ID
   */
  static getNoteRoom(noteId: string): string {
    return `note:${noteId}`
  }

  // ============================================================================
  // Private Methods
  // ============================================================================

  private setState(state: WebSocketState): void {
    if (this.state === state) {
      return
    }

    this.state = state
    this.stateListeners.forEach((listener) => {
      try {
        listener(state)
      } catch {
        // Ignore listener errors
      }
    })
  }

  private handleOpen(): void {
    this.setState(WebSocketState.CONNECTED)
    this.reconnectAttempts = 0

    // Start ping interval
    this.startPingInterval()

    // Flush queued messages
    this.flushMessageQueue()

    // Rejoin rooms
    this.rejoinRooms()

    // Emit connected event
    this.emit(MessageType.CONNECTED, {})
  }

  private handleClose(event: CloseEvent): void {
    this.clearTimers()
    this.ws = null

    // Check if we should reconnect
    if (this.config.autoReconnect && event.code !== 1000) {
      this.scheduleReconnect()
    } else {
      this.setState(WebSocketState.CLOSED)
    }

    // Emit disconnected event
    this.emit(MessageType.DISCONNECTED, {
      code: event.code,
      reason: event.reason,
    })
  }

  private handleError(_event: Event): void {
    // Error handling - connection will be closed after error
    this.emit(MessageType.ERROR, {
      message: 'WebSocket connection error',
    })
  }

  private handleMessage(event: MessageEvent): void {
    try {
      const message: WebSocketMessage = JSON.parse(event.data)

      // Handle pong response
      if (message.type === MessageType.PONG) {
        this.handlePong()
        return
      }

      // Debug log for room events
      if (message.type === MessageType.ROOM_JOINED) {
        console.log('[WebSocket] Room joined confirmed:', message.data)
      }

      // Debug log for member-related events
      if (message.type === MessageType.MEMBER_ADDED ||
          message.type === MessageType.MEMBER_REMOVED ||
          message.type === MessageType.ROLE_UPDATED) {
        console.log('[WebSocket] Received member event:', message.type, message.data)
      }

      // Emit to specific type listeners
      this.emit(message.type, message.data)

      // Emit to wildcard listeners
      this.emit('*', message)
    } catch {
      // Ignore parse errors
    }
  }

  private emit<T = unknown>(type: string, data: T): void {
    const listeners = this.listeners.get(type)
    if (listeners) {
      listeners.forEach((listener) => {
        try {
          listener(data)
        } catch {
          // Ignore listener errors
        }
      })
    }
  }

  private queueMessage(message: WebSocketMessage): void {
    // Don't queue ping/pong messages
    if (message.type === MessageType.PING || message.type === MessageType.PONG) {
      return
    }

    // Enforce max queue size (FIFO)
    while (this.messageQueue.length >= this.config.maxQueueSize) {
      this.messageQueue.shift()
    }

    this.messageQueue.push(message)
  }

  private flushMessageQueue(): void {
    while (this.messageQueue.length > 0) {
      const message = this.messageQueue.shift()
      if (message && this.ws && this.isConnected()) {
        try {
          this.ws.send(JSON.stringify(message))
        } catch {
          // Re-queue if failed
          this.messageQueue.unshift(message)
          break
        }
      }
    }
  }

  private rejoinRooms(): void {
    this.rooms.forEach((roomId) => {
      this.send(MessageType.JOIN_ROOM, { room_id: roomId })
    })
  }

  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.config.maxReconnectAttempts) {
      this.setState(WebSocketState.CLOSED)
      return
    }

    this.setState(WebSocketState.RECONNECTING)
    this.reconnectAttempts++

    // Calculate delay with exponential backoff
    const delay = Math.min(
      this.config.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1),
      this.config.maxReconnectDelay
    )

    this.reconnectTimer = setTimeout(() => {
      this.connect()
    }, delay)
  }

  private startPingInterval(): void {
    this.pingTimer = setInterval(() => {
      if (this.isConnected()) {
        this.sendPing()
      }
    }, this.config.pingInterval)
  }

  private sendPing(): void {
    if (!this.ws || !this.isConnected()) {
      return
    }

    try {
      this.ws.send(JSON.stringify({ type: MessageType.PING, data: {} }))

      // Set pong timeout
      this.pongTimer = setTimeout(() => {
        // Pong not received, close connection
        if (this.ws) {
          this.ws.close(4000, 'Pong timeout')
        }
      }, this.config.pongTimeout)
    } catch {
      // Ignore ping errors
    }
  }

  private handlePong(): void {
    // Clear pong timeout
    if (this.pongTimer) {
      clearTimeout(this.pongTimer)
      this.pongTimer = null
    }
  }

  private clearTimers(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    if (this.pingTimer) {
      clearInterval(this.pingTimer)
      this.pingTimer = null
    }
    if (this.pongTimer) {
      clearTimeout(this.pongTimer)
      this.pongTimer = null
    }
  }
}

// ============================================================================
// Singleton Instance
// ============================================================================

/**
 * Default WebSocket client instance
 */
export const wsClient = new WebSocketClient()

/**
 * Create a new WebSocket client instance
 */
export function createWebSocketClient(config?: WebSocketConfig): WebSocketClient {
  return new WebSocketClient(config)
}

export default wsClient
