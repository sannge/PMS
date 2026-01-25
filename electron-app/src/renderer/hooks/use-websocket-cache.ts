/**
 * WebSocket Cache Invalidation Hook
 *
 * Connects WebSocket events to TanStack Query cache invalidation.
 * When a WebSocket event arrives from another user, the relevant
 * query cache is invalidated to trigger a background refetch.
 *
 * This enables real-time updates across all tabs and users without
 * manual cache management in components.
 *
 * @see https://tanstack.com/query/latest/docs/react/guides/invalidations
 */

import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { wsClient, MessageType, type Unsubscribe } from '@/lib/websocket'
import { queryKeys } from '@/lib/query-client'

// ============================================================================
// Types for WebSocket Event Data
// ============================================================================

interface ApplicationEventData {
  application_id: string
  [key: string]: unknown
}

interface ProjectEventData {
  project_id: string
  application_id?: string
  [key: string]: unknown
}

interface TaskEventData {
  task_id: string
  project_id: string
  [key: string]: unknown
}

interface CommentEventData {
  task_id: string
  comment_id?: string
  [key: string]: unknown
}

interface ChecklistEventData {
  task_id: string
  checklist_id?: string
  [key: string]: unknown
}

interface MemberEventData {
  application_id: string
  user_id: string
  [key: string]: unknown
}

interface ProjectMemberEventData {
  project_id: string
  user_id: string
  [key: string]: unknown
}

interface NotificationEventData {
  notification_id?: string
  [key: string]: unknown
}

interface AttachmentEventData {
  task_id: string
  attachment_id?: string
  [key: string]: unknown
}

// ============================================================================
// Hook
// ============================================================================

/**
 * Hook that subscribes to WebSocket events and invalidates
 * the corresponding TanStack Query caches.
 *
 * Call this once at the app level (e.g., in Dashboard or App component).
 */
