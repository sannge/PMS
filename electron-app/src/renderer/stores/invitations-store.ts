/**
 * Invitations Store
 *
 * Zustand store for managing invitation state in the renderer process.
 * Handles invitation operations: fetch, accept, reject, send, cancel.
 *
 * Features:
 * - Received and sent invitation lists
 * - Accept/reject invitation operations
 * - Send new invitations
 * - Loading and error states
 * - Pending invitation count
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
 * Invitation status enumeration
 */
export type InvitationStatus = 'pending' | 'accepted' | 'rejected' | 'cancelled'

/**
 * Minimal user information for invitation display
 */
export interface UserSummary {
  id: string
  email: string
  full_name: string | null
}

/**
 * Minimal application information for invitation display
 */
export interface ApplicationSummary {
  id: string
  name: string
}

/**
 * Invitation data from the API
 */
export interface Invitation {
  id: string
  application_id: string
  inviter_id: string
  invitee_id: string
  role: ApplicationRole
  status: InvitationStatus
  created_at: string
  responded_at: string | null
}

/**
 * Invitation with related entity details
 */
export interface InvitationWithDetails extends Invitation {
  inviter: UserSummary | null
  invitee: UserSummary | null
  application: ApplicationSummary | null
}

/**
 * Data for creating an invitation
 */
export interface InvitationCreate {
  invitee_id: string
  role: ApplicationRole
}

/**
 * Error with details
 */
export interface InvitationError {
  message: string
  code?: string
  field?: string
}

/**
 * Paginated invitation list response
 */
export interface InvitationListResponse {
  items: InvitationWithDetails[]
  total: number
  skip: number
  limit: number
}

/**
 * Invitations store state
 */
export interface InvitationsState {
  // State
  receivedInvitations: InvitationWithDetails[]
  sentInvitations: InvitationWithDetails[]
  pendingCount: number
  isLoading: boolean
  isSending: boolean
  isAccepting: boolean
  isRejecting: boolean
  isCancelling: boolean
  error: InvitationError | null

  // Pagination for received invitations
  skip: number
  limit: number
  total: number
  hasMore: boolean

