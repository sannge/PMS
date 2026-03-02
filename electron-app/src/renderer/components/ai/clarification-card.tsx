/**
 * Clarification Card
 *
 * Inline clarification card rendered in the chat message stream when Blair
 * needs follow-up input. Shows a question, optional pill-style option buttons,
 * and a free-text input that is always available.
 */

import { useState, useCallback, useRef } from 'react'
import { Send, MessageCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

// ============================================================================
// Types
// ============================================================================

export interface ClarificationCardProps {
  question: string
  options: string[] | null
  context: string | null
  status: 'pending' | 'answered'
  selectedAnswer: string | null
  onSelectOption: (option: string) => void
  onSubmitText: (text: string) => void
}

// ============================================================================
// Component
// ============================================================================

export function ClarificationCard({
  question,
  options,
  context,
  status,
  selectedAnswer,
  onSelectOption,
  onSubmitText,
}: ClarificationCardProps): JSX.Element {
  const [textValue, setTextValue] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const isPending = status === 'pending'

  const handleSubmitText = useCallback(() => {
    const trimmed = textValue.trim()
    if (!trimmed || !isPending) return
    onSubmitText(trimmed)
    setTextValue('')
  }, [textValue, isPending, onSubmitText])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter') {
        e.preventDefault()
        handleSubmitText()
      }
    },
    [handleSubmitText]
  )

  return (
    <div
      role="region"
      aria-label="Clarification needed"
      className={cn(
        'mt-2 rounded-lg border border-border bg-background/80 p-3',
        isPending && 'ring-1 ring-primary/20'
      )}
    >
      {/* Question */}
      <div className="flex items-start gap-2 mb-2">
        <MessageCircle className="h-4 w-4 mt-0.5 text-primary shrink-0" />
        <div>
          <p className="text-xs font-medium">{question}</p>
          {context && (
            <p className="mt-0.5 text-[11px] text-muted-foreground">{context}</p>
          )}
        </div>
      </div>

      {/* Options */}
      {options && options.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-2 pl-6">
          {options.slice(0, 4).map((option) => {
            const isSelected = selectedAnswer === option
            return (
              <button
                key={option}
                type="button"
                disabled={!isPending}
                onClick={() => onSelectOption(option)}
                className={cn(
                  'rounded-full border px-3 py-1 text-xs font-medium transition-colors',
                  isPending
                    ? 'border-border hover:border-primary hover:bg-primary/5 cursor-pointer'
                    : isSelected
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-border opacity-40 cursor-default'
                )}
              >
                {option}
              </button>
            )
          })}
        </div>
      )}

      {/* Free-text input */}
      <div className="flex items-center gap-1.5 pl-6">
        <input
          ref={inputRef}
          type="text"
          value={isPending ? textValue : selectedAnswer || ''}
          onChange={(e) => setTextValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Or type your answer..."
          disabled={!isPending}
          className={cn(
            'flex-1 rounded-lg border border-input bg-muted/50 px-2.5 py-1.5',
            'text-xs placeholder:text-muted-foreground',
            'focus:outline-none focus:ring-1 focus:ring-ring',
            'disabled:opacity-50 disabled:cursor-not-allowed'
          )}
        />
        {isPending && (
          <Button
            size="icon"
            onClick={handleSubmitText}
            disabled={!textValue.trim()}
            className="h-7 w-7 shrink-0 rounded-lg"
          >
            <Send className="h-3 w-3" />
          </Button>
        )}
      </div>
    </div>
  )
}
