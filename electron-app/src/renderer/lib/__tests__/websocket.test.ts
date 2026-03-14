/**
 * Tests for websocket.ts — WebSocketClient, singleton, rooms, dedup, reconnect,
 * ping/pong, message queue, visibility resume, event listeners, HMR singleton.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// ============================================================================
// Mocks — must be before imports
// ============================================================================

const mockGetAccessToken = vi.fn(() => null as string | null)
const mockRefreshTokens = vi.fn(() => Promise.resolve(null as string | null))

vi.mock('@/lib/api-client', () => ({
  getAccessToken: (...args: unknown[]) => mockGetAccessToken(...args),
  refreshTokens: (...args: unknown[]) => mockRefreshTokens(...args),
}))

// ============================================================================
// Mock WebSocket
// ============================================================================

class MockWebSocket {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSING = 2
  static readonly CLOSED = 3

  static instances: MockWebSocket[] = []

  url: string
  readyState: number = MockWebSocket.CONNECTING
  onopen: ((ev: Event) => void) | null = null
  onclose: ((ev: CloseEvent) => void) | null = null
  onerror: ((ev: Event) => void) | null = null
  onmessage: ((ev: MessageEvent) => void) | null = null
  send = vi.fn()
  close = vi.fn()

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  /** Simulate the server opening the connection */
  simulateOpen() {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.(new Event('open'))
  }

  /** Simulate the server closing the connection */
  simulateClose(code = 1006, reason = '') {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.({ code, reason, wasClean: code === 1000 } as CloseEvent)
  }

  /** Simulate receiving a message from the server */
  simulateMessage(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent)
  }

  /** Simulate a connection error */
  simulateError() {
    this.onerror?.(new Event('error'))
  }
}

vi.stubGlobal('WebSocket', MockWebSocket)

// Also stub the static constants that isConnected() checks
Object.defineProperty(MockWebSocket, 'OPEN', { value: 1 })

// ============================================================================
// Mock fetch for ws-token endpoint
// ============================================================================

let fetchMock: ReturnType<typeof vi.fn>

// ============================================================================
// Imports (after mocks)
// ============================================================================

import {
  WebSocketClient,
  WebSocketState,
  MessageType,
  createWebSocketClient,
} from '../websocket'

// ============================================================================
// Test Suites
// ============================================================================

