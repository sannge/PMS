/**
 * AI Sidebar Store
 *
 * Lightweight external store (no zustand dependency) using useSyncExternalStore.
 * Manages sidebar open/close state (persisted), chat messages,
 * thread tracking, streaming status, and rewind mode for time travel.
 *
 * Usage:
 *   const { isOpen, toggle, messages } = useAiSidebar()
 *   const isOpen = useAiSidebar((s) => s.isOpen)
 */

import { useSyncExternalStore, useRef, useCallback } from 'react'
import type { ChatMessage, TokenUsage } from './types'

// ============================================================================
// Types
// ============================================================================

interface AiSidebarData {
  isOpen: boolean
  messages: ChatMessage[]
  threadId: string | null
  isStreaming: boolean
  chatKey: number
  rewindCheckpointId: string | null
  rewindMessageIndex: number | null
  activeSessionId: string | null
  activeSessionTitle: string | null
  view: 'sessions' | 'chat'
  hasMoreMessages: boolean
  isLoadingMore: boolean
  tokenUsage: TokenUsage | null
  contextSummary: string | null
  summarizedAtSequence: number | null
  lastPersistedSequence: number | null
}

interface AiSidebarActions {
  toggle: () => void
  open: () => void
  close: () => void
  resetChat: () => void
  addMessage: (msg: ChatMessage) => void
  updateMessage: (id: string, updater: (msg: ChatMessage) => ChatMessage) => void
  updateLastAssistantMessage: (partial: Partial<ChatMessage>) => void
  setThreadId: (id: string) => void
  setIsStreaming: (val: boolean) => void
  enterRewindMode: (checkpointId: string, messageIndex: number) => void
  exitRewindMode: () => void
  trimMessagesAfter: (index: number) => void
  setActiveSession: (sessionId: string, threadId: string | null, title?: string) => void
  setView: (view: 'sessions' | 'chat') => void
  setHasMoreMessages: (val: boolean) => void
  setIsLoadingMore: (val: boolean) => void
  setTokenUsage: (usage: TokenUsage) => void
  setContextSummary: (summary: string, atSequence: number) => void
  setLastPersistedSequence: (seq: number) => void
  setActiveSessionTitle: (title: string) => void
  linkSession: (sessionId: string) => void
  loadMessages: (messages: ChatMessage[]) => void
  prependMessages: (messages: ChatMessage[]) => void
}

export type AiSidebarState = AiSidebarData & AiSidebarActions

// ============================================================================
// localStorage helpers
// ============================================================================

const SIDEBAR_OPEN_KEY = 'ai-sidebar-open'

function loadSidebarOpen(): boolean {
  try {
    const val = localStorage.getItem(SIDEBAR_OPEN_KEY)
    return val === 'true'
  } catch {
    return false
  }
}

function persistSidebarOpen(isOpen: boolean): void {
  try {
    localStorage.setItem(SIDEBAR_OPEN_KEY, String(isOpen))
  } catch {
    // ignore
  }
}

// ============================================================================
// External Store
// ============================================================================

type Listener = () => void

/** Tracks the index of the last assistant message to avoid scanning on every update */
let lastAssistantIdx = -1

let state: AiSidebarData = {
  isOpen: loadSidebarOpen(),
  messages: [],
  threadId: null,
  isStreaming: false,
  chatKey: 0,
  rewindCheckpointId: null,
  rewindMessageIndex: null,
  activeSessionId: null,
  activeSessionTitle: null,
  view: 'sessions' as const,
  hasMoreMessages: false,
  isLoadingMore: false,
  tokenUsage: null,
  contextSummary: null,
  summarizedAtSequence: null,
  lastPersistedSequence: null,
}

const listeners = new Set<Listener>()

function emit(): void {
  for (const l of listeners) l()
}

function setState(partial: Partial<AiSidebarData>): void {
  state = { ...state, ...partial }
  emit()
}

