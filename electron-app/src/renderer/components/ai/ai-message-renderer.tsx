/**
 * AI Message Renderer
 *
 * Full-featured message renderer with premium styling.
 * User messages: right-aligned gradient bubbles with subtle shadow.
 * Assistant messages: left-aligned clean layout with accent details.
 * Handles markdown, clickable entity references, tool execution cards,
 * source citations, error styling, and rewind dimming.
 */

import React, { useState } from 'react'
import { Sparkles, AlertCircle, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { MarkdownRenderer } from './markdown-renderer'
import { ToolExecutionCard } from './tool-execution-card'
import { SourceCitationList } from './source-citation'
import { InterruptHandler } from './interrupt-handler'
import type { ChatMessage, NavigationTarget } from './types'

// ============================================================================
// Types
// ============================================================================

interface AiMessageRendererProps {
  message: ChatMessage
  onNavigate?: (target: NavigationTarget) => void
  onResolveInterrupt?: (response: Record<string, unknown>) => void
  isRewinding?: boolean
}

// ============================================================================
// Entity Reference Detection
// ============================================================================

const TASK_KEY_PATTERN = /\b([A-Z]{2,10}-\d+)\b/g

function renderContentWithEntities(
  content: string,
  onNavigate?: (target: NavigationTarget) => void
): React.ReactNode {
  if (!onNavigate) return content

  const parts: React.ReactNode[] = []
  let lastIndex = 0
  let match: RegExpExecArray | null

  TASK_KEY_PATTERN.lastIndex = 0

  while ((match = TASK_KEY_PATTERN.exec(content)) !== null) {
    if (match.index > lastIndex) {
      parts.push(content.slice(lastIndex, match.index))
    }

    const taskKey = match[1]
    parts.push(
      <button
        key={`entity-${match.index}`}
        type="button"
        onClick={() =>
          onNavigate({
            type: 'task',
            taskId: taskKey,
            projectId: '',
            applicationId: '',
          })
        }
        className={cn(
          'inline-flex items-center rounded px-1 py-0.5 -mx-0.5',
          'font-mono text-xs font-medium',
          'bg-primary/10 text-primary hover:bg-primary/20',
          'transition-colors cursor-pointer'
        )}
      >
        {taskKey}
      </button>
    )

    lastIndex = match.index + match[0].length
  }

  if (lastIndex < content.length) {
    parts.push(content.slice(lastIndex))
  }

  return parts.length > 0 ? <>{parts}</> : content
}

// ============================================================================
// Image Lightbox
// ============================================================================

function ImageLightbox({
  src,
  alt,
  onClose,
}: {
  src: string
  alt: string
  onClose: () => void
}): JSX.Element {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm"
      onClick={onClose}
    >
      <button
        type="button"
        onClick={onClose}
        className="absolute top-4 right-4 flex h-8 w-8 items-center justify-center rounded-full bg-white/10 text-white hover:bg-white/20 transition-colors"
        aria-label="Close image"
      >
        <X className="h-4 w-4" />
      </button>
      <img
        src={src}
        alt={alt}
        className="max-h-[85vh] max-w-[90vw] rounded-lg object-contain"
        onClick={(e) => e.stopPropagation()}
      />
    </div>
  )
}

// ============================================================================
// Chat Image Gallery
// ============================================================================

function ChatImageGallery({
  images,
}: {
  images: NonNullable<ChatMessage['images']>
}): JSX.Element {
  const [lightboxSrc, setLightboxSrc] = useState<{ src: string; alt: string } | null>(null)

  return (
    <>
      <div className="mb-2 flex flex-wrap gap-2">
        {images.map((img) => (
          <button
            key={img.id}
            type="button"
            onClick={() => setLightboxSrc({ src: img.previewUrl, alt: img.filename || 'Attached image' })}
            className="cursor-pointer rounded-lg overflow-hidden ring-1 ring-white/20 hover:ring-white/40 transition-all hover:scale-[1.02]"
          >
            <img
              src={img.previewUrl}
              alt={img.filename || 'Attached image'}
              className="max-h-48 max-w-[200px] rounded-lg object-cover"
            />
          </button>
        ))}
      </div>
      {lightboxSrc && (
        <ImageLightbox
          src={lightboxSrc.src}
          alt={lightboxSrc.alt}
          onClose={() => setLightboxSrc(null)}
        />
      )}
    </>
  )
}

