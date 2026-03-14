/**
 * Tests for use-ai-chat.ts — SSE streaming, parseSSEChunk, processSSEStream,
 * sendMessage, resumeInterrupt, sendReplayMessage, cancelStream.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

// ============================================================================
// Mocks — must be before imports
// ============================================================================

// Mock api-client (SSE auth now uses getAccessToken/refreshTokens from api-client)
// Use vi.hoisted so mock fns are available when vi.mock factory runs (hoisted above imports)
const { mockGetAccessToken, mockRefreshTokens, mockAuthPost } = vi.hoisted(() => ({
  mockGetAccessToken: vi.fn((): string | null => 'test-token'),
  mockRefreshTokens: vi.fn(),
  mockAuthPost: vi.fn((_endpoint?: string, _body?: unknown) => Promise.resolve({ data: null })),
}))
vi.mock('@/lib/api-client', () => ({
  getAccessToken: () => mockGetAccessToken(),
  refreshTokens: () => mockRefreshTokens(),
  authPost: (endpoint: string, body?: unknown) => mockAuthPost(endpoint, body),
}))

// Mock query-client (used for cache invalidation in onRunFinished)
vi.mock('@/lib/query-client', () => ({
  default: {
    invalidateQueries: vi.fn(),
    removeQueries: vi.fn(),
  },
  queryKeys: {
    chatSessions: ['chat-sessions'],
    chatMessages: (id: string) => ['chat-messages', id],
  },
}))

// Mock crypto.randomUUID
let uuidCounter = 0
vi.stubGlobal('crypto', {
  randomUUID: () => `uuid-${++uuidCounter}`,
})

// Mock requestAnimationFrame/cancelAnimationFrame — JSDOM doesn't run rAF callbacks.
// processSSEStream uses rAF to rate-limit flushBatch (QE-HIGH07), so we schedule
// the callback via queueMicrotask to run after the current synchronous code completes.
// This avoids the rafId assignment race (synchronous execution would cause rafId=null
// inside the callback to be overwritten by the return value assignment).
vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
  queueMicrotask(() => cb(0))
  return 0
})
vi.stubGlobal('cancelAnimationFrame', () => {})

// ============================================================================
// Imports (after mocks)
// ============================================================================

import { useAiChat } from '../use-ai-chat'
import { useAiSidebar } from '../use-ai-sidebar'

// ============================================================================
// Helpers
// ============================================================================

/** Encode text into a Uint8Array for ReadableStream chunks */
function encode(text: string): Uint8Array {
  return new TextEncoder().encode(text)
}

