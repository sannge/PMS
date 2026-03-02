/**
 * Tool Confirmation Card
 *
 * Inline confirmation card rendered in the chat message stream for Blair's
 * write actions. Shows action summary, detail fields, and approve/reject buttons.
 * Supports keyboard shortcuts: Enter to approve, Escape to reject.
 */

import { useCallback, useRef, useEffect } from 'react'
import { Check, X, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

// ============================================================================
// Types
// ============================================================================

export interface ToolConfirmationAction {
  type: string
  summary: string
  details: Record<string, unknown>
}

export interface ToolConfirmationProps {
  action: ToolConfirmationAction
  status: 'pending' | 'approved' | 'rejected'
  onApprove: () => void
  onReject: () => void
}

// ============================================================================
// Detail Renderers
// ============================================================================

const DETAIL_FIELDS: Record<string, { label: string; key: string }[]> = {
  create_task: [
    { label: 'Title', key: 'title' },
    { label: 'Project', key: 'project' },
    { label: 'Priority', key: 'priority' },
    { label: 'Assignee', key: 'assignee' },
  ],
  update_task_status: [
    { label: 'Task', key: 'task_key' },
  ],
  assign_task: [
    { label: 'Task', key: 'task_key' },
    { label: 'Assignee', key: 'assignee' },
  ],
  create_document: [
    { label: 'Title', key: 'title' },
    { label: 'Scope', key: 'scope' },
    { label: 'Folder', key: 'folder' },
  ],
}

function StatusTransition({ details }: { details: Record<string, unknown> }): JSX.Element | null {
  const from = details.from_status as string | undefined
  const to = details.to_status as string | undefined
  if (!from || !to) return null

  return (
    <div className="flex items-center gap-1.5 text-xs">
      <span className="text-muted-foreground">Status</span>
      <span className="font-medium">{from}</span>
      <ChevronRight className="h-3 w-3 text-muted-foreground" />
      <span className="font-medium">{to}</span>
    </div>
  )
}

function DetailFields({ action }: { action: ToolConfirmationAction }): JSX.Element {
  const fields = DETAIL_FIELDS[action.type]

  return (
    <div className="space-y-1">
      {fields?.map(({ label, key }) => {
        const value = action.details[key]
        if (value == null || value === '') return null
        return (
          <div key={key} className="flex items-baseline gap-2 text-xs">
            <span className="text-muted-foreground shrink-0">{label}</span>
            <span className="font-medium truncate">{String(value)}</span>
          </div>
        )
      })}
      {action.type === 'update_task_status' && (
        <StatusTransition details={action.details} />
      )}
      {!fields && Object.entries(action.details).length > 0 && (
        <>
          {Object.entries(action.details).map(([key, value]) => {
            if (value == null || value === '') return null
            return (
              <div key={key} className="flex items-baseline gap-2 text-xs">
                <span className="text-muted-foreground shrink-0">{key}</span>
                <span className="font-medium truncate">{String(value)}</span>
              </div>
            )
          })}
        </>
      )}
    </div>
  )
}

// ============================================================================
// Action Icon
// ============================================================================

function ActionIcon({ type }: { type: string }): JSX.Element {
  const label = type.replace(/_/g, ' ')
  return (
    <div className="flex h-6 w-6 items-center justify-center rounded-md bg-primary/10 text-primary shrink-0">
      <span className="text-[10px] font-bold uppercase leading-none">
        {label.charAt(0)}
      </span>
    </div>
  )
}

// ============================================================================
// Component
// ============================================================================

export function ToolConfirmation({
  action,
  status,
  onApprove,
  onReject,
}: ToolConfirmationProps): JSX.Element {
  const isPending = status === 'pending'

  const cardRef = useRef<HTMLDivElement>(null)

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (!isPending) return
      if (e.key === 'Enter') {
        e.preventDefault()
        onApprove()
      } else if (e.key === 'Escape') {
        e.preventDefault()
        onReject()
      }
    },
    [isPending, onApprove, onReject]
  )

  // Auto-focus the card when pending so keyboard shortcuts work
  useEffect(() => {
    if (isPending) {
      cardRef.current?.focus()
    }
  }, [isPending])

  return (
    <div
      ref={cardRef}
      tabIndex={isPending ? 0 : undefined}
      onKeyDown={handleKeyDown}
      role={isPending ? 'alert' : undefined}
      className={cn(
        'mt-2 rounded-lg border border-border bg-background/80 p-3',
        isPending && 'ring-1 ring-primary/20',
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-ring'
      )}
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-2">
        <ActionIcon type={action.type} />
        <span className="text-xs font-medium">{action.summary}</span>
      </div>

      {/* Details */}
      <div className="mb-3 pl-8">
        <DetailFields action={action} />
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 pl-8">
        {isPending ? (
          <>
            <Button
              size="sm"
              onClick={onApprove}
              className="h-7 gap-1.5 rounded-lg px-3 text-xs"
            >
              <Check className="h-3 w-3" />
              Approve
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={onReject}
              className="h-7 gap-1.5 rounded-lg px-3 text-xs text-destructive hover:text-destructive hover:bg-destructive/10 border-destructive/30"
            >
              <X className="h-3 w-3" />
              Reject
            </Button>
          </>
        ) : (
          <span
            className={cn(
              'inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium',
              status === 'approved'
                ? 'bg-emerald-500/10 text-emerald-600'
                : 'bg-destructive/10 text-destructive'
            )}
          >
            {status === 'approved' ? (
              <>
                <Check className="h-3 w-3" />
                Approved
              </>
            ) : (
              <>
                <X className="h-3 w-3" />
                Cancelled
              </>
            )}
          </span>
        )}
      </div>
    </div>
  )
}
