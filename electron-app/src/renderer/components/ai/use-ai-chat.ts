/**
 * AI Chat Hook
 *
 * Custom hook for streaming chat with the Blair AI backend.
 * Uses fetch + ReadableStream for SSE (POST-based, not EventSource).
 * Handles text deltas, unified activity timeline (thinking steps + tool calls),
 * interrupts, and errors.
 */

import { useCallback, useEffect, useRef } from 'react'
import { getAccessToken, refreshTokens } from '@/lib/api-client'
import { useAiSidebar } from './use-ai-sidebar'
import { authPost } from '@/lib/api-client'
import queryClient, { queryKeys } from '@/lib/query-client'
import type { ActivityItem, ChatMessage, ChatStreamEvent, StoredImage, TokenUsage } from './types'

// ============================================================================
// Helpers
// ============================================================================

function getApiBaseUrl(): string {
  return import.meta.env.VITE_API_URL || 'http://localhost:8001'
}

function generateId(): string {
  return crypto.randomUUID()
}

/** Max width for preview thumbnails stored in chat history (keeps memory small). */
const THUMBNAIL_MAX_WIDTH = 200

/** Max width for lightbox images (medium resolution for expanded view). */
const LIGHTBOX_MAX_WIDTH = 1200

/**
 * Shared image resize helper. Decodes a base64 image, scales it to
 * `maxWidth` (keeping aspect ratio), and returns a data URL at the
 * given JPEG quality.  Returns `fallback` on decode failure.
 *
 * Extracted from createThumbnailDataUrl / createLightboxDataUrl
 * which were ~50 lines of near-identical logic.
 */
async function _resizeImageToDataUrl(
  base64Data: string,
  mediaType: string,
  maxWidth: number,
  quality: number,
): Promise<string | undefined> {
  const fullDataUrl = `data:${mediaType};base64,${base64Data}`
  const img = new Image()
  await new Promise<void>((resolve, reject) => {
    img.onload = () => resolve()
    img.onerror = () => reject(new Error('Image decode failed'))
    img.src = fullDataUrl
  })

  // If image is already within maxWidth, return as-is
  if (img.naturalWidth <= maxWidth) {
    return fullDataUrl
  }

  const scale = maxWidth / img.naturalWidth
  const w = Math.round(img.naturalWidth * scale)
  const h = Math.round(img.naturalHeight * scale)

  const canvas = document.createElement('canvas')
  canvas.width = w
  canvas.height = h
  const ctx = canvas.getContext('2d')
  if (!ctx) return fullDataUrl
  ctx.drawImage(img, 0, 0, w, h)
  return canvas.toDataURL('image/jpeg', quality)
}

/** Transparent 1x1 PNG used as fallback when thumbnail decode fails. */
const FALLBACK_THUMBNAIL =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVQI12NgAAIABQABNjN9GQAAAAlwSFlzAAAWJQAAFiUBSVIk8AAAAA0lEQVQI12P4z8BQDwAEgAF/QualrQAAAABJRU5ErkJggg=='

/**
 * Generate a small thumbnail data URL from a full base64 image.
 * JPEG at 70% quality (~2-5 KB instead of ~5 MB).
 */
async function createThumbnailDataUrl(
  base64Data: string,
  mediaType: string,
): Promise<string> {
  try {
    return (await _resizeImageToDataUrl(base64Data, mediaType, THUMBNAIL_MAX_WIDTH, 0.7)) ?? FALLBACK_THUMBNAIL
  } catch {
    return FALLBACK_THUMBNAIL
  }
}

/**
 * Generate a medium-res lightbox data URL from a full base64 image.
 * JPEG at 85% quality (~50-200KB per image).
 */
async function createLightboxDataUrl(
  base64Data: string,
  mediaType: string,
): Promise<string | undefined> {
  try {
    return await _resizeImageToDataUrl(base64Data, mediaType, LIGHTBOX_MAX_WIDTH, 0.85)
  } catch {
    return undefined
  }
}

/**
 * Valid SSE event types emitted by the Blair AI backend.
 * Reject unknown event types for safety.
 */
