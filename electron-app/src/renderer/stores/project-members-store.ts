/**
 * Project Members Store
 *
 * Zustand store for managing project-level member assignments.
 * Project members are a subset of application members who can work on a specific project.
 *
 * Features:
 * - List project members with user details
 * - Add/remove project members (owners only)
 * - Get available members (application members not yet in project)
 * - Loading and error states
 */

import { create } from 'zustand'
import { getAuthHeaders } from './auth-store'

// ============================================================================
// Types
// ============================================================================

/**
 * Application role enumeration
 */
export type ApplicationRole = 'owner' | 'editor' | 'viewer'

/**
 * Project member role enumeration
 * - admin: Can manage project members + edit/move tasks
 * - member: Can edit/move tasks only
 */
export type ProjectMemberRole = 'admin' | 'member'

/**
 * User summary for display
 */
export interface UserSummary {
  id: string
  email: string
  display_name: string | null
  avatar_url: string | null
}

/**
 * Project member data from the API
 */
export interface ProjectMember {
  id: string
  project_id: string
  user_id: string
  role: ProjectMemberRole
  created_at: string
  updated_at: string
  user: UserSummary | null
}

/**
 * Application member for selection
 */
export interface AppMember {
  id: string
  user_id: string
  role: ApplicationRole
  user: UserSummary | null
}

/**
 * Error with details
 */
export interface ProjectMemberError {
  message: string
  code?: string
}

/**
 * Project members store state
 */
export interface ProjectMembersState {
  // State
  members: ProjectMember[]
  availableMembers: AppMember[]
  currentProjectId: string | null
  isLoading: boolean
  isLoadingAvailable: boolean
  isAdding: boolean
  isRemoving: boolean
  isChangingRole: boolean
  error: ProjectMemberError | null

  // Actions
  fetchMembers: (token: string | null, projectId: string) => Promise<void>
  fetchAvailableMembers: (token: string | null, projectId: string, applicationId: string) => Promise<void>
  addMember: (token: string | null, projectId: string, userId: string, role?: ProjectMemberRole) => Promise<boolean>
  removeMember: (token: string | null, projectId: string, userId: string) => Promise<boolean>
  updateMemberRole: (token: string | null, projectId: string, userId: string, newRole: ProjectMemberRole) => Promise<boolean>

  // Utilities
  setCurrentProject: (projectId: string | null) => void
  clearError: () => void
  reset: () => void

  // Computed helpers
  getCurrentUserRole: (currentUserId: string | null) => ProjectMemberRole | null
  canManageMembers: (currentUserId: string | null, isAppOwner: boolean) => boolean

  // Real-time handlers
  handleMemberAdded: (event: {
    project_id: string
    member_id: string
    user_id: string
    role: string
    user: UserSummary
    added_by: string
  }) => void
  handleMemberRemoved: (event: {
    project_id: string
    user_id: string
    removed_by: string
    tasks_unassigned: number
  }) => void
  handleRoleChanged: (event: {
    project_id: string
    user_id: string
    old_role: string
    new_role: string
    changed_by: string
  }) => void
}

// ============================================================================
// Helper Functions
// ============================================================================

function parseApiError(status: number, data: unknown): ProjectMemberError {
  if (typeof data === 'object' && data !== null) {
    const errorData = data as Record<string, unknown>
    if (typeof errorData.detail === 'string') {
      return { message: errorData.detail }
    }
  }

  switch (status) {
    case 400:
      return { message: 'Invalid request.' }
    case 401:
      return { message: 'Authentication required.' }
    case 403:
      return { message: 'Access denied. Only owners can manage project members.' }
    case 404:
      return { message: 'Not found.' }
    case 409:
      return { message: 'Member already exists in this project.' }
    case 500:
      return { message: 'Server error.' }
    default:
      return { message: 'An unexpected error occurred.' }
  }
}

// ============================================================================
// Initial State
// ============================================================================

const initialState = {
  members: [] as ProjectMember[],
  availableMembers: [] as AppMember[],
  currentProjectId: null as string | null,
  isLoading: false,
  isLoadingAvailable: false,
  isAdding: false,
  isRemoving: false,
  isChangingRole: false,
  error: null as ProjectMemberError | null,
}

// ============================================================================
// Store
// ============================================================================

