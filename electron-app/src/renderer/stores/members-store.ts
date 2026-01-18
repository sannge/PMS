/**
 * Members Store
 *
 * Zustand store for managing application members state in the renderer process.
 * Handles member operations: fetch, update role, and remove.
 *
 * Features:
 * - Application members list with pagination
 * - Role update operations (with role-based permissions)
 * - Remove member operations
 * - Loading and error states
 *
 * Role-based permissions:
 * - Viewer: Can view members only. Cannot edit roles, invite, or remove members.
 * - Editor: Can promote viewers to editors. Can invite with viewer or editor roles.
 * - Owner: Full access - can invite with any role, update any role, remove members.
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
 * Minimal user information for member display
 */
export interface UserSummary {
  id: string
  email: string
  full_name: string | null
}

/**
 * Application member data from the API
 */
export interface Member {
  id: string
  application_id: string
  user_id: string
  role: ApplicationRole
  invitation_id: string | null
  created_at: string
  updated_at: string
}

/**
 * Member with user details
 */
export interface MemberWithUser extends Member {
  user: UserSummary | null
}

/**
 * Data for updating a member
 */
export interface MemberUpdate {
  role?: ApplicationRole
}

/**
 * Member count response
 */
export interface MemberCount {
  total: number
  by_role: {
    owners: number
    editors: number
    viewers: number
  }
}

/**
 * Error with details
 */
export interface MemberError {
  message: string
  code?: string
  field?: string
}

/**
 * Members store state
 */
export interface MembersState {
  // State
  members: MemberWithUser[]
  memberCount: MemberCount | null
  currentApplicationId: string | null
  isLoading: boolean
  isUpdating: boolean
  isRemoving: boolean
  error: MemberError | null

  // Pagination
  skip: number
  limit: number
  hasMore: boolean

