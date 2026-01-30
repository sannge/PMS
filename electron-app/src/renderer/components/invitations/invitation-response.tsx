/**
 * Invitation Response Component
 *
 * Displays an invitation with accept/reject actions.
 *
 * Features:
 * - Displays inviter and application details
 * - Role badge
 * - Accept/reject buttons
 * - Loading states for actions
 * - Error handling
 * - Keyboard accessible
 * - Relative time display
 *
 * Uses TanStack Query for data mutations.
 */

import { useCallback, useState } from 'react'
import { cn } from '@/lib/utils'
import {
  UserPlus,
  Check,
  X,
  Loader2,
  AlertCircle,
  Layers,
} from 'lucide-react'
import {
  useAcceptInvitation,
  useRejectInvitation,
  type InvitationWithDetails,
  type ApplicationRole,
} from '@/hooks/use-invitations'

// ============================================================================
// Types
// ============================================================================

export interface InvitationResponseProps {
  /**
   * Invitation data with details
   */
  invitation: InvitationWithDetails
  /**
   * Callback when invitation is accepted
   */
  onAccept?: (invitation: InvitationWithDetails) => void
  /**
   * Callback when invitation is rejected
   */
  onReject?: (invitation: InvitationWithDetails) => void
  /**
   * Callback when an error occurs
   */
  onError?: (error: string) => void
  /**
   * Whether actions are disabled
   */
  disabled?: boolean
  /**
   * Display mode: 'card' for standalone, 'compact' for list
   */
  variant?: 'card' | 'compact'
  /**
   * Additional CSS classes
   */
  className?: string
}

interface RoleConfig {
  label: string
  colorClass: string
}

// ============================================================================
// Constants
// ============================================================================

