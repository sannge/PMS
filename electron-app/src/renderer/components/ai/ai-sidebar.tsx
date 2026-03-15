/**
 * AI Sidebar Component
 *
 * The main Blair AI copilot sidebar panel. Fixed on the right side of the viewport,
 * resizable via drag handle, with branded header, scrollable message area,
 * animated streaming indicator, suggestion chips, and modern chat input.
 *
 * Supports rewind mode (time travel): clicking the rewind icon on an assistant
 * message dims subsequent messages and shows a banner above the chat input.
 * Sending a new message in rewind mode branches the conversation from that point.
 */

import { useEffect, useRef, useCallback, memo } from 'react'
import {
  X,
  RotateCcw,
  Sparkles,
  BarChart3,
  ListChecks,
  Users,
  Lightbulb,
  ArrowRight,
  ChevronLeft,
  Plus,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'
import { useAiSidebar } from './use-ai-sidebar'
import { useAiSidebarWidth } from './use-ai-sidebar-width'
import { useAiChat } from './use-ai-chat'
import { ChatInput, type ChatInputHandle } from './chat-input'
import { AiMessageRenderer } from './ai-message-renderer'
import { RewindBanner } from './rewind-ui'
import { UserChatOverrideButton } from './user-chat-override'
import type { ChatSessionSummary, NavigationTarget } from './types'
import { ChatSessionList } from './chat-session-list'
import { ChatSkeleton } from './chat-skeleton'
import { TokenUsageBar } from './token-usage-bar'
import { ContextSummaryDivider } from './context-summary-divider'
import { useChatMessages, useChatSessions } from '@/hooks/use-chat-sessions'
import { useQueryClient } from '@tanstack/react-query'
import { queryKeys } from '@/lib/query-client'
import { setPendingAiNavigation, requestScreenSwitch } from '@/lib/ai-navigation'
import './ai-styles.css'

// ============================================================================
// Suggestions
// ============================================================================

const SUGGESTIONS = [
  { icon: BarChart3, text: "What's the status of my projects?", gradient: 'from-blue-500/10 to-cyan-500/5' },
  { icon: ListChecks, text: 'Show me overdue tasks', gradient: 'from-amber-500/10 to-orange-500/5' },
  { icon: Users, text: "Who's available on my team?", gradient: 'from-emerald-500/10 to-teal-500/5' },
  { icon: Lightbulb, text: 'Summarize recent activity', gradient: 'from-purple-500/10 to-violet-500/5' },
]

// ============================================================================
// Streaming Indicator
// ============================================================================

function StreamingIndicator(): JSX.Element {
  return (
    <div className="blair-msg-enter flex items-center gap-3 px-4 py-3">
      <div className="h-5 w-5 rounded-md bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center shadow-sm shadow-amber-500/20 blair-avatar-glow">
        <Sparkles className="h-2.5 w-2.5 text-white" />
      </div>
      <div className="flex items-center gap-1">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="blair-thinking-dot h-1.5 w-1.5 rounded-full bg-gradient-to-r from-amber-400 to-orange-500"
            style={{ animationDelay: `${i * 0.2}s` }}
          />
        ))}
      </div>
      <span className="text-xs text-muted-foreground">Thinking...</span>
    </div>
  )
}

// ============================================================================
// Message List (extracted to subscribe only to messages, avoiding full-store
// re-renders during streaming when only the message content changes)
// ============================================================================

interface MessageListProps {
  rewindMessageIndex: number | null
  onNavigate: (target: NavigationTarget) => void
  onResolveInterrupt: (response: Record<string, unknown>) => Promise<void>
  onRewind: (index: number) => void
}

const MessageList = memo(function MessageList({
  rewindMessageIndex,
  onNavigate,
  onResolveInterrupt,
  onRewind,
}: MessageListProps): JSX.Element {
  const messages = useAiSidebar(s => s.messages)
  const isStreaming = useAiSidebar(s => s.isStreaming)

  return (
    <>
      {messages.map((msg, index) => (
        <div
          key={msg.id}
          className={cn(
            'group relative blair-msg-enter min-w-0',
            rewindMessageIndex !== null && index > rewindMessageIndex && 'blair-rewind-dimmed'
          )}
          style={{ animationDelay: `${Math.min(index * 0.05, 0.3)}s` }}
        >
          <AiMessageRenderer
            message={msg}
            onNavigate={onNavigate}
            onResolveInterrupt={onResolveInterrupt}
            isRewinding={
              rewindMessageIndex !== null && index > rewindMessageIndex
            }
          />
          {/* Rewind icon on assistant messages with checkpoint */}
          {msg.role === 'assistant' &&
            msg.checkpoint_id &&
            !isStreaming &&
            rewindMessageIndex === null && (
              <div className="absolute top-0 right-0">
                <button
                  type="button"
                  onClick={() => onRewind(index)}
                  className={cn(
                    'flex h-6 w-6 items-center justify-center rounded-full',
                    'bg-background border border-border shadow-sm',
                    'opacity-0 group-hover:opacity-100',
                    'transition-opacity duration-150',
                    'hover:bg-accent hover:text-accent-foreground',
                    'focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'
                  )}
                  aria-label="Rewind conversation to this message"
                >
                  <RotateCcw className="h-3 w-3" />
                </button>
              </div>
            )}
        </div>
      ))}
    </>
  )
})

