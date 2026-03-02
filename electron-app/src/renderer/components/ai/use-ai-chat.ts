/**
 * AI Chat Hook
 *
 * Custom hook for streaming chat with the Blair AI backend.
 * Uses fetch + ReadableStream for SSE (POST-based, not EventSource).
 * Handles text deltas, tool call lifecycle, interrupts, and errors.
 */

import { useCallback, useEffect, useRef } from 'react'
import { useAuthToken, getAuthHeaders } from '@/contexts/auth-context'
import { useAiSidebar } from './use-ai-sidebar'
import type { ChatMessage, ChatStreamEvent, ToolCallInfo } from './types'

// ============================================================================
// Helpers
// ============================================================================

function getApiBaseUrl(): string {
  return import.meta.env.VITE_API_URL || 'http://localhost:8001'
}

function generateId(): string {
  return crypto.randomUUID()
}

/**
 * Valid SSE event types emitted by the Blair AI backend.
 * Reject unknown event types for safety.
 */
const VALID_SSE_EVENTS = new Set([
  'text_delta', 'tool_call_start', 'tool_call_end',
  'run_started', 'run_finished', 'interrupt', 'error', 'end',
])

/**
 * Parse an SSE text chunk into individual events.
 * SSE format: "event: <type>\ndata: <json>\n\n"
 * Per SSE spec, multiple data: lines are concatenated with \n.
 */
function parseSSEChunk(chunk: string): ChatStreamEvent[] {
  const events: ChatStreamEvent[] = []
  const blocks = chunk.split('\n\n')

  for (const block of blocks) {
    const trimmed = block.trim()
    if (!trimmed) continue

    let eventType = ''
    const dataLines: string[] = []

    for (const line of trimmed.split('\n')) {
      if (line.startsWith('event: ')) {
        eventType = line.slice(7).trim()
      } else if (line.startsWith('data: ')) {
        dataLines.push(line.slice(6))
      }
    }

    const dataStr = dataLines.join('\n')
    if (!eventType || !dataStr) continue

    // Reject unknown event types
    if (!VALID_SSE_EVENTS.has(eventType)) continue

    try {
      const data = JSON.parse(dataStr)
      events.push({ event: eventType, data } as ChatStreamEvent)
    } catch {
      console.warn('[useAiChat] Failed to parse SSE data:', dataStr)
    }
  }

  return events
}

// ============================================================================
// Shared SSE Stream Processor
// ============================================================================

/**
 * Process an SSE stream from a fetch Response, dispatching events via callbacks.
 * Shared between sendMessage and sendReplayMessage to eliminate duplication.
 * Handles read loop, timeout, event dispatch, and remaining-buffer processing.
 */
