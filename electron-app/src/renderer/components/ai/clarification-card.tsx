/**
 * Clarification Card
 *
 * Inline clarification card rendered in the chat message stream when Blair
 * needs follow-up input. Shows a question, optional pill-style option buttons,
 * and a free-text input that is always available.
 *
 * Supports step-through mode: when `step` and `total` are provided (total > 1),
 * shows step counter and progress dots for multi-question clarification wizards.
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
  /** Current step (1-indexed) for multi-step clarification */
  step?: number
  /** Total number of questions for multi-step clarification */
  total?: number
  /** Number of questions already answered (for progress dots) */
  answeredCount?: number
}

// ============================================================================
// Progress Dots
// ============================================================================

function ProgressDots({
  total,
  answeredCount,
  currentStep,
}: {
  total: number
  answeredCount: number
  currentStep: number
}) {
  return (
    <div
      className="flex items-center justify-center gap-1.5 mt-2 pt-1"
      role="progressbar"
      aria-label={`Step ${currentStep} of ${total}`}
      aria-valuenow={currentStep}
      aria-valuemin={1}
      aria-valuemax={total}
    >
      {Array.from({ length: total }, (_, i) => {
        const stepNum = i + 1
        const isAnswered = stepNum <= answeredCount
        const isCurrent = stepNum === currentStep
        return (
          <span
            key={i}
            role="presentation"
            className={cn(
              'h-1.5 w-1.5 rounded-full transition-colors',
              isAnswered
                ? 'bg-primary'
                : isCurrent
                  ? 'bg-primary/60 ring-1 ring-primary/30'
                  : 'bg-muted-foreground/20',
            )}
          />
        )
      })}
    </div>
  )
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
  step,
  total,
  answeredCount = 0,
}: ClarificationCardProps): JSX.Element {
  const [textValue, setTextValue] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const isPending = status === 'pending'
  const isMultiStep = total != null && total > 1

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
      {/* Header with optional step counter */}
      <div className="flex items-start gap-2 mb-2">
        <MessageCircle className="h-4 w-4 mt-0.5 text-primary shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs font-medium">{question}</p>
            {isMultiStep && step != null && (
              <span className="text-[10px] text-muted-foreground shrink-0">
                {step} of {total}
              </span>
            )}
          </div>
          {context && (
            <p className="mt-0.5 text-[11px] text-muted-foreground">{context}</p>
          )}
        </div>
      </div>

      {/* Options */}
      {options && options.filter(o => o.trim()).length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-2 pl-6">
          {options.filter(o => o.trim()).slice(0, 4).map((option) => {
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
            aria-label="Submit answer"
            className="h-7 w-7 shrink-0 rounded-lg"
          >
            <Send className="h-3 w-3" />
          </Button>
        )}
      </div>

      {/* Progress dots for multi-step */}
      {isMultiStep && (
        <ProgressDots
          total={total!}
          answeredCount={answeredCount}
          currentStep={step ?? 1}
        />
      )}
    </div>
  )
}