/** Build an SSE text block from event type and JSON data */
function sseBlock(event: string, data: Record<string, unknown>): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`
}

/**
 * Create a mock fetch Response with a ReadableStream body.
 * Accepts an array of SSE text chunks that will be enqueued in order.
 */
function mockSSEResponse(chunks: string[], status = 200): Response {
  let index = 0
  const stream = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (index < chunks.length) {
        controller.enqueue(encode(chunks[index]))
        index++
      } else {
        controller.close()
      }
    },
  })

  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({ 'content-type': 'text/event-stream' }),
    body: stream,
    text: async () => 'error body',
  } as unknown as Response
}

/** Get store state helper */
function getState() {
  return useAiSidebar.getState()
}

/** Find last assistant message */
function getAssistant() {
  return getState().messages.find((m) => m.role === 'assistant')
}

// ============================================================================
// Test Suites
// ============================================================================

describe('use-ai-chat', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    uuidCounter = 0
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    getState().resetChat()
    mockGetAccessToken.mockReturnValue('test-token')
    mockRefreshTokens.mockResolvedValue(null)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  // ==========================================================================
  // 1. parseSSEChunk (tested through the hook's streaming behavior)
  // ==========================================================================

  describe('parseSSEChunk — via SSE stream', () => {
    it('parses a single valid SSE event', async () => {
      const chunks = [
        sseBlock('text_delta', { content: 'Hello' }),
        sseBlock('run_finished', { checkpoint_id: 'cp1' }),
        sseBlock('end', {}),
      ]
      fetchMock.mockResolvedValue(mockSSEResponse(chunks))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('test')
      })

      expect(getAssistant()?.content).toBe('Hello')
    })

    it('rejects unknown SSE event types', async () => {
      const chunks = [
        sseBlock('unknown_type', { content: 'bad' }),
        sseBlock('text_delta', { content: 'good' }),
        sseBlock('run_finished', {}),
        sseBlock('end', {}),
      ]
      fetchMock.mockResolvedValue(mockSSEResponse(chunks))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('test')
      })

      expect(getAssistant()?.content).toBe('good')
    })

    it('handles multi-line data fields per SSE spec', async () => {
      const validMultiLine =
        'event: run_finished\ndata: {"checkpoint_id":\ndata: "cp-multi"}\n\n'
      const chunks = [
        sseBlock('text_delta', { content: 'ok' }),
        validMultiLine,
        sseBlock('end', {}),
      ]
      fetchMock.mockResolvedValue(mockSSEResponse(chunks))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('test')
      })

      expect(getAssistant()?.content).toBe('ok')
    })

    it('skips blocks with no event type', async () => {
      const noEventBlock = 'data: {"content":"orphan"}\n\n'
      const chunks = [
        noEventBlock,
        sseBlock('text_delta', { content: 'valid' }),
        sseBlock('run_finished', {}),
        sseBlock('end', {}),
      ]
      fetchMock.mockResolvedValue(mockSSEResponse(chunks))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('test')
      })

      expect(getAssistant()?.content).toBe('valid')
    })

    it('skips blocks with invalid JSON data', async () => {
      const badJson = 'event: text_delta\ndata: {not valid json}\n\n'
      const chunks = [
        badJson,
        sseBlock('text_delta', { content: 'recovered' }),
        sseBlock('run_finished', {}),
        sseBlock('end', {}),
      ]
      fetchMock.mockResolvedValue(mockSSEResponse(chunks))

      const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('test')
      })

      expect(getAssistant()?.content).toBe('recovered')
      expect(warnSpy).toHaveBeenCalled()
      warnSpy.mockRestore()
    })
  })

  // ==========================================================================
  // 2. processSSEStream behaviors
  // ==========================================================================

  describe('processSSEStream — event dispatch', () => {
    it('accumulates text_delta content', async () => {
      const chunks = [
        sseBlock('text_delta', { content: 'Hello' }),
        sseBlock('text_delta', { content: ' world' }),
        sseBlock('run_finished', {}),
        sseBlock('end', {}),
      ]
      fetchMock.mockResolvedValue(mockSSEResponse(chunks))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('test')
      })

      expect(getAssistant()?.content).toBe('Hello world')
    })

    it('upserts thinking_step by node name', async () => {
      const chunks = [
        sseBlock('thinking_step', { node: 'intake', label: 'Intake', status: 'active' }),
        sseBlock('thinking_step', { node: 'intake', label: 'Intake', status: 'complete' }),
        sseBlock('text_delta', { content: 'done' }),
        sseBlock('run_finished', {}),
        sseBlock('end', {}),
      ]
      fetchMock.mockResolvedValue(mockSSEResponse(chunks))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('test')
      })

      const assistant = getAssistant()
      // Should have 1 activity item (upserted, not 2)
      expect(assistant?.activity).toHaveLength(1)
      expect(assistant?.activity?.[0]).toMatchObject({
        type: 'node',
        node: 'intake',
        status: 'complete',
      })
    })

    it('handles tool_call_start and tool_call_end', async () => {
      const chunks = [
        sseBlock('tool_call_start', { id: 'tc-1', name: 'search_docs' }),
        sseBlock('tool_call_end', {
          id: 'tc-1',
          name: 'search_docs',
          summary: 'Found 3 results',
        }),
        sseBlock('text_delta', { content: 'result' }),
        sseBlock('run_finished', {}),
        sseBlock('end', {}),
      ]
      fetchMock.mockResolvedValue(mockSSEResponse(chunks))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('test')
      })

      expect(getAssistant()?.activity).toHaveLength(1)
      expect(getAssistant()?.activity?.[0]).toMatchObject({
        type: 'tool',
        id: 'tc-1',
        name: 'search_docs',
        status: 'complete',
        summary: 'Found 3 results',
      })
    })

    it('sets tool status to error when tool_call_end has error', async () => {
      const chunks = [
        sseBlock('tool_call_start', { id: 'tc-2', name: 'sql_query' }),
        sseBlock('tool_call_end', {
          id: 'tc-2',
          name: 'sql_query',
          error: 'timeout',
        }),
        sseBlock('run_finished', {}),
        sseBlock('end', {}),
      ]
      fetchMock.mockResolvedValue(mockSSEResponse(chunks))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('test')
      })

      expect(getAssistant()?.activity?.[0]).toMatchObject({
        status: 'error',
        error: 'timeout',
      })
    })

    it('sets thread_id on run_started', async () => {
      const chunks = [
        sseBlock('run_started', { thread_id: 'thread-abc' }),
        sseBlock('text_delta', { content: 'hi' }),
        sseBlock('run_finished', {}),
        sseBlock('end', {}),
      ]
      fetchMock.mockResolvedValue(mockSSEResponse(chunks))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('test')
      })

      expect(getState().threadId).toBe('thread-abc')
    })

    it('sets interrupt data on interrupt event', async () => {
      const payload = {
        type: 'clarification',
        question: 'Which project?',
        options: ['A', 'B'],
      }
      const chunks = [
        sseBlock('interrupt', payload),
        sseBlock('run_finished', { interrupted: true, interrupt_payload: payload }),
        sseBlock('end', {}),
      ]
      fetchMock.mockResolvedValue(mockSSEResponse(chunks))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('test')
      })

      const assistant = getAssistant()
      expect(assistant?.interrupted).toBe(true)
      expect(assistant?.interrupt_payload?.question).toBe('Which project?')
    })

    it('sets checkpoint_id and sources on run_finished', async () => {
      const sources = [
        {
          document_id: 'd1',
          document_title: 'Doc',
          document_type: 'page',
          chunk_text: 'text',
          chunk_index: 0,
          score: 0.9,
          source_type: 'semantic',
        },
      ]
      const chunks = [
        sseBlock('text_delta', { content: 'answer' }),
        sseBlock('run_finished', { checkpoint_id: 'cp-99', sources }),
        sseBlock('end', {}),
      ]
      fetchMock.mockResolvedValue(mockSSEResponse(chunks))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('test')
      })

      const assistant = getAssistant()
      expect(assistant?.checkpoint_id).toBe('cp-99')
      expect(assistant?.sources).toHaveLength(1)
    })

    it('handles error event with prior content', async () => {
      // Error after some content — contentAccum is non-empty so QE-011 doesn't overwrite
      const chunks = [
        sseBlock('text_delta', { content: 'partial' }),
        sseBlock('error', { message: 'Rate limit exceeded' }),
        sseBlock('end', {}),
      ]
      fetchMock.mockResolvedValue(mockSSEResponse(chunks))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('test')
      })

      // Error event uses contentAccum (non-empty) as the content
      expect(getAssistant()?.content).toBe('partial')
      expect(getAssistant()?.isError).toBe(true)
    })

    it('handles error event with no prior content', async () => {
      // Error as first event — contentAccum is empty, so error message is used
      // But QE-011 then overwrites since contentAccum is empty and no run_finished
      const chunks = [
        sseBlock('error', { message: 'Rate limit exceeded' }),
        sseBlock('run_finished', {}),
        sseBlock('end', {}),
      ]
      fetchMock.mockResolvedValue(mockSSEResponse(chunks))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('test')
      })

      // Error sets content, then run_finished prevents QE-011 overwrite
      expect(getAssistant()?.content).toContain('Rate limit exceeded')
      expect(getAssistant()?.isError).toBe(true)
    })

    it('QE-011: shows error on empty stream (no content, no run_finished)', async () => {
      const chunks = [sseBlock('end', {})]
      fetchMock.mockResolvedValue(mockSSEResponse(chunks))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('test')
      })

      expect(getAssistant()?.content).toBe('Connection lost. Please try again.')
      expect(getAssistant()?.isError).toBe(true)
    })

    it('FE-013: clears buffer and emits error when exceeding MAX_BUFFER_SIZE', async () => {
      // Send a chunk that's over 1MB without double-newline terminator so buffer grows
      const largeChunk = 'x'.repeat(1_048_577)
      const chunks = [
        largeChunk,
        sseBlock('text_delta', { content: 'after-reset' }),
        sseBlock('run_finished', {}),
        sseBlock('end', {}),
      ]

      const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
      fetchMock.mockResolvedValue(mockSSEResponse(chunks))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('test')
      })

      // Buffer overflow triggers an error event before clearing, then continues
      // The error event sets isError=true on the assistant message
      expect(getAssistant()?.isError).toBe(true)
      expect(warnSpy).toHaveBeenCalledWith(
        expect.stringContaining('SSE buffer exceeded'),
      )
      warnSpy.mockRestore()
    })
  })

  // ==========================================================================
  // 3. sendMessage — fetch setup and store behavior
  // ==========================================================================

  describe('sendMessage', () => {
    it('sends POST to correct URL with auth headers', async () => {
      const chunks = [
        sseBlock('text_delta', { content: 'ok' }),
        sseBlock('run_finished', {}),
        sseBlock('end', {}),
      ]
      fetchMock.mockResolvedValue(mockSSEResponse(chunks))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('hello')
      })

      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/ai/chat/stream'),
        expect.objectContaining({
          method: 'POST',
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
            Authorization: 'Bearer test-token',
          }),
        }),
      )
    })

    it('includes conversation_history from prior messages', async () => {
      // Seed the store with existing messages
      getState().addMessage({
        id: 'old-1',
        role: 'user',
        content: 'prior question',
        timestamp: 1,
      })
      getState().addMessage({
        id: 'old-2',
        role: 'assistant',
        content: 'prior answer',
        timestamp: 2,
      })

      const chunks = [
        sseBlock('text_delta', { content: 'ok' }),
        sseBlock('run_finished', {}),
        sseBlock('end', {}),
      ]
      fetchMock.mockResolvedValue(mockSSEResponse(chunks))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('new question')
      })

      const body = JSON.parse(fetchMock.mock.calls[0][1].body)
      expect(body.conversation_history).toEqual([
        { role: 'user', content: 'prior question' },
        { role: 'assistant', content: 'prior answer' },
      ])
    })

    it('includes thread_id when one exists', async () => {
      getState().setThreadId('existing-thread')

      const chunks = [
        sseBlock('text_delta', { content: 'ok' }),
        sseBlock('run_finished', {}),
        sseBlock('end', {}),
      ]
      fetchMock.mockResolvedValue(mockSSEResponse(chunks))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('test')
      })

      const body = JSON.parse(fetchMock.mock.calls[0][1].body)
      expect(body.thread_id).toBe('existing-thread')
    })

    it('includes application_id when provided', async () => {
      const chunks = [
        sseBlock('text_delta', { content: 'ok' }),
        sseBlock('run_finished', {}),
        sseBlock('end', {}),
      ]
      fetchMock.mockResolvedValue(mockSSEResponse(chunks))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('test', undefined, 'app-123')
      })

      const body = JSON.parse(fetchMock.mock.calls[0][1].body)
      expect(body.application_id).toBe('app-123')
    })

    it('handles HTTP error response (after retries for 5xx)', async () => {
      vi.useFakeTimers()
      fetchMock.mockResolvedValue(mockSSEResponse([], 500))

      const { result } = renderHook(() => useAiChat())

      const sendPromise = act(async () => {
        const p = result.current.sendMessage('test')
        // Advance past both backoff delays: 1s (2^0) + 2s (2^1)
        await vi.advanceTimersByTimeAsync(1000)
        await vi.advanceTimersByTimeAsync(2000)
        await p
      })
      await sendPromise

      // 5xx triggers retries: 1 initial + 2 retries = 3 total
      expect(fetchMock).toHaveBeenCalledTimes(3)
      expect(getAssistant()?.content).toContain('Error: 500')
      expect(getAssistant()?.isError).toBe(true)
      expect(getState().isStreaming).toBe(false)
      vi.useRealTimers()
    })

    it('handles missing response body', async () => {
      fetchMock.mockResolvedValue({
        ok: true,
        status: 200,
        body: null,
        headers: new Headers(),
      })

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('test')
      })

      expect(getAssistant()?.content).toBe('Error: No response body')
      expect(getAssistant()?.isError).toBe(true)
    })

    it('handles network error (after retries)', async () => {
      vi.useFakeTimers()
      fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))

      const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        const p = result.current.sendMessage('test')
        await vi.advanceTimersByTimeAsync(1000)
        await vi.advanceTimersByTimeAsync(2000)
        await p
      })

      // Network errors trigger retries: 1 initial + 2 retries = 3 total
      expect(fetchMock).toHaveBeenCalledTimes(3)
      expect(getAssistant()?.content).toContain('Failed to fetch')
      expect(getAssistant()?.isError).toBe(true)
      expect(getState().isStreaming).toBe(false)
      errSpy.mockRestore()
      vi.useRealTimers()
    })

    it('ignores AbortError silently', async () => {
      const abortErr = new DOMException('The operation was aborted.', 'AbortError')
      fetchMock.mockRejectedValue(abortErr)

      const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('test')
      })

      // AbortError should not log
      expect(errSpy).not.toHaveBeenCalled()
      errSpy.mockRestore()
    })

    it('FE-007: strips base64 data from stored images after send', async () => {
      // Mock Image constructor for thumbnail generation
      const originalImage = globalThis.Image
      class MockImage {
        naturalWidth = 400
        naturalHeight = 300
        onload: (() => void) | null = null
        onerror: (() => void) | null = null
        set src(_val: string) {
          setTimeout(() => this.onload?.(), 0)
        }
      }
      vi.stubGlobal('Image', MockImage)

      // Mock canvas
      const mockCtx = { drawImage: vi.fn() }
      const mockCanvas = {
        width: 0,
        height: 0,
        getContext: () => mockCtx,
        toDataURL: () => 'data:image/jpeg;base64,thumbnail',
      }
      const origCreateElement = document.createElement.bind(document)
      vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
        if (tag === 'canvas') return mockCanvas as unknown as HTMLCanvasElement
        return origCreateElement(tag)
      })

      const chunks = [
        sseBlock('text_delta', { content: 'saw image' }),
        sseBlock('run_finished', {}),
        sseBlock('end', {}),
      ]
      fetchMock.mockResolvedValue(mockSSEResponse(chunks))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('look at this', [
          { data: 'base64encodeddata', mediaType: 'image/png', filename: 'test.png' },
        ])
      })

      const userMsg = getState().messages.find((m) => m.role === 'user')
      // base64 data should be stripped from stored message
      expect(userMsg?.images?.[0]?.data).toBeUndefined()

      vi.stubGlobal('Image', originalImage)
      vi.mocked(document.createElement).mockRestore()
    })

    it('adds user and assistant messages to store', async () => {
      const chunks = [
        sseBlock('text_delta', { content: 'response' }),
        sseBlock('run_finished', {}),
        sseBlock('end', {}),
      ]
      fetchMock.mockResolvedValue(mockSSEResponse(chunks))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('my question')
      })

      const msgs = getState().messages
      expect(msgs).toHaveLength(2)
      expect(msgs[0].role).toBe('user')
      expect(msgs[0].content).toBe('my question')
      expect(msgs[1].role).toBe('assistant')
      expect(msgs[1].content).toBe('response')
    })

    it('sets isStreaming false after completion', async () => {
      expect(getState().isStreaming).toBe(false)

      const chunks = [
        sseBlock('text_delta', { content: 'ok' }),
        sseBlock('run_finished', {}),
        sseBlock('end', {}),
      ]
      fetchMock.mockResolvedValue(mockSSEResponse(chunks))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('test')
      })

      expect(getState().isStreaming).toBe(false)
    })

    it('sends images in request body', async () => {
      // Mock Image constructor for thumbnail generation
      const originalImage = globalThis.Image
      class MockImage {
        naturalWidth = 100
        naturalHeight = 80
        onload: (() => void) | null = null
        onerror: (() => void) | null = null
        set src(_val: string) {
          setTimeout(() => this.onload?.(), 0)
        }
      }
      vi.stubGlobal('Image', MockImage)

      const mockCtx = { drawImage: vi.fn() }
      const mockCanvas = {
        width: 0,
        height: 0,
        getContext: () => mockCtx,
        toDataURL: () => 'data:image/jpeg;base64,thumb',
      }
      const origCreateElement = document.createElement.bind(document)
      vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
        if (tag === 'canvas') return mockCanvas as unknown as HTMLCanvasElement
        return origCreateElement(tag)
      })

      const chunks = [
        sseBlock('text_delta', { content: 'ok' }),
        sseBlock('run_finished', {}),
        sseBlock('end', {}),
      ]
      fetchMock.mockResolvedValue(mockSSEResponse(chunks))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('check', [
          { data: 'imgdata', mediaType: 'image/png', filename: 'f.png' },
        ])
      })

      const body = JSON.parse(fetchMock.mock.calls[0][1].body)
      expect(body.images).toEqual([
        { data: 'imgdata', media_type: 'image/png', filename: 'f.png' },
      ])

      vi.stubGlobal('Image', originalImage)
      vi.mocked(document.createElement).mockRestore()
    })
  })

  // ==========================================================================
  // 3b. SSE 401 retry (sseFetchWithRetry)
  // ==========================================================================

  describe('SSE 401 retry', () => {
    it('retries with refreshed token on 401', async () => {
      // First fetch returns 401
      const unauthorizedResponse = {
        ok: false,
        status: 401,
        body: null,
        headers: new Headers(),
        text: async () => 'Unauthorized',
      } as unknown as Response

      // After refresh, second fetch succeeds
      const chunks = [
        sseBlock('text_delta', { content: 'after-refresh' }),
        sseBlock('run_finished', {}),
        sseBlock('end', {}),
      ]
      const successResponse = mockSSEResponse(chunks)

      fetchMock
        .mockResolvedValueOnce(unauthorizedResponse) // first call: 401
        .mockResolvedValueOnce(successResponse) // retry after refresh

      // After refresh succeeds, getAccessToken() returns the new token
      // (simulates api-client module state update from refreshTokens)
      mockRefreshTokens.mockImplementationOnce(() => {
        mockGetAccessToken.mockReturnValue('new-token')
        return Promise.resolve('new-token')
      })

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('test')
      })

      expect(mockRefreshTokens).toHaveBeenCalledOnce()
      expect(fetchMock).toHaveBeenCalledTimes(2)
      // Retry goes through sseAuthHeaders() which calls getAccessToken()
      expect(fetchMock.mock.calls[1][1].headers).toMatchObject({
        Authorization: 'Bearer new-token',
      })
      expect(getAssistant()?.content).toBe('after-refresh')

      // Restore default mock
      mockGetAccessToken.mockReturnValue('test-token')
    })

    it('shows auth error when refresh returns null on 401', async () => {
      fetchMock.mockResolvedValue({
        ok: false,
        status: 401,
        body: null,
        headers: new Headers(),
        text: async () => 'Unauthorized',
      } as unknown as Response)

      mockRefreshTokens.mockResolvedValueOnce(null)

      const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('test')
      })

      // Now throws auth error instead of returning stale 401 response
      expect(getAssistant()?.content).toContain('Authentication failed')
      expect(getAssistant()?.isError).toBe(true)
      expect(fetchMock).toHaveBeenCalledTimes(1) // no retry when refresh returns null
      errSpy.mockRestore()
    })

    it('shows auth error when refreshTokens throws on 401', async () => {
      fetchMock.mockResolvedValue({
        ok: false,
        status: 401,
        body: null,
        headers: new Headers(),
        text: async () => 'Unauthorized',
      } as unknown as Response)

      mockRefreshTokens.mockRejectedValueOnce(new Error('Token refresh network error'))

      const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('test')
      })

      expect(getAssistant()?.content).toContain('Authentication failed')
      expect(getAssistant()?.isError).toBe(true)
      errSpy.mockRestore()
    })

    it('sends request without Authorization header when token is null', async () => {
      mockGetAccessToken.mockReturnValueOnce(null)

      const chunks = [
        sseBlock('text_delta', { content: 'ok' }),
        sseBlock('run_finished', {}),
        sseBlock('end', {}),
      ]
      fetchMock.mockResolvedValue(mockSSEResponse(chunks))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('test')
      })

      const headers = fetchMock.mock.calls[0][1].headers
      expect(headers).not.toHaveProperty('Authorization')
      expect(headers['Content-Type']).toBe('application/json')
    })
  })

  // ==========================================================================
  // 3c. QE-004: SSE retry backoff for transient failures
  // ==========================================================================

  describe('QE-004: SSE retry backoff', () => {
    beforeEach(() => { vi.useFakeTimers() })
    afterEach(() => { vi.useRealTimers() })

    it('retries 5xx responses with exponential backoff up to 2 times', async () => {
      const chunks = [
        sseBlock('text_delta', { content: 'recovered' }),
        sseBlock('run_finished', {}),
        sseBlock('end', {}),
      ]
      fetchMock
        .mockResolvedValueOnce(mockSSEResponse([], 503)) // attempt 0: 503
        .mockResolvedValueOnce(mockSSEResponse([], 502)) // attempt 1: 502
        .mockResolvedValueOnce(mockSSEResponse(chunks))  // attempt 2: success

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        const p = result.current.sendMessage('test')
        // Exponential: 1000 * 2^0 = 1s, 1000 * 2^1 = 2s
        await vi.advanceTimersByTimeAsync(1000)
        await vi.advanceTimersByTimeAsync(2000)
        await p
      })

      expect(fetchMock).toHaveBeenCalledTimes(3)
      expect(getAssistant()?.content).toBe('recovered')
    })

    it('retries network errors with backoff up to 2 times then throws', async () => {
      fetchMock.mockRejectedValue(new TypeError('Network failure'))

      const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        const p = result.current.sendMessage('test')
        await vi.advanceTimersByTimeAsync(1000)
        await vi.advanceTimersByTimeAsync(2000)
        await p
      })

      // 1 initial + 2 retries = 3
      expect(fetchMock).toHaveBeenCalledTimes(3)
      expect(getAssistant()?.content).toContain('Network failure')
      expect(getAssistant()?.isError).toBe(true)
      errSpy.mockRestore()
    })

    it('does not retry 4xx errors (except 401)', async () => {
      fetchMock.mockResolvedValue(mockSSEResponse([], 403))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('test')
      })

      // No retries for 403
      expect(fetchMock).toHaveBeenCalledTimes(1)
      expect(getAssistant()?.content).toContain('Error: 403')
      expect(getAssistant()?.isError).toBe(true)
    })

    it('does not retry 400 Bad Request', async () => {
      fetchMock.mockResolvedValue(mockSSEResponse([], 400))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('test')
      })

      expect(fetchMock).toHaveBeenCalledTimes(1)
      expect(getAssistant()?.content).toContain('Error: 400')
    })

    it('recovers on second retry after initial 5xx', async () => {
      const chunks = [
        sseBlock('text_delta', { content: 'success' }),
        sseBlock('run_finished', {}),
        sseBlock('end', {}),
      ]
      fetchMock
        .mockResolvedValueOnce(mockSSEResponse([], 500)) // attempt 0: 500
        .mockResolvedValueOnce(mockSSEResponse(chunks))  // attempt 1: success

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        const p = result.current.sendMessage('test')
        // Only 1 backoff: 1000 * 2^0 = 1s
        await vi.advanceTimersByTimeAsync(1000)
        await p
      })

      expect(fetchMock).toHaveBeenCalledTimes(2)
      expect(getAssistant()?.content).toBe('success')
    })

    it('uses exponential delay: 1s for first retry, 2s for second', async () => {
      fetchMock.mockResolvedValue(mockSSEResponse([], 500))

      const { result } = renderHook(() => useAiChat())

      act(() => { result.current.sendMessage('test') })

      // After attempt 0 fails (5xx), backoff = 1000 * 2^0 = 1000ms
      // Advance 999ms — should NOT have retried yet
      await act(async () => { await vi.advanceTimersByTimeAsync(999) })
      expect(fetchMock).toHaveBeenCalledTimes(1)

      // Advance 1ms more — first retry fires
      await act(async () => { await vi.advanceTimersByTimeAsync(1) })
      expect(fetchMock).toHaveBeenCalledTimes(2)

      // After attempt 1 fails (5xx), backoff = 1000 * 2^1 = 2000ms
      // Advance 1999ms — should NOT have retried yet
      await act(async () => { await vi.advanceTimersByTimeAsync(1999) })
      expect(fetchMock).toHaveBeenCalledTimes(2)

      // Advance 1ms more — second retry fires
      await act(async () => { await vi.advanceTimersByTimeAsync(1) })
      expect(fetchMock).toHaveBeenCalledTimes(3)
    })

    it('abort during backoff sleep cancels immediately without extra fetch', async () => {
      fetchMock.mockResolvedValue(mockSSEResponse([], 500))

      const { result } = renderHook(() => useAiChat())

      // Start sending — will get 500 and enter backoff
      act(() => { result.current.sendMessage('test') })

      // Let first fetch complete (attempt 0 → 500)
      await act(async () => { await vi.advanceTimersByTimeAsync(0) })
      expect(fetchMock).toHaveBeenCalledTimes(1)

      // Cancel during the backoff sleep
      act(() => { result.current.cancelStream() })

      // Advance well past all backoff delays
      await act(async () => { await vi.advanceTimersByTimeAsync(10_000) })

      // Should not have made any more fetch calls
      expect(fetchMock).toHaveBeenCalledTimes(1)
      expect(getState().isStreaming).toBe(false)
    })
  })

  // ==========================================================================
  // 4. resumeInterrupt
  // ==========================================================================

  describe('resumeInterrupt', () => {
    it('sends POST to resume URL with thread_id and response', async () => {
      const chunks = [
        sseBlock('text_delta', { content: 'resumed' }),
        sseBlock('run_finished', {}),
        sseBlock('end', {}),
      ]
      fetchMock.mockResolvedValue(mockSSEResponse(chunks))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.resumeInterrupt('thread-42', { approved: true })
      })

      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/ai/chat/resume/stream'),
        expect.objectContaining({ method: 'POST' }),
      )

      const body = JSON.parse(fetchMock.mock.calls[0][1].body)
      expect(body.thread_id).toBe('thread-42')
      expect(body.response).toEqual({ approved: true })
    })

    it('adds assistant placeholder and streams response', async () => {
      const chunks = [
        sseBlock('text_delta', { content: 'continued' }),
        sseBlock('run_finished', {}),
        sseBlock('end', {}),
      ]
      fetchMock.mockResolvedValue(mockSSEResponse(chunks))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.resumeInterrupt('tid', { choice: 'A' })
      })

      expect(getAssistant()?.content).toBe('continued')
    })

    it('handles HTTP error on resume', async () => {
      fetchMock.mockResolvedValue(mockSSEResponse([], 403))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.resumeInterrupt('tid', {})
      })

      expect(getAssistant()?.content).toContain('Error: 403')
      expect(getAssistant()?.isError).toBe(true)
    })

    it('handles network error on resume', async () => {
      vi.useFakeTimers()
      fetchMock.mockRejectedValue(new TypeError('Network error'))

      const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        const p = result.current.resumeInterrupt('tid', {})
        await vi.advanceTimersByTimeAsync(1000)
        await vi.advanceTimersByTimeAsync(2000)
        await p
      })

      expect(getAssistant()?.content).toContain('Network error')
      expect(getAssistant()?.isError).toBe(true)
      expect(getState().isStreaming).toBe(false)
      errSpy.mockRestore()
      vi.useRealTimers()
    })
  })

  // ==========================================================================
  // 5. sendReplayMessage
  // ==========================================================================

  describe('sendReplayMessage', () => {
    it('sends POST to replay URL with checkpoint_id', async () => {
      getState().setThreadId('thread-replay')

      const chunks = [
        sseBlock('text_delta', { content: 'replayed' }),
        sseBlock('run_finished', {}),
        sseBlock('end', {}),
      ]
      fetchMock.mockResolvedValue(mockSSEResponse(chunks))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendReplayMessage('new message', 'cp-old')
      })

      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/ai/chat/replay'),
        expect.objectContaining({ method: 'POST' }),
      )

      const body = JSON.parse(fetchMock.mock.calls[0][1].body)
      expect(body.message).toBe('new message')
      expect(body.checkpoint_id).toBe('cp-old')
      expect(body.thread_id).toBe('thread-replay')
    })

    it('adds user and assistant messages to store', async () => {
      const chunks = [
        sseBlock('text_delta', { content: 'replay answer' }),
        sseBlock('run_finished', {}),
        sseBlock('end', {}),
      ]
      fetchMock.mockResolvedValue(mockSSEResponse(chunks))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendReplayMessage('q', 'cp-1')
      })

      const msgs = getState().messages
      expect(msgs).toHaveLength(2)
      expect(msgs[0].role).toBe('user')
      expect(msgs[1].role).toBe('assistant')
      expect(msgs[1].content).toBe('replay answer')
    })

    it('handles HTTP error on replay', async () => {
      fetchMock.mockResolvedValue(mockSSEResponse([], 400))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendReplayMessage('q', 'cp-1')
      })

      expect(getAssistant()?.content).toContain('Error: 400')
      expect(getAssistant()?.isError).toBe(true)
    })
  })

  // ==========================================================================
  // 6. cancelStream
  // ==========================================================================

  describe('cancelStream', () => {
    it('aborts controller and sets isStreaming to false', async () => {
      vi.useFakeTimers()

      const { result } = renderHook(() => useAiChat())

      // Start a long stream that won't finish
      const neverEndingResponse = {
        ok: true,
        status: 200,
        body: new ReadableStream({
          pull() {
            // Never resolve — simulates a hanging connection
            return new Promise(() => {})
          },
        }),
        headers: new Headers(),
      } as unknown as Response

      fetchMock.mockResolvedValue(neverEndingResponse)

      // Don't await sendMessage — it'll hang on the never-ending stream
      act(() => {
        result.current.sendMessage('test')
      })

      // Allow microtasks to settle (fetch resolves, stream read starts)
      await act(async () => {
        await vi.advanceTimersByTimeAsync(10)
      })

      // Cancel
      act(() => {
        result.current.cancelStream()
      })

      expect(getState().isStreaming).toBe(false)
      // Verify the AbortController signal was triggered (the mechanism that cancels the stream)
      // Note: jsdom doesn't reliably invoke ReadableStream.cancel() synchronously,
      // but we can verify the fetch was called with an AbortSignal
      expect(fetchMock).toHaveBeenCalledWith(
        expect.anything(),
        expect.objectContaining({ signal: expect.any(AbortSignal) }),
      )

      vi.useRealTimers()
    })
  })

  // ==========================================================================
  // 7. Batched flushing (FE-004)
  // ==========================================================================

  describe('FE-004: batched flushing', () => {
    it('flushes multiple text_delta events in a single chunk as one update', async () => {
      // Send multiple text_delta events in a single chunk
      const singleChunk =
        sseBlock('text_delta', { content: 'A' }) +
        sseBlock('text_delta', { content: 'B' }) +
        sseBlock('text_delta', { content: 'C' })
      const chunks = [singleChunk, sseBlock('run_finished', {}), sseBlock('end', {})]
      fetchMock.mockResolvedValue(mockSSEResponse(chunks))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('test')
      })

      // All three deltas accumulated
      expect(getAssistant()?.content).toBe('ABC')
    })
  })

  // ==========================================================================
  // 8. SSE timeout (60s)
  // ==========================================================================

  describe('SSE timeout', () => {
    it('times out after 60s of no events', async () => {
      vi.useFakeTimers()

      // Stream that sends one chunk then hangs
      const hangingBody = new ReadableStream<Uint8Array>({
        start(controller) {
          // Enqueue one chunk to start
          controller.enqueue(encode(sseBlock('text_delta', { content: 'start' })))
        },
        pull() {
          // Never resolve — simulates a hanging connection
          return new Promise(() => {})
        },
      })

      fetchMock.mockResolvedValue({
        ok: true,
        status: 200,
        body: hangingBody,
        headers: new Headers(),
      })

      const { result } = renderHook(() => useAiChat())

      // Start sending (don't await — it'll hang)
      act(() => {
        result.current.sendMessage('test')
      })

      // Allow first chunk to be processed
      await act(async () => {
        await vi.advanceTimersByTimeAsync(100)
      })

      // Advance past 60s timeout
      await act(async () => {
        await vi.advanceTimersByTimeAsync(60_000)
      })

      const assistant = getAssistant()
      expect(assistant?.content).toContain('[Response timed out. Please try again.]')
      expect(assistant?.isError).toBe(true)

      vi.useRealTimers()
    })
  })

  // ==========================================================================
  // 9. Edge cases from R1 audit
  // ==========================================================================

  describe('edge cases', () => {
    it('CR-003: normalizes \\r\\n to \\n in SSE chunks', async () => {
      // Simulate sse_starlette \r\n line endings
      const crlfChunk = 'event: text_delta\r\ndata: {"content":"crlf"}\r\n\r\n' +
        'event: run_finished\r\ndata: {}\r\n\r\n' +
        'event: end\r\ndata: {}\r\n\r\n'
      fetchMock.mockResolvedValue(mockSSEResponse([crlfChunk]))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('test')
      })

      expect(getAssistant()?.content).toBe('crlf')
    })

    it('CR-004/TE-009: caps activity items at MAX_ACTIVITY_ITEMS (100)', async () => {
      // Generate 101 tool_call_start events
      const toolEvents = Array.from({ length: 101 }, (_, i) =>
        sseBlock('tool_call_start', { id: `tc-${i}`, name: `tool_${i}` })
      ).join('')
      const chunks = [
        toolEvents,
        sseBlock('text_delta', { content: 'done' }),
        sseBlock('run_finished', {}),
        sseBlock('end', {}),
      ]
      fetchMock.mockResolvedValue(mockSSEResponse(chunks))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('test')
      })

      // Should cap at 100, not 101 (all running, so eviction finds nothing to remove)
      expect(getAssistant()?.activity?.length).toBe(100)
    })

    it('FIFO eviction: replaces oldest completed items when at cap', async () => {
      // Generate 100 tool events: start + end for first 50 (making them 'complete'),
      // then start 50 more (making them 'running'), then add one more (should evict oldest complete)
      const completeEvents = Array.from({ length: 50 }, (_, i) =>
        sseBlock('tool_call_start', { id: `tc-${i}`, name: `tool_${i}` }) +
        sseBlock('tool_call_end', { id: `tc-${i}`, name: `tool_${i}`, summary: 'done' })
      ).join('')
      const runningEvents = Array.from({ length: 50 }, (_, i) =>
        sseBlock('tool_call_start', { id: `tc-${i + 50}`, name: `tool_${i + 50}` })
      ).join('')
      // This 101st tool should evict tc-0 (oldest completed)
      const overflowEvent = sseBlock('tool_call_start', { id: 'tc-overflow', name: 'tool_overflow' })
      const chunks = [
        completeEvents,
        runningEvents,
        overflowEvent,
        sseBlock('text_delta', { content: 'done' }),
        sseBlock('run_finished', {}),
        sseBlock('end', {}),
      ]
      fetchMock.mockResolvedValue(mockSSEResponse(chunks))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('test')
      })

      const activity = getAssistant()?.activity
      // Still 100 items (evicted one completed to make room)
      expect(activity?.length).toBe(100)
      // The overflow tool should be present
      expect(activity?.some((a) => a.type === 'tool' && a.id === 'tc-overflow')).toBe(true)
      // tc-0 (oldest completed) should have been evicted
      expect(activity?.some((a) => a.type === 'tool' && a.id === 'tc-0')).toBe(false)
    })

    it('TE-008: orphaned tool_call_end (no matching start) is silently ignored', async () => {
      const chunks = [
        sseBlock('tool_call_end', { id: 'orphan-1', name: 'ghost_tool', summary: 'done' }),
        sseBlock('text_delta', { content: 'still works' }),
        sseBlock('run_finished', {}),
        sseBlock('end', {}),
      ]
      fetchMock.mockResolvedValue(mockSSEResponse(chunks))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('test')
      })

      // No activity item created for orphaned tool_call_end
      expect(getAssistant()?.activity).toHaveLength(0)
      expect(getAssistant()?.content).toBe('still works')
    })

    it('CR-006: conversationHistory slices before filtering (O(50) not O(n))', async () => {
      // Seed store with 60 messages: first 55 are good, last 5 are errors
      for (let i = 0; i < 55; i++) {
        getState().addMessage({
          id: `msg-${i}`,
          role: i % 2 === 0 ? 'user' : 'assistant',
          content: `message ${i}`,
          timestamp: i,
        })
      }
      for (let i = 55; i < 60; i++) {
        getState().addMessage({
          id: `msg-${i}`,
          role: 'assistant',
          content: `error ${i}`,
          timestamp: i,
          isError: true,
        })
      }

      const chunks = [
        sseBlock('text_delta', { content: 'ok' }),
        sseBlock('run_finished', {}),
        sseBlock('end', {}),
      ]
      fetchMock.mockResolvedValue(mockSSEResponse(chunks))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('new')
      })

      const body = JSON.parse(fetchMock.mock.calls[0][1].body)
      const history = body.conversation_history || []
      // .slice(-50) first takes messages 10-59 (50 items)
      // Then filter removes the 5 error messages (55-59), leaving 45
      // The first message in history should be message 10, not message 0
      expect(history.length).toBe(45)
      expect(history[0].content).toBe('message 10')
    })

    it('TE-010: error messages (isError: true) are excluded from conversation_history', async () => {
      // Seed store with a normal message and an error message
      getState().addMessage({
        id: 'msg-ok',
        role: 'assistant',
        content: 'good answer',
        timestamp: 1,
      })
      getState().addMessage({
        id: 'msg-err',
        role: 'assistant',
        content: 'Error: something went wrong',
        timestamp: 2,
        isError: true,
      })

      const chunks = [
        sseBlock('text_delta', { content: 'ok' }),
        sseBlock('run_finished', {}),
        sseBlock('end', {}),
      ]
      fetchMock.mockResolvedValue(mockSSEResponse(chunks))

      const { result } = renderHook(() => useAiChat())

      await act(async () => {
        await result.current.sendMessage('follow-up')
      })

      const body = JSON.parse(fetchMock.mock.calls[0][1].body)
      const history = body.conversation_history || []
      // The error message should be filtered out
      const errorEntries = history.filter(
        (h: { content: string }) => h.content.includes('Error: something went wrong')
      )
      expect(errorEntries).toHaveLength(0)
      // The good message should be included
      const goodEntries = history.filter(
        (h: { content: string }) => h.content === 'good answer'
      )
      expect(goodEntries).toHaveLength(1)
    })
  })
})