// ============================================================================
// AI Sidebar
// ============================================================================

export function AiSidebar(): JSX.Element | null {
  const queryClient = useQueryClient()
  // Single subscription instead of 10+ separate useAiSidebar
  // selectors, each of which created its own useSyncExternalStore subscription.
  const {
    isOpen, close, resetChat, messages, isStreaming, chatKey,
    threadId, rewindMessageIndex, rewindCheckpointId,
    enterRewindMode, exitRewindMode,
    activeSessionId, activeSessionTitle, view, setActiveSession, setView,
    hasMoreMessages, contextSummary, loadMessages, setHasMoreMessages,
    isLoadingMore, setIsLoadingMore,
  } = useAiSidebar()
  const { width, onResizeStart } = useAiSidebarWidth()
  const { sendMessage, resumeInterrupt, sendReplayMessage, cancelStream } = useAiChat()
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const chatInputRef = useRef<ChatInputHandle>(null)
  const scrollContainerElRef = useRef<HTMLElement | null>(null)
  const scrollAreaRootRef = useRef<HTMLDivElement | null>(null)

  const threadIdRef = useRef(threadId)
  threadIdRef.current = threadId

  const enterRewindModeRef = useRef(enterRewindMode)
  enterRewindModeRef.current = enterRewindMode

  const handleResolveInterrupt = useCallback(
    async (response: Record<string, unknown>) => {
      if (!threadIdRef.current) return
      try {
        await resumeInterrupt(threadIdRef.current, response)
      } catch (err) {
        console.error('[AiSidebar] Resume failed:', err)
      }
    },
    [resumeInterrupt]
  )

  const handleNavigate = useCallback((target: NavigationTarget) => {
    if (target.type === 'document') {
      setPendingAiNavigation(target)
      requestScreenSwitch('notes')
    }
  }, [])

  const handleRewind = useCallback(
    (messageIndex: number) => {
      const msg = useAiSidebar.getState().messages[messageIndex]
      if (!msg?.checkpoint_id) return
      enterRewindModeRef.current(msg.checkpoint_id, messageIndex)
    },
    []
  )

  const handleReplaySend = useCallback(
    (text: string) => {
      if (rewindMessageIndex === null || !rewindCheckpointId) return
      const store = useAiSidebar.getState()
      store.trimMessagesAfter(rewindMessageIndex)
      store.exitRewindMode()
      sendReplayMessage(text, rewindCheckpointId)
    },
    [rewindMessageIndex, rewindCheckpointId, sendReplayMessage]
  )

  const handleSelectSession = useCallback(
    (session: ChatSessionSummary) => {
      cancelStream()
      initialScrollSettledRef.current = false
      // Remove potentially stale cached messages so the query refetches fresh
      queryClient.removeQueries({ queryKey: queryKeys.chatMessages(session.id) })
      setActiveSession(session.id, session.threadId, session.title)
      setView('chat')
      // Auto-focus chat input after switching to session
      setTimeout(() => chatInputRef.current?.focus(), 150)
    },
    [cancelStream, queryClient, setActiveSession, setView]
  )

  const handleNewChat = useCallback(() => {
    resetChat()
    setView('chat')
    setTimeout(() => chatInputRef.current?.focus(), 150)
  }, [resetChat, setView])

  const handleBackToSessions = useCallback(() => {
    cancelStream()
    prevSessionRef.current = null
    // Clear active session so re-clicking the same session triggers message reload
    useAiSidebar.getState().resetChat()
  }, [cancelStream])

  // Sync session title from the sessions list (picks up LLM-generated titles).
  // Read activeSessionTitle from store directly (not reactive) to avoid a
  // setState → dep change → re-run cycle that triggers "Maximum update depth exceeded".
  const sessionsQuery = useChatSessions()
  useEffect(() => {
    if (!activeSessionId || !sessionsQuery.data) return
    const session = sessionsQuery.data.sessions.find((s) => s.id === activeSessionId)
    const currentTitle = useAiSidebar.getState().activeSessionTitle
    if (session && session.title !== currentTitle) {
      useAiSidebar.getState().setActiveSessionTitle(session.title)
    }
  }, [activeSessionId, sessionsQuery.data])

  // Fetch messages when switching to a session
  const messagesQuery = useChatMessages(view === 'chat' ? activeSessionId : null)

  // Hydrate messages from query into store (only for user-selected sessions).
  // Skip when messages already exist in memory — this prevents a newly linked
  // session (created inline during streaming) from being overwritten by a DB
  // fetch that returns 0 messages (not yet persisted).
  const prevSessionRef = useRef<string | null>(null)
  useEffect(() => {
    // Reset tracking when user navigates back to session list so re-selecting
    // the same session triggers hydration again.
    if (!activeSessionId) {
      prevSessionRef.current = null
      return
    }
    if (activeSessionId !== prevSessionRef.current && messagesQuery.data) {
      // If messages are already in memory (e.g. from an active or just-finished
      // stream), don't overwrite them with the DB fetch.  The DB may not have
      // the messages yet (persist happens in onRunFinished).
      const currentMessages = useAiSidebar.getState().messages
      if (currentMessages.length > 0) {
        prevSessionRef.current = activeSessionId
        return
      }
      prevSessionRef.current = activeSessionId
      const allMessages = messagesQuery.data.pages.slice().reverse().flatMap((p) => p.messages)
      const mapped = allMessages.map((m) => ({
        id: m.id,
        role: m.role as 'user' | 'assistant',
        content: m.content,
        sources: (m.sources as import('./types').SourceCitation[] | undefined) ?? undefined,
        checkpoint_id: m.checkpoint_id ?? undefined,
        isError: m.is_error,
        timestamp: new Date(m.created_at).getTime(),
      }))
      loadMessages(mapped)
      const lastPage = messagesQuery.data.pages[messagesQuery.data.pages.length - 1]
      setHasMoreMessages(lastPage?.has_more ?? false)
      // Delay sentinel observation until initial scroll settles
      initialScrollSettledRef.current = false
      requestAnimationFrame(() => {
        initialScrollSettledRef.current = true
      })
    }
    // StrictMode: reset ref on cleanup so the second mount re-evaluates hydration
    return () => { prevSessionRef.current = null }
  }, [activeSessionId, messagesQuery.data, loadMessages, setHasMoreMessages])

  // Infinite scroll sentinel
  const sentinelRef = useRef<HTMLDivElement>(null)
  const initialScrollSettledRef = useRef(false)

  // Stable refs for IntersectionObserver callback (avoid teardown on every render)
  const hasMoreRef = useRef(hasMoreMessages)
  hasMoreRef.current = hasMoreMessages
  const isLoadingMoreRef = useRef(isLoadingMore)
  isLoadingMoreRef.current = isLoadingMore
  const messagesQueryRef = useRef(messagesQuery)
  messagesQueryRef.current = messagesQuery

  useEffect(() => {
    if (view !== 'chat') return
    // Resolve the scroll viewport from the ScrollArea root on mount.
    // Done here (not in a ref callback) to avoid calling setState during
    // React's commit phase, which caused "Maximum update depth exceeded".
    const root = scrollAreaRootRef.current
    const viewport = root?.querySelector('[data-radix-scroll-area-viewport]') as HTMLElement | null
    scrollContainerElRef.current = viewport
    if (!viewport) return
    const sentinel = sentinelRef.current
    if (!sentinel) return

    const observer = new IntersectionObserver(
      (entries) => {
        if (!initialScrollSettledRef.current) return
        if (
          entries[0].isIntersecting &&
          hasMoreRef.current &&
          !isLoadingMoreRef.current &&
          !messagesQueryRef.current.isFetchingNextPage
        ) {
          setIsLoadingMore(true)
          const el = scrollContainerElRef.current
          if (!el) {
            setIsLoadingMore(false)
            return
          }
          const prevHeight = el.scrollHeight
          messagesQueryRef.current.fetchNextPage().then(() => {
            requestAnimationFrame(() => {
              const newHeight = el.scrollHeight
              el.scrollTop += newHeight - prevHeight
              setIsLoadingMore(false)
            })
          }).catch(() => setIsLoadingMore(false))
        }
      },
      { root: viewport, threshold: 0.1 }
    )
    observer.observe(sentinel)
    return () => observer.disconnect()
    // chatKey changes when resetChat is called (new ScrollArea mounts)
  }, [view, chatKey, setIsLoadingMore])

  const handleSuggestionClick = useCallback(
    (text: string) => {
      sendMessage(text)
    },
    [sendMessage]
  )

  // Track whether the user is near the bottom of the scroll container.
  // Only auto-scroll when they haven't scrolled up to read earlier messages.
  const isNearBottomRef = useRef(true)

  useEffect(() => {
    if (view !== 'chat') return
    const el = scrollContainerElRef.current
    if (!el) return
    const handleScroll = () => {
      const threshold = 80 // px from bottom
      isNearBottomRef.current =
        el.scrollHeight - el.scrollTop - el.clientHeight < threshold
    }
    el.addEventListener('scroll', handleScroll, { passive: true })
    return () => el.removeEventListener('scroll', handleScroll)
  }, [view, chatKey])

  // Auto-scroll to bottom when messages are added or streaming, if user is near bottom
  const prevMsgCountRef = useRef(messages.length)
  useEffect(() => {
    if (isNearBottomRef.current && (messages.length >= prevMsgCountRef.current || isStreaming)) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
    prevMsgCountRef.current = messages.length
  }, [messages.length, isStreaming])

  // Focus chat input when sidebar opens
  useEffect(() => {
    if (isOpen) {
      const timer = setTimeout(() => chatInputRef.current?.focus(), 100)
      return () => clearTimeout(timer)
    }
  }, [isOpen])

  // Refocus chat input when streaming finishes
  const wasStreamingRef = useRef(false)
  useEffect(() => {
    if (wasStreamingRef.current && !isStreaming) {
      chatInputRef.current?.focus()
    }
    wasStreamingRef.current = isStreaming
  }, [isStreaming])

  // Global keyboard shortcut: Ctrl+Shift+A
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.shiftKey && e.key === 'A') {
        e.preventDefault()
        useAiSidebar.getState().toggle()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  if (!isOpen) return null

  return (
    <div
      role="complementary"
      aria-label="AI Assistant"
      className="blair-sidebar relative flex flex-col border-l border-border/50 bg-background shrink-0 overflow-hidden"
      style={{ width }}
    >
      {/* Resize drag handle */}
      <div
        onPointerDown={onResizeStart}
        className={cn(
          'absolute left-0 top-0 bottom-0 w-1 z-10',
          'cursor-col-resize hover:bg-primary/20 active:bg-primary/30',
          'transition-colors duration-150'
        )}
      />

      {/* Header */}
      <div className="relative shrink-0">
        {/* Animated gradient accent bar */}
        <div className="blair-accent-bar h-[2px]" />

        <div className="flex items-center justify-between px-4 py-3 border-b border-border/40">
          <div className="flex items-center gap-2.5">
            {view === 'chat' ? (
              <>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={handleBackToSessions}
                  className="h-7 w-7 rounded-lg hover:bg-muted/80"
                  aria-label="Back to sessions"
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <div className="min-w-0">
                  <h2 className="text-sm font-semibold text-foreground leading-none truncate max-w-[180px]">
                    {activeSessionTitle || 'New Chat'}
                  </h2>
                  <p className="text-[10px] text-muted-foreground/60 mt-0.5">Blair</p>
                </div>
              </>
            ) : (
              <>
                <div className="relative">
                  <div className="h-7 w-7 rounded-lg bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center shadow-lg shadow-amber-500/25">
                    <Sparkles className="h-3.5 w-3.5 text-white" />
                  </div>
                  <span className="absolute -bottom-0.5 -right-0.5 h-2 w-2 rounded-full bg-emerald-400 ring-[1.5px] ring-background" />
                </div>
                <div>
                  <h2 className="text-sm font-semibold text-foreground leading-none">Blair</h2>
                  <p className="text-[10px] text-muted-foreground/60 mt-0.5">AI Assistant</p>
                </div>
              </>
            )}
          </div>
          <div className="flex items-center gap-0.5">
            <Button
              variant="ghost"
              size="icon"
              onClick={handleNewChat}
              className="h-7 w-7 rounded-lg hover:bg-muted/80"
              aria-label="New chat"
            >
              <Plus className="h-3.5 w-3.5" />
            </Button>
            <UserChatOverrideButton />
            <Button
              variant="ghost"
              size="icon"
              onClick={close}
              className="h-7 w-7 rounded-lg hover:bg-muted/80"
              aria-label="Close sidebar"
            >
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </div>

      {/* Body */}
      {view === 'sessions' ? (
        <ChatSessionList onSelectSession={handleSelectSession} />
      ) : (
      <>
      <ScrollArea className="flex-1" key={chatKey} ref={scrollAreaRootRef}>
        <div className="flex flex-col gap-3 p-4 overflow-hidden select-text cursor-text" aria-live={isStreaming ? 'off' : 'polite'}>
          {/* Infinite scroll sentinel */}
          {hasMoreMessages && (
            <div ref={sentinelRef} className="flex justify-center py-2">
              {isLoadingMore && (
                <div className="flex items-center gap-1">
                  {[0, 1, 2].map((i) => (
                    <span key={i} className="h-1.5 w-1.5 rounded-full bg-muted-foreground/40 animate-pulse" style={{ animationDelay: `${i * 0.2}s` }} />
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Context summary divider */}
          {contextSummary && <ContextSummaryDivider summary={contextSummary} />}

          {/* Loading skeleton for session switch */}
          {activeSessionId && messagesQuery.isLoading && messages.length === 0 && <ChatSkeleton />}

          {/* Empty state with suggestions */}
          {messages.length === 0 && !activeSessionId && !messagesQuery.isLoading && (
            <div className="flex flex-col items-center py-8 px-1">
              {/* Animated hero */}
              <div className="relative mb-6">
                <div className="h-16 w-16 rounded-2xl bg-gradient-to-br from-amber-400/15 to-orange-500/10 flex items-center justify-center">
                  <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center shadow-xl shadow-amber-500/25 blair-avatar-glow">
                    <Sparkles className="h-5 w-5 text-white" />
                  </div>
                </div>
                {/* Decorative floating particles */}
                <div className="absolute -top-1 right-0 h-2 w-2 rounded-full bg-amber-400/60 blair-float" />
                <div
                  className="absolute bottom-0 -left-2 h-1.5 w-1.5 rounded-full bg-orange-400/40 blair-float"
                  style={{ animationDelay: '1.2s' }}
                />
                <div
                  className="absolute top-3 -right-3 h-1 w-1 rounded-full bg-amber-300/50 blair-float"
                  style={{ animationDelay: '0.6s' }}
                />
              </div>

              <h3 className="text-base font-semibold text-foreground">Hey, I'm Blair</h3>
              <p className="mt-1.5 text-xs text-muted-foreground max-w-[220px] text-center leading-relaxed">
                Your AI copilot for projects, tasks, and documents
              </p>

              {/* Suggestion chips */}
              <div className="mt-8 w-full space-y-2">
                <p className="text-[10px] font-medium uppercase tracking-widest text-muted-foreground/50 px-1">
                  Suggestions
                </p>
                {SUGGESTIONS.map((s) => {
                  const Icon = s.icon
                  return (
                    <button
                      key={s.text}
                      type="button"
                      onClick={() => handleSuggestionClick(s.text)}
                      className={cn(
                        'group flex w-full items-center gap-3 rounded-xl px-3 py-2.5',
                        'border border-border/40 bg-gradient-to-r',
                        s.gradient,
                        'hover:border-amber-400/30 hover:shadow-sm hover:shadow-amber-500/5',
                        'transition-all duration-200 text-left'
                      )}
                    >
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-background/80 border border-border/30 shadow-sm">
                        <Icon className="h-4 w-4 text-muted-foreground group-hover:text-foreground transition-colors" />
                      </div>
                      <span className="text-xs text-foreground/70 group-hover:text-foreground transition-colors flex-1">
                        {s.text}
                      </span>
                      <ArrowRight className="h-3 w-3 text-muted-foreground/0 group-hover:text-muted-foreground/60 transition-all group-hover:translate-x-0.5" />
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          <MessageList
            rewindMessageIndex={rewindMessageIndex}
            onNavigate={handleNavigate}
            onResolveInterrupt={handleResolveInterrupt}
            onRewind={handleRewind}
          />

          {isStreaming && <StreamingIndicator />}

          <div ref={messagesEndRef} />
        </div>
      </ScrollArea>

      {/* Token Usage Bar */}
      <TokenUsageBar />

      {/* Rewind Banner */}
      {rewindMessageIndex !== null && messages[rewindMessageIndex] && (
        <RewindBanner
          messagePreview={messages[rewindMessageIndex].content}
          onCancel={exitRewindMode}
        />
      )}

      {/* Chat Input */}
      <ChatInput ref={chatInputRef} onReplaySend={rewindMessageIndex !== null ? handleReplaySend : undefined} onCancelStream={cancelStream} />
      </>
      )}
    </div>
  )
}
