/**
 * Stores
 *
 * Re-exports from React Context providers (migrated from Zustand).
 *
 * Note: Most data stores have been migrated to TanStack Query hooks for caching:
 * - tasks-store -> use-queries.ts (useTasks, useTask, useCreateTask, etc.)
 * - comments-store -> use-comments.ts (useCommentsList, useCreateComment, etc.)
 * - applications-store -> use-queries.ts (useApplications, useApplication, etc.)
 * - projects-store -> use-queries.ts (useProjects, useProject, etc.)
 * - members-store -> use-members.ts (useAppMembers, useAddAppMember, etc.)
 * - project-members-store -> use-members.ts (useProjectMembers, useAddProjectMember, etc.)
 * - files-store -> use-attachments.ts (useEntityAttachments, useUploadFile, etc.)
 * - checklists-store -> use-checklists.ts (useChecklists, useCreateChecklist, etc.)
 * - notifications-store -> use-notifications.ts (useNotifications, useMarkAsRead, etc.)
 * - invitations-store -> use-invitations.ts (useReceivedInvitations, useAcceptInvitation, etc.)
 *
 * Remaining stores (now React Context):
 * - auth-store -> auth-context (AuthProvider, useAuthStore)
 * - notification-ui-store -> notification-ui-context (NotificationUIProvider, useNotificationUIStore)
 */

// Auth context - client-side auth state
export {
  AuthProvider,
  useAuthStore,
  getAuthHeaders,
  selectUser,
  selectIsAuthenticated,
  selectIsLoading,
  selectIsInitialized,
  selectError,
  type User,
  type LoginCredentials,
  type RegisterData,
  type TokenResponse,
  type AuthError,
} from '../contexts/auth-context'

// Notification UI context - panel open/close state
export { NotificationUIProvider, useNotificationUIStore } from '../contexts/notification-ui-context'

