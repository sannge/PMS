/**
 * Application Card Component
 *
 * Displays an application in a card format with name, description,
 * project count, and action buttons.
 *
 * Features:
 * - Displays application details
 * - Edit and delete action buttons
 * - Project count badge
 * - Hover effects and accessibility
 */

import { useCallback } from 'react'
import { cn } from '@/lib/utils'
import {
  FolderKanban,
  MoreVertical,
  Edit2,
  Trash2,
  ArrowRight,
  Clock,
} from 'lucide-react'
import type { Application } from '@/stores/applications-store'

// ============================================================================
// Types
// ============================================================================

export interface ApplicationCardProps {
  /**
   * Application data to display
   */
  application: Application
  /**
   * Callback when the card is clicked
   */
  onClick?: (application: Application) => void
  /**
   * Callback when edit is clicked
   */
  onEdit?: (application: Application) => void
  /**
   * Callback when delete is clicked
   */
  onDelete?: (application: Application) => void
  /**
   * Whether actions are disabled
   */
  disabled?: boolean
  /**
   * Additional CSS classes
   */
  className?: string
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Format a date string to a human-readable format
 */
function formatDate(dateString: string): string {
  // Ensure the date is parsed as UTC if no timezone is specified
  let dateStr = dateString
  if (!dateStr.endsWith('Z') && !dateStr.includes('+') && !dateStr.includes('-', 10)) {
    dateStr = dateStr + 'Z'
  }

  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()

  // Handle future dates (negative diff) - show "Just now"
  if (diffMs < 0) {
    return 'Just now'
  }

  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

  if (diffDays === 0) {
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60))
    if (diffHours === 0) {
      const diffMinutes = Math.floor(diffMs / (1000 * 60))
      if (diffMinutes === 0) {
        return 'Just now'
      }
      return `${diffMinutes}m ago`
    }
    return `${diffHours}h ago`
  }
  if (diffDays === 1) {
    return 'Yesterday'
  }
  if (diffDays < 7) {
    return `${diffDays}d ago`
  }
  if (diffDays < 30) {
    const weeks = Math.floor(diffDays / 7)
    return `${weeks}w ago`
  }

  return date.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: date.getFullYear() !== now.getFullYear() ? 'numeric' : undefined,
  })
}

// ============================================================================
// Component
// ============================================================================

export function ApplicationCard({
  application,
  onClick,
  onEdit,
  onDelete,
  disabled = false,
  className,
}: ApplicationCardProps): JSX.Element {
  // Handle card click
  const handleClick = useCallback(() => {
    if (!disabled && onClick) {
      onClick(application)
    }
  }, [application, disabled, onClick])

  // Handle edit click
  const handleEdit = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation()
      if (!disabled && onEdit) {
        onEdit(application)
      }
    },
    [application, disabled, onEdit]
  )

  // Handle delete click
  const handleDelete = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation()
      if (!disabled && onDelete) {
        onDelete(application)
      }
    },
    [application, disabled, onDelete]
  )

  return (
    <div
      onClick={handleClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={(e) => {
        if (onClick && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault()
          handleClick()
        }
      }}
      className={cn(
        'group relative rounded-lg border border-border bg-card p-4 transition-all',
        onClick && !disabled && 'cursor-pointer hover:border-primary/50 hover:shadow-md',
        disabled && 'opacity-50 cursor-not-allowed',
        'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background',
        className
      )}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        {/* Icon and Title */}
        <div className="flex items-start gap-3 min-w-0">
          <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <FolderKanban className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <h3 className="font-semibold text-foreground truncate">
              {application.name}
            </h3>
            {application.description && (
              <p className="mt-1 text-sm text-muted-foreground line-clamp-2">
                {application.description}
              </p>
            )}
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          {onEdit && (
            <button
              onClick={handleEdit}
              disabled={disabled}
              className={cn(
                'rounded-md p-1.5 text-muted-foreground transition-colors',
                'hover:bg-accent hover:text-accent-foreground',
                'focus:outline-none focus:ring-2 focus:ring-ring',
                'disabled:pointer-events-none disabled:opacity-50'
              )}
              title="Edit application"
            >
              <Edit2 className="h-4 w-4" />
            </button>
          )}
          {onDelete && (
            <button
              onClick={handleDelete}
              disabled={disabled}
              className={cn(
                'rounded-md p-1.5 text-muted-foreground transition-colors',
                'hover:bg-destructive/10 hover:text-destructive',
                'focus:outline-none focus:ring-2 focus:ring-ring',
                'disabled:pointer-events-none disabled:opacity-50'
              )}
              title="Delete application"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      {/* Footer */}
      <div className="mt-4 flex items-center justify-between text-sm text-muted-foreground">
        {/* Project Count */}
        <div className="flex items-center gap-4">
          <span className="flex items-center gap-1.5">
            <FolderKanban className="h-4 w-4" />
            {application.projects_count} {application.projects_count === 1 ? 'project' : 'projects'}
          </span>
        </div>

        {/* Last Updated */}
        <div className="flex items-center gap-1.5">
          <Clock className="h-3.5 w-3.5" />
          <span className="text-xs">{formatDate(application.updated_at)}</span>
        </div>
      </div>

      {/* Arrow indicator for clickable cards */}
      {onClick && !disabled && (
        <div className="absolute bottom-4 right-4 opacity-0 group-hover:opacity-100 transition-opacity">
          <ArrowRight className="h-4 w-4 text-primary" />
        </div>
      )}
    </div>
  )
}

export default ApplicationCard
