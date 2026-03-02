/**
 * Interrupt Handler
 *
 * Renders the appropriate HITL card (ToolConfirmation or ClarificationCard)
 * based on the interrupt payload in an assistant message. Manages local
 * status state and calls onResolve with the user's response.
 */

import { useState, useCallback } from 'react'
import { ToolConfirmation } from './tool-confirmation'
import { ClarificationCard } from './clarification-card'
import type { ChatMessage } from './types'

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

export function InterruptHandler({
  message,
  onResolve,
}: InterruptHandlerProps): JSX.Element | null {
  const payload = message.interrupt_payload
  if (!payload) return null

  if (payload.type === 'confirmation') {
    return (
      <ConfirmationHandler
        action={payload.action || ''}
        context={payload.context || {}}
        onResolve={onResolve}
      />
    )
  }

  if (payload.type === 'clarification') {
    return (
      <ClarificationHandler
        question={payload.question || ''}
        options={payload.options || null}
        context={payload.context}
        onResolve={onResolve}
      />
    )
  }

  return null
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

  const actionObj = {
    type: (context.type as string) || action,
    summary: (context.summary as string) || action,
    details: (context.details as Record<string, unknown>) || context,
  }

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
// Clarification Sub-handler
// ============================================================================

function ClarificationHandler({
  question,
  options,
  context,
  onResolve,
}: {
  question: string
  options: string[] | null
  context?: Record<string, unknown>
  onResolve: (response: Record<string, unknown>) => void
}): JSX.Element {
  const [status, setStatus] = useState<'pending' | 'answered'>('pending')
  const [selectedAnswer, setSelectedAnswer] = useState<string | null>(null)

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
    />
  )
}
