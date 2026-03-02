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

import { useEffect, useRef, useCallback } from 'react'
import {
  X,
  RotateCcw,
  Sparkles,
  BarChart3,
  ListChecks,
  Users,
  Lightbulb,
  ArrowRight,
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
import type { NavigationTarget } from './types'
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
// AI Sidebar
// ============================================================================

export function AiSidebar(): JSX.Element | null {
  const {
    isOpen,
    close,
    resetChat,
    messages,
    isStreaming,
    chatKey,
    threadId,
    rewindMessageIndex,
    rewindCheckpointId,
    enterRewindMode,
    exitRewindMode,
  } = useAiSidebar()
  const { width, onResizeStart } = useAiSidebarWidth()
  const { sendMessage, resumeInterrupt, sendReplayMessage, cancelStream } = useAiChat()
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const chatInputRef = useRef<ChatInputHandle>(null)

  const handleResolveInterrupt = useCallback(
    async (response: Record<string, unknown>) => {
      if (!threadId) return
      try {
        await resumeInterrupt(threadId, response)
      } catch (err) {
        console.error('[AiSidebar] Resume failed:', err)
      }
    },
    [threadId, resumeInterrupt]
  )

  const handleNavigate = useCallback((target: NavigationTarget) => {
    if (target.type === 'document') {
      setPendingAiNavigation(target)
      requestScreenSwitch('notes')
    }
  }, [])

  const handleRewind = useCallback(
    (messageIndex: number) => {
      const msg = messages[messageIndex]
      if (!msg?.checkpoint_id) return
      enterRewindMode(msg.checkpoint_id, messageIndex)
    },
    [messages, enterRewindMode]
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

  const handleSuggestionClick = useCallback(
    (text: string) => {
      sendMessage(text)
    },
    [sendMessage]
  )

  // Auto-scroll to bottom when messages are added or streaming
  const prevMsgCountRef = useRef(messages.length)
  useEffect(() => {
    if (messages.length >= prevMsgCountRef.current || isStreaming) {
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
            {/* Blair avatar with glow */}
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
          </div>
          <div className="flex items-center gap-0.5">
            <Button
              variant="ghost"
              size="icon"
              onClick={resetChat}
              className="h-7 w-7 rounded-lg hover:bg-muted/80"
              aria-label="New chat"
            >
              <RotateCcw className="h-3.5 w-3.5" />
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

      {/* Messages */}
      <ScrollArea className="flex-1" key={chatKey}>
        <div className="flex flex-col gap-3 p-4 overflow-hidden select-text cursor-text" aria-live={isStreaming ? 'off' : 'polite'}>
          {/* Empty state with suggestions */}
          {messages.length === 0 && (
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
                {SUGGESTIONS.map((s, i) => {
                  const Icon = s.icon
                  return (
                    <button
                      key={i}
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
                onNavigate={handleNavigate}
                onResolveInterrupt={handleResolveInterrupt}
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
                      onClick={() => handleRewind(index)}
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

          {isStreaming && <StreamingIndicator />}

          <div ref={messagesEndRef} />
        </div>
      </ScrollArea>

      {/* Rewind Banner */}
      {rewindMessageIndex !== null && messages[rewindMessageIndex] && (
        <RewindBanner
          messagePreview={messages[rewindMessageIndex].content}
          onCancel={exitRewindMode}
        />
      )}

      {/* Chat Input */}
      <ChatInput ref={chatInputRef} onReplaySend={rewindMessageIndex !== null ? handleReplaySend : undefined} onCancelStream={cancelStream} />
    </div>
  )
}
