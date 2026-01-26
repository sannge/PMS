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

import { useState, useCallback, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { cn } from '@/lib/utils'
import { User, Edit2, Trash2, Check, X, FileText, FileImage, File, Download, Maximize2 } from 'lucide-react'
import type { Comment, CommentAttachment } from '@/hooks/use-comments'
import { useAuthStore } from '@/stores/auth-store'
import { useFilesStore, formatFileSize, isImageFile } from '@/stores/files-store'
import { queryKeys } from '@/lib/query-client'
import { ImageViewer } from '@/components/ui/image-viewer'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'

// ============================================================================
// Types
// ============================================================================

export interface CommentItemProps {
  comment: Comment
  currentUserId?: string
  /** @deprecated No longer used - edit is handled internally */
  onEdit?: (commentId: string, bodyText: string) => void
  /** @deprecated No longer used - delete is handled internally */
  onDelete?: (commentId: string) => void
  isEditing?: boolean
  disabled?: boolean
  className?: string
}

// Helper to get auth headers
function getAuthHeaders(token: string | null): Record<string, string> {
  if (!token) return {}
  return { Authorization: `Bearer ${token}` }
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Parse date string from backend, handling UTC correctly.
 * Backend sends ISO strings without timezone (e.g., "2024-01-15T10:30:00.123456")
 * which should be interpreted as UTC.
 */
function parseDate(dateString: string): Date {
  // If the date string doesn't have timezone info, treat it as UTC
  if (!dateString.endsWith('Z') && !dateString.includes('+') && !/[+-]\d{2}:\d{2}$/.test(dateString)) {
    return new Date(dateString + 'Z')
  }
  return new Date(dateString)
}

/**
 * Format timestamp with relative time for recent dates, absolute for older ones.
 * - < 1 minute: "Just now"
 * - < 60 minutes: "Xm ago"
 * - < 24 hours: "Xh ago"
 * - >= 24 hours: absolute date/time
 */
function formatTimestamp(dateString: string): string {
  const date = parseDate(dateString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)

  // Handle invalid dates or future dates
  if (isNaN(date.getTime()) || diffMs < 0) {
    return 'Just now'
  }

  // Show relative time for last 24 hours
  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`

  // Show absolute time for older comments
  const isToday = date.toDateString() === now.toDateString()
  const yesterday = new Date(now)
  yesterday.setDate(yesterday.getDate() - 1)
  const isYesterday = date.toDateString() === yesterday.toDateString()

  if (isToday) {
    return `Today at ${date.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })}`
  }

  if (isYesterday) {
    return `Yesterday at ${date.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })}`
  }

  // Older than yesterday - show full date
  const sameYear = date.getFullYear() === now.getFullYear()
  return date.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: sameYear ? undefined : 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

/**
 * Hook to update timestamps periodically
 * Returns null if dateString is null/undefined
 */
function useRelativeTime(dateString: string | null | undefined): string | null {
  const [formattedTime, setFormattedTime] = useState<string | null>(() =>
    dateString ? formatTimestamp(dateString) : null
  )

  useEffect(() => {
    if (!dateString) {
      setFormattedTime(null)
      return
    }

    // Update immediately
    setFormattedTime(formatTimestamp(dateString))

    // Calculate when we need to update next
    const date = parseDate(dateString)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / 60000)

    // Don't set up interval for invalid/future dates or old dates
    if (isNaN(date.getTime()) || diffMs < 0 || diffMins >= 24 * 60) {
      return
    }

    // Update more frequently for recent comments
    let intervalMs: number
    if (diffMins < 1) {
      intervalMs = 10000 // Every 10 seconds for "Just now"
    } else if (diffMins < 60) {
      intervalMs = 60000 // Every minute for "Xm ago"
    } else {
      intervalMs = 60000 * 5 // Every 5 minutes for "Xh ago"
    }

    const interval = setInterval(() => {
      setFormattedTime(formatTimestamp(dateString))
    }, intervalMs)

    return () => clearInterval(interval)
  }, [dateString])

  return formattedTime
}

function getInitials(name: string | null): string {
  if (!name) return '?'
  const parts = name.trim().split(/\s+/)
  if (parts.length === 1) return parts[0].charAt(0).toUpperCase()
  return (parts[0].charAt(0) + parts[parts.length - 1].charAt(0)).toUpperCase()
}

// ============================================================================
// Attachment Display Component
// ============================================================================

interface CommentAttachmentItemProps {
  attachment: CommentAttachment
  preloadedUrl?: string | null  // Pre-fetched URL from batch load
}

function CommentAttachmentItem({ attachment, preloadedUrl }: CommentAttachmentItemProps): JSX.Element {
  const [imageUrl, setImageUrl] = useState<string | null>(preloadedUrl || null)
  const [isLoadingUrl, setIsLoadingUrl] = useState(false)
  const [isViewerOpen, setIsViewerOpen] = useState(false)
  const { getDownloadUrl } = useFilesStore()

  const isImage = isImageFile(attachment.file_type)

  // Update imageUrl when preloadedUrl changes
  useEffect(() => {
    if (preloadedUrl) {
      setImageUrl(preloadedUrl)
    }
  }, [preloadedUrl])

  // Load image preview for image attachments (fallback if not preloaded)
  useEffect(() => {
    if (isImage && !imageUrl && !isLoadingUrl && !preloadedUrl) {
      let isCancelled = false
      setIsLoadingUrl(true)
      getDownloadUrl(attachment.id).then((url) => {
        if (!isCancelled) {
          setImageUrl(url)
          setIsLoadingUrl(false)
        }
      })
      return () => {
        isCancelled = true
      }
    }
  }, [isImage, imageUrl, isLoadingUrl, attachment.id, getDownloadUrl, preloadedUrl])

  const handleDownload = useCallback(async () => {
    const url = await getDownloadUrl(attachment.id)
    if (url) {
      window.open(url, '_blank')
    }
  }, [attachment.id, getDownloadUrl])

  const handleOpenViewer = useCallback(() => {
    if (imageUrl) {
      setIsViewerOpen(true)
    }
  }, [imageUrl])

  // Image attachment - show preview
  if (isImage) {
    return (
      <>
        <div className="group relative mt-2 max-w-xs overflow-hidden rounded-lg border border-border/50 bg-muted/20">
          {imageUrl ? (
            <img
              src={imageUrl}
              alt={attachment.file_name}
              className="max-h-48 w-full object-contain cursor-pointer hover:opacity-90 transition-opacity"
              onClick={handleOpenViewer}
            />
          ) : (
            <div className="flex h-32 w-full items-center justify-center bg-muted/50">
              <FileImage className="h-8 w-8 text-muted-foreground animate-pulse" />
            </div>
          )}
          <div className="absolute inset-0 flex items-center justify-center gap-2 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity">
            <button
              onClick={handleOpenViewer}
              className="flex items-center gap-1.5 rounded-md bg-white/90 px-3 py-1.5 text-xs font-medium text-black hover:bg-white transition-colors"
            >
              <Maximize2 className="h-3.5 w-3.5" />
              View
            </button>
            <button
              onClick={handleDownload}
              className="flex items-center gap-1.5 rounded-md bg-white/90 px-3 py-1.5 text-xs font-medium text-black hover:bg-white transition-colors"
            >
              <Download className="h-3.5 w-3.5" />
            </button>
          </div>
          <div className="px-2 py-1.5 border-t border-border/30 bg-card/50">
            <p className="truncate text-xs text-muted-foreground" title={attachment.file_name}>
              {attachment.file_name}
            </p>
          </div>
        </div>

        {/* Image Viewer Modal */}
        {imageUrl && (
          <ImageViewer
            src={imageUrl}
            alt={attachment.file_name}
            fileName={attachment.file_name}
            isOpen={isViewerOpen}
            onClose={() => setIsViewerOpen(false)}
          />
        )}
      </>
    )
  }

  // Non-image attachment - show file card
  return (
    <button
      onClick={handleDownload}
      className={cn(
        'group mt-2 flex items-center gap-3 rounded-lg border border-border/50 bg-muted/20 px-3 py-2',
        'hover:border-border hover:bg-muted/40 transition-all cursor-pointer',
        'text-left w-full max-w-xs'
      )}
    >
      <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-md bg-primary/10">
        {attachment.file_type?.includes('pdf') ? (
          <FileText className="h-5 w-5 text-red-500" />
        ) : (
          <File className="h-5 w-5 text-muted-foreground" />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-foreground" title={attachment.file_name}>
          {attachment.file_name}
        </p>
        <p className="text-xs text-muted-foreground">
          {formatFileSize(attachment.file_size)}
        </p>
      </div>
      <Download className="h-4 w-4 flex-shrink-0 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
    </button>
  )
}

// ============================================================================
// Component
// ============================================================================

export function CommentItem({
  comment,
  currentUserId,
  onEdit: _onEdit,
  onDelete: _onDelete,
  isEditing = false,
  disabled = false,
  className,
}: CommentItemProps): JSX.Element {
  const queryClient = useQueryClient()
  const token = useAuthStore((s) => s.token)
  const [showActions, setShowActions] = useState(false)
  const [editMode, setEditMode] = useState(false)
  const [editText, setEditText] = useState(comment.body_text || '')
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [attachmentUrls, setAttachmentUrls] = useState<Record<string, string>>({})
  const { getDownloadUrls } = useFilesStore()

  // Update comment mutation
  const updateMutation = useMutation({
    mutationFn: async (bodyText: string) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }
      const response = await window.electronAPI.put<Comment>(
        `/api/comments/${comment.id}`,
        { body_text: bodyText },
        getAuthHeaders(token)
      )
      if (response.status !== 200) {
        throw new Error('Failed to update comment')
      }
      return response.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.comments(comment.task_id) })
      setEditMode(false)
    },
  })

  // Delete comment mutation
  const deleteMutation = useMutation({
    mutationFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }
      const response = await window.electronAPI.delete<void>(
        `/api/comments/${comment.id}`,
        getAuthHeaders(token)
      )
      if (response.status !== 204 && response.status !== 200) {
        throw new Error('Failed to delete comment')
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.comments(comment.task_id) })
    },
  })

  const isMutating = updateMutation.isPending || deleteMutation.isPending

  // Batch load image URLs for attachments
  useEffect(() => {
    if (!comment.attachments || comment.attachments.length === 0) return

    const imageAttachments = comment.attachments.filter((a) => isImageFile(a.file_type))
    if (imageAttachments.length === 0) return

    let isCancelled = false
    const ids = imageAttachments.map((a) => a.id)

    getDownloadUrls(ids).then((urls) => {
      if (!isCancelled) {
        setAttachmentUrls(urls)
      }
    })

    return () => {
      isCancelled = true
    }
  }, [comment.id, comment.attachments, getDownloadUrls])

  // Use hook for auto-updating relative timestamps
  const timestamp = useRelativeTime(comment.created_at)

  // Check if comment was edited (updated_at differs from created_at)
  const wasEdited = comment.updated_at && comment.updated_at !== comment.created_at
  const editedTimestamp = useRelativeTime(wasEdited ? comment.updated_at : null)

  const isOwnComment = currentUserId && comment.author_id === currentUserId
  const canModify = isOwnComment && !comment.is_deleted

  const handleEditSubmit = useCallback(() => {
    if (editText.trim()) {
      updateMutation.mutate(editText.trim())
    }
  }, [editText, updateMutation])

  const handleEditCancel = useCallback(() => {
    setEditText(comment.body_text || '')
    setEditMode(false)
  }, [comment.body_text])

  const handleDeleteClick = useCallback(() => {
    setShowDeleteConfirm(true)
  }, [])

  const handleConfirmDelete = useCallback(() => {
    deleteMutation.mutate()
    setShowDeleteConfirm(false)
  }, [deleteMutation])

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
            {timestamp}
          </span>
          {wasEdited && editedTimestamp && (
            <span className="text-xs text-muted-foreground" title={`Edited ${editedTimestamp}`}>
              (edited {editedTimestamp})
            </span>
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
              disabled={disabled || isMutating}
            />
            <div className="flex items-center gap-2">
              <button
                onClick={handleEditSubmit}
                disabled={!editText.trim() || disabled || isMutating}
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
                {updateMutation.isPending ? 'Saving...' : 'Save'}
              </button>
              <button
                onClick={handleEditCancel}
                disabled={disabled || isMutating}
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
          <>
            <div className="text-sm text-foreground whitespace-pre-wrap break-words">
              {renderCommentContent(comment)}
            </div>

            {/* Attachments */}
            {comment.attachments && comment.attachments.length > 0 && (
              <div className="mt-2 space-y-1">
                {comment.attachments.map((attachment) => (
                  <CommentAttachmentItem
                    key={attachment.id}
                    attachment={attachment}
                    preloadedUrl={attachmentUrls[attachment.id]}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </div>

      {/* Actions */}
      {canModify && !editMode && (showActions || isEditing) && (
        <div className="flex items-center gap-1 flex-shrink-0">
          <button
            onClick={() => setEditMode(true)}
            disabled={disabled || isMutating}
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
          <button
            onClick={handleDeleteClick}
            disabled={disabled || isMutating}
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
        </div>
      )}

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        open={showDeleteConfirm}
        onOpenChange={setShowDeleteConfirm}
        title="Delete comment?"
        description="Are you sure you want to delete this comment? This action cannot be undone."
        confirmLabel="Delete"
        variant="destructive"
        onConfirm={handleConfirmDelete}
      />
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
