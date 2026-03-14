/**
 * Interrupt Handler
 *
 * Renders the appropriate HITL card (ToolConfirmation or ClarificationCard)
 * based on the interrupt payload in an assistant message.
 *
 * Supports batch clarification (multiple questions at once) via the
 * questions[] array in the interrupt payload.
 */

import { useState, useCallback, useMemo, memo } from 'react'
import { ToolConfirmation } from './tool-confirmation'
import { ClarificationCard } from './clarification-card'
import { SearchSelectionCard } from './search-selection-card'
import { Button } from '@/components/ui/button'
import type { ChatMessage, SearchSelectionItem } from './types'

// ============================================================================
// Types
// ============================================================================

export interface InterruptHandlerProps {
  message: ChatMessage
  onResolve: (response: Record<string, unknown>) => void
}

// ============================================================================
// Component
// ============================================================================

export const InterruptHandler = memo(function InterruptHandler({
  message,
  onResolve,
}: InterruptHandlerProps): JSX.Element | null {
  const payload = message.interrupt_payload
  if (!payload) return null

  if (payload.type === 'confirmation') {
    // CR-R3-004: Use top-level summary/details from write tool confirmation payloads
    const confirmContext: Record<string, unknown> = {
      ...(payload.context || {}),
      ...(payload.summary ? { summary: payload.summary } : {}),
      ...(payload.details ? { details: payload.details } : {}),
    }
    return (
      <ConfirmationHandler
        action={payload.action || ''}
        context={confirmContext}
        onResolve={onResolve}
      />
    )
  }

  if (payload.type === 'clarification') {
    // Batch questions (new ReAct flow — all questions at once)
    if (payload.questions && payload.questions.length > 0) {
      return (
        <BatchClarificationHandler
          questions={payload.questions}
          onResolve={onResolve}
        />
      )
    }

    // Single question fallback (backward compat)
    const step = payload.context?.step as number | undefined
    const total = payload.context?.total as number | undefined

    return (
      <ClarificationHandler
        question={payload.question || ''}
        options={payload.options || null}
        context={payload.context}
        step={step}
        total={total}
        onResolve={onResolve}
      />
    )
  }

  if (payload.type === 'selection') {
    return (
      <SelectionHandler
        prompt={payload.prompt || ''}
        items={payload.items || []}
        onResolve={onResolve}
      />
    )
  }

  return null
})

// ============================================================================
// Selection Sub-handler
// ============================================================================

function SelectionHandler({
  prompt,
  items,
  onResolve,
}: {
  prompt: string
  items: SearchSelectionItem[]
  onResolve: (response: Record<string, unknown>) => void
}): JSX.Element {
  // R2: Cap items to 20 so state management agrees with SearchSelectionCard's displayItems
  const cappedItems = useMemo(() => items.slice(0, 20), [items])

  const [selectedIndices, setSelectedIndices] = useState<Set<number>>(
    () => new Set(cappedItems.map(item => item.index))
  )
  const [status, setStatus] = useState<'pending' | 'submitted' | 'skipped'>('pending')

  const handleToggle = useCallback((index: number) => {
    if (status !== 'pending') return
    setSelectedIndices(prev => {
      const next = new Set(prev)
      if (next.has(index)) {
        next.delete(index)
      } else {
        next.add(index)
      }
      return next
    })
  }, [status])

  const handleToggleAll = useCallback(() => {
    if (status !== 'pending') return
    setSelectedIndices(prev => {
      if (cappedItems.every(item => prev.has(item.index))) {
        return new Set()
      }
      return new Set(cappedItems.map(item => item.index))
    })
  }, [status, cappedItems])

  const handleSubmit = useCallback(() => {
    if (status !== 'pending' || selectedIndices.size === 0) return
    setStatus('submitted')
    onResolve({ selected_indices: Array.from(selectedIndices) })
  }, [status, selectedIndices, onResolve])

  const handleSkip = useCallback(() => {
    if (status !== 'pending') return
    setStatus('skipped')
    onResolve({ skipped: true })
  }, [status, onResolve])

  return (
    <SearchSelectionCard
      prompt={prompt}
      items={cappedItems}
      status={status}
      selectedIndices={selectedIndices}
      onToggle={handleToggle}
      onToggleAll={handleToggleAll}
      onSubmit={handleSubmit}
      onSkip={handleSkip}
    />
  )
}

// ============================================================================
// Confirmation Sub-handler
// ============================================================================

function ConfirmationHandler({
  action,
  context,
  onResolve,
}: {
  action: string
  context: Record<string, unknown>
  onResolve: (response: Record<string, unknown>) => void
}): JSX.Element {
  const [status, setStatus] = useState<'pending' | 'approved' | 'rejected'>('pending')

  const handleApprove = useCallback(() => {
    if (status !== 'pending') return
    setStatus('approved')
    onResolve({ approved: true })
  }, [status, onResolve])

  const handleReject = useCallback(() => {
    if (status !== 'pending') return
    setStatus('rejected')
    onResolve({ approved: false })
  }, [status, onResolve])

  const actionObj = useMemo(() => ({
    type: (context.type as string) || action,
    summary: (context.summary as string) || action,
    details: (context.details as Record<string, unknown>) || context,
  }), [action, context])

  return (
    <ToolConfirmation
      action={actionObj}
      status={status}
      onApprove={handleApprove}
      onReject={handleReject}
    />
  )
}

// ============================================================================
// Single Clarification Sub-handler (backward compat)
// ============================================================================

