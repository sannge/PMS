/**
 * CommentItem Component
 *
 * Displays a single comment with author info, content, and actions.
 * Features:
 * - Author avatar and name
 * - Formatted timestamp
 * - TipTap rendered content with @mentions
 * - Edit/delete actions for own comments
 * - Soft-deleted comment display
 */

import { useState, useCallback } from 'react'
import { cn } from '@/lib/utils'
import { User, Edit2, Trash2, MoreHorizontal, Check, X } from 'lucide-react'
import type { Comment } from '@/stores/comments-store'

// ============================================================================
// Types
// ============================================================================

export interface CommentItemProps {
  comment: Comment
  currentUserId?: string
  onEdit?: (commentId: string, bodyText: string) => void
  onDelete?: (commentId: string) => void
  isEditing?: boolean
  disabled?: boolean
  className?: string
}

// ============================================================================
// Helper Functions
// ============================================================================

function formatTimestamp(dateString: string): string {
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7) return `${diffDays}d ago`

  return date.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: date.getFullYear() !== now.getFullYear() ? 'numeric' : undefined,
  })
}

function getInitials(name: string | null): string {
  if (!name) return '?'
  const parts = name.trim().split(/\s+/)
  if (parts.length === 1) return parts[0].charAt(0).toUpperCase()
  return (parts[0].charAt(0) + parts[parts.length - 1].charAt(0)).toUpperCase()
}

// ============================================================================
// Component
// ============================================================================

