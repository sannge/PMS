/**
 * TanStack Query Hooks for Members
 *
 * Provides React Query hooks for application and project member management.
 * Implements optimistic updates for role changes and member removal.
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
import { useAuthToken } from '@/contexts/auth-context'
import { authGet, authPost, authPut, authPatch, authDelete } from '@/lib/api-client'
import { queryKeys } from '@/lib/query-client'

// ============================================================================
// Types
// ============================================================================

export type ApplicationRole = 'owner' | 'editor' | 'viewer'
export type ProjectRole = 'admin' | 'member'

export interface ApplicationMember {
  id: string
  user_id: string
  application_id: string
  role: ApplicationRole
  user_email: string
  user_display_name: string | null
  user_avatar_url: string | null
  created_at: string
  updated_at: string | null
}

export interface ProjectMember {
  id: string
  user_id: string
  project_id: string
  role: ProjectRole
  user_email: string
  user_display_name: string | null
  user_avatar_url: string | null
  created_at: string
  updated_at: string | null
}

export interface AddMemberPayload {
  email: string
  role: ApplicationRole | ProjectRole
}

export interface AddProjectMemberPayload {
  user_id: string
  role: ProjectRole
}

export interface UpdateRolePayload {
  userId: string
  newRole: ApplicationRole | ProjectRole
}

export interface ApiError {
  message: string
  code?: string
  field?: string
}

// ============================================================================
// Helper Functions
// ============================================================================

function parseApiError(status: number, data: unknown): ApiError {
  if (typeof data === 'object' && data !== null) {
    const errorData = data as Record<string, unknown>
    if (typeof errorData.detail === 'string') {
      return { message: errorData.detail }
    }
    if (typeof errorData.detail === 'object' && errorData.detail !== null) {
      const detail = errorData.detail as Record<string, unknown>
      if (typeof detail.message === 'string') {
        return { message: detail.message }
      }
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
      return { message: 'Invalid request. Please check your input.' }
    case 401:
      return { message: 'Authentication required. Please log in again.' }
    case 403:
      return { message: 'Access denied. You do not have permission.' }
    case 404:
      return { message: 'Member not found.' }
    case 409:
      return { message: 'Conflict. Please try again.' }
    case 422:
      return { message: 'Validation error. Please check your input.' }
    case 500:
      return { message: 'Server error. Please try again later.' }
    default:
      return { message: 'An unexpected error occurred.' }
  }
}

// ============================================================================
// Application Member Queries
// ============================================================================

/**
 * Fetch application members.
 */
export function useAppMembers(
  applicationId: string | undefined
): UseQueryResult<ApplicationMember[], Error> {
  const token = useAuthToken()

  return useQuery({
    queryKey: queryKeys.appMembers(applicationId || ''),
    queryFn: async () => {
      const response = await authGet<ApplicationMember[]>(
        `/api/applications/${applicationId}/members`
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data || []
    },
    enabled: !!token && !!applicationId,
    staleTime: 30 * 1000, // 30 seconds - refetch when stale for add member dialogs
    gcTime: 24 * 60 * 60 * 1000,
    refetchOnMount: true, // Refetch only if stale; WS MEMBER_ADDED/REMOVED events invalidate cache
    refetchOnWindowFocus: false, // WS real-time invalidation handles freshness
  })
}

/**
 * Add a member to an application via invitation.
 */
export function useInviteAppMember(
  applicationId: string
): UseMutationResult<void, Error, AddMemberPayload> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: AddMemberPayload) => {
      const response = await authPost<void>(
        `/api/applications/${applicationId}/invite`,
        { email: data.email, role: data.role }
      )

      if (response.status !== 201 && response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }
    },
    onSuccess: () => {
      // Invalidate members to refetch
      queryClient.invalidateQueries({ queryKey: queryKeys.appMembers(applicationId) })
    },
  })
}

/**
 * Update an application member's role.
 */
export function useUpdateAppMemberRole(
  applicationId: string
): UseMutationResult<
  ApplicationMember,
  Error,
  UpdateRolePayload,
  { previous?: ApplicationMember[] }
> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ userId, newRole }: UpdateRolePayload) => {
      const response = await authPut<ApplicationMember>(
        `/api/applications/${applicationId}/members/${userId}`,
        { role: newRole }
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
    // Optimistic update
    onMutate: async ({ userId, newRole }) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.appMembers(applicationId) })

      const previous = queryClient.getQueryData<ApplicationMember[]>(
        queryKeys.appMembers(applicationId)
      )

      queryClient.setQueryData<ApplicationMember[]>(
        queryKeys.appMembers(applicationId),
        (old) =>
          old?.map((m) =>
            m.user_id === userId ? { ...m, role: newRole as ApplicationRole } : m
          )
      )

      return { previous }
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.appMembers(applicationId), context.previous)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.appMembers(applicationId) })
    },
  })
}

/**
 * Remove a member from an application.
 */
export function useRemoveAppMember(
  applicationId: string
): UseMutationResult<void, Error, string> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (userId: string) => {
      const response = await authDelete<void>(
        `/api/applications/${applicationId}/members/${userId}`
      )

      if (response.status !== 204 && response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.appMembers(applicationId) })
    },
  })
}

// ============================================================================
// Project Member Queries
// ============================================================================

/**
 * Fetch project members.
 */
export function useProjectMembers(
  projectId: string | undefined
): UseQueryResult<ProjectMember[], Error> {
  const token = useAuthToken()

  return useQuery({
    queryKey: queryKeys.projectMembers(projectId || ''),
    queryFn: async () => {
      const response = await authGet<ProjectMember[]>(
        `/api/projects/${projectId}/members`
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data || []
    },
    enabled: !!token && !!projectId,
    staleTime: 30 * 1000, // 30 seconds - members may change frequently
    gcTime: 24 * 60 * 60 * 1000,
    refetchOnWindowFocus: false, // WS real-time invalidation handles freshness
  })
}

/**
 * Add a member to a project.
 */
export function useAddProjectMember(
  projectId: string
): UseMutationResult<ProjectMember, Error, AddProjectMemberPayload> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: AddProjectMemberPayload) => {
      const response = await authPost<ProjectMember>(
        `/api/projects/${projectId}/members`,
        { user_id: data.user_id, role: data.role }
      )

      if (response.status !== 201) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
    onSuccess: (newMember) => {
      // Add to members list
      queryClient.setQueryData<ProjectMember[]>(
        queryKeys.projectMembers(projectId),
        (old) => (old ? [...old, newMember] : [newMember])
      )
    },
  })
}

/**
 * Update a project member's role.
 */
export function useUpdateProjectMemberRole(
  projectId: string
): UseMutationResult<ProjectMember, Error, UpdateRolePayload, { previous?: ProjectMember[] }> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ userId, newRole }: UpdateRolePayload) => {
      const response = await authPatch<ProjectMember>(
        `/api/projects/${projectId}/members/${userId}/role`,
        { role: newRole }
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
    // Optimistic update
    onMutate: async ({ userId, newRole }) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.projectMembers(projectId) })

      const previous = queryClient.getQueryData<ProjectMember[]>(
        queryKeys.projectMembers(projectId)
      )

      queryClient.setQueryData<ProjectMember[]>(
        queryKeys.projectMembers(projectId),
        (old) =>
          old?.map((m) => (m.user_id === userId ? { ...m, role: newRole as ProjectRole } : m))
      )

      return { previous }
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.projectMembers(projectId), context.previous)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.projectMembers(projectId) })
      // Also invalidate tasks since permissions may have changed
      queryClient.invalidateQueries({ queryKey: queryKeys.tasks(projectId) })
    },
  })
}

/**
 * Remove a member from a project.
 */
export function useRemoveProjectMember(
  projectId: string
): UseMutationResult<void, Error, string> {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (userId: string) => {
      const response = await authDelete<void>(
        `/api/projects/${projectId}/members/${userId}`
      )

      if (response.status !== 204 && response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.projectMembers(projectId) })
    },
  })
}
