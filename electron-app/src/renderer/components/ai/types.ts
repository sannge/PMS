/**
 * AI Sidebar TypeScript Types
 *
 * Shared type definitions for the Blair AI copilot sidebar system.
 * Covers chat messages, tool calls, source citations, SSE events,
 * HITL interrupts, image attachments, and navigation targets.
 */

// ============================================================================
// Tool Calls
// ============================================================================

export interface ToolCallInfo {
  id: string
  name: string
  status: 'running' | 'complete' | 'error'
  summary?: string
  details?: string
  error?: string
}

// ============================================================================
// Source Citations
// ============================================================================

export interface SourceCitation {
  document_id: string
  document_title: string
  document_type: string
  heading_context?: string
  chunk_text: string
  chunk_index: number
  score: number
  source_type: 'semantic' | 'keyword' | 'fuzzy' | 'sql'
  entity_name?: string
  application_id?: string
}

// ============================================================================
// Interrupts (HITL)
// ============================================================================

export interface InterruptPayload {
  type: 'confirmation' | 'clarification'
  action?: string
  question?: string
  options?: string[]
  context?: Record<string, unknown>
}

// ============================================================================
// Image Attachments
// ============================================================================

export interface PendingImage {
  id: string
  data: string // base64
  mediaType: string
  filename?: string
  previewUrl: string
}

// ============================================================================
// Chat Messages
// ============================================================================

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  images?: PendingImage[]
  tool_calls?: ToolCallInfo[]
  sources?: SourceCitation[]
  checkpoint_id?: string
  interrupted?: boolean
  interrupt_payload?: InterruptPayload
  isError?: boolean
  timestamp: number
}

// ============================================================================
// Navigation
// ============================================================================

export type NavigationTarget =
  | { type: 'task'; taskId: string; projectId: string; applicationId: string }
  | { type: 'document'; documentId: string; applicationId?: string; highlight?: HighlightParams }
  | { type: 'project'; projectId: string; applicationId: string }

export interface HighlightParams {
  headingContext?: string
  chunkText?: string
  chunkIndex?: number
  elementId?: string
}

// ============================================================================
// SSE Stream Events (discriminated union)
// ============================================================================

export interface TextDeltaEvent {
  event: 'text_delta'
  data: { content: string }
}

export interface ToolCallStartEvent {
  event: 'tool_call_start'
  data: { id: string; name: string }
}

export interface ToolCallEndEvent {
  event: 'tool_call_end'
  data: {
    id: string
    name: string
    summary?: string
    details?: string
    error?: string
  }
}

export interface RunStartedEvent {
  event: 'run_started'
  data: { thread_id: string }
}

export interface RunFinishedEvent {
  event: 'run_finished'
  data: {
    thread_id?: string
    checkpoint_id?: string
    sources?: SourceCitation[]
    interrupted?: boolean
    interrupt_payload?: InterruptPayload
  }
}

export interface InterruptEvent {
  event: 'interrupt'
  data: InterruptPayload & { thread_id?: string }
}

export interface ErrorEvent {
  event: 'error'
  data: { message: string; code?: string }
}

export interface EndEvent {
  event: 'end'
  data: Record<string, never>
}

export type ChatStreamEvent =
  | TextDeltaEvent
  | ToolCallStartEvent
  | ToolCallEndEvent
  | RunStartedEvent
  | RunFinishedEvent
  | InterruptEvent
  | ErrorEvent
  | EndEvent
