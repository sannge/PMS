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

import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { wsClient, MessageType, type Unsubscribe } from '@/lib/websocket'
import { queryKeys } from '@/lib/query-client'
import type { Task } from '@/hooks/use-queries'
import { showBrowserNotification } from '@/lib/notifications'
import { useAuthStore } from '@/contexts/auth-context'

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
  attachment_ids?: string[]
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
  notification_type?: string
  title?: string
  message?: string
  entity_type?: string
  entity_id?: string
  [key: string]: unknown
}

interface AttachmentEventData {
  task_id: string
  attachment_id?: string
  [key: string]: unknown
}

interface DocumentEventData {
  document_id: string
  scope: string
  scope_id: string
  folder_id?: string | null
  actor_id?: string | null
  /** For project-scoped items, the parent application ID */
  application_id?: string | null
  [key: string]: unknown
}

interface FolderEventData {
  folder_id: string
  scope: string
  scope_id: string
  parent_id?: string | null
  actor_id?: string | null
  /** For project-scoped items, the parent application ID */
  application_id?: string | null
  [key: string]: unknown
}

// ============================================================================
// Hook
// ============================================================================

/**
 * Options for the WebSocket cache invalidation hook.
 */
export interface WebSocketCacheOptions {
  /**
   * Callback when current user is removed from an application.
   * Use this to handle navigation (e.g., redirect away from removed app).
   */
  onCurrentUserRemoved?: (applicationId: string) => void

  /**
   * Callback when a project is deleted.
   * Use this to handle navigation (e.g., redirect away from deleted project).
   */
  onProjectDeleted?: (projectId: string, applicationId: string) => void
}

/**
 * Hook that subscribes to WebSocket events and invalidates
 * the corresponding TanStack Query caches.
 *
 * Call this once at the app level (e.g., in Dashboard or App component).
 */
