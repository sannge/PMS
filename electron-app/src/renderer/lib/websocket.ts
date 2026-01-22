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
  TASK_MOVED = 'task_moved',

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

  // Invitation/member events (application level)
  INVITATION_RECEIVED = 'invitation_received',
  INVITATION_RESPONSE = 'invitation_response',
  MEMBER_ADDED = 'member_added',
  MEMBER_REMOVED = 'member_removed',
  ROLE_UPDATED = 'role_updated',

  // Project member events (project level)
  PROJECT_MEMBER_ADDED = 'project_member_added',
  PROJECT_MEMBER_REMOVED = 'project_member_removed',
  PROJECT_ROLE_CHANGED = 'project_role_changed',

  // Attachment events
  ATTACHMENT_UPLOADED = 'attachment_uploaded',
  ATTACHMENT_DELETED = 'attachment_deleted',

  // Checklist events
  CHECKLIST_CREATED = 'checklist_created',
  CHECKLIST_UPDATED = 'checklist_updated',
  CHECKLIST_DELETED = 'checklist_deleted',
  CHECKLISTS_REORDERED = 'checklists_reordered',
  CHECKLIST_ITEM_TOGGLED = 'checklist_item_toggled',
  CHECKLIST_ITEM_ADDED = 'checklist_item_added',
  CHECKLIST_ITEM_UPDATED = 'checklist_item_updated',
  CHECKLIST_ITEM_DELETED = 'checklist_item_deleted',
  CHECKLIST_ITEMS_REORDERED = 'checklist_items_reordered',

  // Comment events
  COMMENT_ADDED = 'comment_added',
  COMMENT_UPDATED = 'comment_updated',
  COMMENT_DELETED = 'comment_deleted',

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
 * Task moved event data (Kanban drag-and-drop)
 */
export interface TaskMovedEventData {
  task_id: string
  project_id: string
  old_status_id: string | null
  new_status_id: string | null
  old_rank: string | null
  new_rank: string
  task: Record<string, unknown>
  timestamp: string
  changed_by?: string
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
  /** WebSocket server URL (default: derived from VITE_API_URL) */
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

/**
 * Get WebSocket URL from API URL environment variable
 */
function getWebSocketUrl(): string {
  const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8001'
  // Convert http(s):// to ws(s)://
  const wsUrl = apiUrl.replace(/^http/, 'ws')
  return `${wsUrl}/ws`
}

const DEFAULT_CONFIG: Required<WebSocketConfig> = {
  url: getWebSocketUrl(),
  token: '',
  autoReconnect: true,
  maxReconnectAttempts: 10,
  reconnectDelay: 1000,
  maxReconnectDelay: 30000,
  pingInterval: 30000,  // 30 seconds keepalive interval
  pongTimeout: 10000,   // 10 seconds pong timeout
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
  private dedupCleanupTimer: ReturnType<typeof setInterval> | null = null
  private messageQueue: WebSocketMessage[] = []
  private rooms: Set<string> = new Set()
  private roomRefs: Map<string, number> = new Map() // Reference counting for rooms
  private listeners: Map<string, Set<WebSocketEventListener>> = new Map()
  private stateListeners: Set<WebSocketEventListener<WebSocketState>> = new Set()

  // Message deduplication - stores message IDs with their timestamps
  private processedMessageIds: Map<string, number> = new Map()
  private readonly MESSAGE_DEDUP_TTL_MS = 60000 // 1 minute TTL
  private readonly MAX_DEDUP_CACHE_SIZE = 1000

  // Visibility and network state tracking
  private isPageVisible: boolean = true
  private wasConnectedBeforeHidden: boolean = false
  private visibilityHandler: (() => void) | null = null
  private onlineHandler: (() => void) | null = null
  private offlineHandler: (() => void) | null = null

  constructor(config: WebSocketConfig = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config }
    this.setupBrowserEventListeners()
  }

  /**
   * Set up browser event listeners for visibility and network changes
   */
  private setupBrowserEventListeners(): void {
    if (typeof document === 'undefined' || typeof window === 'undefined') {
      return // Not in browser environment
    }

    // Handle page visibility changes (tab switch, minimize)
    this.visibilityHandler = () => {
      const wasVisible = this.isPageVisible
      this.isPageVisible = document.visibilityState === 'visible'

      if (!wasVisible && this.isPageVisible) {
        // Page became visible - verify connection is still alive
        this.handleVisibilityResume()
      } else if (wasVisible && !this.isPageVisible) {
        // Page became hidden - track connection state
        this.wasConnectedBeforeHidden = this.isConnected()
      }
    }
    document.addEventListener('visibilitychange', this.visibilityHandler)

    // Handle network online/offline events
    this.onlineHandler = () => {
      console.log('[WebSocket] Network online, attempting reconnect')
      // Reset reconnect attempts on network recovery
      this.reconnectAttempts = 0
      if (this.config.token && this.state !== WebSocketState.CONNECTED) {
        this.connect()
      }
    }
    window.addEventListener('online', this.onlineHandler)

    this.offlineHandler = () => {
      console.log('[WebSocket] Network offline')
      // Don't try to reconnect while offline
    }
    window.addEventListener('offline', this.offlineHandler)
  }