const ROLE_CONFIG: Record<ApplicationRole, RoleConfig> = {
  owner: {
    label: 'Owner',
    colorClass: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  },
  editor: {
    label: 'Editor',
    colorClass: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  },
  viewer: {
    label: 'Viewer',
    colorClass: 'bg-slate-100 text-slate-700 dark:bg-slate-900/30 dark:text-slate-400',
  },
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Format relative time
 */
function formatRelativeTime(dateString: string): string {
  // Ensure UTC parsing - append 'Z' if no timezone indicator
  let dateStr = dateString
  if (!dateStr.endsWith('Z') && !dateStr.includes('+') && !dateStr.includes('-', 10)) {
    dateStr = dateStr + 'Z'
  }

  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()

  // Handle future dates or very recent
  if (diffMs < 0 || diffMs < 60000) return 'Just now'

  const diffMin = Math.floor(diffMs / (1000 * 60))
  const diffHour = Math.floor(diffMs / (1000 * 60 * 60))
  const diffDay = Math.floor(diffMs / (1000 * 60 * 60 * 24))
  const diffWeek = Math.floor(diffDay / 7)

  if (diffMin < 60) {
    return `${diffMin}m ago`
  }
  if (diffHour < 24) {
    return `${diffHour}h ago`
  }
  if (diffDay < 7) {
    return `${diffDay}d ago`
  }
  if (diffWeek < 4) {
    return `${diffWeek}w ago`
  }

  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

/**
 * Get inviter display name
 */
function getInviterName(invitation: InvitationWithDetails): string {
  if (invitation.inviter?.display_name) {
    return invitation.inviter.display_name
  }
  if (invitation.inviter?.email) {
    return invitation.inviter.email
  }
  return 'Unknown user'
}

/**
 * Get application display name
 */
function getApplicationName(invitation: InvitationWithDetails): string {
  return invitation.application?.name || 'Unknown application'
}

// ============================================================================
// Component
// ============================================================================

export function InvitationResponse({
  invitation,
  onAccept,
  onReject,
  onError,
  disabled = false,
  variant = 'card',
  className,
}: InvitationResponseProps): JSX.Element {
  // Local state for error display
  const [error, setError] = useState<string | null>(null)

  // TanStack Query mutations
  const acceptInvitation = useAcceptInvitation()
  const rejectInvitation = useRejectInvitation()

  const roleConfig = ROLE_CONFIG[invitation.role]
  const isAccepting = acceptInvitation.isPending
  const isRejecting = rejectInvitation.isPending
  const isProcessing = isAccepting || isRejecting

  // Handle accept
  const handleAccept = useCallback(
    async (e: React.MouseEvent) => {
      e.stopPropagation()
      if (disabled || isProcessing) return

      setError(null)

      try {
        await acceptInvitation.mutateAsync(invitation.id)
        onAccept?.(invitation)
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : 'Failed to accept invitation'
        setError(errorMsg)
        onError?.(errorMsg)
      }
    },
    [invitation, disabled, isProcessing, acceptInvitation, onAccept, onError]
  )

  // Handle reject
  const handleReject = useCallback(
    async (e: React.MouseEvent) => {
      e.stopPropagation()
      if (disabled || isProcessing) return

      setError(null)

      try {
        await rejectInvitation.mutateAsync(invitation.id)
        onReject?.(invitation)
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : 'Failed to reject invitation'
        setError(errorMsg)
        onError?.(errorMsg)
      }
    },
    [invitation, disabled, isProcessing, rejectInvitation, onReject, onError]
  )

  // Render compact variant (for notification lists)
  if (variant === 'compact') {
    return (
      <div
        className={cn(
          'group relative flex items-center gap-3 p-3 transition-colors',
          'bg-primary/5',
          disabled && 'opacity-50 cursor-not-allowed',
          className
        )}
      >
        {/* Icon */}
        <div className="flex-shrink-0 flex h-9 w-9 items-center justify-center rounded-full bg-teal-100 text-teal-600 dark:bg-teal-900/30 dark:text-teal-400">
          <UserPlus className="h-4 w-4" />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-foreground line-clamp-1">
            Invitation from {getInviterName(invitation)}
          </p>
          <p className="mt-0.5 text-xs text-muted-foreground line-clamp-1">
            Join <span className="font-medium">{getApplicationName(invitation)}</span> as{' '}
            <span className={cn('inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium', roleConfig.colorClass)}>
              {roleConfig.label}
            </span>
          </p>
          <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
            <span>{formatRelativeTime(invitation.created_at)}</span>
          </div>
        </div>

        {/* Actions */}
        <div className="flex-shrink-0 flex items-center gap-1">
          <button
            onClick={handleAccept}
            disabled={disabled || isProcessing}
            className={cn(
              'rounded-md p-1.5 transition-colors',
              'bg-green-100 text-green-600 hover:bg-green-200',
              'dark:bg-green-900/30 dark:text-green-400 dark:hover:bg-green-900/50',
              'focus:outline-none focus:ring-2 focus:ring-ring',
              'disabled:pointer-events-none disabled:opacity-50'
            )}
            title="Accept invitation"
            aria-label="Accept invitation"
          >
            {isAccepting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Check className="h-4 w-4" />
            )}
          </button>
          <button
            onClick={handleReject}
            disabled={disabled || isProcessing}
            className={cn(
              'rounded-md p-1.5 transition-colors',
              'bg-red-100 text-red-600 hover:bg-red-200',
              'dark:bg-red-900/30 dark:text-red-400 dark:hover:bg-red-900/50',
              'focus:outline-none focus:ring-2 focus:ring-ring',
              'disabled:pointer-events-none disabled:opacity-50'
            )}
            title="Reject invitation"
            aria-label="Reject invitation"
          >
            {isRejecting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <X className="h-4 w-4" />
            )}
          </button>
        </div>
      </div>
    )
  }

  // Render card variant (standalone)
  return (
    <div
      className={cn(
        'rounded-lg border border-border bg-card p-4 transition-colors',
        'hover:border-primary/20',
        disabled && 'opacity-50 cursor-not-allowed',
        className
      )}
    >
      {/* Header */}
      <div className="flex items-start gap-3">
        {/* Icon */}
        <div className="flex-shrink-0 flex h-10 w-10 items-center justify-center rounded-full bg-teal-100 text-teal-600 dark:bg-teal-900/30 dark:text-teal-400">
          <UserPlus className="h-5 w-5" />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-foreground">
            {getInviterName(invitation)} invited you
          </p>
          <div className="mt-1 flex items-center gap-2 text-sm text-muted-foreground">
            <Layers className="h-3.5 w-3.5" />
            <span className="font-medium text-foreground">{getApplicationName(invitation)}</span>
          </div>
        </div>

        {/* Role Badge */}
        <span
          className={cn(
            'flex-shrink-0 inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium',
            roleConfig.colorClass
          )}
        >
          {roleConfig.label}
        </span>
      </div>

      {/* Time */}
      <p className="mt-3 text-xs text-muted-foreground">
        Received {formatRelativeTime(invitation.created_at)}
      </p>

      {/* Error */}
      {error && (
        <div className="mt-3 flex items-center gap-2 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          <AlertCircle className="h-4 w-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Actions */}
      <div className="mt-4 flex items-center gap-2">
        <button
          onClick={handleAccept}
          disabled={disabled || isProcessing}
          className={cn(
            'flex flex-1 items-center justify-center gap-2 rounded-md py-2 px-3 text-sm font-medium transition-colors',
            'bg-primary text-primary-foreground',
            'hover:bg-primary/90',
            'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
            'disabled:pointer-events-none disabled:opacity-50'
          )}
        >
          {isAccepting ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Accepting...
            </>
          ) : (
            <>
              <Check className="h-4 w-4" />
              Accept
            </>
          )}
        </button>
        <button
          onClick={handleReject}
          disabled={disabled || isProcessing}
          className={cn(
            'flex flex-1 items-center justify-center gap-2 rounded-md border border-input bg-background py-2 px-3 text-sm font-medium transition-colors',
            'hover:bg-accent hover:text-accent-foreground',
            'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
            'disabled:pointer-events-none disabled:opacity-50'
          )}
        >
          {isRejecting ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Rejecting...
            </>
          ) : (
            <>
              <X className="h-4 w-4" />
              Reject
            </>
          )}
        </button>
      </div>
    </div>
  )
}

// ============================================================================
// Exports
// ============================================================================

export { formatRelativeTime, ROLE_CONFIG }
export default InvitationResponse