export function CommentItem({
  comment,
  currentUserId,
  onEdit,
  onDelete,
  isEditing = false,
  disabled = false,
  className,
}: CommentItemProps): JSX.Element {
  const [showActions, setShowActions] = useState(false)
  const [editMode, setEditMode] = useState(false)
  const [editText, setEditText] = useState(comment.body_text || '')

  const isOwnComment = currentUserId && comment.author_id === currentUserId
  const canModify = isOwnComment && !comment.is_deleted

  const handleEditSubmit = useCallback(() => {
    if (editText.trim() && onEdit) {
      onEdit(comment.id, editText.trim())
      setEditMode(false)
    }
  }, [comment.id, editText, onEdit])

  const handleEditCancel = useCallback(() => {
    setEditText(comment.body_text || '')
    setEditMode(false)
  }, [comment.body_text])

  const handleDelete = useCallback(() => {
    if (onDelete) {
      onDelete(comment.id)
    }
  }, [comment.id, onDelete])

  // Deleted comment display
  if (comment.is_deleted) {
    return (
      <div
        className={cn(
          'flex items-start gap-3 py-3 px-2',
          'opacity-50',
          className
        )}
      >
        <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-muted">
          <User className="h-4 w-4 text-muted-foreground" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm italic text-muted-foreground">[Comment deleted]</p>
        </div>
      </div>
    )
  }

  return (
    <div
      className={cn(
        'group flex items-start gap-3 py-3 px-2 rounded-md',
        'transition-colors duration-100',
        'hover:bg-muted/30',
        className
      )}
      onMouseEnter={() => setShowActions(true)}
      onMouseLeave={() => setShowActions(false)}
    >
      {/* Avatar */}
      {comment.author_avatar_url ? (
        <img
          src={comment.author_avatar_url}
          alt={comment.author_name || 'User'}
          className="h-8 w-8 flex-shrink-0 rounded-full object-cover"
        />
      ) : (
        <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary text-xs font-medium">
          {getInitials(comment.author_name)}
        </div>
      )}

      {/* Content */}
      <div className="flex-1 min-w-0">
        {/* Header */}
        <div className="flex items-center gap-2 mb-1">
          <span className="text-sm font-medium text-foreground">
            {comment.author_name || 'Unknown user'}
          </span>
          <span className="text-xs text-muted-foreground">
            {formatTimestamp(comment.created_at)}
          </span>
          {comment.updated_at && comment.updated_at !== comment.created_at && (
            <span className="text-xs text-muted-foreground">(edited)</span>
          )}
        </div>

        {/* Body */}
        {editMode ? (
          <div className="flex flex-col gap-2">
            <textarea
              value={editText}
              onChange={(e) => setEditText(e.target.value)}
              className={cn(
                'w-full min-h-[60px] p-2 rounded-md',
                'border border-border bg-background',
                'text-sm text-foreground',
                'focus:outline-none focus:ring-1 focus:ring-ring',
                'resize-none'
              )}
              placeholder="Edit your comment..."
              disabled={disabled}
            />
            <div className="flex items-center gap-2">
              <button
                onClick={handleEditSubmit}
                disabled={!editText.trim() || disabled}
                className={cn(
                  'inline-flex items-center gap-1 px-2 py-1 rounded-md',
                  'text-xs font-medium',
                  'bg-primary text-primary-foreground',
                  'hover:bg-primary/90',
                  'disabled:opacity-50 disabled:cursor-not-allowed',
                  'transition-colors'
                )}
              >
                <Check className="h-3 w-3" />
                Save
              </button>
              <button
                onClick={handleEditCancel}
                disabled={disabled}
                className={cn(
                  'inline-flex items-center gap-1 px-2 py-1 rounded-md',
                  'text-xs font-medium',
                  'bg-muted text-muted-foreground',
                  'hover:bg-muted/80',
                  'disabled:opacity-50 disabled:cursor-not-allowed',
                  'transition-colors'
                )}
              >
                <X className="h-3 w-3" />
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <div className="text-sm text-foreground whitespace-pre-wrap break-words">
            {renderCommentContent(comment)}
          </div>
        )}
      </div>

      {/* Actions */}
      {canModify && !editMode && (showActions || isEditing) && (
        <div className="flex items-center gap-1 flex-shrink-0">
          {onEdit && (
            <button
              onClick={() => setEditMode(true)}
              disabled={disabled}
              className={cn(
                'flex h-6 w-6 items-center justify-center rounded-md',
                'text-muted-foreground',
                'hover:bg-muted hover:text-foreground',
                'disabled:opacity-50 disabled:cursor-not-allowed',
                'transition-colors'
              )}
              title="Edit"
            >
              <Edit2 className="h-3 w-3" />
            </button>
          )}
          {onDelete && (
            <button
              onClick={handleDelete}
              disabled={disabled}
              className={cn(
                'flex h-6 w-6 items-center justify-center rounded-md',
                'text-muted-foreground',
                'hover:bg-destructive/10 hover:text-destructive',
                'disabled:opacity-50 disabled:cursor-not-allowed',
                'transition-colors'
              )}
              title="Delete"
            >
              <Trash2 className="h-3 w-3" />
            </button>
          )}
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Content Rendering
// ============================================================================

/**
 * Render comment content with @mentions highlighted
 */
function renderCommentContent(comment: Comment): JSX.Element {
  const text = comment.body_text || ''

  // If we have mentions, try to highlight them in the text
  if (comment.mentions.length > 0) {
    const mentionNames = comment.mentions
      .map((m) => m.user_name)
      .filter((n): n is string => !!n)

    if (mentionNames.length > 0) {
      // Create a regex to match @mentions
      const mentionPattern = new RegExp(
        `@(${mentionNames.map((n) => escapeRegex(n)).join('|')})`,
        'gi'
      )

      const parts = text.split(mentionPattern)

      return (
        <>
          {parts.map((part, index) => {
            const isMention = mentionNames.some(
              (n) => n.toLowerCase() === part.toLowerCase()
            )
            if (isMention) {
              return (
                <span
                  key={index}
                  className="inline-flex items-center px-1 py-0.5 rounded bg-primary/10 text-primary text-xs font-medium"
                >
                  @{part}
                </span>
              )
            }
            return <span key={index}>{part}</span>
          })}
        </>
      )
    }
  }

  return <>{text}</>
}

function escapeRegex(str: string): string {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

// ============================================================================
// Exports
// ============================================================================

export default CommentItem