function ClarificationHandler({
  question,
  options,
  context,
  step,
  total,
  onResolve,
}: {
  question: string
  options: string[] | null
  context?: Record<string, unknown>
  step?: number
  total?: number
  onResolve: (response: Record<string, unknown>) => void
}): JSX.Element {
  const [status, setStatus] = useState<'pending' | 'answered'>('pending')
  const [selectedAnswer, setSelectedAnswer] = useState<string | null>(null)
  const answeredCount = step != null ? Math.max(0, step - 1) : 0

  const handleSelectOption = useCallback(
    (option: string) => {
      if (status !== 'pending') return
      setSelectedAnswer(option)
      setStatus('answered')
      onResolve({ answer: option })
    },
    [status, onResolve]
  )

  const handleSubmitText = useCallback(
    (text: string) => {
      if (status !== 'pending') return
      setSelectedAnswer(text)
      setStatus('answered')
      onResolve({ answer: text })
    },
    [status, onResolve]
  )

  const contextStr = context
    ? (context.description as string) || (context.hint as string) || null
    : null

  return (
    <ClarificationCard
      question={question}
      options={options}
      context={contextStr}
      status={status}
      selectedAnswer={selectedAnswer}
      onSelectOption={handleSelectOption}
      onSubmitText={handleSubmitText}
      step={step}
      total={total}
      answeredCount={answeredCount}
    />
  )
}

// ============================================================================
// Batch Clarification Handler (all questions at once)
// ============================================================================

function BatchClarificationHandler({
  questions,
  onResolve,
}: {
  questions: Array<{ question: string; options?: string[] | null }>
  onResolve: (response: Record<string, unknown>) => void
}): JSX.Element {
  const [answers, setAnswers] = useState<Record<number, string>>({})
  const [submitted, setSubmitted] = useState(false)
  const allAnswered = useMemo(() =>
    questions.length > 0 &&
    Object.keys(answers).length === questions.length &&
    Object.values(answers).every(a => a.trim().length > 0),
  [answers, questions])

  const handleAnswer = useCallback((index: number, answer: string) => {
    if (submitted) return
    setAnswers(prev => ({ ...prev, [index]: answer }))
  }, [submitted])

  const handleSubmit = useCallback(() => {
    if (!allAnswered || submitted) return
    setSubmitted(true)
    const result = questions.map((q, i) => ({
      question: q.question,
      answer: answers[i] || '',
    }))
    onResolve({ answers: result })
  }, [allAnswered, submitted, questions, answers, onResolve])

  return (
    <div role="region" aria-label="Batch clarification" className="space-y-3 rounded-lg border border-border bg-muted/30 p-4">
      <p className="text-sm font-medium text-foreground">
        I need a few details before I can help:
      </p>
      {questions.map((q, i) => (
        <BatchQuestionItem
          key={i}
          index={i}
          question={q.question}
          options={q.options || null}
          answer={answers[i] || null}
          disabled={submitted}
          onAnswer={handleAnswer}
        />
      ))}
      <Button
        size="sm"
        onClick={handleSubmit}
        disabled={!allAnswered || submitted}
        className="mt-2 w-full"
      >
        {submitted ? 'Submitted' : 'Submit All'}
      </Button>
    </div>
  )
}

/** Individual question within a batch */
const BatchQuestionItem = memo(function BatchQuestionItem({
  index,
  question,
  options,
  answer,
  disabled,
  onAnswer,
}: {
  index: number
  question: string
  options: string[] | null
  answer: string | null
  disabled: boolean
  onAnswer: (index: number, answer: string) => void
}): JSX.Element {
  const [textInput, setTextInput] = useState('')

  const handleOptionClick = useCallback(
    (opt: string) => {
      setTextInput('') // CR-R4-004: Clear text input when option is selected
      onAnswer(index, opt.trim())
    },
    [index, onAnswer]
  )

  const handleTextSubmit = useCallback(() => {
    if (textInput.trim()) {
      onAnswer(index, textInput.trim())
      setTextInput('')
    }
  }, [index, textInput, onAnswer])

  // DA-R4-007: Show options even after answering (before submit) so user can change
  const isOptionAnswer = options?.includes(answer ?? '')

  return (
    <div className="space-y-1.5">
      <p className="text-sm text-muted-foreground">
        <span className="font-medium text-foreground">{index + 1}.</span> {question}
      </p>
      {options && options.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {options.map((opt) => (
            <button
              key={opt}
              onClick={() => handleOptionClick(opt)}
              disabled={disabled}
              className={`rounded-full border px-3 py-1 text-xs transition-colors ${
                answer === opt
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-border text-muted-foreground hover:border-primary/50 hover:text-foreground'
              } disabled:cursor-not-allowed disabled:opacity-50`}
            >
              {opt}
            </button>
          ))}
        </div>
      )}
      {(!answer || !isOptionAnswer) && !disabled && (
        <div className="flex gap-1.5">
          <input
            type="text"
            value={textInput}
            onChange={(e) => setTextInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleTextSubmit()
            }}
            disabled={disabled}
            maxLength={500}
            placeholder={answer ? 'Change your answer...' : 'Type your answer...'}
            className="flex-1 rounded-md border border-border bg-background px-2.5 py-1.5 text-xs placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary disabled:cursor-not-allowed disabled:opacity-50"
          />
        </div>
      )}
      {answer && (
        <p className="text-xs text-primary">&#10003; {answer}</p>
      )}
    </div>
  )
})