const VALID_SSE_EVENTS = new Set([
  'text_delta', 'tool_call_start', 'tool_call_end',
  'run_started', 'run_finished', 'interrupt', 'thinking_step', 'error', 'end',
  'token_usage', 'context_summary', 'phase_changed',
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

/** Cap activity items to prevent unbounded memory growth */
const MAX_ACTIVITY_ITEMS = 100

/**
 * FIFO eviction for activity items: remove the oldest completed/error item
 * to make room for new ones. Only drops items that are finished (complete,
 * error, or node-complete). If all items are still running, does nothing
 * (which shouldn't happen in practice — 100 concurrent running items).
 */
function evictOldestCompleted(map: Map<string, ActivityItem>): void {
  for (const [key, item] of map) {
    const isFinished =
      (item.type === 'tool' && (item.status === 'complete' || item.status === 'error')) ||
      (item.type === 'node' && item.status === 'complete')
    if (isFinished) {
      map.delete(key)
      return
    }
  }
}

/**
 * Process an SSE stream from a fetch Response, dispatching events via callbacks.
 * Shared between sendMessage, sendReplayMessage, and resumeInterrupt.
 * Handles read loop, timeout, event dispatch, and remaining-buffer processing.
 *
 * Uses a unified activity timeline that merges thinking_step (pipeline nodes)
 * and tool_call_start/end events into a single chronological list.
 */
/** Max SSE buffer size (1 MB) to prevent unbounded growth from malformed events */
const MAX_BUFFER_SIZE = 1_048_576

async function processSSEStream(
  res: Response,
  controller: AbortController,
  callbacks: {
    updateLastAssistantMessage: (partial: Partial<ChatMessage>) => void
    setThreadId: (id: string) => void
    setIsStreaming: (val: boolean) => void
    setTokenUsage?: (usage: TokenUsage) => void
    setActiveSessionId?: (id: string) => void
    onContextSummary?: (summary: string, upToSequence: number) => void
    onRunFinished?: (sessionId: string) => void
  }
): Promise<void> {
  const reader = res.body!.getReader()
  const decoder = new TextDecoder()
  let contentAccum = ''
  // Use a Map for in-flight activity tracking to avoid O(n) array
  // spreads on every tool_call_start/end event. Convert to array only on flush.
  const activityMap = new Map<string, ActivityItem>()
  let buffer = ''
  let timeoutId: ReturnType<typeof setTimeout> | null = null
  let receivedRunFinished = false
  let receivedError = false
  let receivedSessionId = ''

  // Batch flags — accumulate changes per chunk, flush once
  let contentDirty = false
  let activityDirty = false
  // Monotonic counter incremented on every activityMap mutation.
  // flushBatch only creates a new array when the version has advanced,
  // which correctly detects mid-list updates (e.g. a non-last tool
  // transitioning from running → complete) that the old size+last-item
  // heuristic silently dropped.
  let activityVersion = 0
  let lastFlushedVersion = 0

  // Timeout if no events received for 60 seconds
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
            contentDirty = true
          }
          break

        case 'thinking_step': {
          // Ensure type:'node' is present (backend includes it, but be defensive)
          const step: ActivityItem = { type: 'node' as const, ...evt.data }
          // Upsert by node name; Map gives O(1) lookup instead of findIndex
          const nodeKey = `node:${step.node}`
          if (!activityMap.has(nodeKey) && activityMap.size >= MAX_ACTIVITY_ITEMS) {
            evictOldestCompleted(activityMap)
          }
          if (activityMap.has(nodeKey) || activityMap.size < MAX_ACTIVITY_ITEMS) {
            activityMap.set(nodeKey, step)
            activityDirty = true
            activityVersion++
          }
          break
        }

        case 'tool_call_start': {
          const toolKey = `tool:${evt.data.id}`
          if (!activityMap.has(toolKey) && activityMap.size >= MAX_ACTIVITY_ITEMS) {
            evictOldestCompleted(activityMap)
          }
          if (activityMap.has(toolKey) || activityMap.size < MAX_ACTIVITY_ITEMS) {
            activityMap.set(toolKey, {
              type: 'tool' as const,
              id: evt.data.id,
              name: evt.data.name,
              status: 'running' as const,
            })
            activityDirty = true
            activityVersion++
          }
          break
        }

        case 'tool_call_end': {
          const toolKey = `tool:${evt.data.id}`
          if (activityMap.has(toolKey)) {
            activityMap.set(toolKey, {
              type: 'tool' as const,
              id: evt.data.id,
              name: evt.data.name,
              status: evt.data.error ? 'error' as const : 'complete' as const,
              summary: evt.data.summary,
              details: evt.data.details,
              error: evt.data.error,
            })
            activityDirty = true
            activityVersion++
          }
          break
        }

        case 'token_usage': {
          const usage: TokenUsage = {
            inputTokens: evt.data.input_tokens,
            outputTokens: evt.data.output_tokens,
            totalTokens: evt.data.total_tokens,
            contextLimit: evt.data.context_limit,
          }
          callbacks.setTokenUsage?.(usage)
          break
        }

        case 'context_summary': {
          callbacks.onContextSummary?.(evt.data.summary, evt.data.up_to_sequence)
          break
        }

        case 'phase_changed': {
          // Update current_phase on the assistant message for the phase
          // indicator text. Do NOT add an activity item — the thinking_step
          // event already handles the timeline entry (adding one here with
          // a different key caused every step to render twice).
          callbacks.updateLastAssistantMessage({
            current_phase: evt.data.phase,
          })
          break
        }

        case 'run_started':
          callbacks.setThreadId(evt.data.thread_id)
          if (evt.data.session_id) callbacks.setActiveSessionId?.(evt.data.session_id)
          break

        case 'interrupt':
          callbacks.updateLastAssistantMessage({
            interrupted: true,
            interrupt_payload: evt.data,
          })
          break

        case 'run_finished':
          receivedRunFinished = true
          if (evt.data.session_id) receivedSessionId = evt.data.session_id
          callbacks.updateLastAssistantMessage({
            checkpoint_id: evt.data.checkpoint_id,
            sources: evt.data.sources,
            // Only set interrupted/interrupt_payload if explicitly present
            // to avoid overwriting values set by an earlier 'interrupt' event
            ...(evt.data.interrupted != null && { interrupted: evt.data.interrupted }),
            ...(evt.data.interrupt_payload != null && { interrupt_payload: evt.data.interrupt_payload }),
          })
          break

        case 'error':
          receivedError = true
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

  /** FE-004: Flush batched content/activity updates once per chunk */
  const flushBatch = () => {
    const partial: Partial<ChatMessage> = {}
    if (contentDirty) {
      partial.content = contentAccum
      contentDirty = false
    }
    if (activityDirty && activityVersion !== lastFlushedVersion) {
      partial.activity = Array.from(activityMap.values())
      lastFlushedVersion = activityVersion
      activityDirty = false
    }
    if (Object.keys(partial).length > 0) {
      callbacks.updateLastAssistantMessage(partial)
    }
  }

  /** Rate-limit flushBatch to at most once per animation frame */
  let rafId: number | null = null
  function scheduleFlush() {
    if (rafId !== null) return
    rafId = requestAnimationFrame(() => {
      rafId = null
      flushBatch()
    })
  }

  try {
    resetTimeout()

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      resetTimeout()
      const decoded = decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')

      // Check buffer size BEFORE appending to catch malformed
      // events that never terminate with double-newline. If the buffer already
      // exceeds MAX_BUFFER_SIZE, try to salvage complete events first.
      if (buffer.length + decoded.length > MAX_BUFFER_SIZE) {
        // Try to process any complete events already in the buffer
        const lastComplete = buffer.lastIndexOf('\n\n')
        if (lastComplete > 0) {
          const processable = buffer.substring(0, lastComplete + 2)
          buffer = buffer.substring(lastComplete + 2)
          processEvents(parseSSEChunk(processable))
          scheduleFlush()
        }
        // If buffer is still too large even after processing, clear it
        if (buffer.length + decoded.length > MAX_BUFFER_SIZE) {
          console.warn('[useAiChat] SSE buffer exceeded 1MB, clearing malformed data')
          buffer = ''
          // Emit error to the stream handler so the user is notified
          processEvents([{ event: 'error', data: { message: 'Response data exceeded buffer limit' } } as ChatStreamEvent])
          scheduleFlush()
          // After clearing, we discard the current decoded chunk as stream state
          // is now undefined. The error event has already notified the user.
          continue
        }
      }

      buffer += decoded

      // Only parse complete SSE blocks (terminated by double newline)
      const lastDoubleNewline = buffer.lastIndexOf('\n\n')
      if (lastDoubleNewline === -1) continue

      const completePart = buffer.slice(0, lastDoubleNewline + 2)
      buffer = buffer.slice(lastDoubleNewline + 2)

      processEvents(parseSSEChunk(completePart))
      scheduleFlush()
    }

    // Process any remaining buffer (handles ALL event types, not just text_delta)
    if (buffer.trim()) {
      processEvents(parseSSEChunk(buffer))
      flushBatch()
    }

    // If stream completed without content, run_finished, or error event, treat as connection lost
    if (!contentAccum && !receivedRunFinished && !receivedError) {
      callbacks.updateLastAssistantMessage({
        content: 'Connection lost. Please try again.',
        isError: true,
      })
    }

    // Trigger message persistence after stream completes
    if (receivedSessionId) {
      callbacks.onRunFinished?.(receivedSessionId)
    }
  } finally {
    if (timeoutId) clearTimeout(timeoutId)
    if (rafId !== null) { cancelAnimationFrame(rafId); rafId = null }
    try { await reader.cancel(); } catch { /* already closed */ }
  }
}

