/**
 * Query Hooks Index
 *
 * Central export for all TanStack Query hooks.
 * Import from this file for cleaner imports.
 */

// Re-export query client utilities
export { queryKeys, clearQueryCache, prefetchQuery } from '@/lib/query-client'

// Application queries
export {
  useApplications,
  useApplication,
  useCreateApplication,
  useUpdateApplication,
  useDeleteApplication,
} from './use-queries'

// Project queries
export {
  useProjects,
  useProject,
  useCreateProject,
  useUpdateProject,
  useDeleteProject,
} from './use-queries'

// Task queries
export {
  useTasks,
  useTask,
  useCreateTask,
  useUpdateTask,
  useDeleteTask,
  useMoveTask,
  useTaskStatuses,
  isTaskDone,
} from './use-queries'

// Comment queries
export {
  useComments,
  useCommentsList,
  useComment,
  useCreateComment,
  useUpdateComment,
  useDeleteComment,
} from './use-comments'

// Member queries
export {
  useAppMembers,
  useInviteAppMember,
  useUpdateAppMemberRole,
  useRemoveAppMember,
  useProjectMembers,
  useAddProjectMember,
  useUpdateProjectMemberRole,
  useRemoveProjectMember,
} from './use-members'

// Notification queries
export {
  useNotifications,
  useUnreadCount,
  useMarkAsRead,
  useMarkAllAsRead,
  useDeleteNotification,
} from './use-notifications'

// Attachment queries
export {
  useAttachments,
  useDownloadUrl,
  useDownloadUrls,
  useUploadAttachment,
  useDeleteAttachment,
  useDownloadAttachment,
} from './use-attachments'

// WebSocket cache invalidation
export { useWebSocketCacheInvalidation } from './use-websocket-cache'

// Type re-exports for convenience
export type {
  Application,
  ApplicationCreate,
  ApplicationUpdate,
  Project,
  ProjectCreate,
  ProjectUpdate,
  Task,
  TaskCreate,
  TaskUpdate,
  TaskMovePayload,
  TaskStatus,
  TaskStatusInfo,
  ApiError,
} from './use-queries'

export type {
  Comment,
  CommentCreate,
  CommentUpdate,
  Mention,
  CommentAttachment,
} from './use-comments'

export type {
  ApplicationMember,
  ProjectMember,
  ApplicationRole,
  ProjectRole,
} from './use-members'

export type {
  Notification,
  NotificationType,
} from './use-notifications'

export type {
  Attachment,
  DownloadUrl,
  UploadProgress,
} from './use-attachments'
