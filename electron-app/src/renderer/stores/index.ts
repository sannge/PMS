/**
 * Stores
 *
 * Re-exports all Zustand stores for easy imports.
 *
 * Note: Many stores have been migrated to TanStack Query hooks:
 * - tasks-store -> use-queries.ts (useTasks, useTask, useCreateTask, etc.)
 * - comments-store -> use-comments.ts (useCommentsList, useCreateComment, etc.)
 * - applications-store -> use-queries.ts (useApplications, useApplication, etc.)
 * - projects-store -> use-queries.ts (useProjects, useProject, etc.)
 * - members-store -> use-members.ts (useAppMembers, useAddAppMember, etc.)
 * - project-members-store -> use-members.ts (useProjectMembers, useAddProjectMember, etc.)
 */

// Core stores that remain in Zustand
export { useAuthStore, getAuthHeaders } from './auth-store'
export { useNotificationsStore } from './notifications-store'
export { useInvitationsStore } from './invitations-store'
export { useNotesStore } from './notes-store'

// Feature-specific stores
export { useChecklistsStore, type Checklist, type ChecklistItem } from './checklists-store'

// Files store - still used for file upload/download state
export { useFilesStore } from './files-store'