  // Actions
  fetchReceivedInvitations: (token: string | null, options?: { skip?: number; limit?: number; status?: InvitationStatus }) => Promise<void>
  fetchSentInvitations: (token: string | null, applicationId?: string) => Promise<void>
  fetchPendingCount: (token: string | null) => Promise<number>
  sendInvitation: (token: string | null, applicationId: string, data: InvitationCreate) => Promise<InvitationWithDetails | null>
  acceptInvitation: (token: string | null, invitationId: string) => Promise<boolean>
  rejectInvitation: (token: string | null, invitationId: string) => Promise<boolean>
  cancelInvitation: (token: string | null, invitationId: string) => Promise<boolean>
  addReceivedInvitation: (invitation: InvitationWithDetails) => void
  removeReceivedInvitation: (invitationId: string) => void
  clearError: () => void
  reset: () => void
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Parse API error response
 */
function parseApiError(status: number, data: unknown): InvitationError {
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
      return { message: 'Invitation not found.' }
    case 409:
      return { message: 'User already has a pending invitation or is already a member.' }
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
  receivedInvitations: [],
  sentInvitations: [],
  pendingCount: 0,
  isLoading: false,
  isSending: false,
  isAccepting: false,
  isRejecting: false,
  isCancelling: false,
  error: null,
  skip: 0,
  limit: 20,
  total: 0,
  hasMore: false,
}

// ============================================================================
// Store
// ============================================================================

/**
 * Invitations store using zustand
 */
export const useInvitationsStore = create<InvitationsState>((set, get) => ({
  // Initial state
  ...initialState,

  /**
   * Fetch received invitations (invitations where current user is the invitee)
   */
  fetchReceivedInvitations: async (token, options = {}) => {
    const { skip = 0, limit, status } = options
    const effectiveLimit = limit ?? get().limit

    set({ isLoading: true, error: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const params = new URLSearchParams()
      params.append('skip', String(skip))
      params.append('limit', String(effectiveLimit))
      if (status) {
        params.append('status', status)
      }

      const response = await window.electronAPI.get<InvitationWithDetails[]>(
        `/api/invitations?${params.toString()}`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        const error = parseApiError(response.status, response.data)
        set({ isLoading: false, error })
        return
      }

      const invitations = response.data || []
      set({
        receivedInvitations: skip === 0 ? invitations : [...get().receivedInvitations, ...invitations],
        skip,
        hasMore: invitations.length === effectiveLimit,
        isLoading: false,
      })
    } catch (err) {
      const error: InvitationError = {
        message: err instanceof Error ? err.message : 'Failed to fetch invitations',
      }
      set({ isLoading: false, error })
    }
  },

  /**
   * Fetch sent invitations (invitations where current user is the inviter)
   */
  fetchSentInvitations: async (token, applicationId) => {
    set({ isLoading: true, error: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      let url = '/api/invitations/sent'
      if (applicationId) {
        url = `/api/invitations/applications/${applicationId}`
      }

      const response = await window.electronAPI.get<InvitationWithDetails[]>(
        url,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        const error = parseApiError(response.status, response.data)
        set({ isLoading: false, error })
        return
      }

      const invitations = response.data || []
      set({
        sentInvitations: invitations,
        isLoading: false,
      })
    } catch (err) {
      const error: InvitationError = {
        message: err instanceof Error ? err.message : 'Failed to fetch sent invitations',
      }
      set({ isLoading: false, error })
    }
  },

  /**
   * Fetch pending invitation count
   */
  fetchPendingCount: async (token) => {
    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.get<{ count: number }>(
        '/api/invitations/count',
        getAuthHeaders(token)
      )

      if (response.status === 200) {
        const count = response.data?.count || 0
        set({ pendingCount: count })
        return count
      }

      return 0
    } catch {
      return 0
    }
  },

  /**
   * Send a new invitation
   */
  sendInvitation: async (token, applicationId, data) => {
    set({ isSending: true, error: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.post<InvitationWithDetails>(
        `/api/invitations/applications/${applicationId}`,
        data,
        getAuthHeaders(token)
      )

      if (response.status !== 201) {
        const error = parseApiError(response.status, response.data)
        set({ isSending: false, error })
        return null
      }

      const invitation = response.data
      // Add the new invitation to the sent list
      set({
        sentInvitations: [invitation, ...get().sentInvitations],
        isSending: false,
      })
      return invitation
    } catch (err) {
      const error: InvitationError = {
        message: err instanceof Error ? err.message : 'Failed to send invitation',
      }
      set({ isSending: false, error })
      return null
    }
  },

  /**
   * Accept an invitation
   */
  acceptInvitation: async (token, invitationId) => {
    set({ isAccepting: true, error: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.post<InvitationWithDetails>(
        `/api/invitations/${invitationId}/accept`,
        {},
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        const error = parseApiError(response.status, response.data)
        set({ isAccepting: false, error })
        return false
      }

      // Remove the accepted invitation from the received list
      const receivedInvitations = get().receivedInvitations.filter(
        (inv) => inv.id !== invitationId
      )
      set({
        receivedInvitations,
        pendingCount: Math.max(0, get().pendingCount - 1),
        isAccepting: false,
      })
      return true
    } catch (err) {
      const error: InvitationError = {
        message: err instanceof Error ? err.message : 'Failed to accept invitation',
      }
      set({ isAccepting: false, error })
      return false
    }
  },

  /**
   * Reject an invitation
   */
  rejectInvitation: async (token, invitationId) => {
    set({ isRejecting: true, error: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.post<InvitationWithDetails>(
        `/api/invitations/${invitationId}/reject`,
        {},
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        const error = parseApiError(response.status, response.data)
        set({ isRejecting: false, error })
        return false
      }

      // Remove the rejected invitation from the received list
      const receivedInvitations = get().receivedInvitations.filter(
        (inv) => inv.id !== invitationId
      )
      set({
        receivedInvitations,
        pendingCount: Math.max(0, get().pendingCount - 1),
        isRejecting: false,
      })
      return true
    } catch (err) {
      const error: InvitationError = {
        message: err instanceof Error ? err.message : 'Failed to reject invitation',
      }
      set({ isRejecting: false, error })
      return false
    }
  },

  /**
   * Cancel a sent invitation
   */
  cancelInvitation: async (token, invitationId) => {
    set({ isCancelling: true, error: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.delete<void>(
        `/api/invitations/${invitationId}`,
        getAuthHeaders(token)
      )

      if (response.status !== 204 && response.status !== 200) {
        const error = parseApiError(response.status, response.data)
        set({ isCancelling: false, error })
        return false
      }

      // Remove the cancelled invitation from the sent list
      const sentInvitations = get().sentInvitations.filter(
        (inv) => inv.id !== invitationId
      )
      set({
        sentInvitations,
        isCancelling: false,
      })
      return true
    } catch (err) {
      const error: InvitationError = {
        message: err instanceof Error ? err.message : 'Failed to cancel invitation',
      }
      set({ isCancelling: false, error })
      return false
    }
  },

  /**
   * Add a received invitation (used for WebSocket updates)
   */
  addReceivedInvitation: (invitation) => {
    const receivedInvitations = [invitation, ...get().receivedInvitations]
    set({
      receivedInvitations,
      pendingCount: get().pendingCount + 1,
    })
  },

  /**
   * Remove a received invitation (used for WebSocket updates)
   */
  removeReceivedInvitation: (invitationId) => {
    const receivedInvitations = get().receivedInvitations.filter(
      (inv) => inv.id !== invitationId
    )
    set({
      receivedInvitations,
      pendingCount: Math.max(0, get().pendingCount - 1),
    })
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

export const selectReceivedInvitations = (state: InvitationsState): InvitationWithDetails[] =>
  state.receivedInvitations

export const selectSentInvitations = (state: InvitationsState): InvitationWithDetails[] =>
  state.sentInvitations

export const selectPendingCount = (state: InvitationsState): number =>
  state.pendingCount

export const selectIsLoading = (state: InvitationsState): boolean =>
  state.isLoading

export const selectIsSending = (state: InvitationsState): boolean =>
  state.isSending

export const selectIsAccepting = (state: InvitationsState): boolean =>
  state.isAccepting

export const selectIsRejecting = (state: InvitationsState): boolean =>
  state.isRejecting

export const selectError = (state: InvitationsState): InvitationError | null =>
  state.error

export default useInvitationsStore