async function processSSEStream(
  res: Response,
  controller: AbortController,
  callbacks: {
    updateLastAssistantMessage: (partial: Partial<ChatMessage>) => void
    setThreadId: (id: string) => void
    setIsStreaming: (val: boolean) => void
  }
): Promise<void> {
  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let contentAccum = ''
  const toolCalls = new Map<string, ToolCallInfo>()
  let buffer = ''
  let timeoutId: ReturnType<typeof setTimeout> | null = null

  // F9: Timeout if no events received for 60 seconds
  const SSE_TIMEOUT_MS = 60_000
  const resetTimeout = () => {
    if (timeoutId) clearTimeout(timeoutId)
    timeoutId = setTimeout(() => {
      callbacks.updateLastAssistantMessage({
        content: contentAccum + '\n\n[Response timed out. Please try again.]',
        isError: true,
      })
      controller.abort()
    }, SSE_TIMEOUT_MS)
  }

  const processEvents = (events: ChatStreamEvent[]) => {
    for (const evt of events) {
      switch (evt.event) {
        case 'text_delta':
          if (evt.data.content) {
            contentAccum += evt.data.content
            callbacks.updateLastAssistantMessage({ content: contentAccum })
          }
          break

        case 'tool_call_start':
          toolCalls.set(evt.data.id, {
            id: evt.data.id,
            name: evt.data.name,
            status: 'running',
          })
          callbacks.updateLastAssistantMessage({
            tool_calls: Array.from(toolCalls.values()),
          })
          break

        case 'tool_call_end': {
          const existing = toolCalls.get(evt.data.id)
          toolCalls.set(evt.data.id, {
            ...existing,
            id: evt.data.id,
            name: evt.data.name,
            status: evt.data.error ? 'error' : 'complete',
            summary: evt.data.summary,
            details: evt.data.details,
            error: evt.data.error,
          })
          callbacks.updateLastAssistantMessage({
            tool_calls: Array.from(toolCalls.values()),
          })
          break
        }

        case 'run_started':
          callbacks.setThreadId(evt.data.thread_id)
          break

        case 'interrupt':
          callbacks.updateLastAssistantMessage({
            interrupted: true,
            interrupt_payload: evt.data,
          })
          break

        case 'run_finished':
          callbacks.updateLastAssistantMessage({
            checkpoint_id: evt.data.checkpoint_id,
            sources: evt.data.sources,
            interrupted: evt.data.interrupted,
            interrupt_payload: evt.data.interrupt_payload,
          })
          break

        case 'error':
          callbacks.updateLastAssistantMessage({
            content: contentAccum || `Error: ${evt.data.message}`,
            isError: true,
          })
          break

        case 'end':
          // Stream complete
          break
      }
    }
  }

  try {
    resetTimeout()

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      resetTimeout()
      // Normalize \r\n → \n (sse_starlette uses \r\n line endings)
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')

      // Only parse complete SSE blocks (terminated by double newline)
      const lastDoubleNewline = buffer.lastIndexOf('\n\n')
      if (lastDoubleNewline === -1) continue

      const completePart = buffer.slice(0, lastDoubleNewline + 2)
      buffer = buffer.slice(lastDoubleNewline + 2)

      processEvents(parseSSEChunk(completePart))
    }

    // Process any remaining buffer (handles ALL event types, not just text_delta)
    if (buffer.trim()) {
      processEvents(parseSSEChunk(buffer))
    }
  } finally {
    if (timeoutId) clearTimeout(timeoutId)
  }
}

// ============================================================================
// Hook
// ============================================================================