export const useProjectMembersStore = create<ProjectMembersState>((set, get) => ({
  ...initialState,

  /**
   * Fetch project members
   */
  fetchMembers: async (token, projectId) => {
    // Clear members if fetching a different project to avoid showing stale data
    const currentId = get().currentProjectId
    if (currentId && currentId !== projectId) {
      set({ members: [], availableMembers: [], isLoading: true, error: null, currentProjectId: projectId })
    } else {
      set({ isLoading: true, error: null, currentProjectId: projectId })
    }

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.get<ProjectMember[]>(
        `/api/projects/${projectId}/members`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        const error = parseApiError(response.status, response.data)
        set({ isLoading: false, error })
        return
      }

      set({
        members: response.data || [],
        isLoading: false,
      })
    } catch (err) {
      const error: ProjectMemberError = {
        message: err instanceof Error ? err.message : 'Failed to fetch project members',
      }
      set({ isLoading: false, error })
    }
  },

  /**
   * Fetch application members who are not yet project members
   */
  fetchAvailableMembers: async (token, projectId, applicationId) => {
    set({ isLoadingAvailable: true, error: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      // Get all application members
      const appResponse = await window.electronAPI.get<AppMember[]>(
        `/api/applications/${applicationId}/members`,
        getAuthHeaders(token)
      )

      if (appResponse.status !== 200) {
        const error = parseApiError(appResponse.status, appResponse.data)
        set({ isLoadingAvailable: false, error })
        return
      }

      const allAppMembers = appResponse.data || []
      const currentProjectMembers = get().members
      const currentMemberUserIds = new Set(currentProjectMembers.map((m) => m.user_id))

      // Filter out members who are already in the project
      // Also filter out viewers (only editors and owners can be project members)
      const available = allAppMembers.filter(
        (m) => !currentMemberUserIds.has(m.user_id) && m.role !== 'viewer'
      )

      set({
        availableMembers: available,
        isLoadingAvailable: false,
      })
    } catch (err) {
      const error: ProjectMemberError = {
        message: err instanceof Error ? err.message : 'Failed to fetch available members',
      }
      set({ isLoadingAvailable: false, error })
    }
  },

  /**
   * Add a member to the project
   */
  addMember: async (token, projectId, userId, role = 'member' as ProjectMemberRole) => {
    set({ isAdding: true, error: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.post<ProjectMember>(
        `/api/projects/${projectId}/members`,
        { user_id: userId, role },
        getAuthHeaders(token)
      )

      if (response.status !== 201) {
        const error = parseApiError(response.status, response.data)
        set({ isAdding: false, error })
        return false
      }

      const newMember = response.data
      const currentMembers = get().members

      // Check if already added by WebSocket event (race condition prevention)
      if (currentMembers.some((m) => m.user_id === userId)) {
        // Already added via WebSocket, just clear loading state
        set({
          availableMembers: get().availableMembers.filter((m) => m.user_id !== userId),
          isAdding: false,
        })
        return true
      }

      // Update members list
      set({
        members: [...currentMembers, newMember],
        // Remove from available
        availableMembers: get().availableMembers.filter((m) => m.user_id !== userId),
        isAdding: false,
      })

      return true
    } catch (err) {
      const error: ProjectMemberError = {
        message: err instanceof Error ? err.message : 'Failed to add member',
      }
      set({ isAdding: false, error })
      return false
    }
  },

  /**
   * Remove a member from the project
   */
  removeMember: async (token, projectId, userId) => {
    const previous = get().members

    // Optimistic removal
    set({
      members: previous.filter((m) => m.user_id !== userId),
      isRemoving: true,
      error: null,
    })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.delete<void>(
        `/api/projects/${projectId}/members/${userId}`,
        getAuthHeaders(token)
      )

      // Accept 200, 204 (success), and 404 (already removed) as success
      const isSuccess = response.status === 200 || response.status === 204 || response.status === 404
      if (!isSuccess) {
        // Rollback only on actual errors
        set({ members: previous, isRemoving: false, error: parseApiError(response.status, response.data) })
        return false
      }

      // Don't re-add member - WebSocket event will handle final state
      // Just ensure member is removed (in case WebSocket already handled it)
      const currentMembers = get().members
      const stillExists = currentMembers.some((m) => m.user_id === userId)
      if (stillExists) {
        // Remove it if WebSocket hasn't done so yet
        set({
          members: currentMembers.filter((m) => m.user_id !== userId),
          isRemoving: false,
        })
      } else {
        set({ isRemoving: false })
      }
      return true
    } catch (err) {
      // Rollback
      set({
        members: previous,
        isRemoving: false,
        error: { message: err instanceof Error ? err.message : 'Failed to remove member' },
      })
      return false
    }
  },

  /**
   * Update a member's role
   */
  updateMemberRole: async (token, projectId, userId, newRole) => {
    const previous = get().members
    const memberToUpdate = previous.find((m) => m.user_id === userId)
    if (!memberToUpdate) return false

    // Optimistic update
    set({
      members: previous.map((m) =>
        m.user_id === userId ? { ...m, role: newRole, updated_at: new Date().toISOString() } : m
      ),
      isChangingRole: true,
      error: null,
    })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.patch<ProjectMember>(
        `/api/projects/${projectId}/members/${userId}/role`,
        { role: newRole },
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        // Rollback
        set({ members: previous, isChangingRole: false, error: parseApiError(response.status, response.data) })
        return false
      }

      // Update with server response
      set({
        members: get().members.map((m) => (m.user_id === userId ? response.data : m)),
        isChangingRole: false,
      })

      return true
    } catch (err) {
      // Rollback
      set({
        members: previous,
        isChangingRole: false,
        error: { message: err instanceof Error ? err.message : 'Failed to change role' },
      })
      return false
    }
  },

  /**
   * Set the current project ID
   */
  setCurrentProject: (projectId) => {
    if (projectId !== get().currentProjectId) {
      set({ ...initialState, currentProjectId: projectId })
    }
  },

  /**
   * Clear the current error
   */
  clearError: () => {
    set({ error: null })
  },

  /**
   * Reset the store
   */
  reset: () => {
    set(initialState)
  },

  /**
   * Get the current user's project role
   */
  getCurrentUserRole: (currentUserId) => {
    if (!currentUserId) return null
    const member = get().members.find((m) => m.user_id === currentUserId)
    return member?.role || null
  },

  /**
   * Check if current user can manage project members
   * App owners always can, project admins can
   */
  canManageMembers: (currentUserId, isAppOwner) => {
    if (isAppOwner) return true
    if (!currentUserId) return false
    const member = get().members.find((m) => m.user_id === currentUserId)
    return member?.role === 'admin'
  },

  // ============================================================================
  // Real-time WebSocket Handlers
  // ============================================================================

  /**
   * Handle WebSocket project_member_added event
   */
  handleMemberAdded: (event) => {
    const { project_id, member_id, user_id, role, user } = event
    const currentProjectId = get().currentProjectId

    // Only update if viewing the same project
    if (currentProjectId !== project_id) return

    // Check if member already exists
    const existingMember = get().members.find((m) => m.user_id === user_id)
    if (existingMember) return

    // Add the new member
    const newMember: ProjectMember = {
      id: member_id,
      project_id,
      user_id,
      role: role as ProjectMemberRole,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      user: user || null,
    }

    set({
      members: [...get().members, newMember],
      // Remove from available members if present
      availableMembers: get().availableMembers.filter((m) => m.user_id !== user_id),
    })
  },

  /**
   * Handle WebSocket project_member_removed event
   */
  handleMemberRemoved: (event) => {
    const { project_id, user_id } = event
    const currentProjectId = get().currentProjectId

    // Only update if viewing the same project
    if (currentProjectId !== project_id) return

    set({
      members: get().members.filter((m) => m.user_id !== user_id),
    })
  },

  /**
   * Handle WebSocket project_role_changed event
   */
  handleRoleChanged: (event) => {
    const { project_id, user_id, new_role } = event
    const currentProjectId = get().currentProjectId

    // Only update if viewing the same project
    if (currentProjectId !== project_id) return

    set({
      members: get().members.map((m) =>
        m.user_id === user_id
          ? { ...m, role: new_role as ProjectMemberRole, updated_at: new Date().toISOString() }
          : m
      ),
    })
  },
}))

// ============================================================================
// Selectors
// ============================================================================

export const selectProjectMembers = (state: ProjectMembersState): ProjectMember[] => state.members

export const selectAvailableMembers = (state: ProjectMembersState): AppMember[] => state.availableMembers

export const selectIsLoading = (state: ProjectMembersState): boolean => state.isLoading

export const selectError = (state: ProjectMembersState): ProjectMemberError | null => state.error

export default useProjectMembersStore
