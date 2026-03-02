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
import { toast } from 'sonner'
import { wsClient, MessageType, type Unsubscribe } from '@/lib/websocket'
import { queryKeys } from '@/lib/query-client'
import type { Task } from '@/hooks/use-queries'
import { showBrowserNotification } from '@/lib/notifications'
import { useAuthUser } from '@/contexts/auth-context'
import type { DocumentListResponse } from './use-documents'
import type { FolderTreeNode } from './use-document-folders'

// ============================================================================
// Types for WebSocket Event Data
// ============================================================================

interface ApplicationEventData {
  application_id: string
}

interface ProjectEventData {
  project_id: string
  application_id?: string
}

interface TaskEventData {
  task_id: string
  project_id: string
  task?: Record<string, unknown>
}

interface CommentEventData {
  task_id: string
  comment_id?: string
  attachment_ids?: string[]
}

interface ChecklistEventData {
  task_id: string
  checklist_id?: string
}

interface MemberEventData {
  application_id: string
  user_id: string
}

interface ProjectMemberEventData {
  project_id: string
  user_id: string
  application_id?: string
}

interface NotificationEventData {
  notification_id?: string
  notification_type?: string
  title?: string
  message?: string
  entity_type?: string
  entity_id?: string
}

interface AttachmentEventData {
  task_id: string
  attachment_id?: string
}

interface DocumentEventData {
  document_id: string
  scope: string
  scope_id: string
  folder_id?: string | null
  actor_id?: string | null
  /** For project-scoped items, the parent application ID */
  application_id?: string | null
  timestamp?: string
}

interface FolderEventData {
  folder_id: string
  scope: string
  scope_id: string
  parent_id?: string | null
  actor_id?: string | null
  /** For project-scoped items, the parent application ID */
  application_id?: string | null
  timestamp?: string

}

// ============================================================================
// Event Deduplication
// ============================================================================
//
// For project-scoped documents/folders, the backend broadcasts the same event
// to both the project room AND the application room so users viewing either
// scope receive updates. When a client is subscribed to both rooms (e.g.,
// viewing a project within an application), it receives the same event twice.
//
// This deduplicator filters out duplicate events by fingerprint within a short
// time window so each handler runs only once per unique event.

const DEDUP_WINDOW_MS = 1000
const DEDUP_CLEANUP_THRESHOLD = 50
const DEDUP_CLEANUP_INTERVAL_MS = 5000

/** Tracks recently seen event fingerprints with their arrival timestamps. */
const recentEvents = new Map<string, number>()
let lastCleanupTime = 0

/**
 * Clear the event deduplication cache.
 * Call on logout to prevent stale fingerprints across sessions.
 */
export function clearEventDedup(): void {
  recentEvents.clear()
  lastCleanupTime = 0
}

/**
 * Returns true if this event fingerprint was already seen within DEDUP_WINDOW_MS.
 * Otherwise records it and returns false (first occurrence).
 *
 * Fingerprints use only event_type + entity_id (no server timestamp) so that
 * the same logical event received from two different WS rooms (project + app)
 * always produces the same fingerprint regardless of serialization timing.
 * The 1-second dedup window is sufficient to collapse cross-room duplicates.
 */