export function useAiChat() {
  const token = useAuthToken()
  const {
    threadId,
    addMessage,
    updateLastAssistantMessage,
    setThreadId,
    setIsStreaming,
  } = useAiSidebar()

  const abortRef = useRef<AbortController | null>(null)

  // Abort any in-flight stream when the hook unmounts (e.g. sidebar closes)
  useEffect(() => {
    return () => {
      abortRef.current?.abort()
    }
  }, [])

  const sendMessage = useCallback(
    async (text: string, images?: { data: string; mediaType: string; filename?: string }[], applicationId?: string) => {
      // Abort any in-flight stream
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller

      // Capture conversation history BEFORE adding new messages to the store.
      // Backend caps at 50 entries; send most recent to stay within limit.
      const priorMessages = useAiSidebar.getState().messages
      const conversationHistory = priorMessages
        .filter((m) => m.content)
        .map((m) => ({ role: m.role, content: m.content }))
        .slice(-50)

      // Add user message to store
      const userMsg: ChatMessage = {
        id: generateId(),
        role: 'user',
        content: text,
        images: images?.map((img) => ({
          id: generateId(),
          data: img.data,
          mediaType: img.mediaType,
          filename: img.filename,
          previewUrl: `data:${img.mediaType};base64,${img.data}`,
        })),
        timestamp: Date.now(),
      }
      addMessage(userMsg)

      // Add placeholder assistant message
      const assistantMsg: ChatMessage = {
        id: generateId(),
        role: 'assistant',
        content: '',
        tool_calls: [],
        sources: [],
        timestamp: Date.now(),
      }
      addMessage(assistantMsg)
      setIsStreaming(true)

      try {
        const baseUrl = getApiBaseUrl()
        const body: Record<string, unknown> = { message: text }
        if (threadId) body.thread_id = threadId
        if (applicationId) body.application_id = applicationId
        if (conversationHistory.length > 0) body.conversation_history = conversationHistory
        if (images?.length) {
          body.images = images.map((img) => ({
            data: img.data,
            media_type: img.mediaType,
            filename: img.filename,
          }))
        }

        const res = await fetch(`${baseUrl}/api/ai/chat/stream`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...getAuthHeaders(token),
          },
          body: JSON.stringify(body),
          signal: controller.signal,
        })

        if (!res.ok) {
          const errText = await res.text().catch(() => 'Unknown error')
          updateLastAssistantMessage({
            content: `Error: ${res.status} - ${errText}`,
            isError: true,
          })
          setIsStreaming(false)
          return
        }

        if (!res.body) {
          updateLastAssistantMessage({ content: 'Error: No response body', isError: true })
          setIsStreaming(false)
          return
        }

        await processSSEStream(res, controller, {
          updateLastAssistantMessage,
          setThreadId,
          setIsStreaming,
        })
      } catch (err) {
        if ((err as Error).name === 'AbortError') return
        console.error('[useAiChat] Stream error:', err)
        updateLastAssistantMessage({
          content: `Error: ${(err as Error).message || 'Connection failed'}`,
          isError: true,
        })
      } finally {
        setIsStreaming(false)
        abortRef.current = null
      }
    },
    [token, threadId, addMessage, updateLastAssistantMessage, setThreadId, setIsStreaming]
  )

  const resumeInterrupt = useCallback(
    async (tid: string, response: Record<string, unknown>) => {
      try {
        const baseUrl = getApiBaseUrl()
        const res = await fetch(`${baseUrl}/api/ai/chat/resume`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...getAuthHeaders(token),
          },
          body: JSON.stringify({ thread_id: tid, response }),
        })

        if (!res.ok) {
          const errText = await res.text().catch(() => 'Unknown error')
          throw new Error(`${res.status}: ${errText}`)
        }

        return await res.json()
      } catch (err) {
        console.error('[useAiChat] Resume error:', err)
        throw err
      }
    },
    [token]
  )

  const sendReplayMessage = useCallback(
    async (text: string, checkpointId: string) => {
      // Abort any in-flight stream
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller

      // Add user message to store
      const userMsg: ChatMessage = {
        id: generateId(),
        role: 'user',
        content: text,
        timestamp: Date.now(),
      }
      addMessage(userMsg)

      // Add placeholder assistant message
      const assistantMsg: ChatMessage = {
        id: generateId(),
        role: 'assistant',
        content: '',
        tool_calls: [],
        sources: [],
        timestamp: Date.now(),
      }
      addMessage(assistantMsg)
      setIsStreaming(true)

      try {
        const baseUrl = getApiBaseUrl()
        const body: Record<string, unknown> = {
          message: text,
          thread_id: threadId,
          checkpoint_id: checkpointId,
        }

        const res = await fetch(`${baseUrl}/api/ai/chat/replay`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...getAuthHeaders(token),
          },
          body: JSON.stringify(body),
          signal: controller.signal,
        })

        if (!res.ok) {
          const errText = await res.text().catch(() => 'Unknown error')
          updateLastAssistantMessage({
            content: `Error: ${res.status} - ${errText}`,
            isError: true,
          })
          setIsStreaming(false)
          return
        }

        if (!res.body) {
          updateLastAssistantMessage({ content: 'Error: No response body', isError: true })
          setIsStreaming(false)
          return
        }

        await processSSEStream(res, controller, {
          updateLastAssistantMessage,
          setThreadId,
          setIsStreaming,
        })
      } catch (err) {
        if ((err as Error).name === 'AbortError') return
        console.error('[useAiChat] Replay stream error:', err)
        updateLastAssistantMessage({
          content: `Error: ${(err as Error).message || 'Connection failed'}`,
          isError: true,
        })
      } finally {
        setIsStreaming(false)
        abortRef.current = null
      }
    },
    [token, threadId, addMessage, updateLastAssistantMessage, setThreadId, setIsStreaming]
  )

  const cancelStream = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setIsStreaming(false)
  }, [setIsStreaming])

  return { sendMessage, sendReplayMessage, resumeInterrupt, cancelStream }
}
