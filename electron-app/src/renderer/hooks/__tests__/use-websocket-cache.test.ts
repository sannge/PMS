/**
 * Tests for use-websocket-cache.ts — WebSocket event to TanStack Query cache invalidation.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook } from '@testing-library/react'

// ============================================================================
// Mocks
// ============================================================================

// Capture wsClient.on handlers so we can trigger them in tests
type Handler = (data: unknown) => void
const handlers = new Map<string, Handler>()
const unsubFns: ReturnType<typeof vi.fn>[] = []

const mockWsClientOn = vi.fn((type: string, handler: Handler) => {
  handlers.set(type, handler)
  const unsub = vi.fn()
  unsubFns.push(unsub)
  return unsub
})

vi.mock('@/lib/websocket', () => ({
  wsClient: { on: (...args: unknown[]) => mockWsClientOn(args[0] as string, args[1] as Handler) },
  MessageType: {
    APPLICATION_UPDATED: 'application_updated',
    APPLICATION_DELETED: 'application_deleted',
    PROJECT_CREATED: 'project_created',
    PROJECT_UPDATED: 'project_updated',
    PROJECT_DELETED: 'project_deleted',
    PROJECT_STATUS_CHANGED: 'project_status_changed',
    TASK_CREATED: 'task_created',
    TASK_UPDATED: 'task_updated',
    TASK_DELETED: 'task_deleted',
    TASK_STATUS_CHANGED: 'task_status_changed',
    TASK_MOVED: 'task_moved',
    COMMENT_ADDED: 'comment_added',
    COMMENT_UPDATED: 'comment_updated',
    COMMENT_DELETED: 'comment_deleted',
    CHECKLIST_CREATED: 'checklist_created',
    CHECKLIST_UPDATED: 'checklist_updated',
    CHECKLIST_DELETED: 'checklist_deleted',
    CHECKLISTS_REORDERED: 'checklists_reordered',
    CHECKLIST_ITEM_TOGGLED: 'checklist_item_toggled',
    CHECKLIST_ITEM_ADDED: 'checklist_item_added',
    CHECKLIST_ITEM_UPDATED: 'checklist_item_updated',
    CHECKLIST_ITEM_DELETED: 'checklist_item_deleted',
    CHECKLIST_ITEMS_REORDERED: 'checklist_items_reordered',
    MEMBER_ADDED: 'member_added',
    MEMBER_REMOVED: 'member_removed',
    ROLE_UPDATED: 'role_updated',
    PROJECT_MEMBER_ADDED: 'project_member_added',
    PROJECT_MEMBER_REMOVED: 'project_member_removed',
    PROJECT_ROLE_CHANGED: 'project_role_changed',
    NOTIFICATION: 'notification',
    NOTIFICATION_READ: 'notification_read',
    ATTACHMENT_UPLOADED: 'attachment_uploaded',
    ATTACHMENT_DELETED: 'attachment_deleted',
    DOCUMENT_CREATED: 'document_created',
    DOCUMENT_UPDATED: 'document_updated',
    DOCUMENT_DELETED: 'document_deleted',
    FOLDER_CREATED: 'folder_created',
    FOLDER_UPDATED: 'folder_updated',
    FOLDER_DELETED: 'folder_deleted',
    INVITATION_RESPONSE: 'invitation_response',
    INVITATION_RECEIVED: 'invitation_received',
    EMBEDDING_UPDATED: 'embedding_updated',
    ENTITIES_EXTRACTED: 'entities_extracted',
    IMPORT_COMPLETED: 'import_completed',
    IMPORT_FAILED: 'import_failed',
    REINDEX_PROGRESS: 'reindex_progress',
  },
}))

const mockInvalidateQueries = vi.fn()
const mockRemoveQueries = vi.fn()
const mockSetQueryData = vi.fn()
const mockSetQueriesData = vi.fn()
const mockRefetchQueries = vi.fn()

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({
    invalidateQueries: mockInvalidateQueries,
    removeQueries: mockRemoveQueries,
    setQueryData: mockSetQueryData,
    setQueriesData: mockSetQueriesData,
    refetchQueries: mockRefetchQueries,
  }),
}))

// Use vi.hoisted for mock fns used in hoisted vi.mock factories
const { mockUseAuthUserId } = vi.hoisted(() => ({
  mockUseAuthUserId: vi.fn(() => 'current-user-id'),
}))

vi.mock('@/contexts/auth-context', () => ({
  useAuthUserId: () => mockUseAuthUserId(),
}))

vi.mock('@/lib/query-client', () => ({
  queryKeys: {
    applications: ['applications'],
    application: (id: string) => ['application', id],
    projects: (appId: string) => ['projects', appId],
    project: (id: string) => ['project', id],
    archivedProjects: (appId: string) => ['projects', appId, 'archived'],
    myProjects: (appId: string) => ['myProjects', appId],
    myProjectsCrossApp: ['myProjects', 'cross-app'],
    myTasksCrossApp: ['myTasks', 'cross-app'],
    tasks: (projectId: string) => ['tasks', projectId],
    task: (id: string) => ['task', id],
    comments: (taskId: string) => ['comments', taskId],
    comment: (id: string) => ['comment', id],
    checklists: (taskId: string) => ['checklists', taskId],
    appMembers: (appId: string) => ['appMembers', appId],
    projectMembers: (projectId: string) => ['projectMembers', projectId],
    notifications: ['notifications'],
    unreadCount: ['notifications', 'unread'],
    attachments: (taskId: string) => ['attachments', taskId],
    downloadUrl: (id: string) => ['downloadUrl', id],
    invitations: ['invitations'],
    pendingInvitations: ['invitations', 'pending'],
    documents: (scope: string, scopeId: string) => ['documents', scope, scopeId],
    document: (id: string) => ['document', id],
    documentFolders: (scope: string, scopeId: string) => ['documentFolders', scope, scopeId],
    scopesSummary: () => ['documents', 'scopes-summary'],
    knowledgePermissions: (scope: string, scopeId: string) => ['knowledge-permissions', scope, scopeId],
    importJobs: ['ai', 'import', 'jobs'],
    documentIndexStatus: (docId: string) => ['ai', 'index-status', docId],
    applicationIndexStatus: (appId: string) => ['ai', 'index-status', 'application', appId],
  },
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@/lib/notifications', () => ({
  showBrowserNotification: vi.fn(),
}))

// ============================================================================
// Import after mocks
// ============================================================================

import { useWebSocketCacheInvalidation, clearEventDedup } from '../use-websocket-cache'
import { showBrowserNotification } from '@/lib/notifications'
import { toast } from 'sonner'

// ============================================================================
// Helpers
// ============================================================================

function triggerEvent(type: string, data: unknown) {
  const handler = handlers.get(type)
  if (!handler) throw new Error(`No handler registered for ${type}`)
  handler(data)
}

function invalidatedKeys(): unknown[][] {
  return mockInvalidateQueries.mock.calls.map((c) => c[0].queryKey)
}

function removedKeys(): unknown[][] {
  return mockRemoveQueries.mock.calls.map((c) => c[0].queryKey)
}

// ============================================================================
// Tests
// ============================================================================

describe('useWebSocketCacheInvalidation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    handlers.clear()
    unsubFns.length = 0
    clearEventDedup()
    mockUseAuthUserId.mockReturnValue('current-user-id')
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  function mount(options = {}) {
    return renderHook(() => useWebSocketCacheInvalidation(options))
  }

  // ==========================================================================
  // Cleanup on unmount
  // ==========================================================================

  describe('cleanup on unmount', () => {
    it('registers handlers for all event types via wsClient.on', () => {
      mount()
      // Should register many handlers
      expect(mockWsClientOn.mock.calls.length).toBeGreaterThan(20)
    })

    it('calls all unsubscribe functions on unmount', () => {
      const { unmount } = mount()
      const count = unsubFns.length
      expect(count).toBeGreaterThan(0)

      unmount()

      for (const unsub of unsubFns) {
        expect(unsub).toHaveBeenCalledOnce()
      }
    })
  })

  // ==========================================================================
  // Event deduplication
  // ==========================================================================

  describe('event deduplication', () => {
    it('deduplicates same document event within DEDUP_WINDOW_MS', () => {
      mount()

      triggerEvent('document_created', {
        document_id: 'doc-1', scope: 'project', scope_id: 'proj-1',
      })
      const callsFirst = mockInvalidateQueries.mock.calls.length

      // Trigger same event again (simulating cross-room duplicate)
      triggerEvent('document_created', {
        document_id: 'doc-1', scope: 'project', scope_id: 'proj-1',
      })
      const callsSecond = mockInvalidateQueries.mock.calls.length

      // Second trigger should be deduplicated (no additional calls)
      expect(callsSecond).toBe(callsFirst)
    })

    it('allows same event after DEDUP_WINDOW_MS expires', () => {
      mount()

      triggerEvent('document_created', {
        document_id: 'doc-2', scope: 'application', scope_id: 'app-1',
      })
      const callsFirst = mockInvalidateQueries.mock.calls.length

      // Advance time past dedup window
      const now = Date.now()
      vi.spyOn(Date, 'now').mockReturnValue(now + 1100)

      triggerEvent('document_created', {
        document_id: 'doc-2', scope: 'application', scope_id: 'app-1',
      })

      expect(mockInvalidateQueries.mock.calls.length).toBeGreaterThan(callsFirst)
    })

    it('clearEventDedup resets dedup state', () => {
      mount()

      triggerEvent('folder_created', {
        folder_id: 'f-1', scope: 'project', scope_id: 'p-1',
      })
      const callsFirst = mockInvalidateQueries.mock.calls.length

      clearEventDedup()

      triggerEvent('folder_created', {
        folder_id: 'f-1', scope: 'project', scope_id: 'p-1',
      })

      expect(mockInvalidateQueries.mock.calls.length).toBeGreaterThan(callsFirst)
    })
  })

  // ==========================================================================
  // Application events
  // ==========================================================================

  describe('application events', () => {
    it('APPLICATION_UPDATED invalidates application and applications list', () => {
      mount()
      triggerEvent('application_updated', { application_id: 'app-1' })

      expect(invalidatedKeys()).toContainEqual(['application', 'app-1'])
      expect(invalidatedKeys()).toContainEqual(['applications'])
    })

    it('APPLICATION_DELETED removes application query and invalidates list', () => {
      mount()
      triggerEvent('application_deleted', { application_id: 'app-1' })

      expect(removedKeys()).toContainEqual(['application', 'app-1'])
      expect(invalidatedKeys()).toContainEqual(['applications'])
    })
  })

  // ==========================================================================
  // Project events
  // ==========================================================================

  describe('project events', () => {
    it('PROJECT_CREATED invalidates projects, myProjects, and cross-app', () => {
      mount()
      triggerEvent('project_created', { project_id: 'p-1', application_id: 'app-1' })

      expect(invalidatedKeys()).toContainEqual(['projects', 'app-1'])
      expect(invalidatedKeys()).toContainEqual(['myProjects', 'app-1'])
      expect(invalidatedKeys()).toContainEqual(['myProjects', 'cross-app'])
    })

    it('PROJECT_CREATED does nothing without application_id', () => {
      mount()
      triggerEvent('project_created', { project_id: 'p-1' })

      expect(mockInvalidateQueries).not.toHaveBeenCalled()
    })

    it('PROJECT_UPDATED invalidates project, projects, myProjects, application (not archived)', () => {
      mount()
      triggerEvent('project_updated', { project_id: 'p-1', application_id: 'app-1' })

      expect(invalidatedKeys()).toContainEqual(['project', 'p-1'])
      expect(invalidatedKeys()).toContainEqual(['projects', 'app-1'])
      expect(invalidatedKeys()).toContainEqual(['application', 'app-1'])
      expect(invalidatedKeys()).toContainEqual(['applications'])
      // archivedProjects NOT invalidated — PROJECT_STATUS_CHANGED handles archival
      expect(invalidatedKeys()).not.toContainEqual(['projects', 'app-1', 'archived'])
    })

    it('PROJECT_DELETED removes project and tasks, calls onProjectDeleted', () => {
      const onProjectDeleted = vi.fn()
      mount({ onProjectDeleted })
      triggerEvent('project_deleted', { project_id: 'p-1', application_id: 'app-1' })

      expect(removedKeys()).toContainEqual(['project', 'p-1'])
      expect(removedKeys()).toContainEqual(['tasks', 'p-1'])
      expect(invalidatedKeys()).toContainEqual(['projects', 'app-1'])
      expect(onProjectDeleted).toHaveBeenCalledWith('p-1', 'app-1')
    })

    it('PROJECT_STATUS_CHANGED invalidates project and related lists', () => {
      mount()
      triggerEvent('project_status_changed', { project_id: 'p-1', application_id: 'app-1' })

      expect(invalidatedKeys()).toContainEqual(['project', 'p-1'])
      expect(invalidatedKeys()).toContainEqual(['projects', 'app-1'])
      expect(invalidatedKeys()).toContainEqual(['myProjects', 'cross-app'])
    })
  })

  // ==========================================================================
  // Task events
  // ==========================================================================

  describe('task events', () => {
    it('TASK_CREATED invalidates tasks, project, and myTasksCrossApp', () => {
      mount()
      triggerEvent('task_created', { task_id: 't-1', project_id: 'p-1' })

      expect(invalidatedKeys()).toContainEqual(['tasks', 'p-1'])
      expect(invalidatedKeys()).toContainEqual(['project', 'p-1'])
      expect(invalidatedKeys()).toContainEqual(['myTasks', 'cross-app'])
    })

    it('TASK_UPDATED with full payload uses setQueryData (no invalidation for task)', () => {
      mount()
      const task = { id: 't-1', title: 'Updated Task', status: 'done' }
      triggerEvent('task_updated', { task_id: 't-1', project_id: 'p-1', task })

      expect(mockSetQueryData).toHaveBeenCalledWith(['task', 't-1'], task)
      expect(mockSetQueryData).toHaveBeenCalledWith(
        ['tasks', 'p-1'],
        expect.any(Function)
      )
      // Should still invalidate myTasksCrossApp
      expect(invalidatedKeys()).toContainEqual(['myTasks', 'cross-app'])
    })

    it('TASK_UPDATED with partial payload falls back to invalidation', () => {
      mount()
      triggerEvent('task_updated', { task_id: 't-1', project_id: 'p-1', task: { id: 't-1' } })

      // No title → partial payload → invalidate
      expect(invalidatedKeys()).toContainEqual(['task', 't-1'])
      expect(invalidatedKeys()).toContainEqual(['tasks', 'p-1'])
    })

    it('TASK_DELETED removes task and filters from list', () => {
      mount()
      triggerEvent('task_deleted', { task_id: 't-1', project_id: 'p-1' })

      expect(removedKeys()).toContainEqual(['task', 't-1'])
      expect(mockSetQueryData).toHaveBeenCalledWith(
        ['tasks', 'p-1'],
        expect.any(Function)
      )
      expect(invalidatedKeys()).toContainEqual(['project', 'p-1'])
    })

    it('TASK_DELETED setQueryData filter function removes the task', () => {
      mount()
      triggerEvent('task_deleted', { task_id: 't-1', project_id: 'p-1' })

      // Find the setQueryData call for tasks list and invoke the updater
      const tasksCall = mockSetQueryData.mock.calls.find(
        (c) => JSON.stringify(c[0]) === JSON.stringify(['tasks', 'p-1'])
      )
      expect(tasksCall).toBeDefined()
      const updater = tasksCall![1] as (old: unknown[]) => unknown[]
      const result = updater([
        { id: 't-1', title: 'Remove me' },
        { id: 't-2', title: 'Keep me' },
      ])
      expect(result).toEqual([{ id: 't-2', title: 'Keep me' }])
    })

    it('TASK_STATUS_CHANGED with full payload uses setQueryData', () => {
      mount()
      const task = { id: 't-1', title: 'Task', status: 'done' }
      triggerEvent('task_status_changed', { task_id: 't-1', project_id: 'p-1', task })

      expect(mockSetQueryData).toHaveBeenCalledWith(['task', 't-1'], task)
      expect(invalidatedKeys()).toContainEqual(['myTasks', 'cross-app'])
    })

    it('TASK_MOVED with full payload uses setQueryData, no myTasksCrossApp', () => {
      mount()
      const task = { id: 't-1', title: 'Moved', status: 'todo' }
      triggerEvent('task_moved', { task_id: 't-1', project_id: 'p-1', task })

      expect(mockSetQueryData).toHaveBeenCalledWith(['task', 't-1'], task)
      // TASK_MOVED should NOT invalidate myTasksCrossApp
      expect(invalidatedKeys()).not.toContainEqual(['myTasks', 'cross-app'])
    })
  })

  // ==========================================================================
  // Comment events
  // ==========================================================================

  describe('comment events', () => {
    it('COMMENT_ADDED invalidates comments', () => {
      mount()
      triggerEvent('comment_added', { task_id: 't-1' })
      expect(invalidatedKeys()).toContainEqual(['comments', 't-1'])
    })

    it('COMMENT_UPDATED invalidates comment and comments list', () => {
      mount()
      triggerEvent('comment_updated', { task_id: 't-1', comment_id: 'c-1' })
      expect(invalidatedKeys()).toContainEqual(['comment', 'c-1'])
      expect(invalidatedKeys()).toContainEqual(['comments', 't-1'])
    })

    it('COMMENT_DELETED invalidates comments and attachments', () => {
      mount()
      triggerEvent('comment_deleted', { task_id: 't-1' })
      expect(invalidatedKeys()).toContainEqual(['comments', 't-1'])
      expect(invalidatedKeys()).toContainEqual(['attachments', 't-1'])
    })
  })

  // ==========================================================================
  // Checklist events
  // ==========================================================================

  describe('checklist events', () => {
    it('CHECKLIST_CREATED invalidates checklists and task', () => {
      mount()
      triggerEvent('checklist_created', { task_id: 't-1' })
      expect(invalidatedKeys()).toContainEqual(['checklists', 't-1'])
      expect(invalidatedKeys()).toContainEqual(['task', 't-1'])
    })

    it('CHECKLIST_ITEM_TOGGLED invalidates checklists and task', () => {
      mount()
      triggerEvent('checklist_item_toggled', { task_id: 't-1' })
      expect(invalidatedKeys()).toContainEqual(['checklists', 't-1'])
      expect(invalidatedKeys()).toContainEqual(['task', 't-1'])
    })

    it('CHECKLISTS_REORDERED invalidates checklists only (not task)', () => {
      mount()
      triggerEvent('checklists_reordered', { task_id: 't-1' })
      expect(invalidatedKeys()).toContainEqual(['checklists', 't-1'])
      expect(invalidatedKeys()).not.toContainEqual(['task', 't-1'])
    })
  })

  // ==========================================================================
  // Member events
  // ==========================================================================

  describe('member events', () => {
    it('MEMBER_ADDED invalidates appMembers', () => {
      mount()
      triggerEvent('member_added', { application_id: 'app-1', user_id: 'other-user' })
      expect(invalidatedKeys()).toContainEqual(['appMembers', 'app-1'])
    })

    it('MEMBER_ADDED for current user also invalidates scopesSummary', () => {
      mount()
      triggerEvent('member_added', { application_id: 'app-1', user_id: 'current-user-id' })

      expect(invalidatedKeys()).toContainEqual(['appMembers', 'app-1'])
      expect(invalidatedKeys()).toContainEqual(['documents', 'scopes-summary'])
    })

    it('MEMBER_REMOVED for current user removes app, calls onCurrentUserRemoved', () => {
      const onCurrentUserRemoved = vi.fn()
      mount({ onCurrentUserRemoved })
      triggerEvent('member_removed', { application_id: 'app-1', user_id: 'current-user-id' })

      expect(removedKeys()).toContainEqual(['application', 'app-1'])
      expect(mockSetQueryData).toHaveBeenCalledWith(['applications'], expect.any(Function))
      expect(mockRefetchQueries).toHaveBeenCalledWith({ queryKey: ['applications'] })
      expect(onCurrentUserRemoved).toHaveBeenCalledWith('app-1')
      expect(invalidatedKeys()).toContainEqual(['documents', 'scopes-summary'])
    })

    it('MEMBER_REMOVED for current user filters app from list cache', () => {
      mount()
      triggerEvent('member_removed', { application_id: 'app-1', user_id: 'current-user-id' })

      const setDataCall = mockSetQueryData.mock.calls.find(
        (c) => JSON.stringify(c[0]) === JSON.stringify(['applications'])
      )
      expect(setDataCall).toBeDefined()
      const updater = setDataCall![1] as (old: { id: string }[]) => { id: string }[]
      const result = updater([{ id: 'app-1' }, { id: 'app-2' }])
      expect(result).toEqual([{ id: 'app-2' }])
    })

    it('MEMBER_REMOVED for other user invalidates applications (not remove)', () => {
      mount()
      triggerEvent('member_removed', { application_id: 'app-1', user_id: 'other-user' })

      expect(invalidatedKeys()).toContainEqual(['applications'])
      expect(invalidatedKeys()).toContainEqual(['application', 'app-1'])
      // Should NOT call onCurrentUserRemoved or remove queries
      expect(mockRefetchQueries).not.toHaveBeenCalled()
    })

    it('ROLE_UPDATED invalidates appMembers and application', () => {
      mount()
      triggerEvent('role_updated', { application_id: 'app-1', user_id: 'other-user' })

      expect(invalidatedKeys()).toContainEqual(['appMembers', 'app-1'])
      expect(invalidatedKeys()).toContainEqual(['application', 'app-1'])
    })

    it('ROLE_UPDATED for current user also invalidates knowledge caches', () => {
      mount()
      triggerEvent('role_updated', { application_id: 'app-1', user_id: 'current-user-id' })

      expect(invalidatedKeys()).toContainEqual(['documents', 'scopes-summary'])
      expect(invalidatedKeys()).toContainEqual(['knowledge-permissions'])
    })
  })

  // ==========================================================================
  // Project member events
  // ==========================================================================

  describe('project member events', () => {
    it('PROJECT_MEMBER_ADDED invalidates projectMembers', () => {
      mount()
      triggerEvent('project_member_added', {
        project_id: 'p-1', user_id: 'other-user', application_id: 'app-1',
      })
      expect(invalidatedKeys()).toContainEqual(['projectMembers', 'p-1'])
    })

    it('PROJECT_MEMBER_ADDED for current user invalidates knowledge caches', () => {
      mount()
      triggerEvent('project_member_added', {
        project_id: 'p-1', user_id: 'current-user-id', application_id: 'app-1',
      })

      expect(invalidatedKeys()).toContainEqual(['projects-with-content', 'app-1'])
      expect(invalidatedKeys()).toContainEqual(['knowledge-permissions', 'project', 'p-1'])
    })

    it('PROJECT_MEMBER_REMOVED invalidates projectMembers and tasks', () => {
      mount()
      triggerEvent('project_member_removed', {
        project_id: 'p-1', user_id: 'other-user',
      })
      expect(invalidatedKeys()).toContainEqual(['projectMembers', 'p-1'])
      expect(invalidatedKeys()).toContainEqual(['tasks', 'p-1'])
    })

    it('PROJECT_ROLE_CHANGED for current user invalidates knowledge caches', () => {
      mount()
      triggerEvent('project_role_changed', {
        project_id: 'p-1', user_id: 'current-user-id', application_id: 'app-1',
      })

      expect(invalidatedKeys()).toContainEqual(['projects-with-content', 'app-1'])
      expect(invalidatedKeys()).toContainEqual(['knowledge-permissions', 'project', 'p-1'])
    })
  })

  // ==========================================================================
  // Notification events
  // ==========================================================================

  describe('notification events', () => {
    it('NOTIFICATION invalidates notifications and unreadCount', () => {
      mount()
      triggerEvent('notification', {})
      expect(invalidatedKeys()).toContainEqual(['notifications'])
      expect(invalidatedKeys()).toContainEqual(['notifications', 'unread'])
    })

    it('NOTIFICATION with title/message triggers desktop notification', () => {
      mount()
      triggerEvent('notification', { title: 'New task', message: 'You were assigned' })

      expect(showBrowserNotification).toHaveBeenCalledWith('New task', 'You were assigned')
    })

    it('NOTIFICATION member_removed fallback removes app and calls callback', () => {
      const onCurrentUserRemoved = vi.fn()
      mount({ onCurrentUserRemoved })
      triggerEvent('notification', {
        notification_type: 'member_removed',
        entity_type: 'application',
        entity_id: 'app-1',
      })

      expect(removedKeys()).toContainEqual(['application', 'app-1'])
      expect(mockRefetchQueries).toHaveBeenCalledWith({ queryKey: ['applications'] })
      expect(onCurrentUserRemoved).toHaveBeenCalledWith('app-1')
    })

    it('NOTIFICATION_READ invalidates notifications and unreadCount', () => {
      mount()
      triggerEvent('notification_read', {})
      expect(invalidatedKeys()).toContainEqual(['notifications'])
      expect(invalidatedKeys()).toContainEqual(['notifications', 'unread'])
    })
  })

  // ==========================================================================
  // Attachment events
  // ==========================================================================

  describe('attachment events', () => {
    it('ATTACHMENT_UPLOADED invalidates attachments', () => {
      mount()
      triggerEvent('attachment_uploaded', { task_id: 't-1' })
      expect(invalidatedKeys()).toContainEqual(['attachments', 't-1'])
    })

    it('ATTACHMENT_DELETED invalidates attachments and removes download URL', () => {
      mount()
      triggerEvent('attachment_deleted', { task_id: 't-1', attachment_id: 'att-1' })

      expect(invalidatedKeys()).toContainEqual(['attachments', 't-1'])
      expect(removedKeys()).toContainEqual(['downloadUrl', 'att-1'])
    })
  })

  // ==========================================================================
  // Document events
  // ==========================================================================

  describe('document events', () => {
    it('DOCUMENT_CREATED invalidates documents, folders, scopesSummary, search', () => {
      mount()
      triggerEvent('document_created', {
        document_id: 'doc-1', scope: 'application', scope_id: 'app-1',
      })

      expect(invalidatedKeys()).toContainEqual(['documents', 'application', 'app-1'])
      expect(invalidatedKeys()).toContainEqual(['documentFolders', 'application', 'app-1'])
      expect(invalidatedKeys()).toContainEqual(['documents', 'scopes-summary'])
      expect(invalidatedKeys()).toContainEqual(['search'])
    })

    it('DOCUMENT_CREATED for project scope also invalidates application queries', () => {
      mount()
      triggerEvent('document_created', {
        document_id: 'doc-1', scope: 'project', scope_id: 'proj-1', application_id: 'app-1',
      })

      expect(invalidatedKeys()).toContainEqual(['documents', 'project', 'proj-1'])
      expect(invalidatedKeys()).toContainEqual(['projects-with-content'])
      expect(invalidatedKeys()).toContainEqual(['documents', 'application', 'app-1'])
      expect(invalidatedKeys()).toContainEqual(['documentFolders', 'application', 'app-1'])
    })

    it('DOCUMENT_UPDATED skips document and list invalidation for own action (QE-013)', () => {
      mount()
      triggerEvent('document_updated', {
        document_id: 'doc-1', scope: 'application', scope_id: 'app-1',
        actor_id: 'current-user-id', timestamp: '2026-03-04T12:00:00Z',
      })

      // Should NOT invalidate the individual document query (own action)
      expect(invalidatedKeys()).not.toContainEqual(['document', 'doc-1'])
      // Should NOT invalidate document list (QE-013 fix: uses setQueriesData instead)
      expect(invalidatedKeys()).not.toContainEqual(['documents', 'application', 'app-1'])
      // Should use setQueriesData to surgically update updated_at in list cache
      expect(mockSetQueriesData).toHaveBeenCalledWith(
        { queryKey: ['documents', 'application', 'app-1'], exact: false },
        expect.any(Function)
      )
    })

    it('DOCUMENT_UPDATED own action setQueriesData updates updated_at in list (QE-013)', () => {
      mount()
      triggerEvent('document_updated', {
        document_id: 'doc-1', scope: 'application', scope_id: 'app-1',
        actor_id: 'current-user-id', timestamp: '2026-03-04T12:00:00Z',
      })

      const call = mockSetQueriesData.mock.calls.find(
        (c) => JSON.stringify(c[0]) === JSON.stringify({ queryKey: ['documents', 'application', 'app-1'], exact: false })
      )
      expect(call).toBeDefined()
      const updater = call![1] as (old: unknown) => unknown
      const result = updater({
        items: [
          { id: 'doc-1', title: 'Doc 1', updated_at: '2026-01-01T00:00:00Z' },
          { id: 'doc-2', title: 'Doc 2', updated_at: '2026-01-01T00:00:00Z' },
        ],
        next_cursor: null,
      }) as { items: Array<{ id: string; updated_at: string }> }
      expect(result.items[0].updated_at).toBe('2026-03-04T12:00:00Z')
      expect(result.items[1].updated_at).toBe('2026-01-01T00:00:00Z')
    })

    it('DOCUMENT_UPDATED own action returns old data unchanged when doc not in list (QE-013)', () => {
      mount()
      triggerEvent('document_updated', {
        document_id: 'doc-99', scope: 'application', scope_id: 'app-1',
        actor_id: 'current-user-id', timestamp: '2026-03-04T12:00:00Z',
      })

      const call = mockSetQueriesData.mock.calls.find(
        (c) => JSON.stringify(c[0]) === JSON.stringify({ queryKey: ['documents', 'application', 'app-1'], exact: false })
      )
      const updater = call![1] as (old: unknown) => unknown
      const oldData = { items: [{ id: 'doc-1', title: 'Doc 1' }], next_cursor: null }
      expect(updater(oldData)).toBe(oldData)
    })

    it('DOCUMENT_UPDATED own action for project scope also updates app list cache (QE-013)', () => {
      mount()
      triggerEvent('document_updated', {
        document_id: 'doc-1', scope: 'project', scope_id: 'proj-1',
        actor_id: 'current-user-id', application_id: 'app-1',
        timestamp: '2026-03-04T12:00:00Z',
      })

      // Should NOT invalidate either list
      expect(invalidatedKeys()).not.toContainEqual(['documents', 'project', 'proj-1'])
      expect(invalidatedKeys()).not.toContainEqual(['documents', 'application', 'app-1'])
      // Should setQueriesData for both project scope and application scope
      expect(mockSetQueriesData).toHaveBeenCalledWith(
        { queryKey: ['documents', 'project', 'proj-1'], exact: false },
        expect.any(Function)
      )
      expect(mockSetQueriesData).toHaveBeenCalledWith(
        { queryKey: ['documents', 'application', 'app-1'], exact: false },
        expect.any(Function)
      )
    })

    it('DOCUMENT_UPDATED invalidates document for other users action', () => {
      mount()
      triggerEvent('document_updated', {
        document_id: 'doc-1', scope: 'application', scope_id: 'app-1',
        actor_id: 'other-user',
      })

      expect(invalidatedKeys()).toContainEqual(['document', 'doc-1'])
      expect(invalidatedKeys()).toContainEqual(['documents', 'application', 'app-1'])
    })

    it('DOCUMENT_UPDATED with folder_id also invalidates folders', () => {
      mount()
      triggerEvent('document_updated', {
        document_id: 'doc-1', scope: 'application', scope_id: 'app-1',
        actor_id: 'other-user', folder_id: 'f-1',
      })

      expect(invalidatedKeys()).toContainEqual(['documentFolders', 'application', 'app-1'])
    })

    it('DOCUMENT_DELETED removes document and filters from list cache', () => {
      mount()
      triggerEvent('document_deleted', {
        document_id: 'doc-1', scope: 'application', scope_id: 'app-1',
        actor_id: 'other-user',
      })

      expect(removedKeys()).toContainEqual(['document', 'doc-1'])
      expect(mockSetQueriesData).toHaveBeenCalled()
    })

    it('DOCUMENT_DELETED own action skips redundant invalidations', () => {
      mount()
      triggerEvent('document_deleted', {
        document_id: 'doc-1', scope: 'application', scope_id: 'app-1',
        actor_id: 'current-user-id',
      })

      // Should still remove and setQueriesData
      expect(removedKeys()).toContainEqual(['document', 'doc-1'])
      // Should NOT invalidate folders/scopesSummary/search (onSuccess handles those)
      expect(invalidatedKeys()).not.toContainEqual(['documentFolders', 'application', 'app-1'])
      expect(invalidatedKeys()).not.toContainEqual(['documents', 'scopes-summary'])
    })

    it('DOCUMENT_DELETED other user action invalidates folders/scopesSummary/search', () => {
      mount()
      triggerEvent('document_deleted', {
        document_id: 'doc-1', scope: 'application', scope_id: 'app-1',
        actor_id: 'other-user',
      })

      expect(invalidatedKeys()).toContainEqual(['documentFolders', 'application', 'app-1'])
      expect(invalidatedKeys()).toContainEqual(['documents', 'scopes-summary'])
      expect(invalidatedKeys()).toContainEqual(['search'])
    })
  })

  // ==========================================================================
  // Folder events
  // ==========================================================================

  describe('folder events', () => {
    it('FOLDER_CREATED invalidates documentFolders', () => {
      mount()
      triggerEvent('folder_created', {
        folder_id: 'f-1', scope: 'application', scope_id: 'app-1',
      })

      expect(invalidatedKeys()).toContainEqual(['documentFolders', 'application', 'app-1'])
    })

    it('FOLDER_CREATED for project scope also invalidates application folders', () => {
      mount()
      triggerEvent('folder_created', {
        folder_id: 'f-1', scope: 'project', scope_id: 'proj-1', application_id: 'app-1',
      })

      expect(invalidatedKeys()).toContainEqual(['documentFolders', 'project', 'proj-1'])
      expect(invalidatedKeys()).toContainEqual(['projects-with-content'])
      expect(invalidatedKeys()).toContainEqual(['documentFolders', 'application', 'app-1'])
    })

    it('FOLDER_UPDATED invalidates documentFolders', () => {
      mount()
      triggerEvent('folder_updated', {
        folder_id: 'f-1', scope: 'application', scope_id: 'app-1',
      })
      expect(invalidatedKeys()).toContainEqual(['documentFolders', 'application', 'app-1'])
    })

    it('FOLDER_DELETED removes folder from tree via setQueriesData', () => {
      mount()
      triggerEvent('folder_deleted', {
        folder_id: 'f-1', scope: 'application', scope_id: 'app-1',
        actor_id: 'other-user',
      })

      expect(mockSetQueriesData).toHaveBeenCalled()
      // Other user: should invalidate documents/scopesSummary
      expect(invalidatedKeys()).toContainEqual(['documents', 'application', 'app-1'])
      expect(invalidatedKeys()).toContainEqual(['documents', 'scopes-summary'])
    })

    it('FOLDER_DELETED own action skips redundant invalidations', () => {
      mount()
      triggerEvent('folder_deleted', {
        folder_id: 'f-1', scope: 'application', scope_id: 'app-1',
        actor_id: 'current-user-id',
      })

      // Should still setQueriesData (for IndexedDB consistency)
      expect(mockSetQueriesData).toHaveBeenCalled()
      // Should NOT invalidate documents/scopesSummary/search
      expect(invalidatedKeys()).not.toContainEqual(['documents', 'application', 'app-1'])
      expect(invalidatedKeys()).not.toContainEqual(['documents', 'scopes-summary'])
    })

    it('FOLDER_DELETED tree removal function filters recursively', () => {
      mount()
      triggerEvent('folder_deleted', {
        folder_id: 'child-f', scope: 'application', scope_id: 'app-1',
        actor_id: 'other-user',
      })

      // Find the setQueriesData call and test the updater function
      const call = mockSetQueriesData.mock.calls[0]
      const updater = call[1] as (old: unknown) => unknown
      const tree = [
        {
          id: 'parent-f',
          children: [
            { id: 'child-f', children: [] },
            { id: 'sibling-f', children: [] },
          ],
        },
      ]
      const result = updater(tree) as Array<{ id: string; children: Array<{ id: string }> }>
      expect(result[0].children).toHaveLength(1)
      expect(result[0].children[0].id).toBe('sibling-f')
    })
  })

  // ==========================================================================
  // Invitation events
  // ==========================================================================

  describe('invitation events', () => {
    it('INVITATION_RESPONSE invalidates appMembers and invitations', () => {
      mount()
      triggerEvent('invitation_response', { application_id: 'app-1' })

      expect(invalidatedKeys()).toContainEqual(['appMembers', 'app-1'])
      expect(invalidatedKeys()).toContainEqual(['invitations'])
    })

    it('INVITATION_RECEIVED invalidates invitations and pendingInvitations', () => {
      mount()
      triggerEvent('invitation_received', {})

      expect(invalidatedKeys()).toContainEqual(['invitations'])
      expect(invalidatedKeys()).toContainEqual(['invitations', 'pending'])
    })
  })

  // ==========================================================================
  // AI indexing events
  // ==========================================================================

  describe('AI indexing events', () => {
    it('EMBEDDING_UPDATED invalidates index status and updates document cache', () => {
      mount()
      triggerEvent('embedding_updated', {
        document_id: 'doc-1', chunk_count: 5, timestamp: '2026-01-01',
        embedding_status: 'synced',
      })

      expect(invalidatedKeys()).toContainEqual(['ai', 'index-status', 'doc-1'])
      // setQueryData updates individual doc
      expect(mockSetQueryData).toHaveBeenCalledWith(
        ['document', 'doc-1'],
        expect.any(Function)
      )
      // setQueriesData updates document lists
      expect(mockSetQueriesData).toHaveBeenCalled()
    })

    it('ENTITIES_EXTRACTED invalidates documentIndexStatus', () => {
      mount()
      triggerEvent('entities_extracted', {
        document_id: 'doc-1', entities_count: 3, relationships_count: 2, timestamp: '2026-01-01',
      })

      expect(invalidatedKeys()).toContainEqual(['ai', 'index-status', 'doc-1'])
    })
  })

  // ==========================================================================
  // AI import events
  // ==========================================================================

  describe('AI import events', () => {
    it('IMPORT_COMPLETED invalidates importJobs and shows toast', () => {
      mount()
      triggerEvent('import_completed', {
        job_id: 'j-1', document_id: 'doc-1', title: 'My Doc', scope: 'application',
      })

      expect(invalidatedKeys()).toContainEqual(['ai', 'import', 'jobs'])
      expect(toast.success).toHaveBeenCalledWith('Import complete: My Doc')
    })

    it('IMPORT_FAILED invalidates importJobs and shows error toast', () => {
      mount()
      triggerEvent('import_failed', {
        job_id: 'j-1', error_message: 'Parse error', file_name: 'bad.pdf',
      })

      expect(invalidatedKeys()).toContainEqual(['ai', 'import', 'jobs'])
      expect(toast.error).toHaveBeenCalledWith('Import failed: bad.pdf', {
        description: 'Parse error',
      })
    })
  })

  // ==========================================================================
  // AI reindex events
  // ==========================================================================

  describe('AI reindex events', () => {
    it('REINDEX_PROGRESS invalidates applicationIndexStatus', () => {
      mount()
      triggerEvent('reindex_progress', {
        application_id: 'app-1', total: 10, processed: 5, failed: 0,
      })

      expect(invalidatedKeys()).toContainEqual(['ai', 'index-status', 'application', 'app-1'])
    })
  })
})