// ============================================================================
// SSE Fetch with 401 Retry
// ============================================================================

/**
 * Build auth headers using the freshest token from api-client module state.
 * Avoids stale closure over React state's `token`.
 */
function sseAuthHeaders(): Record<string, string> {
  const token = getAccessToken()
  if (!token) return {}
  return { Authorization: `Bearer ${token}` }
}

/** Max retries for transient (5xx / network) failures */
const SSE_MAX_RETRIES = 2
/** Base delay in ms for exponential backoff: 1s, 2s, 4s, ... */
const SSE_RETRY_BASE_MS = 1000

/**
 * Sleep that races against an AbortSignal — resolves early if aborted.
 * Returns true if aborted, false if the delay elapsed normally.
 */
function abortableSleep(ms: number, signal?: AbortSignal | null): Promise<boolean> {
  if (signal?.aborted) return Promise.resolve(true)
  return new Promise(resolve => {
    const timer = setTimeout(() => { cleanup(); resolve(false) }, ms)
    const onAbort = () => { clearTimeout(timer); cleanup(); resolve(true) }
    const cleanup = () => signal?.removeEventListener('abort', onAbort)
    signal?.addEventListener('abort', onAbort)
  })
}

/**
 * Fetch an SSE endpoint with automatic 401 retry and exponential backoff
 * for transient failures (5xx, network errors).
 * - 401: refresh token and retry once (no delay)
 * - 5xx / network error: retry up to SSE_MAX_RETRIES with exponential backoff
 * - Other 4xx: no retry
 */