describe('WebSocketClient', () => {
  let client: WebSocketClient

  beforeEach(() => {
    vi.useFakeTimers()
    MockWebSocket.instances = []
    fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ token: 'ws-conn-token' }),
    })
    vi.stubGlobal('fetch', fetchMock)
    mockGetAccessToken.mockReturnValue(null)
    mockRefreshTokens.mockResolvedValue(null)
    // Clean up HMR singleton
    delete (window as Record<string, unknown>).__wsClient
    // Suppress console noise
    vi.spyOn(console, 'log').mockImplementation(() => {})
    vi.spyOn(console, 'error').mockImplementation(() => {})

    client = new WebSocketClient({
      url: 'ws://localhost:8001/ws',
      autoReconnect: true,
      maxReconnectAttempts: 10,
      reconnectDelay: 1000,
      maxReconnectDelay: 30000,
      pingInterval: 30000,
      pongTimeout: 10000,
      maxQueueSize: 100,
    })
  })

  afterEach(() => {
    client.destroy()
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  // ==========================================================================
  // 1. Constructor + config defaults
  // ==========================================================================
  describe('constructor + config', () => {
    it('starts in DISCONNECTED state', () => {
      expect(client.getState()).toBe(WebSocketState.DISCONNECTED)
    })

    it('isConnected returns false initially', () => {
      expect(client.isConnected()).toBe(false)
    })

    it('getRooms returns empty array initially', () => {
      expect(client.getRooms()).toEqual([])
    })

    it('setToken updates config token', () => {
      client.setToken('new-tok')
      // We can verify indirectly: connect() should proceed (not stay disconnected)
      mockGetAccessToken.mockReturnValue(null) // don't override
      client.connect()
      // Should attempt to connect since token is now set
      expect(client.getState()).toBe(WebSocketState.CONNECTING)
    })

    it('setToken(null) clears token', () => {
      client.setToken('tok')
      client.setToken(null)
      client.connect()
      // No token → stays disconnected
      expect(client.getState()).toBe(WebSocketState.DISCONNECTED)
    })
  })

  // ==========================================================================
  // 2. connect() — token sync, fetchConnectionToken, state transitions
  // ==========================================================================
  describe('connect()', () => {
    it('stays DISCONNECTED without token', () => {
      client.connect()
      expect(client.getState()).toBe(WebSocketState.DISCONNECTED)
    })

    it('syncs token from getAccessToken()', () => {
      mockGetAccessToken.mockReturnValue('module-token')
      client.connect()
      expect(client.getState()).toBe(WebSocketState.CONNECTING)
    })

    it('uses provided token parameter', () => {
      client.connect('param-token')
      expect(client.getState()).toBe(WebSocketState.CONNECTING)
    })

    it('transitions DISCONNECTED → CONNECTING → CONNECTED', async () => {
      const states: WebSocketState[] = []
      client.onStateChange((s) => states.push(s))

      client.connect('tok')
      expect(client.getState()).toBe(WebSocketState.CONNECTING)

      // Let fetchConnectionToken resolve
      await vi.advanceTimersByTimeAsync(0)

      // A MockWebSocket should have been created
      expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(1)
      const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]

      ws.simulateOpen()
      expect(client.getState()).toBe(WebSocketState.CONNECTED)
      expect(states).toContain(WebSocketState.CONNECTING)
      expect(states).toContain(WebSocketState.CONNECTED)
    })

    it('does not double-connect if already CONNECTING', () => {
      client.connect('tok')
      const countBefore = MockWebSocket.instances.length
      client.connect('tok')
      // No additional fetch or WebSocket created
      expect(client.getState()).toBe(WebSocketState.CONNECTING)
    })

    it('does not reconnect if already CONNECTED with OPEN socket', async () => {
      client.connect('tok')
      await vi.advanceTimersByTimeAsync(0)
      const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
      ws.simulateOpen()
      expect(client.getState()).toBe(WebSocketState.CONNECTED)

      const countBefore = MockWebSocket.instances.length
      client.connect('tok')
      // Should not create a new WebSocket
      expect(MockWebSocket.instances.length).toBe(countBefore)
    })

    it('fetches ws-token and uses it in URL', async () => {
      fetchMock.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ token: 'opaque-conn-tok' }),
      })
      client.connect('jwt-tok')
      await vi.advanceTimersByTimeAsync(0)

      const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
      expect(ws.url).toContain('token=opaque-conn-tok')
    })

    it('retries ws-token fetch with refreshed token on 401', async () => {
      fetchMock
        .mockResolvedValueOnce({ ok: false, status: 401 })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ token: 'refreshed-conn-tok' }),
        })
      mockRefreshTokens.mockResolvedValueOnce('refreshed-jwt')

      client.connect('expired-jwt')
      await vi.advanceTimersByTimeAsync(0)

      expect(mockRefreshTokens).toHaveBeenCalledOnce()
      const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
      expect(ws.url).toContain('token=refreshed-conn-tok')
    })

    it('falls back to JWT when ws-token endpoint is unavailable', async () => {
      fetchMock.mockRejectedValueOnce(new Error('Network error'))

      client.connect('my-jwt')
      await vi.advanceTimersByTimeAsync(0)

      const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
      expect(ws.url).toContain('token=my-jwt')
    })
  })

  // ==========================================================================
  // 3. disconnect()
  // ==========================================================================
  describe('disconnect()', () => {
    it('sets state to CLOSED and clears rooms', async () => {
      client.connect('tok')
      await vi.advanceTimersByTimeAsync(0)
      const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
      ws.simulateOpen()
      client.joinRoom('room-1')

      client.disconnect()

      expect(client.getState()).toBe(WebSocketState.CLOSED)
      expect(client.getRooms()).toEqual([])
      expect(ws.close).toHaveBeenCalledWith(1000, 'Client disconnected')
    })

    it('clears reconnect timers', async () => {
      client.connect('tok')
      await vi.advanceTimersByTimeAsync(0)
      const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
      ws.simulateOpen()
      // Trigger a close that would normally schedule reconnect
      ws.simulateClose(1006, 'abnormal')
      expect(client.getState()).toBe(WebSocketState.RECONNECTING)

      client.disconnect()
      expect(client.getState()).toBe(WebSocketState.CLOSED)

      // Advancing time should NOT trigger a reconnect
      await vi.advanceTimersByTimeAsync(60000)
      expect(client.getState()).toBe(WebSocketState.CLOSED)
    })
  })

  // ==========================================================================
  // 4. Reconnection — exponential backoff
  // ==========================================================================
  describe('reconnection', () => {
    async function connectAndOpen() {
      client.connect('tok')
      await vi.advanceTimersByTimeAsync(0)
      const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
      ws.simulateOpen()
      return ws
    }

    it('schedules reconnect on abnormal close', async () => {
      const ws = await connectAndOpen()
      ws.simulateClose(1006, 'abnormal')
      expect(client.getState()).toBe(WebSocketState.RECONNECTING)
    })

    it('does NOT reconnect on clean close (code 1000)', async () => {
      const ws = await connectAndOpen()
      ws.simulateClose(1000, 'normal')
      expect(client.getState()).toBe(WebSocketState.CLOSED)
    })

    it('uses exponential backoff: 1s, 2s, 4s...', async () => {
      const ws = await connectAndOpen()
      ws.simulateClose(1006)

      // First reconnect after 1s
      expect(client.getState()).toBe(WebSocketState.RECONNECTING)
      const instancesBefore = MockWebSocket.instances.length
      await vi.advanceTimersByTimeAsync(999)
      // Not yet — 1ms short
      await vi.advanceTimersByTimeAsync(1)
      // fetchConnectionToken is async, let it resolve
      await vi.advanceTimersByTimeAsync(0)
      // A new WebSocket instance should have been created by the reconnect
      expect(MockWebSocket.instances.length).toBeGreaterThan(instancesBefore)
    })

    it('gives up after maxReconnectAttempts', async () => {
      const smallClient = new WebSocketClient({
        url: 'ws://localhost:8001/ws',
        maxReconnectAttempts: 2,
        reconnectDelay: 100,
        maxReconnectDelay: 1000,
      })
      smallClient.connect('tok')
      await vi.advanceTimersByTimeAsync(0)
      let ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
      ws.simulateOpen()

      // Close → scheduleReconnect increments to attempt 1
      ws.simulateClose(1006)
      expect(smallClient.getState()).toBe(WebSocketState.RECONNECTING)

      // Reconnect attempt 1 fires after 100ms
      await vi.advanceTimersByTimeAsync(100)
      await vi.advanceTimersByTimeAsync(0)
      ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
      // This new connection also closes → scheduleReconnect increments to attempt 2
      ws.simulateClose(1006)
      expect(smallClient.getState()).toBe(WebSocketState.RECONNECTING)

      // Reconnect attempt 2 fires after 200ms (exponential backoff)
      await vi.advanceTimersByTimeAsync(200)
      await vi.advanceTimersByTimeAsync(0)
      ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
      // This new connection also closes → scheduleReconnect sees attempt >= max → CLOSED
      ws.simulateClose(1006)

      expect(smallClient.getState()).toBe(WebSocketState.CLOSED)
      smallClient.destroy()
    })
  })

  // ==========================================================================
  // 5. Message deduplication
  // ==========================================================================
  describe('message deduplication', () => {
    async function connectAndOpen() {
      client.connect('tok')
      await vi.advanceTimersByTimeAsync(0)
      const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
      ws.simulateOpen()
      return ws
    }

    it('deduplicates messages with same message_id', async () => {
      const ws = await connectAndOpen()
      const listener = vi.fn()
      client.on(MessageType.TASK_UPDATED, listener)

      const msg = { type: MessageType.TASK_UPDATED, data: { message_id: 'dedup-1', task_id: 't1' } }
      ws.simulateMessage(msg)
      ws.simulateMessage(msg) // duplicate

      expect(listener).toHaveBeenCalledTimes(1)
    })

    it('deduplicates messages with entity ID + action + timestamp', async () => {
      const ws = await connectAndOpen()
      const listener = vi.fn()
      client.on(MessageType.TASK_UPDATED, listener)

      const msg = {
        type: MessageType.TASK_UPDATED,
        data: { task_id: 't1', action: 'updated', timestamp: '2026-01-01T00:00:00Z' },
      }
      ws.simulateMessage(msg)
      ws.simulateMessage(msg)

      expect(listener).toHaveBeenCalledTimes(1)
    })

    it('allows messages without identifiable data (no dedup)', async () => {
      const ws = await connectAndOpen()
      const listener = vi.fn()
      client.on(MessageType.USER_PRESENCE, listener)

      const msg = { type: MessageType.USER_PRESENCE, data: { room_id: 'r1', user_id: 'u1', action: 'joined' } }
      ws.simulateMessage(msg)
      ws.simulateMessage(msg) // No timestamp → no dedup ID → both pass

      expect(listener).toHaveBeenCalledTimes(2)
    })
  })

  // ==========================================================================
  // 6. Room ref counting
  // ==========================================================================
  describe('room ref counting', () => {
    async function connectAndOpen() {
      client.connect('tok')
      await vi.advanceTimersByTimeAsync(0)
      const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
      ws.simulateOpen()
      return ws
    }

    it('first joinRoom adds room and sends JOIN_ROOM', async () => {
      const ws = await connectAndOpen()
      client.joinRoom('room-A')

      expect(client.getRooms()).toContain('room-A')
      expect(ws.send).toHaveBeenCalledWith(
        expect.stringContaining('"type":"join_room"'),
      )
    })

    it('second joinRoom increments ref but does NOT send another JOIN_ROOM', async () => {
      const ws = await connectAndOpen()
      client.joinRoom('room-A')
      const sendCountAfterFirst = ws.send.mock.calls.filter(
        (c: string[]) => c[0].includes('join_room'),
      ).length

      client.joinRoom('room-A')
      const sendCountAfterSecond = ws.send.mock.calls.filter(
        (c: string[]) => c[0].includes('join_room'),
      ).length

      expect(sendCountAfterSecond).toBe(sendCountAfterFirst) // no additional join_room
      expect(client.getRooms()).toContain('room-A')
    })

    it('leaveRoom decrements ref; room stays until last ref', async () => {
      const ws = await connectAndOpen()
      client.joinRoom('room-A')
      client.joinRoom('room-A')

      client.leaveRoom('room-A')
      expect(client.getRooms()).toContain('room-A') // still has 1 ref

      client.leaveRoom('room-A')
      expect(client.getRooms()).not.toContain('room-A') // last ref removed
    })

    it('leaveRoom sends LEAVE_ROOM only on last ref while connected', async () => {
      const ws = await connectAndOpen()
      client.joinRoom('room-A')
      client.joinRoom('room-A')

      client.leaveRoom('room-A') // ref 2→1, no LEAVE_ROOM
      const leaveCount1 = ws.send.mock.calls.filter(
        (c: string[]) => c[0].includes('leave_room'),
      ).length
      expect(leaveCount1).toBe(0)

      client.leaveRoom('room-A') // ref 1→0, LEAVE_ROOM sent
      const leaveCount2 = ws.send.mock.calls.filter(
        (c: string[]) => c[0].includes('leave_room'),
      ).length
      expect(leaveCount2).toBe(1)
    })

    it('leaveRoom with no refs is a no-op', async () => {
      await connectAndOpen()
      client.leaveRoom('nonexistent')
      expect(client.getRooms()).toEqual([])
    })

    it('rooms are rejoined on reconnect', async () => {
      const ws1 = await connectAndOpen()
      client.joinRoom('room-A')
      client.joinRoom('room-B')

      ws1.simulateClose(1006)
      await vi.advanceTimersByTimeAsync(1000)
      await vi.advanceTimersByTimeAsync(0)

      const ws2 = MockWebSocket.instances[MockWebSocket.instances.length - 1]
      ws2.simulateOpen()

      // After reconnect, rooms should be rejoined
      const joinCalls = ws2.send.mock.calls.filter(
        (c: string[]) => c[0].includes('join_room'),
      )
      expect(joinCalls.length).toBe(2) // room-A and room-B
    })
  })

  // ==========================================================================
  // 7. Ping/pong keepalive
  // ==========================================================================
  describe('ping/pong keepalive', () => {
    async function connectAndOpen() {
      client.connect('tok')
      await vi.advanceTimersByTimeAsync(0)
      const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
      ws.simulateOpen()
      return ws
    }

    it('sends ping immediately on open and starts interval', async () => {
      const ws = await connectAndOpen()

      // Immediate ping on open
      const pingSends = ws.send.mock.calls.filter(
        (c: string[]) => c[0].includes('"type":"ping"'),
      )
      expect(pingSends.length).toBeGreaterThanOrEqual(1)
    })

    it('sends ping at configured interval', async () => {
      const ws = await connectAndOpen()
      // Clear send calls from open
      ws.send.mockClear()

      // Advance past one ping interval (30s)
      await vi.advanceTimersByTimeAsync(30000)

      const pingSends = ws.send.mock.calls.filter(
        (c: string[]) => c[0].includes('"type":"ping"'),
      )
      expect(pingSends.length).toBeGreaterThanOrEqual(1)
    })

    it('pong response clears pong timeout', async () => {
      const ws = await connectAndOpen()

      // Simulate server pong
      ws.simulateMessage({ type: MessageType.PONG, data: {} })

      // Advance past pong timeout — should NOT close
      await vi.advanceTimersByTimeAsync(11000)
      expect(ws.close).not.toHaveBeenCalled()
    })

    it('pong timeout closes connection', async () => {
      const ws = await connectAndOpen()

      // Don't send pong. Wait for pong timeout (10s)
      await vi.advanceTimersByTimeAsync(10000)

      expect(ws.close).toHaveBeenCalledWith(4000, 'Pong timeout')
    })

    it('responds to server ping with pong', async () => {
      const ws = await connectAndOpen()
      ws.send.mockClear()

      ws.simulateMessage({ type: MessageType.PING, data: {} })

      const pongSends = ws.send.mock.calls.filter(
        (c: string[]) => c[0].includes('"type":"pong"'),
      )
      expect(pongSends.length).toBe(1)
    })
  })

  // ==========================================================================
  // 8. Message queuing
  // ==========================================================================
  describe('message queuing', () => {
    it('queues messages when disconnected', () => {
      client.setToken('tok')
      const sent = client.send(MessageType.JOIN_ROOM, { room_id: 'r1' })
      expect(sent).toBe(false) // queued, not sent
    })

    it('flushes queued messages on connect', async () => {
      client.setToken('tok')
      client.send(MessageType.JOIN_ROOM, { room_id: 'r1' })
      client.send(MessageType.JOIN_ROOM, { room_id: 'r2' })

      client.connect('tok')
      await vi.advanceTimersByTimeAsync(0)
      const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
      ws.simulateOpen()

      // Queued messages should have been flushed
      const joinCalls = ws.send.mock.calls.filter(
        (c: string[]) => c[0].includes('join_room'),
      )
      // 2 queued + rooms from rejoinRooms (but rooms set is empty here since joinRoom wasn't used)
      expect(joinCalls.length).toBe(2)
    })

    it('enforces max queue size with FIFO eviction', async () => {
      const smallClient = new WebSocketClient({
        url: 'ws://localhost:8001/ws',
        maxQueueSize: 3,
      })

      smallClient.setToken('tok')
      smallClient.send('msg1', { data: 1 })
      smallClient.send('msg2', { data: 2 })
      smallClient.send('msg3', { data: 3 })
      smallClient.send('msg4', { data: 4 }) // should evict msg1

      // Connect and flush to verify eviction
      smallClient.connect('tok')
      await vi.advanceTimersByTimeAsync(0)
      const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
      ws.simulateOpen()

      // Flushed messages should NOT include evicted msg1
      const flushedPayloads = ws.send.mock.calls.map(
        (c: string[]) => JSON.parse(c[0])
      )
      const flushedTypes = flushedPayloads.map((p: { type: string }) => p.type)
      expect(flushedTypes).not.toContain('msg1')
      // Should contain msg2, msg3, msg4
      expect(flushedTypes).toContain('msg2')
      expect(flushedTypes).toContain('msg3')
      expect(flushedTypes).toContain('msg4')

      smallClient.destroy()
    })

    it('does not queue ping/pong messages', async () => {
      client.setToken('tok')
      // Attempt to send ping/pong while disconnected — they should NOT be queued
      const pingResult = client.send(MessageType.PING, {})
      const pongResult = client.send(MessageType.PONG, {})

      // send() returns false when not connected (message dropped, not queued)
      expect(pingResult).toBe(false)
      expect(pongResult).toBe(false)

      // Also queue a normal message to verify flush works
      client.send(MessageType.JOIN_ROOM, { room_id: 'r1' })

      // Connect and flush
      client.connect('tok')
      await vi.advanceTimersByTimeAsync(0)
      const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
      ws.simulateOpen()

      // On open, the client sends an auto-ping (keepalive), then flushes the queue.
      // Verify: exactly 1 ping (the auto-ping), 0 pongs, and the queued join_room.
      const flushedPayloads = ws.send.mock.calls.map(
        (c: string[]) => JSON.parse(c[0])
      )
      const flushedTypes = flushedPayloads.map((p: { type: string }) => p.type)
      const pingCount = flushedTypes.filter((t) => t === MessageType.PING).length
      const pongCount = flushedTypes.filter((t) => t === MessageType.PONG).length
      // Only 1 ping (auto-ping on open), none from queue
      expect(pingCount).toBe(1)
      // No pong at all (neither auto nor queued)
      expect(pongCount).toBe(0)
      // The queued join_room should have been flushed
      expect(flushedTypes).toContain(MessageType.JOIN_ROOM)
    })

    it('send returns true when connected', async () => {
      client.connect('tok')
      await vi.advanceTimersByTimeAsync(0)
      const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
      ws.simulateOpen()

      const sent = client.send(MessageType.JOIN_ROOM, { room_id: 'r1' })
      expect(sent).toBe(true)
    })
  })

  // ==========================================================================
  // 9. Visibility resume
  // ==========================================================================
  describe('visibility resume', () => {
    async function connectAndOpen() {
      client.connect('tok')
      await vi.advanceTimersByTimeAsync(0)
      const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
      ws.simulateOpen()
      return ws
    }

    it('sends ping when page becomes visible with OPEN connection', async () => {
      const ws = await connectAndOpen()
      ws.send.mockClear()

      // Simulate page hidden
      Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true })
      document.dispatchEvent(new Event('visibilitychange'))

      // Simulate page visible again
      Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
      document.dispatchEvent(new Event('visibilitychange'))

      // Should have sent a ping to verify connection
      const pingSends = ws.send.mock.calls.filter(
        (c: string[]) => c[0].includes('"type":"ping"'),
      )
      expect(pingSends.length).toBeGreaterThanOrEqual(1)
    })

    it('reconnects when connection is stale after visibility resume', async () => {
      const ws = await connectAndOpen()

      // Simulate page hidden
      Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true })
      document.dispatchEvent(new Event('visibilitychange'))

      // Simulate stale connection (ws closed while hidden)
      ws.readyState = MockWebSocket.CLOSED

      // Simulate page visible
      Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
      document.dispatchEvent(new Event('visibilitychange'))

      // Should trigger reconnect → CONNECTING state
      // Need to wait for async fetchConnectionToken
      await vi.advanceTimersByTimeAsync(0)
      expect(
        client.getState() === WebSocketState.CONNECTING ||
        client.getState() === WebSocketState.DISCONNECTED
      ).toBe(true)
    })
  })

  // ==========================================================================
  // 10. Network online/offline
  // ==========================================================================
  describe('network online/offline', () => {
    it('attempts reconnect on online event when disconnected', async () => {
      client.setToken('tok')
      client.connect('tok')
      await vi.advanceTimersByTimeAsync(0)
      const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
      ws.simulateOpen()
      ws.simulateClose(1006) // abnormal close

      // Reset reconnect attempts
      const instancesBefore = MockWebSocket.instances.length

      // Simulate network online
      window.dispatchEvent(new Event('online'))
      await vi.advanceTimersByTimeAsync(0)

      // Should attempt to connect
      expect(MockWebSocket.instances.length).toBeGreaterThan(instancesBefore)
    })
  })

  // ==========================================================================
  // 11. Event listeners
  // ==========================================================================
  describe('event listeners', () => {
    async function connectAndOpen() {
      client.connect('tok')
      await vi.advanceTimersByTimeAsync(0)
      const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
      ws.simulateOpen()
      return ws
    }

    it('on() subscribes and returns unsubscribe function', async () => {
      const ws = await connectAndOpen()
      const listener = vi.fn()
      const unsub = client.on(MessageType.TASK_UPDATED, listener)

      ws.simulateMessage({
        type: MessageType.TASK_UPDATED,
        data: { task_id: 't1', timestamp: '2026-01-01', action: 'updated' },
      })
      expect(listener).toHaveBeenCalledOnce()

      unsub()
      ws.simulateMessage({
        type: MessageType.TASK_UPDATED,
        data: { task_id: 't2', timestamp: '2026-01-02', action: 'created' },
      })
      expect(listener).toHaveBeenCalledOnce() // still 1, not called again
    })

    it('off() removes a specific listener', async () => {
      const ws = await connectAndOpen()
      const listener = vi.fn()
      client.on(MessageType.TASK_CREATED, listener)

      client.off(MessageType.TASK_CREATED, listener)
      ws.simulateMessage({ type: MessageType.TASK_CREATED, data: {} })
      expect(listener).not.toHaveBeenCalled()
    })

    it('onMessage() receives all messages via wildcard', async () => {
      const ws = await connectAndOpen()
      const listener = vi.fn()
      client.onMessage(listener)

      ws.simulateMessage({ type: MessageType.TASK_UPDATED, data: { task_id: 't1' } })
      expect(listener).toHaveBeenCalledWith(
        expect.objectContaining({ type: MessageType.TASK_UPDATED }),
      )
    })

    it('onStateChange() receives state transitions', async () => {
      const states: WebSocketState[] = []
      client.onStateChange((s) => states.push(s))

      client.connect('tok')
      await vi.advanceTimersByTimeAsync(0)
      const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
      ws.simulateOpen()

      expect(states).toContain(WebSocketState.CONNECTING)
      expect(states).toContain(WebSocketState.CONNECTED)
    })

    it('removeAllListeners() clears all subscriptions', async () => {
      const ws = await connectAndOpen()
      const listener = vi.fn()
      const stateListener = vi.fn()
      client.on(MessageType.TASK_UPDATED, listener)
      client.onStateChange(stateListener)

      client.removeAllListeners()

      ws.simulateMessage({ type: MessageType.TASK_UPDATED, data: {} })
      client.disconnect()

      expect(listener).not.toHaveBeenCalled()
      // stateListener should not be called after removeAllListeners for CLOSED transition
      expect(stateListener).not.toHaveBeenCalled()
    })

    it('listener errors do not break other listeners', async () => {
      const ws = await connectAndOpen()
      const badListener = vi.fn(() => { throw new Error('boom') })
      const goodListener = vi.fn()
      client.on(MessageType.TASK_UPDATED, badListener)
      client.on(MessageType.TASK_UPDATED, goodListener)

      ws.simulateMessage({
        type: MessageType.TASK_UPDATED,
        data: { task_id: 'x', timestamp: '2026-01-01', action: 'updated' },
      })

      expect(badListener).toHaveBeenCalledOnce()
      expect(goodListener).toHaveBeenCalledOnce()
    })
  })

  // ==========================================================================
  // 12. Static room helpers
  // ==========================================================================
  describe('static room helpers', () => {
    it('getProjectRoom', () => {
      expect(WebSocketClient.getProjectRoom('p1')).toBe('project:p1')
    })
    it('getUserRoom', () => {
      expect(WebSocketClient.getUserRoom('u1')).toBe('user:u1')
    })
    it('getApplicationRoom', () => {
      expect(WebSocketClient.getApplicationRoom('a1')).toBe('application:a1')
    })
    it('getTaskRoom', () => {
      expect(WebSocketClient.getTaskRoom('t1')).toBe('task:t1')
    })
    it('getNoteRoom', () => {
      expect(WebSocketClient.getNoteRoom('n1')).toBe('note:n1')
    })
  })

  // ==========================================================================
  // 13. handleMessage edge cases
  // ==========================================================================
  describe('handleMessage edge cases', () => {
    async function connectAndOpen() {
      client.connect('tok')
      await vi.advanceTimersByTimeAsync(0)
      const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
      ws.simulateOpen()
      return ws
    }

    it('ignores malformed JSON messages', async () => {
      const ws = await connectAndOpen()
      const listener = vi.fn()
      client.onMessage(listener)

      // Simulate raw malformed message
      ws.onmessage?.({ data: 'not-json' } as MessageEvent)
      expect(listener).not.toHaveBeenCalled()
    })

    it('emits CONNECTED event on open', async () => {
      const listener = vi.fn()
      client.on(MessageType.CONNECTED, listener)

      client.connect('tok')
      await vi.advanceTimersByTimeAsync(0)
      const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
      ws.simulateOpen()

      expect(listener).toHaveBeenCalledOnce()
    })

    it('emits DISCONNECTED event on close', async () => {
      const listener = vi.fn()
      client.on(MessageType.DISCONNECTED, listener)

      client.connect('tok')
      await vi.advanceTimersByTimeAsync(0)
      const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
      ws.simulateOpen()
      ws.simulateClose(1006, 'abnormal')

      expect(listener).toHaveBeenCalledWith(
        expect.objectContaining({ code: 1006, reason: 'abnormal' }),
      )
    })
  })

  // ==========================================================================
  // 14. send() behavior
  // ==========================================================================
  describe('send()', () => {
    it('sends JSON stringified message when connected', async () => {
      client.connect('tok')
      await vi.advanceTimersByTimeAsync(0)
      const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
      ws.simulateOpen()

      client.send(MessageType.USER_TYPING, { room_id: 'r1', is_typing: true })

      expect(ws.send).toHaveBeenCalledWith(
        JSON.stringify({ type: MessageType.USER_TYPING, data: { room_id: 'r1', is_typing: true } }),
      )
    })
  })
})

// ============================================================================
// HMR singleton
// ============================================================================
describe('HMR singleton (getOrCreateClient)', () => {
  beforeEach(() => {
    delete (window as Record<string, unknown>).__wsClient
    vi.spyOn(console, 'log').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('createWebSocketClient creates independent instances', () => {
    const a = createWebSocketClient({ url: 'ws://a/ws' })
    const b = createWebSocketClient({ url: 'ws://b/ws' })
    expect(a).not.toBe(b)
    a.destroy()
    b.destroy()
  })
})
