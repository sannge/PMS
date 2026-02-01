/**
 * TanStack Query Hooks for Invitations
 *
 * Provides React Query hooks for invitation management with:
 * - Received and sent invitation lists
 * - Accept/reject invitation operations
 * - Send and cancel invitations
 * - Pending count tracking
 * - Optimistic updates with rollback
 * - IndexedDB persistence for offline access
 *
 * @see https://tanstack.com/query/latest
 */

import {
  useQuery,
  useMutation,
  useQueryClient,
  UseQueryResult,
  UseMutationResult,
} from '@tanstack/react-query'
import { useAuthStore } from '@/contexts/auth-context'
import { queryKeys } from '@/lib/query-client'

// ============================================================================
// Types
// ============================================================================

export type ApplicationRole = 'owner' | 'editor' | 'viewer'
export type InvitationStatus = 'pending' | 'accepted' | 'rejected' | 'cancelled'

export interface UserSummary {
  id: string
  email: string
  display_name: string | null
}

export interface ApplicationSummary {
  id: string
  name: string
}

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

export interface InvitationWithDetails extends Invitation {
  inviter: UserSummary | null
  invitee: UserSummary | null
  application: ApplicationSummary | null
}

export interface InvitationCreate {
  invitee_id: string
  role: ApplicationRole
}

export interface ApiError {
  message: string
  code?: string
  field?: string
}

// ============================================================================
// Helper Functions
// ============================================================================

function getAuthHeaders(token: string | null): Record<string, string> {
  if (!token) return {}
  return { Authorization: `Bearer ${token}` }
}

function parseApiError(status: number, data: unknown): ApiError {
  if (typeof data === 'object' && data !== null) {
    const errorData = data as Record<string, unknown>
    if (typeof errorData.detail === 'string') {
      return { message: errorData.detail }
    }
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

  switch (status) {
    case 400:
      return { message: 'Invalid request.' }
    case 401:
      return { message: 'Authentication required.' }
    case 403:
      return { message: 'Access denied.' }
    case 404:
      return { message: 'Invitation not found.' }
    case 409:
      return { message: 'User already has a pending invitation or is already a member.' }
    case 500:
      return { message: 'Server error.' }
    default:
      return { message: 'An unexpected error occurred.' }
  }
}

// ============================================================================
// Invitation Queries
// ============================================================================

/**
 * Fetch received invitations (where current user is invitee).
 */
export function useReceivedInvitations(
  status?: InvitationStatus
): UseQueryResult<InvitationWithDetails[], Error> {
  const token = useAuthStore((s) => s.token)

  return useQuery({
    queryKey: queryKeys.receivedInvitations(status),
    queryFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const params = new URLSearchParams()
      if (status) {
        params.append('status', status)
      }

      const url = `/api/invitations${params.toString() ? `?${params.toString()}` : ''}`
      const response = await window.electronAPI.get<InvitationWithDetails[]>(
        url,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data || []
    },
    enabled: !!token,
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 24 * 60 * 60 * 1000,
  })
}

/**
 * Fetch sent invitations (where current user is inviter).
 */
export function useSentInvitations(
  applicationId?: string
): UseQueryResult<InvitationWithDetails[], Error> {
  const token = useAuthStore((s) => s.token)

  return useQuery({
    queryKey: queryKeys.sentInvitations(applicationId),
    queryFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const url = applicationId
        ? `/api/invitations/applications/${applicationId}`
        : '/api/invitations/sent'

      const response = await window.electronAPI.get<InvitationWithDetails[]>(
        url,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data || []
    },
    enabled: !!token,
    staleTime: 5 * 60 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
  })
}

/**
 * Fetch pending invitation count.
 */
export function usePendingInvitationCount(): UseQueryResult<number, Error> {
  const token = useAuthStore((s) => s.token)

  return useQuery({
    queryKey: queryKeys.pendingInvitationCount,
    queryFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.get<{ count: number }>(
        '/api/invitations/count',
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        return 0
      }

      return response.data?.count || 0
    },
    enabled: !!token,
    staleTime: 60 * 1000, // 1 minute
    refetchInterval: 60 * 1000, // Poll every minute
  })
}

// ============================================================================
// Invitation Mutations
// ============================================================================

/**
 * Send a new invitation.
 */