export function useWebSocketCacheInvalidation(options: WebSocketCacheOptions = {}): void {
  const queryClient = useQueryClient()
  const optionsRef = useRef(options)
  const currentUser = useAuthStore((state) => state.user)
  const currentUserRef = useRef(currentUser)

  // Keep refs up to date
  useEffect(() => {
    optionsRef.current = options
  }, [options])

  useEffect(() => {
    currentUserRef.current = currentUser
  }, [currentUser])

  useEffect(() => {
    console.log('[WebSocket-Cache] Hook mounted, setting up listeners')
    console.log('[WebSocket-Cache] wsClient:', wsClient)
    console.log('[WebSocket-Cache] wsClient.isConnected:', wsClient?.isConnected?.())
    const unsubscribers: Unsubscribe[] = []

    // Debug: log ALL incoming WebSocket messages
    unsubscribers.push(
      wsClient.onMessage((message) => {
        console.log('[WebSocket-Cache] Received message:', message.type, message.data)
      })
    )

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
          queryClient.invalidateQueries({ queryKey: queryKeys.myProjects(data.application_id) })
          queryClient.invalidateQueries({ queryKey: queryKeys.myProjectsCrossApp })
        }
      })
    )

    unsubscribers.push(
      wsClient.on<ProjectEventData>(MessageType.PROJECT_UPDATED, (data) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.project(data.project_id) })
        if (data.application_id) {
          queryClient.invalidateQueries({ queryKey: queryKeys.projects(data.application_id) })
          queryClient.invalidateQueries({ queryKey: queryKeys.myProjects(data.application_id) })
          queryClient.invalidateQueries({ queryKey: queryKeys.myProjectsCrossApp })
          // Also invalidate archived projects cache (project may have been archived/restored)
          queryClient.invalidateQueries({ queryKey: queryKeys.archivedProjects(data.application_id) })
          // Invalidate application cache to update projects_count
          queryClient.invalidateQueries({ queryKey: queryKeys.application(data.application_id) })
          queryClient.invalidateQueries({ queryKey: queryKeys.applications })
        }
      })
    )

    unsubscribers.push(
      wsClient.on<ProjectEventData>(MessageType.PROJECT_DELETED, (data) => {
        queryClient.removeQueries({ queryKey: queryKeys.project(data.project_id) })
        queryClient.removeQueries({ queryKey: queryKeys.tasks(data.project_id) })
        if (data.application_id) {
          queryClient.invalidateQueries({ queryKey: queryKeys.projects(data.application_id) })
          queryClient.invalidateQueries({ queryKey: queryKeys.myProjects(data.application_id) })
          queryClient.invalidateQueries({ queryKey: queryKeys.myProjectsCrossApp })
          queryClient.invalidateQueries({ queryKey: queryKeys.application(data.application_id) })
          queryClient.invalidateQueries({ queryKey: queryKeys.applications })
          // Notify parent to redirect if user is viewing this project
          optionsRef.current.onProjectDeleted?.(data.project_id, data.application_id)
        }
      })
    )

    unsubscribers.push(
      wsClient.on<ProjectEventData>(MessageType.PROJECT_STATUS_CHANGED, (data) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.project(data.project_id) })
        if (data.application_id) {
          queryClient.invalidateQueries({ queryKey: queryKeys.projects(data.application_id) })
          queryClient.invalidateQueries({ queryKey: queryKeys.myProjects(data.application_id) })
          queryClient.invalidateQueries({ queryKey: queryKeys.myProjectsCrossApp })
        }
      })
    )

    // ========================================================================
    // Task Events
    // ========================================================================

    unsubscribers.push(
      wsClient.on<TaskEventData>(MessageType.TASK_CREATED, (data) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.tasks(data.project_id) })
        queryClient.invalidateQueries({ queryKey: queryKeys.project(data.project_id) })
        queryClient.invalidateQueries({ queryKey: queryKeys.myTasksCrossApp })
      })
    )

    unsubscribers.push(
      wsClient.on<TaskEventData>(MessageType.TASK_UPDATED, (data) => {
        // WS payload: { task_id, project_id, task: { id, title, ... } }
        const taskPayload = (data as Record<string, unknown>).task as Record<string, unknown> | undefined
        if (taskPayload?.id && taskPayload?.title) {
          // Full task payload — update cache in-place, no refetch needed
          const task = taskPayload as unknown as Task
          queryClient.setQueryData<Task>(queryKeys.task(data.task_id), task)
          queryClient.setQueryData<Task[]>(queryKeys.tasks(data.project_id), (old) =>
            old?.map((t) => (t.id === data.task_id ? task : t))
          )
        } else {
          // Partial payload — fall back to invalidation
          queryClient.invalidateQueries({ queryKey: queryKeys.task(data.task_id) })
          queryClient.invalidateQueries({ queryKey: queryKeys.tasks(data.project_id) })
        }
        // Invalidate cross-app list — updates can change assignee which affects "My Tasks"
        queryClient.invalidateQueries({ queryKey: queryKeys.myTasksCrossApp })
      })
    )

    unsubscribers.push(
      wsClient.on<TaskEventData>(MessageType.TASK_DELETED, (data) => {
        queryClient.removeQueries({ queryKey: queryKeys.task(data.task_id) })
        // Remove from list cache directly instead of refetching
        queryClient.setQueryData<Task[]>(queryKeys.tasks(data.project_id), (old) =>
          old?.filter((t) => t.id !== data.task_id)
        )
        queryClient.invalidateQueries({ queryKey: queryKeys.project(data.project_id) })
        queryClient.invalidateQueries({ queryKey: queryKeys.myTasksCrossApp })
      })
    )

    unsubscribers.push(
      wsClient.on<TaskEventData>(MessageType.TASK_STATUS_CHANGED, (data) => {
        const taskPayload = (data as Record<string, unknown>).task as Record<string, unknown> | undefined
        if (taskPayload?.id && taskPayload?.title) {
          const task = taskPayload as unknown as Task
          queryClient.setQueryData<Task>(queryKeys.task(data.task_id), task)
          queryClient.setQueryData<Task[]>(queryKeys.tasks(data.project_id), (old) =>
            old?.map((t) => (t.id === data.task_id ? task : t))
          )
        } else {
          queryClient.invalidateQueries({ queryKey: queryKeys.task(data.task_id) })
          queryClient.invalidateQueries({ queryKey: queryKeys.tasks(data.project_id) })
        }
        queryClient.invalidateQueries({ queryKey: queryKeys.myTasksCrossApp })
      })
    )

    unsubscribers.push(
      wsClient.on<TaskEventData>(MessageType.TASK_MOVED, (data) => {
        const taskPayload = (data as Record<string, unknown>).task as Record<string, unknown> | undefined
        if (taskPayload?.id && taskPayload?.title) {
          const task = taskPayload as unknown as Task
          queryClient.setQueryData<Task>(queryKeys.task(data.task_id), task)
          queryClient.setQueryData<Task[]>(queryKeys.tasks(data.project_id), (old) =>
            old?.map((t) => (t.id === data.task_id ? task : t))
          )
        } else {
          queryClient.invalidateQueries({ queryKey: queryKeys.task(data.task_id) })
          queryClient.invalidateQueries({ queryKey: queryKeys.tasks(data.project_id) })
        }
        // No myTasksCrossApp invalidation — column moves don't change cross-app membership
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
        // Invalidate attachments cache - comment deletion may have removed attachments
        queryClient.invalidateQueries({ queryKey: queryKeys.attachments(data.task_id) })
        queryClient.invalidateQueries({ queryKey: ['attachments', 'task', data.task_id] })
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
        console.log('[WebSocket-Cache] MEMBER_REMOVED received:', data)

        // Check if current user is the one being removed
        const currentUserId = currentUserRef.current?.id
        const isCurrentUserRemoved = currentUserId === data.user_id
        console.log('[WebSocket-Cache] MEMBER_REMOVED check: currentUserId=', currentUserId, 'data.user_id=', data.user_id, 'isCurrentUserRemoved=', isCurrentUserRemoved)

        // Always invalidate the members list
        queryClient.invalidateQueries({ queryKey: queryKeys.appMembers(data.application_id) })

        if (isCurrentUserRemoved) {
          // For removed user: force immediate cache update and notify for redirect
          console.log('[WebSocket-Cache] Current user was removed, updating cache and notifying')

          // Remove the specific application from cache (user no longer has access)
          queryClient.removeQueries({ queryKey: queryKeys.application(data.application_id) })

          // Directly remove from applications list cache (instant UI update)
          queryClient.setQueryData<{ id: string }[]>(
            queryKeys.applications,
            (old) => {
              if (!old) return old
              const filtered = old.filter((app) => app.id !== data.application_id)
              console.log('[WebSocket-Cache] Filtered applications:', old.length, '->', filtered.length)
              return filtered
            }
          )

          // Also refetch to ensure consistency with backend
          queryClient.refetchQueries({ queryKey: queryKeys.applications })

          // Call the callback so the app can redirect if needed
          optionsRef.current.onCurrentUserRemoved?.(data.application_id)
        } else {
          // For other users: just invalidate to update member lists
          queryClient.invalidateQueries({ queryKey: queryKeys.applications })
          queryClient.invalidateQueries({ queryKey: queryKeys.application(data.application_id) })
        }
      })
    )

    unsubscribers.push(
      wsClient.on<MemberEventData>(MessageType.ROLE_UPDATED, (data) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.appMembers(data.application_id) })
        // Also invalidate application to refresh user_role for permission checks
        queryClient.invalidateQueries({ queryKey: queryKeys.application(data.application_id) })
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
      wsClient.on<NotificationEventData>(MessageType.NOTIFICATION, (data) => {
        console.log('[WebSocket-Cache] NOTIFICATION event received:', data)
        queryClient.invalidateQueries({ queryKey: queryKeys.notifications })
        queryClient.invalidateQueries({ queryKey: queryKeys.unreadCount })

        // Handle member_removed notification as fallback (in case MEMBER_REMOVED event missed)
        if (data.notification_type === 'member_removed' && data.entity_type === 'application' && data.entity_id) {
          console.log('[WebSocket-Cache] NOTIFICATION: member_removed detected, updating cache for app:', data.entity_id)

          // Remove the specific application from cache
          queryClient.removeQueries({ queryKey: queryKeys.application(data.entity_id) })

          // Directly remove from applications list cache
          queryClient.setQueryData<{ id: string }[]>(
            queryKeys.applications,
            (old) => {
              if (!old) return old
              const filtered = old.filter((app) => app.id !== data.entity_id)
              console.log('[WebSocket-Cache] Filtered applications via NOTIFICATION:', old.length, '->', filtered.length)
              return filtered
            }
          )

          // Refetch to ensure consistency
          queryClient.refetchQueries({ queryKey: queryKeys.applications })

          // Call redirect callback
          optionsRef.current.onCurrentUserRemoved?.(data.entity_id)
        }

        // Show desktop notification if title and message are provided
        if (data.title && data.message) {
          console.log('[WebSocket-Cache] Calling showBrowserNotification')
          showBrowserNotification(data.title, data.message)
        } else {
          console.log('[WebSocket-Cache] Missing title or message, skipping desktop notification')
        }
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
    // Document Events (Knowledge Base)
    // Skip own actions - optimistic updates already handled the local cache
    // ========================================================================

    unsubscribers.push(
      wsClient.on<DocumentEventData>(MessageType.DOCUMENT_CREATED, (data) => {
        // Skip own actions - already handled by optimistic update
        if (data.actor_id && data.actor_id === currentUserRef.current?.id) return

        queryClient.invalidateQueries({ queryKey: queryKeys.documents(data.scope, data.scope_id) })
        queryClient.invalidateQueries({ queryKey: queryKeys.documentFolders(data.scope, data.scope_id) })
        queryClient.invalidateQueries({ queryKey: queryKeys.scopesSummary() })
        if (data.scope === 'project') {
          queryClient.invalidateQueries({ queryKey: ['projects-with-content'] })
          // Also invalidate application queries for users viewing app tree
          if (data.application_id) {
            queryClient.invalidateQueries({ queryKey: queryKeys.documents('application', data.application_id) })
            queryClient.invalidateQueries({ queryKey: queryKeys.documentFolders('application', data.application_id) })
          }
        }
      })
    )

    unsubscribers.push(
      wsClient.on<DocumentEventData>(MessageType.DOCUMENT_UPDATED, (data) => {
        // Skip own actions - already handled by optimistic update
        if (data.actor_id && data.actor_id === currentUserRef.current?.id) return

        queryClient.invalidateQueries({ queryKey: queryKeys.document(data.document_id) })
        queryClient.invalidateQueries({ queryKey: queryKeys.documents(data.scope, data.scope_id) })
        if (data.folder_id !== undefined) {
          queryClient.invalidateQueries({ queryKey: queryKeys.documentFolders(data.scope, data.scope_id) })
        }
        // Also invalidate application queries for project-scoped updates
        if (data.scope === 'project' && data.application_id) {
          queryClient.invalidateQueries({ queryKey: queryKeys.documents('application', data.application_id) })
          if (data.folder_id !== undefined) {
            queryClient.invalidateQueries({ queryKey: queryKeys.documentFolders('application', data.application_id) })
          }
        }
      })
    )

    unsubscribers.push(
      wsClient.on<DocumentEventData>(MessageType.DOCUMENT_DELETED, (data) => {
        // Skip own actions - already handled by optimistic update
        if (data.actor_id && data.actor_id === currentUserRef.current?.id) return

        queryClient.removeQueries({ queryKey: queryKeys.document(data.document_id) })
        queryClient.invalidateQueries({ queryKey: queryKeys.documents(data.scope, data.scope_id) })
        queryClient.invalidateQueries({ queryKey: queryKeys.documentFolders(data.scope, data.scope_id) })
        queryClient.invalidateQueries({ queryKey: queryKeys.scopesSummary() })
        if (data.scope === 'project') {
          queryClient.invalidateQueries({ queryKey: ['projects-with-content'] })
          // Also invalidate application queries for users viewing app tree
          if (data.application_id) {
            queryClient.invalidateQueries({ queryKey: queryKeys.documents('application', data.application_id) })
            queryClient.invalidateQueries({ queryKey: queryKeys.documentFolders('application', data.application_id) })
          }
        }
      })
    )

    // ========================================================================
    // Folder Events (Knowledge Base)
    // Skip own actions - optimistic updates already handled the local cache
    // ========================================================================

    unsubscribers.push(
      wsClient.on<FolderEventData>(MessageType.FOLDER_CREATED, (data) => {
        // Skip own actions - already handled by optimistic update
        if (data.actor_id && data.actor_id === currentUserRef.current?.id) return

        queryClient.invalidateQueries({ queryKey: queryKeys.documentFolders(data.scope, data.scope_id) })
        if (data.scope === 'project') {
          queryClient.invalidateQueries({ queryKey: ['projects-with-content'] })
        }
      })
    )

    unsubscribers.push(
      wsClient.on<FolderEventData>(MessageType.FOLDER_UPDATED, (data) => {
        // Skip own actions - already handled by optimistic update
        if (data.actor_id && data.actor_id === currentUserRef.current?.id) return

        queryClient.invalidateQueries({ queryKey: queryKeys.documentFolders(data.scope, data.scope_id) })
      })
    )

    unsubscribers.push(
      wsClient.on<FolderEventData>(MessageType.FOLDER_DELETED, (data) => {
        // Skip own actions - already handled by optimistic update
        if (data.actor_id && data.actor_id === currentUserRef.current?.id) return

        queryClient.invalidateQueries({ queryKey: queryKeys.documentFolders(data.scope, data.scope_id) })
        queryClient.invalidateQueries({ queryKey: queryKeys.documents(data.scope, data.scope_id) })
        if (data.scope === 'project') {
          queryClient.invalidateQueries({ queryKey: ['projects-with-content'] })
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
      console.log('[WebSocket-Cache] Hook cleanup, removing listeners')
      unsubscribers.forEach((unsubscribe) => unsubscribe())
    }
  }, [queryClient])
}

/**
 * Alias for backward compatibility
 */
export const useQueryCacheSync = useWebSocketCacheInvalidation

export default useWebSocketCacheInvalidation