function subscribe(listener: Listener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

// Actions (stable references -- not recreated per render)
const actions: AiSidebarActions = {
  toggle: () => {
    const next = !state.isOpen
    persistSidebarOpen(next)
    setState({ isOpen: next })
  },
  open: () => {
    persistSidebarOpen(true)
    setState({ isOpen: true })
  },
  close: () => {
    persistSidebarOpen(false)
    setState({ isOpen: false })
  },
  resetChat: () => {
    lastAssistantIdx = -1
    setState({
      messages: [],
      threadId: null,
      isStreaming: false,
      rewindCheckpointId: null,
      rewindMessageIndex: null,
      chatKey: state.chatKey + 1,
      activeSessionId: null,
      activeSessionTitle: null,
      view: 'sessions' as const,
      tokenUsage: null,
      contextSummary: null,
      summarizedAtSequence: null,
      lastPersistedSequence: null,
      hasMoreMessages: false,
      isLoadingMore: false,
    })
  },
  addMessage: (msg: ChatMessage) => {
    const newMessages = [...state.messages, msg]
    const trimmed = newMessages.length > 200 ? newMessages.slice(-200) : newMessages
    if (msg.role === 'assistant') {
      lastAssistantIdx = trimmed.length - 1
    }
    setState({ messages: trimmed })
  },
  updateMessage: (id: string, updater: (msg: ChatMessage) => ChatMessage) => {
    setState({
      messages: state.messages.map((m) => (m.id === id ? updater(m) : m)),
    })
  },
  updateLastAssistantMessage: (partial: Partial<ChatMessage>) => {
    const idx = lastAssistantIdx
    if (idx < 0 || idx >= state.messages.length || state.messages[idx].role !== 'assistant') {
      // Fallback: scan backward if tracked index is stale
      for (let i = state.messages.length - 1; i >= 0; i--) {
        if (state.messages[i].role === 'assistant') {
          lastAssistantIdx = i
          const msgs = [...state.messages]
          msgs[i] = { ...msgs[i], ...partial }
          setState({ messages: msgs })
          return
        }
      }
      return
    }
    const msgs = [...state.messages]
    msgs[idx] = { ...msgs[idx], ...partial }
    setState({ messages: msgs })
  },
  setThreadId: (id: string) => {
    setState({ threadId: id })
  },
  setIsStreaming: (val: boolean) => {
    setState({ isStreaming: val })
  },
  enterRewindMode: (checkpointId: string, messageIndex: number) => {
    setState({ rewindCheckpointId: checkpointId, rewindMessageIndex: messageIndex })
  },
  exitRewindMode: () => {
    setState({ rewindCheckpointId: null, rewindMessageIndex: null })
  },
  trimMessagesAfter: (index: number) => {
    const trimmed = state.messages.slice(0, index + 1)
    // Recompute lastAssistantIdx for the trimmed set
    lastAssistantIdx = -1
    for (let i = trimmed.length - 1; i >= 0; i--) {
      if (trimmed[i].role === 'assistant') {
        lastAssistantIdx = i
        break
      }
    }
    setState({ messages: trimmed })
  },
  setActiveSession: (sessionId: string, threadId: string | null, title?: string) => {
    lastAssistantIdx = -1
    setState({
      activeSessionId: sessionId,
      activeSessionTitle: title ?? null,
      threadId,
      messages: [],
      tokenUsage: null,
      contextSummary: null,
      summarizedAtSequence: null,
      lastPersistedSequence: null,
    })
  },
  setView: (view: 'sessions' | 'chat') => {
    setState({ view })
  },
  setHasMoreMessages: (val: boolean) => {
    setState({ hasMoreMessages: val })
  },
  setIsLoadingMore: (val: boolean) => {
    setState({ isLoadingMore: val })
  },
  setTokenUsage: (usage: TokenUsage) => {
    setState({ tokenUsage: usage })
  },
  setContextSummary: (summary: string, atSequence: number) => {
    setState({ contextSummary: summary, summarizedAtSequence: atSequence })
  },
  setLastPersistedSequence: (seq: number) => {
    setState({ lastPersistedSequence: seq })
  },
  setActiveSessionTitle: (title: string) => {
    setState({ activeSessionTitle: title })
  },
  linkSession: (sessionId: string) => {
    // Associate current chat with a session ID without clearing messages.
    // Used when the backend assigns a session_id to a new conversation.
    setState({ activeSessionId: sessionId })
  },
  loadMessages: (messages: ChatMessage[]) => {
    lastAssistantIdx = -1
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'assistant') {
        lastAssistantIdx = i
        break
      }
    }
    setState({ messages })
  },
  prependMessages: (messages: ChatMessage[]) => {
    const combined = [...messages, ...state.messages]
    lastAssistantIdx = -1
    for (let i = combined.length - 1; i >= 0; i--) {
      if (combined[i].role === 'assistant') {
        lastAssistantIdx = i
        break
      }
    }
    setState({ messages: combined })
  },
}

// ============================================================================
// Hook
// ============================================================================

/**
 * Hook overloads:
 *   useAiSidebar()                  -> full AiSidebarState
 *   useAiSidebar(s => s.isOpen)     -> selected value (re-render skipped when slice unchanged)
 */
export function useAiSidebar(): AiSidebarState
export function useAiSidebar<T>(selector: (s: AiSidebarState) => T): T
export function useAiSidebar<T>(selector?: (s: AiSidebarState) => T): AiSidebarState | T {
  // Keep the selector in a ref so the getSnapshot callback is stable
  // but always applies the latest selector function.
  const selectorRef = useRef(selector)
  selectorRef.current = selector

  // Cache the last selected value so useSyncExternalStore can use Object.is
  // to skip re-renders when the selected slice hasn't changed.
  const lastSelectedRef = useRef<{ data: AiSidebarData; value: unknown } | null>(null)

  const getSelectedSnapshot = useCallback((): AiSidebarState | T => {
    const data = state // module-level state
    const sel = selectorRef.current

    if (!sel) {
      // Full-state mode: return merged object, but reuse it when data is the same
      const last = lastSelectedRef.current
      if (last && last.data === data) return last.value as AiSidebarState
      const merged = { ...data, ...actions }
      lastSelectedRef.current = { data, value: merged }
      return merged
    }

    // Selector mode: apply selector, reuse when result is the same
    const last = lastSelectedRef.current
    if (last && last.data === data) return last.value as T
    const selected = sel({ ...data, ...actions })
    lastSelectedRef.current = { data, value: selected }
    return selected
  }, [])

  return useSyncExternalStore(subscribe, getSelectedSnapshot, getSelectedSnapshot)
}

/**
 * Static getState for use outside React (e.g. keyboard shortcuts).
 */
useAiSidebar.getState = (): AiSidebarState => ({ ...state, ...actions })