  /**
   * Clean up browser event listeners
   */
  private cleanupBrowserEventListeners(): void {
    if (typeof document !== 'undefined' && this.visibilityHandler) {
      document.removeEventListener('visibilitychange', this.visibilityHandler)
    }
    if (typeof window !== 'undefined') {
      if (this.onlineHandler) {
        window.removeEventListener('online', this.onlineHandler)
      }
      if (this.offlineHandler) {
        window.removeEventListener('offline', this.offlineHandler)
      }
    }
  }

  /**
   * Handle page becoming visible again
   */
  private handleVisibilityResume(): void {
    console.log('[WebSocket] Page visible, verifying connection')

    // If we were connected before hidden, verify connection is still alive
    if (this.wasConnectedBeforeHidden || this.state === WebSocketState.CONNECTED) {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        // Send immediate ping to verify connection is responsive
        this.sendPing()
      } else {
        // Connection is stale - reconnect
        console.log('[WebSocket] Connection stale after visibility resume, reconnecting')
        this.reconnectAttempts = 0
        this.ws = null
        this.setState(WebSocketState.DISCONNECTED)
        if (this.config.token) {
          this.connect()
        }
      }
    }
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
    // Check both internal state AND actual WebSocket readyState
    return this.state === WebSocketState.CONNECTED &&
           this.ws !== null &&
           this.ws.readyState === WebSocket.OPEN
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

    // Don't connect if already connecting
    if (this.state === WebSocketState.CONNECTING) {
      return
    }