async function sseFetchWithRetry(
  url: string,
  init: RequestInit,
): Promise<Response> {
  const signal = init.signal as AbortSignal | undefined
  const doFetch = (headers: Record<string, string>) =>
    fetch(url, { ...init, headers: { ...(init.headers as Record<string, string>), ...headers } })

  let lastError: unknown
  let authRetries = 0
  for (let attempt = 0; attempt <= SSE_MAX_RETRIES; attempt++) {
    // Bail out early if already aborted (avoids stalling during backoff)
    if (signal?.aborted) throw new DOMException('The operation was aborted.', 'AbortError')

    try {
      const res = await doFetch(sseAuthHeaders())

      // 401: refresh token and retry once (no backoff).
      // Continue loop so the refreshed token goes through sseAuthHeaders()
      // and gets full exponential backoff retry coverage on subsequent failures.
      if (res.status === 401) {
        if (authRetries >= 1) {
          throw new Error('Authentication failed. Please sign in again.')
        }
        authRetries++
        let newToken: string | null = null
        try {
          newToken = await refreshTokens()
        } catch {
          throw new Error('Authentication failed. Please sign in again.')
        }
        if (newToken) continue
        throw new Error('Authentication failed. Please sign in again.')
      }

      // 5xx: retryable — exponential backoff and try again
      if (res.status >= 500 && attempt < SSE_MAX_RETRIES) {
        const aborted = await abortableSleep(SSE_RETRY_BASE_MS * 2 ** attempt, signal)
        if (aborted) throw new DOMException('The operation was aborted.', 'AbortError')
        continue
      }

      // 2xx, 3xx, other 4xx: return as-is
      return res
    } catch (err) {
      // Non-retryable errors: abort and auth failures
      if ((err as Error).name === 'AbortError') throw err
      if ((err as Error).message?.includes('Authentication failed')) throw err
      // Network error: retryable
      lastError = err
      if (attempt < SSE_MAX_RETRIES) {
        const aborted = await abortableSleep(SSE_RETRY_BASE_MS * 2 ** attempt, signal)
        if (aborted) throw new DOMException('The operation was aborted.', 'AbortError')
        continue
      }
    }
  }

  // All retries exhausted — rethrow the last network error
  throw lastError
}