  // Actions
  fetchMembers: (
    token: string | null,
    applicationId: string,
    options?: { skip?: number; role?: ApplicationRole }
  ) => Promise<void>
  fetchMemberCount: (token: string | null, applicationId: string) => Promise<MemberCount | null>
  updateMemberRole: (
    token: string | null,
    applicationId: string,
    userId: string,
    data: MemberUpdate
  ) => Promise<MemberWithUser | null>
  removeMember: (
    token: string | null,
    applicationId: string,
    userId: string
  ) => Promise<boolean>
  addMember: (member: MemberWithUser) => void
  updateMemberInList: (member: MemberWithUser) => void
  updateMemberRoleInList: (userId: string, newRole: ApplicationRole) => void
  removeMemberFromList: (userId: string) => void
  setCurrentApplicationId: (applicationId: string | null) => void
  clearError: () => void
  reset: () => void
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Parse API error response
 */
function parseApiError(status: number, data: unknown): MemberError {
  // Handle FastAPI validation errors
  if (typeof data === 'object' && data !== null) {
    const errorData = data as Record<string, unknown>

    // FastAPI HTTPException format
    if (typeof errorData.detail === 'string') {
      return { message: errorData.detail }
    }

    // FastAPI validation error format
    if (Array.isArray(errorData.detail)) {
      const firstError = errorData.detail[0]
      if (firstError && typeof firstError === 'object') {
        const field = (firstError as Record<string, unknown>).loc
        const msg = (firstError as Record<string, unknown>).msg
        return {
          message: String(msg || 'Validation error'),
          field: Array.isArray(field) ? String(field[field.length - 1]) : undefined,
        }
      }
    }
  }

  // Default error messages based on status
  switch (status) {
    case 400:
      return { message: 'Invalid request. Please check your input.' }
    case 401:
      return { message: 'Authentication required. Please log in again.' }
    case 403:
      return { message: 'Access denied.' }
    case 404:
      return { message: 'Member not found.' }
    case 409:
      return { message: 'Conflict. The member may already exist or cannot be modified.' }
    case 422:
      return { message: 'Validation error. Please check your input.' }
    case 500:
      return { message: 'Server error. Please try again later.' }
    default:
      return { message: 'An unexpected error occurred.' }
  }
}

// ============================================================================
// Initial State
// ============================================================================

const initialState = {
  members: [],
  memberCount: null,
  currentApplicationId: null,
  isLoading: false,
  isUpdating: false,
  isRemoving: false,
  error: null,
  skip: 0,
  limit: 50,
  hasMore: false,
}

// ============================================================================
// Store
// ============================================================================

/**
 * Members store using zustand
 */
export const useMembersStore = create<MembersState>((set, get) => ({
  // Initial state
  ...initialState,

  /**
   * Fetch members for an application
   */
  fetchMembers: async (token, applicationId, options = {}) => {
    const { skip = 0, role } = options

    set({ isLoading: true, error: null, currentApplicationId: applicationId })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const params = new URLSearchParams()
      params.append('skip', String(skip))
      params.append('limit', String(get().limit))
      if (role) {
        params.append('role', role)
      }

      const response = await window.electronAPI.get<MemberWithUser[]>(
        `/api/applications/${applicationId}/members?${params.toString()}`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        const error = parseApiError(response.status, response.data)
        set({ isLoading: false, error })
        return
      }

      const members = response.data || []
      set({
        members: skip === 0 ? members : [...get().members, ...members],
        skip,
        hasMore: members.length === get().limit,
        isLoading: false,
      })
    } catch (err) {
      const error: MemberError = {
        message: err instanceof Error ? err.message : 'Failed to fetch members',
      }
      set({ isLoading: false, error })
    }
  },

  /**
   * Fetch member count for an application
   */
  fetchMemberCount: async (token, applicationId) => {
    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.get<MemberCount>(
        `/api/applications/${applicationId}/members/count`,
        getAuthHeaders(token)
      )

      if (response.status === 200) {
        const count = response.data
        set({ memberCount: count })
        return count
      }

      return null
    } catch {
      return null
    }
  },

  /**
   * Update a member's role
   *
   * Permissions:
   * - Viewer: Cannot update roles
   * - Editor: Can only promote viewers to editors
   * - Owner: Can update any role
   */
  updateMemberRole: async (token, applicationId, userId, data) => {
    set({ isUpdating: true, error: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.put<MemberWithUser>(
        `/api/applications/${applicationId}/members/${userId}`,
        data,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        const error = parseApiError(response.status, response.data)
        set({ isUpdating: false, error })
        return null
      }

      const updatedMember = response.data
      // Update the member in the list
      const members = get().members.map((member) =>
        member.user_id === userId ? updatedMember : member
      )
      set({
        members,
        isUpdating: false,
      })
      return updatedMember
    } catch (err) {
      const error: MemberError = {
        message: err instanceof Error ? err.message : 'Failed to update member role',
      }
      set({ isUpdating: false, error })
      return null
    }
  },

  /**
   * Remove a member from the application
   *
   * Permissions:
   * - Any member can remove themselves
   * - Only owners can remove other members
   */
  removeMember: async (token, applicationId, userId) => {
    set({ isRemoving: true, error: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.delete<void>(
        `/api/applications/${applicationId}/members/${userId}`,
        getAuthHeaders(token)
      )

      if (response.status !== 204 && response.status !== 200) {
        const error = parseApiError(response.status, response.data)
        set({ isRemoving: false, error })
        return false
      }

      // Remove the member from the list
      const members = get().members.filter((member) => member.user_id !== userId)
      set({
        members,
        isRemoving: false,
      })
      return true
    } catch (err) {
      const error: MemberError = {
        message: err instanceof Error ? err.message : 'Failed to remove member',
      }
      set({ isRemoving: false, error })
      return false
    }
  },

  /**
   * Add a member to the list (used for WebSocket updates)
   */
  addMember: (member) => {
    const members = [...get().members, member]
    set({ members })
  },

  /**
   * Update a member in the list (used for WebSocket updates)
   */
  updateMemberInList: (member) => {
    const members = get().members.map((m) =>
      m.user_id === member.user_id ? member : m
    )
    set({ members })
  },

  /**
   * Update only a member's role in the list (used for WebSocket role updates)
   */
  updateMemberRoleInList: (userId, newRole) => {
    const members = get().members.map((m) =>
      m.user_id === userId ? { ...m, role: newRole, updated_at: new Date().toISOString() } : m
    )
    set({ members })
  },

  /**
   * Remove a member from the list (used for WebSocket updates)
   */
  removeMemberFromList: (userId) => {
    const members = get().members.filter((m) => m.user_id !== userId)
    set({ members })
  },

  /**
   * Set the current application ID
   */
  setCurrentApplicationId: (applicationId) => {
    set({ currentApplicationId: applicationId })
  },

  /**
   * Clear the current error
   */
  clearError: () => {
    set({ error: null })
  },

  /**
   * Reset the store to initial state
   */
  reset: () => {
    set(initialState)
  },
}))

// ============================================================================
// Selectors
// ============================================================================

export const selectMembers = (state: MembersState): MemberWithUser[] =>
  state.members

export const selectMemberCount = (state: MembersState): MemberCount | null =>
  state.memberCount

export const selectCurrentApplicationId = (state: MembersState): string | null =>
  state.currentApplicationId

export const selectIsLoading = (state: MembersState): boolean =>
  state.isLoading

export const selectIsUpdating = (state: MembersState): boolean =>
  state.isUpdating

export const selectIsRemoving = (state: MembersState): boolean =>
  state.isRemoving

export const selectError = (state: MembersState): MemberError | null =>
  state.error

export const selectMemberByUserId = (userId: string) => (state: MembersState): MemberWithUser | undefined =>
  state.members.find((m) => m.user_id === userId)

export const selectOwners = (state: MembersState): MemberWithUser[] =>
  state.members.filter((m) => m.role === 'owner')

export const selectEditors = (state: MembersState): MemberWithUser[] =>
  state.members.filter((m) => m.role === 'editor')

export const selectViewers = (state: MembersState): MemberWithUser[] =>
  state.members.filter((m) => m.role === 'viewer')

export default useMembersStore