function isDuplicateEvent(fingerprint: string): boolean {
  const now = Date.now()
  const lastSeen = recentEvents.get(fingerprint)
  if (lastSeen !== undefined && now - lastSeen < DEDUP_WINDOW_MS) {
    return true
  }
  recentEvents.set(fingerprint, now)
  // Periodic cleanup of stale entries (time-guarded to avoid running on every call)
  if (recentEvents.size > DEDUP_CLEANUP_THRESHOLD && now - lastCleanupTime > DEDUP_CLEANUP_INTERVAL_MS) {
    lastCleanupTime = now
    for (const [key, time] of recentEvents) {
      if (now - time > DEDUP_WINDOW_MS) recentEvents.delete(key)
    }
  }
  return false
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
  const currentUser = useAuthUser()
  const currentUserRef = useRef(currentUser)

  // Keep refs up to date
  useEffect(() => {
    optionsRef.current = options
  }, [options])

  useEffect(() => {
    currentUserRef.current = currentUser
  }, [currentUser])

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
        const taskPayload = data.task
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
        const taskPayload = data.task
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
        const taskPayload = data.task
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

        // New member needs scopesSummary refreshed to show the new app tab
        const isCurrentUser = data.user_id === currentUserRef.current?.id
        if (isCurrentUser) {
          queryClient.invalidateQueries({ queryKey: queryKeys.scopesSummary() })
        }
      })
    )

    unsubscribers.push(
      wsClient.on<MemberEventData>(MessageType.MEMBER_REMOVED, (data) => {
        // Check if current user is the one being removed
        const currentUserId = currentUserRef.current?.id
        const isCurrentUserRemoved = currentUserId === data.user_id

        // Always invalidate the members list
        queryClient.invalidateQueries({ queryKey: queryKeys.appMembers(data.application_id) })

        if (isCurrentUserRemoved) {
          // For removed user: force immediate cache update and notify for redirect
          // Remove the specific application from cache (user no longer has access)
          queryClient.removeQueries({ queryKey: queryKeys.application(data.application_id) })

          // Directly remove from applications list cache (instant UI update)
          queryClient.setQueryData<{ id: string }[]>(
            queryKeys.applications,
            (old) => {
              if (!old) return old
              return old.filter((app) => app.id !== data.application_id)
            }
          )

          // Also refetch to ensure consistency with backend
          queryClient.refetchQueries({ queryKey: queryKeys.applications })

          // Call the callback so the app can redirect if needed
          optionsRef.current.onCurrentUserRemoved?.(data.application_id)

          // Clean up knowledge permission caches (user no longer has access)
          queryClient.invalidateQueries({ queryKey: queryKeys.scopesSummary() })
          queryClient.removeQueries({ queryKey: ['projects-with-content', data.application_id] })
          queryClient.removeQueries({ queryKey: ['knowledge-permissions'] })
        } else {
          // For other users: just invalidate to update member lists
          queryClient.invalidateQueries({ queryKey: queryKeys.applications })
          queryClient.invalidateQueries({ queryKey: queryKeys.application(data.application_id) })
          // No knowledge cache invalidation needed — other users' permissions unchanged
        }
      })
    )

    unsubscribers.push(
      wsClient.on<MemberEventData>(MessageType.ROLE_UPDATED, (data) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.appMembers(data.application_id) })
        // Also invalidate application to refresh user_role for permission checks
        queryClient.invalidateQueries({ queryKey: queryKeys.application(data.application_id) })

        // Invalidate knowledge permission caches only for the affected user
        const isCurrentUser = data.user_id === currentUserRef.current?.id
        if (isCurrentUser) {
          queryClient.invalidateQueries({ queryKey: queryKeys.scopesSummary() })
          queryClient.invalidateQueries({ queryKey: ['projects-with-content', data.application_id] })
          queryClient.invalidateQueries({ queryKey: ['knowledge-permissions'] })
        }
      })
    )

    // ========================================================================
    // Project Member Events
    // ========================================================================

    unsubscribers.push(
      wsClient.on<ProjectMemberEventData>(MessageType.PROJECT_MEMBER_ADDED, (data) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.projectMembers(data.project_id) })

        const isCurrentUser = data.user_id === currentUserRef.current?.id
        if (isCurrentUser) {
          // Scope to specific app if available, otherwise invalidate all
          if (data.application_id) {
            queryClient.invalidateQueries({ queryKey: ['projects-with-content', data.application_id] })
          } else {
            queryClient.invalidateQueries({ queryKey: ['projects-with-content'] })
          }
          queryClient.invalidateQueries({ queryKey: queryKeys.knowledgePermissions('project', data.project_id) })
        }
      })
    )

    unsubscribers.push(
      wsClient.on<ProjectMemberEventData>(MessageType.PROJECT_MEMBER_REMOVED, (data) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.projectMembers(data.project_id) })
        // Also invalidate tasks since permissions may have changed
        queryClient.invalidateQueries({ queryKey: queryKeys.tasks(data.project_id) })

        const isCurrentUser = data.user_id === currentUserRef.current?.id
        if (isCurrentUser) {
          if (data.application_id) {
            queryClient.invalidateQueries({ queryKey: ['projects-with-content', data.application_id] })
          } else {
            queryClient.invalidateQueries({ queryKey: ['projects-with-content'] })
          }
          queryClient.invalidateQueries({ queryKey: queryKeys.knowledgePermissions('project', data.project_id) })
        }
      })
    )

    unsubscribers.push(
      wsClient.on<ProjectMemberEventData>(MessageType.PROJECT_ROLE_CHANGED, (data) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.projectMembers(data.project_id) })
        // Also invalidate tasks since permissions may have changed
        queryClient.invalidateQueries({ queryKey: queryKeys.tasks(data.project_id) })

        // Invalidate knowledge permission caches for the affected user
        const isCurrentUser = data.user_id === currentUserRef.current?.id
        if (isCurrentUser) {
          // projects-with-content returns can_edit per project — stale after role change
          if (data.application_id) {
            queryClient.invalidateQueries({ queryKey: ['projects-with-content', data.application_id] })
          } else {
            queryClient.invalidateQueries({ queryKey: ['projects-with-content'] })
          }
          queryClient.invalidateQueries({ queryKey: queryKeys.knowledgePermissions('project', data.project_id) })
        }
      })
    )

    // ========================================================================
    // Notification Events
    // ========================================================================

    unsubscribers.push(
      wsClient.on<NotificationEventData>(MessageType.NOTIFICATION, (data) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.notifications })
        queryClient.invalidateQueries({ queryKey: queryKeys.unreadCount })

        // Handle member_removed notification as fallback (in case MEMBER_REMOVED event missed)
        if (data.notification_type === 'member_removed' && data.entity_type === 'application' && data.entity_id) {
          // Remove the specific application from cache
          queryClient.removeQueries({ queryKey: queryKeys.application(data.entity_id) })

          // Directly remove from applications list cache
          queryClient.setQueryData<{ id: string }[]>(
            queryKeys.applications,
            (old) => {
              if (!old) return old
              return old.filter((app) => app.id !== data.entity_id)
            }
          )

          // Refetch to ensure consistency
          queryClient.refetchQueries({ queryKey: queryKeys.applications })

          // Call redirect callback
          optionsRef.current.onCurrentUserRemoved?.(data.entity_id)
        }

        // Show desktop notification if title and message are provided
        if (data.title && data.message) {
          showBrowserNotification(data.title, data.message)
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
    // Own actions: always run setQueriesData for IndexedDB consistency,
    // skip redundant invalidateQueries (onSuccess handles those).
    // ========================================================================

    unsubscribers.push(
      wsClient.on<DocumentEventData>(MessageType.DOCUMENT_CREATED, (data) => {
        if (isDuplicateEvent(`doc_created:${data.document_id}`)) return
        // NOTE: Do NOT skip own actions. Invalidation ensures IndexedDB persisted cache
        // is updated with server-confirmed data (real ID replacing temp ID, accurate timestamps).
        queryClient.invalidateQueries({ queryKey: queryKeys.documents(data.scope, data.scope_id) })
        queryClient.invalidateQueries({ queryKey: queryKeys.documentFolders(data.scope, data.scope_id) })
        queryClient.invalidateQueries({ queryKey: queryKeys.scopesSummary() })
        queryClient.invalidateQueries({ queryKey: ['search'] })
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
        if (isDuplicateEvent(`doc_updated:${data.document_id}`)) return
        const isOwnAction = data.actor_id && data.actor_id === currentUserRef.current?.id

        // For own actions, the save mutation already updates the individual document
        // cache via setQueryData + invalidateQueries (use-edit-mode.ts:313,329).
        // Only refetch for OTHER users' changes.
        if (!isOwnAction) {
          queryClient.invalidateQueries({ queryKey: queryKeys.document(data.document_id) })
        }
        // Document list queries are NOT handled by the save mutation,
        // so always invalidate them to keep tree/list views in sync.
        queryClient.invalidateQueries({ queryKey: queryKeys.documents(data.scope, data.scope_id) })
        queryClient.invalidateQueries({ queryKey: ['search'] })
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
        if (isDuplicateEvent(`doc_deleted:${data.document_id}`)) return
        // NOTE: Do NOT skip own actions here. Same IndexedDB rehydration issue
        // as FOLDER_DELETED — optimistic update only touches in-memory cache,
        // but stale data in IndexedDB can cause deleted documents to reappear.
        const isOwnAction = data.actor_id && data.actor_id === currentUserRef.current?.id

        queryClient.removeQueries({ queryKey: queryKeys.document(data.document_id) })
        // Directly remove from list caches to avoid race with DB commit
        queryClient.setQueriesData<DocumentListResponse>(
          { queryKey: queryKeys.documents(data.scope, data.scope_id), exact: false },
          (old) => old ? { ...old, items: old.items.filter(i => i.id !== data.document_id) } : old
        )

        // Skip invalidations that onSuccess already handles for own actions
        if (!isOwnAction) {
          queryClient.invalidateQueries({ queryKey: queryKeys.documentFolders(data.scope, data.scope_id) })
          queryClient.invalidateQueries({ queryKey: queryKeys.scopesSummary() })
          queryClient.invalidateQueries({ queryKey: ['search'] })
        }
        if (data.scope === 'project') {
          if (!isOwnAction) {
            queryClient.invalidateQueries({ queryKey: ['projects-with-content'] })
          }
          if (data.application_id) {
            queryClient.setQueriesData<DocumentListResponse>(
              { queryKey: queryKeys.documents('application', data.application_id), exact: false },
              (old) => old ? { ...old, items: old.items.filter(i => i.id !== data.document_id) } : old
            )
            queryClient.invalidateQueries({ queryKey: queryKeys.documentFolders('application', data.application_id) })
          }
        }
      })
    )

    // ========================================================================
    // Folder Events (Knowledge Base)
    // Own actions: always run setQueriesData for IndexedDB consistency,
    // skip redundant invalidateQueries (onSuccess handles those).
    // ========================================================================

    unsubscribers.push(
      wsClient.on<FolderEventData>(MessageType.FOLDER_CREATED, (data) => {
        if (isDuplicateEvent(`folder_created:${data.folder_id}`)) return
        // NOTE: Do NOT skip own actions. The optimistic update adds the folder
        // to in-memory cache, but without running this handler the invalidation
        // that fetches accurate server data (materialized_path, depth, document_count)
        // would be skipped, and stale IndexedDB data could omit the new folder on remount.
        queryClient.invalidateQueries({ queryKey: queryKeys.documentFolders(data.scope, data.scope_id) })
        if (data.scope === 'project') {
          queryClient.invalidateQueries({ queryKey: ['projects-with-content'] })
          if (data.application_id) {
            queryClient.invalidateQueries({ queryKey: queryKeys.documentFolders('application', data.application_id) })
          }
        }
      })
    )

    unsubscribers.push(
      wsClient.on<FolderEventData>(MessageType.FOLDER_UPDATED, (data) => {
        if (isDuplicateEvent(`folder_updated:${data.folder_id}`)) return
        // NOTE: Do NOT skip own actions. Same IndexedDB consistency rationale:
        // invalidation ensures the persisted cache is updated with server-confirmed data.
        queryClient.invalidateQueries({ queryKey: queryKeys.documentFolders(data.scope, data.scope_id) })
        if (data.scope === 'project' && data.application_id) {
          queryClient.invalidateQueries({ queryKey: queryKeys.documentFolders('application', data.application_id) })
        }
      })
    )

    unsubscribers.push(
      wsClient.on<FolderEventData>(MessageType.FOLDER_DELETED, (data) => {
        if (isDuplicateEvent(`folder_deleted:${data.folder_id}`)) return
        // NOTE: Do NOT skip own actions here. The optimistic update in useDeleteFolder
        // only updates the in-memory TanStack Query cache, but IndexedDB persistence
        // still holds stale data. If we skip, the debounced persister writes stale data
        // to IndexedDB, and on remount/rehydration the deleted folder reappears.
        // Always run this handler to ensure the cache (and persisted state) stays consistent.
        const isOwnAction = data.actor_id && data.actor_id === currentUserRef.current?.id

        // Directly remove from tree cache to avoid race with DB commit
        const removeFolder = (nodes: FolderTreeNode[]): FolderTreeNode[] =>
          nodes
            .filter(n => n.id !== data.folder_id)
            .map(n => ({ ...n, children: removeFolder(n.children) }))

        queryClient.setQueriesData<FolderTreeNode[]>(
          { queryKey: queryKeys.documentFolders(data.scope, data.scope_id) },
          (old) => old ? removeFolder(old) : old
        )

        // Skip invalidations that onSuccess already handles for own actions
        if (!isOwnAction) {
          queryClient.invalidateQueries({ queryKey: queryKeys.documents(data.scope, data.scope_id) })
          queryClient.invalidateQueries({ queryKey: queryKeys.scopesSummary() })
          queryClient.invalidateQueries({ queryKey: ['search'] })
        }
        if (data.scope === 'project') {
          if (!isOwnAction) {
            queryClient.invalidateQueries({ queryKey: ['projects-with-content'] })
          }
          if (data.application_id) {
            queryClient.setQueriesData<FolderTreeNode[]>(
              { queryKey: queryKeys.documentFolders('application', data.application_id) },
              (old) => old ? removeFolder(old) : old
            )
            queryClient.invalidateQueries({ queryKey: queryKeys.documents('application', data.application_id) })
          }
        }
      })
    )

    // ========================================================================
    // Document Lock Events — handled by useActiveLocks hook via setQueryData.
    // No app-level invalidation needed: in-place WS updates are precise, and
    // invalidation would trigger refetches that can race with setQueryData
    // (especially for cross-scope queries where the endpoint's scope filter
    // correctly excludes the lock, undoing the optimistic WS update).
    // ========================================================================

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

    // ========================================================================
    // AI Indexing Events
    // ========================================================================

    unsubscribers.push(
      wsClient.on<{ document_id: string; chunk_count: number; timestamp: string }>(
        MessageType.EMBEDDING_UPDATED,
        (data) => {
          queryClient.invalidateQueries({
            queryKey: queryKeys.documentIndexStatus(data.document_id),
          })
          // Surgically update is_embedding_stale instead of invalidating the full
          // document query (which refetches content_json, potentially large).
          queryClient.setQueryData(
            queryKeys.document(data.document_id),
            (old: Record<string, unknown> | undefined) =>
              old ? { ...old, is_embedding_stale: false, embedding_sync_pending: false } : old
          )
        }
      )
    )

    unsubscribers.push(
      wsClient.on<{ document_id: string; entities_count: number; relationships_count: number; timestamp: string }>(
        MessageType.ENTITIES_EXTRACTED,
        (data) => {
          queryClient.invalidateQueries({
            queryKey: queryKeys.documentIndexStatus(data.document_id),
          })
        }
      )
    )

    // ========================================================================
    // AI Import Events
    // ========================================================================

    unsubscribers.push(
      wsClient.on<{ job_id: string; document_id: string; title: string; scope: string }>(
        MessageType.IMPORT_COMPLETED,
        (data) => {
          queryClient.invalidateQueries({ queryKey: queryKeys.importJobs })
          toast.success(`Import complete: ${data.title}`)
        }
      )
    )

    unsubscribers.push(
      wsClient.on<{ job_id: string; error_message: string; file_name: string }>(
        MessageType.IMPORT_FAILED,
        (data) => {
          queryClient.invalidateQueries({ queryKey: queryKeys.importJobs })
          toast.error(`Import failed: ${data.file_name}`, {
            description: data.error_message,
          })
        }
      )
    )

    // ========================================================================
    // AI Reindex Progress Events
    // ========================================================================

    unsubscribers.push(
      wsClient.on<{ application_id: string; total: number; processed: number; failed: number }>(
        MessageType.REINDEX_PROGRESS,
        (data) => {
          queryClient.invalidateQueries({
            queryKey: queryKeys.applicationIndexStatus(data.application_id),
          })
        }
      )
    )

    // Cleanup on unmount
    return () => {
      unsubscribers.forEach((unsubscribe) => unsubscribe())
    }
  }, [queryClient])
}

export default useWebSocketCacheInvalidation
