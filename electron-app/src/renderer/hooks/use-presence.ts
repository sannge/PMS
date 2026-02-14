/**
 * usePresence Hook
 *
 * Manages real-time presence for task/room viewers.
 * Shows who else is viewing the same task with idle states.
 *
 * Features:
 * - Join/leave room tracking
 * - Heartbeat for presence updates
 * - Idle state detection
 * - Typing indicator support
 */

import { useEffect, useCallback, useState, useRef } from 'react'
import { useWebSocket } from './use-websocket'
import { useAuthStore } from '@/contexts/auth-context'

// ============================================================================
// Types
// ============================================================================

export interface PresenceUser {
  user_id: string
  user_name: string
  avatar_url: string | null
  idle: boolean
  joined_at: string
}

export interface UsePresenceOptions {
  roomId: string | null
  roomType: 'task' | 'project' | 'note'
  enabled?: boolean
  heartbeatInterval?: number
  idleTimeout?: number
}

export interface UsePresenceReturn {
  viewers: PresenceUser[]
  isTyping: Record<string, { user_name: string; expires_at: number }>
  sendTypingIndicator: () => void
  isConnected: boolean
}

// ============================================================================
// Constants
// ============================================================================

const DEFAULT_HEARTBEAT_INTERVAL = 30000 // 30 seconds
const DEFAULT_IDLE_TIMEOUT = 60000 // 1 minute
const TYPING_INDICATOR_TTL = 3000 // 3 seconds

// ============================================================================
// Hook
// ============================================================================

export function usePresence({
  roomId,
  roomType,
  enabled = true,
  heartbeatInterval = DEFAULT_HEARTBEAT_INTERVAL,
  idleTimeout = DEFAULT_IDLE_TIMEOUT,
}: UsePresenceOptions): UsePresenceReturn {
  const { send: sendMessage, status, subscribe } = useWebSocket()
  const user = useAuthStore((state) => state.user)

  const [viewers, setViewers] = useState<PresenceUser[]>([])
  const [isTyping, setIsTyping] = useState<Record<string, { user_name: string; expires_at: number }>>({})

  const lastActivityRef = useRef<number>(Date.now())
  const isIdleRef = useRef(false)
  const heartbeatIntervalRef = useRef<NodeJS.Timeout | null>(null)
  const typingTimeoutRef = useRef<NodeJS.Timeout | null>(null)

  // Build room ID
  const fullRoomId = roomId ? `${roomType}:${roomId}` : null

  // Store values in refs to avoid effect re-runs
  const sendMessageRef = useRef(sendMessage)
  const userRef = useRef(user)
  const idleTimeoutRef = useRef(idleTimeout)
  const heartbeatIntervalValueRef = useRef(heartbeatInterval)

  // Keep refs up to date
  useEffect(() => {
    sendMessageRef.current = sendMessage
    userRef.current = user
    idleTimeoutRef.current = idleTimeout
    heartbeatIntervalValueRef.current = heartbeatInterval
  })

  // Send typing indicator (stable reference)
  const sendTypingIndicator = useCallback(() => {
    if (!fullRoomId || !userRef.current) return

    sendMessageRef.current('typing_indicator', {
      room_id: fullRoomId,
      ttl_ms: TYPING_INDICATOR_TTL,
    })
  }, [fullRoomId])

  // Subscribe to WebSocket events - minimal dependencies
  useEffect(() => {
    if (!enabled || !fullRoomId || !status.isConnected) return

    const currentUser = userRef.current
    if (!currentUser) return

    // Send heartbeat function (defined inside effect to capture current fullRoomId)
    const sendHeartbeat = () => {
      if (!fullRoomId || !userRef.current) return

      const now = Date.now()
      const idle = now - lastActivityRef.current > idleTimeoutRef.current
      isIdleRef.current = idle

      sendMessageRef.current('presence_heartbeat', {
        room_id: fullRoomId,
        idle,
      })
    }

    // Track activity function
    const trackActivity = () => {
      lastActivityRef.current = Date.now()
      if (isIdleRef.current && fullRoomId) {
        isIdleRef.current = false
        sendMessageRef.current('presence_heartbeat', {
          room_id: fullRoomId,
          idle: false,
        })
      }
    }

    // Handle presence update
    const handlePresenceUpdate = (data: { room_id: string; users: PresenceUser[] }) => {
      if (data.room_id !== fullRoomId) return
      const otherUsers = data.users.filter((u) => u.user_id !== userRef.current?.id)
      setViewers(otherUsers)
    }

    // Handle typing indicator
    const handleTypingIndicator = (data: {
      room_id: string
      user_id: string
      user_name: string
      expires_at: number
    }) => {
      if (data.room_id !== fullRoomId || data.user_id === userRef.current?.id) return

      setIsTyping((prev) => ({
        ...prev,
        [data.user_id]: {
          user_name: data.user_name,
          expires_at: data.expires_at,
        },
      }))

      setTimeout(() => {
        setIsTyping((prev) => {
          const { [data.user_id]: _, ...rest } = prev
          return rest
        })
      }, TYPING_INDICATOR_TTL)
    }

    // Subscribe to presence events
    const unsubPresence = subscribe('presence_update', handlePresenceUpdate)
    const unsubTyping = subscribe('typing_indicator', handleTypingIndicator)

    // Join room
    sendMessageRef.current('join_room', { room_id: fullRoomId })

    // Start heartbeat
    sendHeartbeat()
    heartbeatIntervalRef.current = setInterval(sendHeartbeat, heartbeatIntervalValueRef.current)

    // Track activity
    window.addEventListener('mousemove', trackActivity)
    window.addEventListener('keydown', trackActivity)
    window.addEventListener('click', trackActivity)

    return () => {
      // Leave room
      sendMessageRef.current('leave_room', { room_id: fullRoomId })

      // Stop heartbeat
      if (heartbeatIntervalRef.current) {
        clearInterval(heartbeatIntervalRef.current)
        heartbeatIntervalRef.current = null
      }

      setViewers([])
      unsubPresence()
      unsubTyping()
      window.removeEventListener('mousemove', trackActivity)
      window.removeEventListener('keydown', trackActivity)
      window.removeEventListener('click', trackActivity)
    }
  }, [enabled, fullRoomId, status.isConnected, subscribe])

  // Clean up on unmount
  useEffect(() => {
    return () => {
      if (heartbeatIntervalRef.current) {
        clearInterval(heartbeatIntervalRef.current)
      }
      if (typingTimeoutRef.current) {
        clearTimeout(typingTimeoutRef.current)
      }
    }
  }, [])

  return {
    viewers,
    isTyping,
    sendTypingIndicator,
    isConnected: status.isConnected,
  }
}

export default usePresence
