/**
 * CommentInput Component
 *
 * Input field for creating new comments with @mention support.
 * Features:
 * - Textarea with auto-resize
 * - @mention trigger and autocomplete
 * - Submit on Ctrl+Enter
 * - Character count
 * - Loading state
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import { cn } from '@/lib/utils'
import { Send, Loader2, AtSign } from 'lucide-react'

// ============================================================================
// Types
// ============================================================================

export interface MentionSuggestion {
  id: string
  name: string
  email?: string
  avatar_url?: string
}

export interface CommentInputProps {
  onSubmit: (content: { body_text: string; body_json?: Record<string, unknown> }) => void
  placeholder?: string
  disabled?: boolean
  isSubmitting?: boolean
  mentionSuggestions?: MentionSuggestion[]
  onMentionSearch?: (query: string) => void
  onTyping?: () => void
  className?: string
}

// ============================================================================
// Constants
// ============================================================================

const MAX_COMMENT_LENGTH = 10000
const MENTION_TRIGGER = '@'
const TYPING_DEBOUNCE_MS = 2000

// ============================================================================
// Component
// ============================================================================

export function CommentInput({
  onSubmit,
  placeholder = 'Write a comment... (@ to mention)',
  disabled = false,
  isSubmitting = false,
  mentionSuggestions = [],
  onMentionSearch,
  onTyping,
  className,
}: CommentInputProps): JSX.Element {
  const [text, setText] = useState('')
  const [showMentions, setShowMentions] = useState(false)
  const [mentionQuery, setMentionQuery] = useState('')
  const [selectedMentionIndex, setSelectedMentionIndex] = useState(0)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const mentionStartRef = useRef<number | null>(null)
  const lastTypingRef = useRef<number>(0)

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current
    if (textarea) {
      textarea.style.height = 'auto'
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`
    }
  }, [text])

  // Handle text change and mention detection
  const handleTextChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      const newText = e.target.value
      setText(newText)

      // Emit typing indicator (debounced)
      if (onTyping && newText.length > 0) {
        const now = Date.now()
        if (now - lastTypingRef.current > TYPING_DEBOUNCE_MS) {
          lastTypingRef.current = now
          onTyping()
        }
      }

      // Check for @ mention trigger
      const cursorPos = e.target.selectionStart || 0
      const textBeforeCursor = newText.substring(0, cursorPos)
      const lastAtIndex = textBeforeCursor.lastIndexOf(MENTION_TRIGGER)

      if (lastAtIndex !== -1) {
        const textAfterAt = textBeforeCursor.substring(lastAtIndex + 1)
        // Check if this is a valid mention context (no spaces in the query)
        if (!textAfterAt.includes(' ') && !textAfterAt.includes('\n')) {
          mentionStartRef.current = lastAtIndex
          setMentionQuery(textAfterAt)
          setShowMentions(true)
          setSelectedMentionIndex(0)
          if (onMentionSearch) {
            onMentionSearch(textAfterAt)
          }
          return
        }
      }

      setShowMentions(false)
      mentionStartRef.current = null
    },
    [onMentionSearch, onTyping]
  )

  // Insert mention
  const insertMention = useCallback(
    (suggestion: MentionSuggestion) => {
      if (mentionStartRef.current === null) return

      const beforeMention = text.substring(0, mentionStartRef.current)
      const cursorPos = textareaRef.current?.selectionStart || text.length
      const afterMention = text.substring(cursorPos)

      const newText = `${beforeMention}@${suggestion.name} ${afterMention}`
      setText(newText)
      setShowMentions(false)
      mentionStartRef.current = null

      // Focus and position cursor
      setTimeout(() => {
        if (textareaRef.current) {
          const newCursorPos = beforeMention.length + suggestion.name.length + 2
          textareaRef.current.focus()
          textareaRef.current.setSelectionRange(newCursorPos, newCursorPos)
        }
      }, 0)
    },
    [text]
  )

  // Handle keyboard navigation for mentions
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (showMentions && mentionSuggestions.length > 0) {
        if (e.key === 'ArrowDown') {
          e.preventDefault()
          setSelectedMentionIndex((i) =>
            i < mentionSuggestions.length - 1 ? i + 1 : 0
          )
          return
        }
        if (e.key === 'ArrowUp') {
          e.preventDefault()
          setSelectedMentionIndex((i) =>
            i > 0 ? i - 1 : mentionSuggestions.length - 1
          )
          return
        }
        if (e.key === 'Enter' || e.key === 'Tab') {
          e.preventDefault()
          insertMention(mentionSuggestions[selectedMentionIndex])
          return
        }
        if (e.key === 'Escape') {
          e.preventDefault()
          setShowMentions(false)
          return
        }
      }

      // Submit on Ctrl+Enter or Cmd+Enter
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault()
        handleSubmit()
      }
    },
    [showMentions, mentionSuggestions, selectedMentionIndex, insertMention]
  )

  // Handle submit
  const handleSubmit = useCallback(() => {
    const trimmedText = text.trim()
    if (!trimmedText || disabled || isSubmitting) return

    // Build simple content object
    onSubmit({ body_text: trimmedText })
    setText('')
    setShowMentions(false)
  }, [text, disabled, isSubmitting, onSubmit])

  const isOverLimit = text.length > MAX_COMMENT_LENGTH
  const canSubmit = text.trim().length > 0 && !isOverLimit && !disabled && !isSubmitting

  return (
    <div className={cn('relative', className)}>
      {/* Mention suggestions dropdown */}
      {showMentions && mentionSuggestions.length > 0 && (
        <div
          className={cn(
            'absolute bottom-full left-0 mb-1 w-64 max-h-48 overflow-y-auto',
            'rounded-md border border-border bg-popover shadow-lg',
            'z-50'
          )}
        >
          {mentionSuggestions.map((suggestion, index) => (
            <button
              key={suggestion.id}
              onClick={() => insertMention(suggestion)}
              className={cn(
                'flex w-full items-center gap-2 px-3 py-2 text-left',
                'text-sm transition-colors',
                index === selectedMentionIndex
                  ? 'bg-accent text-accent-foreground'
                  : 'hover:bg-muted'
              )}
            >
              {suggestion.avatar_url ? (
                <img
                  src={suggestion.avatar_url}
                  alt={suggestion.name}
                  className="h-6 w-6 rounded-full"
                />
              ) : (
                <div className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 text-primary text-xs font-medium">
                  {suggestion.name.charAt(0).toUpperCase()}
                </div>
              )}
              <div className="flex-1 min-w-0">
                <div className="font-medium truncate">{suggestion.name}</div>
                {suggestion.email && (
                  <div className="text-xs text-muted-foreground truncate">
                    {suggestion.email}
                  </div>
                )}
              </div>
            </button>
          ))}
        </div>
      )}

      {/* Input area */}
      <div
        className={cn(
          'flex gap-2 rounded-lg border border-border bg-background p-2',
          'focus-within:ring-1 focus-within:ring-ring',
          'transition-shadow'
        )}
      >
        <textarea
          ref={textareaRef}
          value={text}
          onChange={handleTextChange}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled || isSubmitting}
          rows={1}
          className={cn(
            'flex-1 min-h-[36px] max-h-[200px] resize-none',
            'bg-transparent text-sm text-foreground',
            'placeholder:text-muted-foreground',
            'focus:outline-none',
            'disabled:opacity-50 disabled:cursor-not-allowed'
          )}
        />

        <div className="flex flex-col items-end justify-between gap-1">
          {/* Submit button */}
          <button
            onClick={handleSubmit}
            disabled={!canSubmit}
            className={cn(
              'flex h-8 w-8 items-center justify-center rounded-md',
              'text-primary-foreground bg-primary',
              'hover:bg-primary/90',
              'disabled:opacity-50 disabled:cursor-not-allowed',
              'transition-colors'
            )}
            title="Send (Ctrl+Enter)"
          >
            {isSubmitting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </button>

          {/* Character count */}
          {text.length > 0 && (
            <span
              className={cn(
                'text-[10px] tabular-nums',
                isOverLimit ? 'text-destructive' : 'text-muted-foreground'
              )}
            >
              {text.length}/{MAX_COMMENT_LENGTH}
            </span>
          )}
        </div>
      </div>

      {/* Hint */}
      <div className="mt-1 flex items-center gap-2 text-[10px] text-muted-foreground">
        <span className="flex items-center gap-0.5">
          <AtSign className="h-2.5 w-2.5" />
          to mention
        </span>
        <span>|</span>
        <span>Ctrl+Enter to send</span>
      </div>
    </div>
  )
}

// ============================================================================
// Exports
// ============================================================================

export default CommentInput