    // If already "connected", verify the connection is actually alive
    if (this.state === WebSocketState.CONNECTED) {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        return
      } else {
        // Connection state is out of sync - force reconnect
        this.ws = null
        this.setState(WebSocketState.DISCONNECTED)
      }
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
      console.error('[WebSocket] Connection error:', error)
      this.handleError(error as Event)
    }
  }

  /**
   * Disconnect from WebSocket server
   */
  disconnect(): void {
    this.clearTimers()
    this.reconnectAttempts = 0

    // Store current autoReconnect setting and temporarily disable
    const wasAutoReconnect = this.config.autoReconnect

    if (this.ws) {
      // Temporarily prevent reconnection on intentional close
      this.config.autoReconnect = false
      this.ws.close(1000, 'Client disconnected')
      this.ws = null
    }

    this.setState(WebSocketState.CLOSED)
    this.rooms.clear()

    // Restore autoReconnect setting so future connections work
    this.config.autoReconnect = wasAutoReconnect
  }

  /**
   * Full cleanup including browser event listeners
   * Call this when the client instance is no longer needed
   */
  destroy(): void {
    this.disconnect()
    this.cleanupBrowserEventListeners()
    this.removeAllListeners()
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
   * Join a room for targeted updates (with reference counting)
   * Multiple components can join the same room - actual join happens on first ref
   */
  joinRoom(roomId: string): void {
    const currentRefs = this.roomRefs.get(roomId) || 0
    this.roomRefs.set(roomId, currentRefs + 1)

    // Only actually join if this is the first reference
    if (currentRefs === 0) {
      this.rooms.add(roomId)
      this.send(MessageType.JOIN_ROOM, { room_id: roomId })
    }
  }

  /**
   * Leave a room (with reference counting)
   * Room is only actually left when all references are released
   */
  leaveRoom(roomId: string): void {
    const currentRefs = this.roomRefs.get(roomId) || 0
    if (currentRefs <= 0) {
      return
    }

    const newRefs = currentRefs - 1
    this.roomRefs.set(roomId, newRefs)

    // Only actually leave if no more references
    if (newRefs === 0) {
      this.roomRefs.delete(roomId)
      // Only remove from local set if we can actually send the leave message
      // This ensures rooms persist across reconnections
      if (this.isConnected()) {
        this.rooms.delete(roomId)
        this.send(MessageType.LEAVE_ROOM, { room_id: roomId })
      }
      // If not connected, keep in rooms set so it's rejoined on reconnection
    }
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

    // Send immediate ping to verify connection is alive
    this.sendPing()

    // Start ping interval
    this.startPingInterval()

    // Start dedup cache cleanup interval
    this.startDedupCleanupInterval()

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

      // Handle pong response (from our ping)
      if (message.type === MessageType.PONG) {
        this.handlePong()
        return
      }

      // Handle ping from server - respond with pong
      if (message.type === MessageType.PING) {
        this.send(MessageType.PONG, {})
        return
      }

      // Message deduplication - check if we've already processed this message
      const messageId = this.getMessageId(message)
      if (messageId && this.isDuplicateMessage(messageId)) {
        return // Skip duplicate message
      }

      // Emit to specific type listeners
      this.emit(message.type, message.data)

      // Emit to wildcard listeners
      this.emit('*', message)
    } catch {
      // Ignore parse errors
    }
  }

  /**
   * Extract a unique message ID from a message for deduplication
   */
  private getMessageId(message: WebSocketMessage): string | null {
    const data = message.data as Record<string, unknown>

    // First, check if the message has an explicit message_id
    if (data && typeof data.message_id === 'string') {
      return data.message_id
    }

    // Generate an ID from entity-related messages based on entity ID + action + timestamp
    if (data && typeof data.timestamp === 'string') {
      const entityId = data.task_id || data.project_id || data.note_id ||
                       data.comment_id || data.checklist_id || data.notification_id
      if (entityId) {
        return `${message.type}:${entityId}:${data.action || 'unknown'}:${data.timestamp}`
      }
    }

    return null // No deduplication for messages without identifiable data
  }

  /**
   * Check if a message has been recently processed
   */
  private isDuplicateMessage(messageId: string): boolean {
    const now = Date.now()

    // Clean up expired entries periodically
    if (this.processedMessageIds.size > this.MAX_DEDUP_CACHE_SIZE / 2) {
      this.cleanupDedupCache(now)
    }

    // Check if we've seen this message
    if (this.processedMessageIds.has(messageId)) {
      return true
    }

    // Record this message
    this.processedMessageIds.set(messageId, now)
    return false
  }

  /**
   * Remove expired entries from the deduplication cache
   */
  private cleanupDedupCache(now: number): void {
    const expireTime = now - this.MESSAGE_DEDUP_TTL_MS

    for (const [id, timestamp] of this.processedMessageIds) {
      if (timestamp < expireTime) {
        this.processedMessageIds.delete(id)
      }
    }

    // If still too large, remove oldest entries
    if (this.processedMessageIds.size > this.MAX_DEDUP_CACHE_SIZE) {
      const entries = Array.from(this.processedMessageIds.entries())
        .sort((a, b) => a[1] - b[1])
      const toRemove = entries.slice(0, entries.length - this.MAX_DEDUP_CACHE_SIZE)
      for (const [id] of toRemove) {
        this.processedMessageIds.delete(id)
      }
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
    if (!this.ws || !this.isConnected() || this.messageQueue.length === 0) {
      return
    }

    // Process queue without losing messages on partial failure
    const failedMessages: WebSocketMessage[] = []

    while (this.messageQueue.length > 0) {
      const message = this.messageQueue.shift()
      if (!message) continue

      // Check connection is still valid before each send
      if (!this.ws || !this.isConnected()) {
        // Connection lost mid-flush - re-queue remaining messages
        failedMessages.push(message)
        failedMessages.push(...this.messageQueue.splice(0))
        break
      }

      try {
        this.ws.send(JSON.stringify(message))
      } catch {
        // Send failed - collect this message and remaining queue
        failedMessages.push(message)
        failedMessages.push(...this.messageQueue.splice(0))
        break
      }
    }

    // Re-queue all failed messages at front (preserving order)
    if (failedMessages.length > 0) {
      this.messageQueue.unshift(...failedMessages)
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

  private startDedupCleanupInterval(): void {
    // Clean up dedup cache every 30 seconds to prevent memory leaks
    this.dedupCleanupTimer = setInterval(() => {
      this.cleanupDedupCache(Date.now())
    }, 30000)
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
    if (this.dedupCleanupTimer) {
      clearInterval(this.dedupCleanupTimer)
      this.dedupCleanupTimer = null
    }
  }
}

// ============================================================================
// Singleton Instance (HMR-safe)
// ============================================================================

// Use window to persist the singleton across HMR reloads
declare global {
  interface Window {
    __wsClient?: WebSocketClient
  }
}

/**
 * Get or create the WebSocket client singleton
 * This survives Vite HMR reloads to prevent multiple instances
 */
function getOrCreateClient(): WebSocketClient {
  if (typeof window !== 'undefined') {
    if (!window.__wsClient) {
      window.__wsClient = new WebSocketClient()
    }
    return window.__wsClient
  }
  // Fallback for non-browser environments
  return new WebSocketClient()
}

/**
 * Default WebSocket client instance
 */
export const wsClient = getOrCreateClient()

/**
 * Create a new WebSocket client instance
 */
export function createWebSocketClient(config?: WebSocketConfig): WebSocketClient {
  return new WebSocketClient(config)
}

export default wsClient