// ============================================================================
// Hook
// ============================================================================

export function useAiChat() {
  const addMessage = useAiSidebar(s => s.addMessage)
  const updateMessage = useAiSidebar(s => s.updateMessage)
  const updateLastAssistantMessage = useAiSidebar(s => s.updateLastAssistantMessage)
  const setThreadId = useAiSidebar(s => s.setThreadId)
  const setIsStreaming = useAiSidebar(s => s.setIsStreaming)

  const abortRef = useRef<AbortController | null>(null)

  // Abort any in-flight stream when the hook unmounts (e.g. sidebar closes)
  useEffect(() => {
    return () => {
      abortRef.current?.abort()
    }
  }, [])

  /**
   * Shared streaming lifecycle used by sendMessage, resumeInterrupt,
   * and sendReplayMessage. Handles abort controller setup, placeholder
   * assistant message, sseFetchWithRetry, error handling, processSSEStream,
   * and the finally block.
   */
  const _runStream = useCallback(
    async (
      url: string,
      body: Record<string, unknown>,
      opts?: {
        addUserMessage?: { content: string; images?: ChatMessage['images'] }
      },
    ) => {
      // Abort any in-flight stream
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller

      // Optionally add user message first
      if (opts?.addUserMessage) {
        const userMsg: ChatMessage = {
          id: generateId(),
          role: 'user',
          content: opts.addUserMessage.content,
          images: opts.addUserMessage.images,
          timestamp: Date.now(),
        }
        addMessage(userMsg)

        // Immediately strip base64 from stored message to free memory.
        // The fetch body uses the original images, not the stored message.
        if (userMsg.images?.length) {
          updateMessage(userMsg.id, (msg) => ({
            ...msg,
            images: msg.images?.map((img) => {
              const stored: StoredImage = {
                id: img.id,
                mediaType: img.mediaType,
                filename: img.filename,
                previewUrl: img.previewUrl,
                data: undefined,
                lightboxUrl: 'lightboxUrl' in img ? (img as StoredImage).lightboxUrl : undefined,
              }
              return stored
            }),
          }))
        }
      }

      // Add placeholder assistant message
      const assistantMsg: ChatMessage = {
        id: generateId(),
        role: 'assistant',
        content: '',
        activity: [],
        sources: [],
        timestamp: Date.now(),
      }
      addMessage(assistantMsg)
      setIsStreaming(true)

      try {
        const res = await sseFetchWithRetry(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
          signal: controller.signal,
        })

        if (!res.ok) {
          const errText = await res.text().catch(() => 'Unknown error')
          let userMessage: string
          if (res.status === 503) {
            userMessage = 'Blair is temporarily unavailable. Please try again in a moment.'
          } else if (res.status === 429) {
            userMessage = 'Rate limit reached. Please wait a moment before sending another message.'
          } else {
            userMessage = `Error: ${res.status} - ${errText}`
          }
          updateLastAssistantMessage({
            content: userMessage,
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
          setTokenUsage: useAiSidebar.getState().setTokenUsage,
          onContextSummary: (summary: string, upToSequence: number) => {
            useAiSidebar.getState().setContextSummary(summary, upToSequence)
          },
          setActiveSessionId: (id: string) => {
            const s = useAiSidebar.getState()
            if (!s.activeSessionId) {
              // Link session without clearing in-flight messages
              s.linkSession(id)
            }
            s.setView('chat')
          },
          onRunFinished: (sessionId: string) => {
            if (!sessionId) return
            // Guard: prevent stale SSE from wrong session after rapid switch
            const currentSessionId = useAiSidebar.getState().activeSessionId
            if (currentSessionId && sessionId !== currentSessionId) return

            const st = useAiSidebar.getState()
            const msgs = st.messages
            const lastAssistant = msgs[msgs.length - 1]
            const lastUser = msgs.length >= 2 ? msgs[msgs.length - 2] : null
            const toPersist: Array<{ role: string; content: string; sources?: unknown; checkpoint_id?: string; is_error?: boolean }> = []
            if (lastUser?.role === 'user') toPersist.push({ role: 'user', content: lastUser.content })
            if (lastAssistant?.role === 'assistant') toPersist.push({
              role: 'assistant',
              content: lastAssistant.content,
              sources: lastAssistant.sources,
              checkpoint_id: lastAssistant.checkpoint_id,
              is_error: lastAssistant.isError ?? false,
            })
            if (!toPersist.length) return

            // Persist with retry — bail out if the user switches sessions mid-retry
            const capturedSessionId = sessionId
            // Returns true if user switched sessions OR started a new chat (activeSessionId becomes null).
            // In both cases, silently cancelling the persist is correct — the message belongs to
            // the old session which will be loaded from the server when the user navigates back.
            const isSessionStale = () => useAiSidebar.getState().activeSessionId !== capturedSessionId
            const persistWithRetry = async (retries = 2): Promise<{ next_sequence?: number } | null> => {
              for (let attempt = 0; attempt <= retries; attempt++) {
                // Cancel stale retry chain if user switched to a different session
                if (isSessionStale()) return null
                try {
                  const res = await authPost(`/api/ai/sessions/${capturedSessionId}/messages`, { messages: toPersist })
                  return res.data as { next_sequence?: number } | null
                } catch {
                  if (attempt === retries) {
                    // Check staleness before throwing — avoids spurious warning on wrong session
                    if (isSessionStale()) return null
                    throw new Error('persist failed')
                  }
                  await new Promise((r) => setTimeout(r, 1000 * (attempt + 1)))
                  // Re-check after sleep — user may have switched sessions during delay
                  if (isSessionStale()) return null
                }
              }
              // Unreachable: loop always returns or throws on final iteration
              throw new Error('persist failed')
            }

            persistWithRetry()
              .then((data) => {
                const nextSeq = data?.next_sequence
                if (nextSeq) {
                  useAiSidebar.getState().setLastPersistedSequence(nextSeq)
                }
                // Invalidate session list after persist succeeds so the new session appears
                queryClient.invalidateQueries({ queryKey: queryKeys.chatSessions })
                // Invalidate cached messages for this session — the cache may hold
                // a stale empty result from the fetch that raced with streaming.
                // Use invalidateQueries (not removeQueries) to revalidate in the
                // background without evicting data the user may be viewing.
                queryClient.invalidateQueries({ queryKey: queryKeys.chatMessages(capturedSessionId) })
                // Delayed re-invalidation picks up LLM-generated title from worker job
                setTimeout(() => {
                  queryClient.invalidateQueries({ queryKey: queryKeys.chatSessions })
                }, 3000)
                // Auto-summarize after persist (using real DB sequence)
                const sidebar = useAiSidebar.getState()
                if (
                  sidebar.tokenUsage &&
                  sidebar.tokenUsage.totalTokens > sidebar.tokenUsage.contextLimit * 0.9 &&
                  !sidebar.contextSummary &&
                  nextSeq
                ) {
                  authPost(`/api/ai/sessions/${capturedSessionId}/summarize`, {
                    up_to_sequence: nextSeq - 1,
                  })
                    .then((sumRes) => {
                      const sumData = sumRes.data as { summary?: string } | null
                      if (sumData?.summary) {
                        useAiSidebar.getState().setContextSummary(sumData.summary, nextSeq - 1)
                      }
                    })
                    .catch(() => {}) // OK to swallow summarize errors
                }
              })
              .catch(() => {
                // Surface persist failure to user
                const sidebar = useAiSidebar.getState()
                const last = sidebar.messages[sidebar.messages.length - 1]
                if (last?.role === 'assistant') {
                  sidebar.updateLastAssistantMessage({
                    content: last.content + '\n\n⚠️ _Warning: This message may not have been saved._',
                  })
                }
              })
          },
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
    [addMessage, updateMessage, updateLastAssistantMessage, setThreadId, setIsStreaming],
  )

  const sendMessage = useCallback(
    async (text: string, images?: { data: string; mediaType: string; filename?: string }[], applicationId?: string) => {
      // Capture conversation history BEFORE adding new messages to the store.
      const sidebarState = useAiSidebar.getState()
      const priorMessages = sidebarState.messages
      let conversationHistory: Array<{ role: string; content: string }>
      if (sidebarState.contextSummary) {
        const recentMessages = priorMessages
          .slice(-20)
          .filter((m) => m.content && !m.isError)
          .map((m) => ({ role: m.role, content: m.content }))
        conversationHistory = [
          { role: 'assistant', content: `[Previous context summary]: ${sidebarState.contextSummary}` },
          ...recentMessages,
        ]
      } else {
        conversationHistory = priorMessages
          .slice(-50)
          .filter((m) => m.content && !m.isError)
          .map((m) => ({ role: m.role, content: m.content }))
      }

      // Build user message with small thumbnail previewUrls (not full base64 data URLs).
      const imageEntries = images
        ? await Promise.all(
            images.map(async (img) => ({
              id: generateId(),
              data: img.data,
              mediaType: img.mediaType,
              filename: img.filename,
              previewUrl: await createThumbnailDataUrl(img.data, img.mediaType),
              lightboxUrl: await createLightboxDataUrl(img.data, img.mediaType),
            }))
          )
        : undefined

      const baseUrl = getApiBaseUrl()
      const body: Record<string, unknown> = { message: text }
      const activeSessionId = useAiSidebar.getState().activeSessionId
      if (activeSessionId) body.session_id = activeSessionId
      const currentThreadId = useAiSidebar.getState().threadId
      if (currentThreadId) body.thread_id = currentThreadId
      if (applicationId) body.application_id = applicationId
      if (conversationHistory.length > 0) body.conversation_history = conversationHistory
      if (images?.length) {
        body.images = images.map((img) => ({
          data: img.data,
          media_type: img.mediaType,
          filename: img.filename,
        }))
      }

      await _runStream(`${baseUrl}/api/ai/chat/stream`, body, {
        addUserMessage: { content: text, images: imageEntries },
      })
    },
    [_runStream]
  )

  const resumeInterrupt = useCallback(
    async (tid: string, response: Record<string, unknown>) => {
      const baseUrl = getApiBaseUrl()
      await _runStream(`${baseUrl}/api/ai/chat/resume/stream`, {
        thread_id: tid,
        response,
      })
    },
    [_runStream]
  )

  const sendReplayMessage = useCallback(
    async (text: string, checkpointId: string) => {
      const baseUrl = getApiBaseUrl()
      const body: Record<string, unknown> = {
        message: text,
        thread_id: useAiSidebar.getState().threadId,
        checkpoint_id: checkpointId,
      }

      await _runStream(`${baseUrl}/api/ai/chat/replay`, body, {
        addUserMessage: { content: text },
      })
    },
    [_runStream]
  )

  const cancelStream = useCallback(async () => {
    // 1. Server-side cancel (best-effort)
    const threadId = useAiSidebar.getState().threadId
    if (threadId) {
      const baseUrl = getApiBaseUrl()
      try {
        await fetch(`${baseUrl}/api/ai/chat/cancel/${threadId}`, {
          method: 'POST',
          headers: { ...sseAuthHeaders(), 'Content-Type': 'application/json' },
        })
      } catch { /* best-effort */ }
    }

    // 2. Client-side abort
    abortRef.current?.abort()
    abortRef.current = null
    // Only update if actually streaming to avoid unnecessary store emit → re-render
    if (useAiSidebar.getState().isStreaming) {
      setIsStreaming(false)
    }

    // 3. Mark empty assistant messages as cancelled
    const messages = useAiSidebar.getState().messages
    const lastMsg = messages[messages.length - 1]
    if (lastMsg?.role === 'assistant' && !lastMsg.content) {
      updateLastAssistantMessage({ content: '_Cancelled._' })
    }
  }, [setIsStreaming, updateLastAssistantMessage])

  return { sendMessage, sendReplayMessage, resumeInterrupt, cancelStream }
}
