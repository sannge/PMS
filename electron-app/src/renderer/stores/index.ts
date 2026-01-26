/**
 * Stores
 *
 * Re-exports all Zustand stores for easy imports.
 */

export { useAuthStore, getAuthHeaders } from './auth-store'
export { useApplicationsStore } from './applications-store'
export { useFilesStore } from './files-store'
export { useInvitationsStore } from './invitations-store'
export { useMembersStore } from './members-store'
export { useNotesStore } from './notes-store'
export { useNotificationsStore } from './notifications-store'
export { useProjectsStore } from './projects-store'

// Note: tasks-store has been migrated to TanStack Query hooks in use-queries.ts
// Use useTasks(), useTask(), useCreateTask(), useUpdateTask(), useMoveTask() instead

// Note: comments-store has been migrated to TanStack Query hooks in use-comments.ts
// Use useComments(), useCreateComment(), useUpdateComment(), useDeleteComment() instead

// New stores for feature 017
export { useChecklistsStore, type Checklist, type ChecklistItem } from './checklists-store'
export { useProjectMembersStore, type ProjectMember, type AppMember } from './project-members-store'