export function useWebSocketCacheInvalidation(): void {
  const queryClient = useQueryClient()

  useEffect(() => {
    const unsubscribers: Unsubscribe[] = []

    // ========================================================================
    // Application Events
    // ========================================================================

    unsubscribers.push(
      wsClient.on<ApplicationEventData>(MessageType.APPLICATION_UPDATED, (data) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.application(data.application_id) })
        queryClient.invalidateQueries({ queryKey: queryKeys.applications })
      })
    )

    unsubscribers.push(
      wsClient.on<ApplicationEventData>(MessageType.APPLICATION_DELETED, (data) => {
        queryClient.removeQueries({ queryKey: queryKeys.application(data.application_id) })
        queryClient.invalidateQueries({ queryKey: queryKeys.applications })
      })
    )

    // ========================================================================
    // Project Events
    // ========================================================================

    unsubscribers.push(
      wsClient.on<ProjectEventData>(MessageType.PROJECT_CREATED, (data) => {
        if (data.application_id) {
          queryClient.invalidateQueries({ queryKey: queryKeys.projects(data.application_id) })
        }
      })
    )

    unsubscribers.push(
      wsClient.on<ProjectEventData>(MessageType.PROJECT_UPDATED, (data) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.project(data.project_id) })
        if (data.application_id) {
          queryClient.invalidateQueries({ queryKey: queryKeys.projects(data.application_id) })
        }
      })
    )

    unsubscribers.push(
      wsClient.on<ProjectEventData>(MessageType.PROJECT_DELETED, (data) => {
        queryClient.removeQueries({ queryKey: queryKeys.project(data.project_id) })
        queryClient.removeQueries({ queryKey: queryKeys.tasks(data.project_id) })
        if (data.application_id) {
          queryClient.invalidateQueries({ queryKey: queryKeys.projects(data.application_id) })
        }
      })
    )

    unsubscribers.push(
      wsClient.on<ProjectEventData>(MessageType.PROJECT_STATUS_CHANGED, (data) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.project(data.project_id) })
        if (data.application_id) {
          queryClient.invalidateQueries({ queryKey: queryKeys.projects(data.application_id) })
        }
      })
    )

    // ========================================================================
    // Task Events
    // ========================================================================

    unsubscribers.push(
      wsClient.on<TaskEventData>(MessageType.TASK_CREATED, (data) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.tasks(data.project_id) })
      })
    )

    unsubscribers.push(
      wsClient.on<TaskEventData>(MessageType.TASK_UPDATED, (data) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.task(data.task_id) })
        queryClient.invalidateQueries({ queryKey: queryKeys.tasks(data.project_id) })
      })
    )

    unsubscribers.push(
      wsClient.on<TaskEventData>(MessageType.TASK_DELETED, (data) => {
        queryClient.removeQueries({ queryKey: queryKeys.task(data.task_id) })
        queryClient.invalidateQueries({ queryKey: queryKeys.tasks(data.project_id) })
      })
    )

    unsubscribers.push(
      wsClient.on<TaskEventData>(MessageType.TASK_STATUS_CHANGED, (data) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.task(data.task_id) })
        queryClient.invalidateQueries({ queryKey: queryKeys.tasks(data.project_id) })
      })
    )

    unsubscribers.push(
      wsClient.on<TaskEventData>(MessageType.TASK_MOVED, (data) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.task(data.task_id) })
        queryClient.invalidateQueries({ queryKey: queryKeys.tasks(data.project_id) })
      })
    )

    // ========================================================================
    // Comment Events
    // ========================================================================

    unsubscribers.push(
      wsClient.on<CommentEventData>(MessageType.COMMENT_ADDED, (data) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.comments(data.task_id) })
      })
    )

    unsubscribers.push(
      wsClient.on<CommentEventData>(MessageType.COMMENT_UPDATED, (data) => {
        if (data.comment_id) {
          queryClient.invalidateQueries({ queryKey: queryKeys.comment(data.comment_id) })
        }
        queryClient.invalidateQueries({ queryKey: queryKeys.comments(data.task_id) })
      })
    )

    unsubscribers.push(
      wsClient.on<CommentEventData>(MessageType.COMMENT_DELETED, (data) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.comments(data.task_id) })
      })
    )

    // ========================================================================
    // Checklist Events
    // ========================================================================

    unsubscribers.push(
      wsClient.on<ChecklistEventData>(MessageType.CHECKLIST_CREATED, (data) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.checklists(data.task_id) })
        queryClient.invalidateQueries({ queryKey: queryKeys.task(data.task_id) })
      })
    )

    unsubscribers.push(
      wsClient.on<ChecklistEventData>(MessageType.CHECKLIST_UPDATED, (data) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.checklists(data.task_id) })
        queryClient.invalidateQueries({ queryKey: queryKeys.task(data.task_id) })
      })
    )

    unsubscribers.push(
      wsClient.on<ChecklistEventData>(MessageType.CHECKLIST_DELETED, (data) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.checklists(data.task_id) })
        queryClient.invalidateQueries({ queryKey: queryKeys.task(data.task_id) })
      })
    )

    unsubscribers.push(
      wsClient.on<ChecklistEventData>(MessageType.CHECKLISTS_REORDERED, (data) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.checklists(data.task_id) })
      })
    )

    unsubscribers.push(
      wsClient.on<ChecklistEventData>(MessageType.CHECKLIST_ITEM_TOGGLED, (data) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.checklists(data.task_id) })
        queryClient.invalidateQueries({ queryKey: queryKeys.task(data.task_id) })
      })
    )

    unsubscribers.push(
      wsClient.on<ChecklistEventData>(MessageType.CHECKLIST_ITEM_ADDED, (data) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.checklists(data.task_id) })
      })
    )

    unsubscribers.push(
      wsClient.on<ChecklistEventData>(MessageType.CHECKLIST_ITEM_UPDATED, (data) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.checklists(data.task_id) })
      })
    )

    unsubscribers.push(
      wsClient.on<ChecklistEventData>(MessageType.CHECKLIST_ITEM_DELETED, (data) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.checklists(data.task_id) })
      })
    )

    unsubscribers.push(
      wsClient.on<ChecklistEventData>(MessageType.CHECKLIST_ITEMS_REORDERED, (data) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.checklists(data.task_id) })
      })
    )

    // ========================================================================
    // Application Member Events
    // ========================================================================

    unsubscribers.push(
      wsClient.on<MemberEventData>(MessageType.MEMBER_ADDED, (data) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.appMembers(data.application_id) })
      })
    )

    unsubscribers.push(
      wsClient.on<MemberEventData>(MessageType.MEMBER_REMOVED, (data) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.appMembers(data.application_id) })
      })
    )

    unsubscribers.push(
      wsClient.on<MemberEventData>(MessageType.ROLE_UPDATED, (data) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.appMembers(data.application_id) })
      })
    )

    // ========================================================================
    // Project Member Events
    // ========================================================================

    unsubscribers.push(
      wsClient.on<ProjectMemberEventData>(MessageType.PROJECT_MEMBER_ADDED, (data) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.projectMembers(data.project_id) })
      })
    )

    unsubscribers.push(
      wsClient.on<ProjectMemberEventData>(MessageType.PROJECT_MEMBER_REMOVED, (data) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.projectMembers(data.project_id) })
        // Also invalidate tasks since permissions may have changed
        queryClient.invalidateQueries({ queryKey: queryKeys.tasks(data.project_id) })
      })
    )

    unsubscribers.push(
      wsClient.on<ProjectMemberEventData>(MessageType.PROJECT_ROLE_CHANGED, (data) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.projectMembers(data.project_id) })
        // Also invalidate tasks since permissions may have changed
        queryClient.invalidateQueries({ queryKey: queryKeys.tasks(data.project_id) })
      })
    )

    // ========================================================================
    // Notification Events
    // ========================================================================

    unsubscribers.push(
      wsClient.on<NotificationEventData>(MessageType.NOTIFICATION, () => {
        queryClient.invalidateQueries({ queryKey: queryKeys.notifications })
        queryClient.invalidateQueries({ queryKey: queryKeys.unreadCount })
      })
    )

    unsubscribers.push(
      wsClient.on<NotificationEventData>(MessageType.NOTIFICATION_READ, () => {
        queryClient.invalidateQueries({ queryKey: queryKeys.notifications })
        queryClient.invalidateQueries({ queryKey: queryKeys.unreadCount })
      })
    )

    // ========================================================================
    // Attachment Events
    // ========================================================================

    unsubscribers.push(
      wsClient.on<AttachmentEventData>(MessageType.ATTACHMENT_UPLOADED, (data) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.attachments(data.task_id) })
      })
    )

    unsubscribers.push(
      wsClient.on<AttachmentEventData>(MessageType.ATTACHMENT_DELETED, (data) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.attachments(data.task_id) })
        if (data.attachment_id) {
          queryClient.removeQueries({ queryKey: queryKeys.downloadUrl(data.attachment_id) })
        }
      })
    )

    // ========================================================================
    // Invitation Events (also update member lists)
    // ========================================================================

    unsubscribers.push(
      wsClient.on<{ application_id: string }>(MessageType.INVITATION_RESPONSE, (data) => {
        // When someone accepts an invitation, refresh the members list
        queryClient.invalidateQueries({ queryKey: queryKeys.appMembers(data.application_id) })
        queryClient.invalidateQueries({ queryKey: queryKeys.invitations })
      })
    )

    unsubscribers.push(
      wsClient.on(MessageType.INVITATION_RECEIVED, () => {
        queryClient.invalidateQueries({ queryKey: queryKeys.invitations })
        queryClient.invalidateQueries({ queryKey: queryKeys.pendingInvitations })
      })
    )

    // Cleanup on unmount
    return () => {
      unsubscribers.forEach((unsubscribe) => unsubscribe())
    }
  }, [queryClient])
}

/**
 * Alias for backward compatibility
 */
export const useQueryCacheSync = useWebSocketCacheInvalidation

export default useWebSocketCacheInvalidation