export function useSendInvitation(
  applicationId: string
): UseMutationResult<InvitationWithDetails, Error, InvitationCreate, { previous?: InvitationWithDetails[] }> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: InvitationCreate) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.post<InvitationWithDetails>(
        `/api/invitations/applications/${applicationId}`,
        data,
        getAuthHeaders(token)
      )

      if (response.status !== 201) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
    onSuccess: (newInvitation) => {
      // Add to sent invitations cache
      queryClient.setQueryData<InvitationWithDetails[]>(
        queryKeys.sentInvitations(applicationId),
        (old) => [newInvitation, ...(old || [])]
      )
      queryClient.invalidateQueries({ queryKey: queryKeys.sentInvitations() })
    },
  })
}

/**
 * Accept an invitation.
 */
export function useAcceptInvitation(): UseMutationResult<
  InvitationWithDetails,
  Error,
  string,
  { previous?: InvitationWithDetails[]; previousCount?: number }
> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (invitationId: string) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.post<InvitationWithDetails>(
        `/api/invitations/${invitationId}/accept`,
        {},
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
    onMutate: async (invitationId) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.receivedInvitations() })
      await queryClient.cancelQueries({ queryKey: queryKeys.pendingInvitationCount })

      const previous = queryClient.getQueryData<InvitationWithDetails[]>(
        queryKeys.receivedInvitations()
      )
      const previousCount = queryClient.getQueryData<number>(queryKeys.pendingInvitationCount)

      // Optimistic remove from received
      queryClient.setQueryData<InvitationWithDetails[]>(
        queryKeys.receivedInvitations(),
        (old) => old?.filter((inv) => inv.id !== invitationId)
      )

      // Decrement count
      queryClient.setQueryData<number>(queryKeys.pendingInvitationCount, (old) =>
        Math.max(0, (old || 0) - 1)
      )

      return { previous, previousCount }
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.receivedInvitations(), context.previous)
      }
      if (context?.previousCount !== undefined) {
        queryClient.setQueryData(queryKeys.pendingInvitationCount, context.previousCount)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.receivedInvitations() })
      queryClient.invalidateQueries({ queryKey: queryKeys.pendingInvitationCount })
      // Also refresh applications since user may have gained access
      queryClient.invalidateQueries({ queryKey: queryKeys.applications })
    },
  })
}

/**
 * Reject an invitation.
 */
export function useRejectInvitation(): UseMutationResult<
  InvitationWithDetails,
  Error,
  string,
  { previous?: InvitationWithDetails[]; previousCount?: number }
> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (invitationId: string) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.post<InvitationWithDetails>(
        `/api/invitations/${invitationId}/reject`,
        {},
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
    onMutate: async (invitationId) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.receivedInvitations() })
      await queryClient.cancelQueries({ queryKey: queryKeys.pendingInvitationCount })

      const previous = queryClient.getQueryData<InvitationWithDetails[]>(
        queryKeys.receivedInvitations()
      )
      const previousCount = queryClient.getQueryData<number>(queryKeys.pendingInvitationCount)

      // Optimistic remove from received
      queryClient.setQueryData<InvitationWithDetails[]>(
        queryKeys.receivedInvitations(),
        (old) => old?.filter((inv) => inv.id !== invitationId)
      )

      // Decrement count
      queryClient.setQueryData<number>(queryKeys.pendingInvitationCount, (old) =>
        Math.max(0, (old || 0) - 1)
      )

      return { previous, previousCount }
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.receivedInvitations(), context.previous)
      }
      if (context?.previousCount !== undefined) {
        queryClient.setQueryData(queryKeys.pendingInvitationCount, context.previousCount)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.receivedInvitations() })
      queryClient.invalidateQueries({ queryKey: queryKeys.pendingInvitationCount })
    },
  })
}

/**
 * Cancel a sent invitation.
 */
export function useCancelInvitation(
  applicationId?: string
): UseMutationResult<void, Error, string, { previous?: InvitationWithDetails[] }> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (invitationId: string) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.delete<void>(
        `/api/invitations/${invitationId}`,
        getAuthHeaders(token)
      )

      if (response.status !== 204 && response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }
    },
    onMutate: async (invitationId) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.sentInvitations(applicationId) })

      const previous = queryClient.getQueryData<InvitationWithDetails[]>(
        queryKeys.sentInvitations(applicationId)
      )

      // Optimistic remove from sent
      queryClient.setQueryData<InvitationWithDetails[]>(
        queryKeys.sentInvitations(applicationId),
        (old) => old?.filter((inv) => inv.id !== invitationId)
      )

      return { previous }
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.sentInvitations(applicationId), context.previous)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.sentInvitations() })
    },
  })
}
