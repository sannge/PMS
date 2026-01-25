/**
 * CommentThread Component
 *
 * Displays a list of comments for a task with infinite scroll.
 * Features:
 * - Comment list with pagination
 * - Comment creation with @mentions
 * - Edit/delete for own comments
 * - Real-time updates via WebSocket
 * - Loading and empty states
 */

import { useEffect, useCallback, useRef } from 'react'
import { cn } from '@/lib/utils'
import { MessageSquare, Loader2, AlertCircle } from 'lucide-react'
import { useCommentsStore, type Comment } from '@/stores/comments-store'
import { useAuthStore } from '@/stores/auth-store'
import { useFilesStore } from '@/stores/files-store'
import { CommentItem } from './CommentItem'
import { CommentInput, type MentionSuggestion } from './CommentInput'
import { TypingIndicator } from '@/components/presence'
import { SkeletonComments } from '@/components/ui/skeleton'
import { wsClient, MessageType } from '@/lib/websocket'

// ============================================================================
// Types
// ============================================================================

export interface CommentThreadProps {
  taskId: string
  onMentionSearch?: (query: string) => void
  mentionSuggestions?: MentionSuggestion[]
  typingUsers?: Record<string, { user_name: string; expires_at: number }>
  onTyping?: () => void
  className?: string
}

// ============================================================================
// Component
// ============================================================================

