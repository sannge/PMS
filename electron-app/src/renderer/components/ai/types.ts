/**
 * AI Sidebar TypeScript Types
 *
 * Shared type definitions for the Blair AI copilot sidebar system.
 * Covers chat messages, activity timeline, source citations, SSE events,
 * HITL interrupts, image attachments, and navigation targets.
 */

// ============================================================================
// Activity Timeline (unified nodes + tool calls)
// ============================================================================

/** A single item in Blair's activity timeline — either a pipeline step or a tool call. */
export type ActivityItem =
  | { type: 'node'; node: string; label: string; status: 'active' | 'complete'; details?: string }
  | { type: 'tool'; id: string; name: string; status: 'running' | 'complete' | 'error';
      summary?: string; details?: string; error?: string }

// ============================================================================
// Tool Calls (kept for ToolExecutionCard compatibility)
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
// Search Selection (HITL)
// ============================================================================

export interface SearchSelectionItem {
  index: number
  title: string
  heading?: string
  snippet: string
  score: number
  document_id: string
}

// ============================================================================
// Interrupts (HITL)
// ============================================================================

export interface InterruptPayload {
  type: 'confirmation' | 'clarification' | 'selection'
  action?: string
  /** Summary text for confirmation actions (e.g., "Create task 'X' in Project Y") */
  summary?: string
  /** Structured details for confirmation actions (task_id, project_name, etc.) */
  details?: Record<string, unknown>
  question?: string
  options?: string[]
  /** Batch questions — sent when request_clarification returns multiple questions at once */
  questions?: Array<{ question: string; options?: string[] | null }>
  context?: Record<string, unknown>
  /** Prompt text for selection UI */
  prompt?: string
  /** Search result items for selection UI */
  items?: SearchSelectionItem[]
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

/** Stored image after send — base64 data stripped to free memory */
export type StoredImage = Omit<PendingImage, 'data'> & { data?: undefined; lightboxUrl?: string }

// ============================================================================
// Chat Messages
// ============================================================================

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  images?: (PendingImage | StoredImage)[]
  activity?: ActivityItem[]
  sources?: SourceCitation[]
  current_phase?: string
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
  | { type: 'task'; taskId: string; projectId?: string; applicationId?: string }
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
  data: { thread_id: string; session_id?: string }
}

export interface RunFinishedEvent {
  event: 'run_finished'
  data: {
    thread_id?: string
    session_id?: string
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

export interface ThinkingStepEvent {
  event: 'thinking_step'
  data: { type?: 'node'; node: string; label: string; status: 'active' | 'complete'; details?: string }
}

export interface EndEvent {
  event: 'end'
  data: Record<string, never>
}

export interface TokenUsageEvent {
  event: 'token_usage'
  data: { input_tokens: number; output_tokens: number; total_tokens: number; context_limit: number }
}

export interface ContextSummaryEvent {
  event: 'context_summary'
  data: { summary: string; up_to_sequence: number }
}

export interface PhaseChangedEvent {
  event: 'phase_changed'
  data: { phase: string; label: string }
}

export type ChatStreamEvent =
  | TextDeltaEvent
  | ToolCallStartEvent
  | ToolCallEndEvent
  | RunStartedEvent
  | RunFinishedEvent
  | InterruptEvent
  | ThinkingStepEvent
  | ErrorEvent
  | EndEvent
  | TokenUsageEvent
  | ContextSummaryEvent
  | PhaseChangedEvent

// ============================================================================
// Token Usage
// ============================================================================

export interface TokenUsage {
  inputTokens: number
  outputTokens: number
  totalTokens: number
  contextLimit: number
}

// ============================================================================
// Chat Session Summary
// ============================================================================

export interface ChatSessionSummary {
  id: string
  title: string
  createdAt: string
  updatedAt: string
  messageCount: number
  lastMessagePreview: string
  applicationId: string | null
  threadId: string | null
  totalInputTokens: number
  totalOutputTokens: number
  contextSummary: string | null
  summarizedAtSequence: number | null
}