// ============================================================================
// User Message
// ============================================================================

function UserMessage({
  message,
  onNavigate,
}: {
  message: ChatMessage
  onNavigate?: (target: NavigationTarget) => void
}): JSX.Element {
  return (
    <div className="flex w-full justify-end">
      <div
        className={cn(
          'max-w-[85%] rounded-2xl rounded-br-sm',
          'bg-gradient-to-br from-primary to-primary/85',
          'text-primary-foreground px-4 py-2.5',
          'text-sm leading-relaxed',
          'shadow-md shadow-primary/10'
        )}
      >
        {/* Image gallery with click-to-expand */}
        {message.images && message.images.length > 0 && (
          <ChatImageGallery images={message.images} />
        )}

        <p className="whitespace-pre-wrap break-words">
          {renderContentWithEntities(message.content, onNavigate)}
        </p>
      </div>
    </div>
  )
}

// ============================================================================
// Assistant Message
// ============================================================================

function AssistantMessage({
  message,
  onNavigate,
  onResolveInterrupt,
}: {
  message: ChatMessage
  onNavigate?: (target: NavigationTarget) => void
  onResolveInterrupt?: (response: Record<string, unknown>) => void
}): JSX.Element {
  const hasContent = !!message.content
  const hasTools = message.tool_calls && message.tool_calls.length > 0
  const hasSources = message.sources && message.sources.length > 0

  return (
    <div className="flex w-full justify-start gap-2.5">
      {/* Mini Blair avatar */}
      <div className="h-5 w-5 rounded-md bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center shadow-sm shadow-amber-500/15 shrink-0 mt-0.5">
        <Sparkles className="h-2.5 w-2.5 text-white" />
      </div>

      <div className="max-w-[calc(100%-2rem)] min-w-0 space-y-2 text-sm leading-relaxed overflow-hidden">
        {/* Tool execution cards */}
        {hasTools && (
          <div className="space-y-1.5">
            {message.tool_calls!.map((tc) => (
              <ToolExecutionCard key={tc.id} tool={tc} />
            ))}
          </div>
        )}

        {/* Markdown-rendered content */}
        {hasContent && (
          <div className="text-foreground">
            <MarkdownRenderer content={message.content} />
          </div>
        )}

        {/* HITL Interrupt Card */}
        {message.interrupted && message.interrupt_payload && onResolveInterrupt && (
          <InterruptHandler
            message={message}
            onResolve={onResolveInterrupt}
          />
        )}

        {/* Source citations */}
        {hasSources && (
          <SourceCitationList
            sources={message.sources!}
            onNavigate={onNavigate}
          />
        )}
      </div>
    </div>
  )
}

// ============================================================================
// Error Message
// ============================================================================

function ErrorMessage({ message }: { message: ChatMessage }): JSX.Element {
  return (
    <div className="flex w-full justify-start gap-2.5">
      <div className="h-5 w-5 rounded-md bg-red-500/15 flex items-center justify-center shrink-0 mt-0.5">
        <AlertCircle className="h-3 w-3 text-red-500" />
      </div>
      <div
        className={cn(
          'max-w-[calc(100%-2rem)] min-w-0 rounded-xl',
          'border border-red-500/20 bg-red-500/5',
          'px-3.5 py-2.5 text-sm leading-relaxed'
        )}
      >
        <p className="text-red-500 whitespace-pre-wrap break-words">
          {message.content}
        </p>
      </div>
    </div>
  )
}

// ============================================================================
// Main Component
// ============================================================================

export function AiMessageRenderer({
  message,
  onNavigate,
  onResolveInterrupt,
  isRewinding,
}: AiMessageRendererProps): JSX.Element {
  const isError = message.isError === true

  return (
    <div
      className={cn(
        'transition-opacity duration-200',
        isRewinding && 'opacity-40'
      )}
    >
      {message.role === 'user' && (
        <UserMessage message={message} onNavigate={onNavigate} />
      )}
      {message.role === 'assistant' && !isError && (
        <AssistantMessage
          message={message}
          onNavigate={onNavigate}
          onResolveInterrupt={onResolveInterrupt}
        />
      )}
      {message.role === 'assistant' && isError && (
        <ErrorMessage message={message} />
      )}
    </div>
  )
}