export function CommentThread({
  taskId,
  onMentionSearch,
  mentionSuggestions = [],
  typingUsers = {},
  onTyping,
  className,
}: CommentThreadProps): JSX.Element {
  const token = useAuthStore((state) => state.token)
  const userId = useAuthStore((state) => state.user?.id)
  const removeAttachmentsByIds = useFilesStore((state) => state.removeAttachmentsByIds)

  const {
    comments,
    isLoading,
    isLoadingMore,
    isCreating,
    hasMore,
    error,
    fetchComments,
    loadMore,
    createComment,
    updateComment,
    deleteComment,
    clearError,
    handleCommentAdded,
    handleCommentUpdated,
    handleCommentDeleted,
  } = useCommentsStore()

  const observerRef = useRef<IntersectionObserver | null>(null)
  const loadMoreRef = useRef<HTMLDivElement>(null)

  // Fetch comments on mount or task change
  useEffect(() => {
    fetchComments(token, taskId)
  }, [token, taskId, fetchComments])

  // Subscribe to WebSocket events for real-time updates
  useEffect(() => {
    if (!taskId) return

    const roomId = `task:${taskId}`

    // Join the room for this task
    wsClient.joinRoom(roomId)

    // Handle comment added event - use full comment data directly
    const onCommentAdded = (data: { task_id?: string; comment?: Comment }) => {
      if (data.task_id === taskId && data.comment) {
        handleCommentAdded(data.comment)
      }
    }

    // Handle comment updated event - use full comment data directly
    const onCommentUpdated = (data: { task_id?: string; comment_id?: string; comment?: Comment }) => {
      if (data.task_id === taskId && data.comment_id && data.comment) {
        handleCommentUpdated(data.comment_id, data.comment)
      }
    }

    // Handle comment deleted event
    const onCommentDeleted = (data: { task_id?: string; comment_id?: string; attachment_ids?: string[] }) => {
      if (data.task_id === taskId && data.comment_id) {
        handleCommentDeleted(data.comment_id)
        // Remove associated attachments from the task's attachment list
        if (data.attachment_ids && data.attachment_ids.length > 0) {
          removeAttachmentsByIds(data.attachment_ids)
        }
      }
    }

    // Subscribe to events
    wsClient.on(MessageType.COMMENT_ADDED, onCommentAdded)
    wsClient.on(MessageType.COMMENT_UPDATED, onCommentUpdated)
    wsClient.on(MessageType.COMMENT_DELETED, onCommentDeleted)

    // Cleanup: leave room and unsubscribe
    return () => {
      wsClient.leaveRoom(roomId)
      wsClient.off(MessageType.COMMENT_ADDED, onCommentAdded)
      wsClient.off(MessageType.COMMENT_UPDATED, onCommentUpdated)
      wsClient.off(MessageType.COMMENT_DELETED, onCommentDeleted)
    }
  }, [taskId, handleCommentAdded, handleCommentUpdated, handleCommentDeleted, removeAttachmentsByIds])

  // Setup infinite scroll observer
  useEffect(() => {
    if (observerRef.current) {
      observerRef.current.disconnect()
    }

    observerRef.current = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore && !isLoadingMore) {
          loadMore(token)
        }
      },
      { threshold: 0.1 }
    )

    if (loadMoreRef.current) {
      observerRef.current.observe(loadMoreRef.current)
    }

    return () => {
      if (observerRef.current) {
        observerRef.current.disconnect()
      }
    }
  }, [hasMore, isLoadingMore, loadMore, token])

  // Handlers
  const handleSubmit = useCallback(
    async (content: { body_text: string; body_json?: Record<string, unknown> }, attachmentIds?: string[]) => {
      await createComment(token, taskId, {
        ...content,
        attachment_ids: attachmentIds,
      })
    },
    [token, taskId, createComment]
  )

  const handleEdit = useCallback(
    async (commentId: string, bodyText: string) => {
      await updateComment(token, commentId, { body_text: bodyText })
    },
    [token, updateComment]
  )

  const handleDelete = useCallback(
    async (commentId: string) => {
      await deleteComment(token, commentId)
    },
    [token, deleteComment]
  )

  // Loading state - show skeleton
  if (isLoading && comments.length === 0) {
    return (
      <div className={cn('flex flex-col h-full', className)}>
        {/* Header */}
        <div className="flex items-center gap-2 px-2 py-2 border-b border-border">
          <MessageSquare className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-medium text-foreground">Comments</span>
        </div>
        {/* Skeleton content */}
        <div className="flex-1 overflow-y-auto p-4">
          <SkeletonComments count={3} />
        </div>
      </div>
    )
  }

  // Error state
  if (error && comments.length === 0) {
    return (
      <div className={cn('flex flex-col', className)}>
        <div className="flex flex-col items-center justify-center py-8 gap-2">
          <AlertCircle className="h-8 w-8 text-destructive" />
          <p className="text-sm text-destructive">{error.message}</p>
          <button
            onClick={() => {
              clearError()
              fetchComments(token, taskId)
            }}
            className={cn(
              'text-sm text-primary underline',
              'hover:no-underline'
            )}
          >
            Try again
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className={cn('flex flex-col h-full', className)}>
      {/* Header */}
      <div className="flex items-center gap-2 px-2 py-2 border-b border-border">
        <MessageSquare className="h-4 w-4 text-muted-foreground" />
        <span className="text-sm font-medium text-foreground">
          Comments
        </span>
        {comments.length > 0 && (
          <span className="text-xs text-muted-foreground">
            ({comments.filter((c) => !c.is_deleted).length})
          </span>
        )}
      </div>

      {/* Comment list */}
      <div className="flex-1 overflow-y-auto">
        {comments.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 px-4">
            <MessageSquare className="h-10 w-10 text-muted-foreground/50 mb-2" />
            <p className="text-sm text-muted-foreground text-center">
              No comments yet. Be the first to comment!
            </p>
          </div>
        ) : (
          <div className="divide-y divide-border/50">
            {comments.map((comment) => (
              <CommentItem
                key={comment.id}
                comment={comment}
                currentUserId={userId}
                onEdit={handleEdit}
                onDelete={handleDelete}
                disabled={isCreating}
              />
            ))}

            {/* Load more trigger */}
            {hasMore && (
              <div
                ref={loadMoreRef}
                className="flex items-center justify-center py-4"
              >
                {isLoadingMore ? (
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                ) : (
                  <button
                    onClick={() => loadMore(token)}
                    className={cn(
                      'text-sm text-primary',
                      'hover:underline'
                    )}
                  >
                    Load more comments
                  </button>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Error banner */}
      {error && comments.length > 0 && (
        <div className="flex items-center gap-2 px-3 py-2 bg-destructive/10 border-t border-destructive/20">
          <AlertCircle className="h-4 w-4 text-destructive flex-shrink-0" />
          <p className="text-xs text-destructive flex-1">{error.message}</p>
          <button
            onClick={clearError}
            className="text-xs text-destructive underline"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Typing indicator */}
      {Object.keys(typingUsers).length > 0 && (
        <div className="px-3 py-1 border-t border-border">
          <TypingIndicator typingUsers={typingUsers} />
        </div>
      )}

      {/* Comment input */}
      <div className="border-t border-border p-3">
        <CommentInput
          taskId={taskId}
          onSubmit={handleSubmit}
          isSubmitting={isCreating}
          onMentionSearch={onMentionSearch}
          mentionSuggestions={mentionSuggestions}
          onTyping={onTyping}
        />
      </div>
    </div>
  )
}

// ============================================================================
// Exports
// ============================================================================

export default CommentThread
