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
import type { ChatMessage } from './types'

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
}

interface AiSidebarActions {
  toggle: () => void
  open: () => void
  close: () => void
  resetChat: () => void
  addMessage: (msg: ChatMessage) => void
  updateLastAssistantMessage: (partial: Partial<ChatMessage>) => void
  setThreadId: (id: string) => void
  setIsStreaming: (val: boolean) => void
  enterRewindMode: (checkpointId: string, messageIndex: number) => void
  exitRewindMode: () => void
  trimMessagesAfter: (index: number) => void
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

let state: AiSidebarData = {
  isOpen: loadSidebarOpen(),
  messages: [],
  threadId: null,
  isStreaming: false,
  chatKey: 0,
  rewindCheckpointId: null,
  rewindMessageIndex: null,
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
    setState({
      messages: [],
      threadId: null,
      isStreaming: false,
      rewindCheckpointId: null,
      rewindMessageIndex: null,
      chatKey: state.chatKey + 1,
    })
  },
  addMessage: (msg: ChatMessage) => {
    setState({ messages: [...state.messages, msg] })
  },
  updateLastAssistantMessage: (partial: Partial<ChatMessage>) => {
    const msgs = [...state.messages]
    for (let i = msgs.length - 1; i >= 0; i--) {
      if (msgs[i].role === 'assistant') {
        msgs[i] = { ...msgs[i], ...partial }
        break
      }
    }
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
    setState({ messages: state.messages.slice(0, index + 1) })
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
