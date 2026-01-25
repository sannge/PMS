/**
 * TanStack Query Hooks for Comments
 *
 * Provides React Query hooks for comment CRUD operations with:
 * - Cursor-based pagination
 * - Optimistic updates with rollback
 * - TipTap JSON content support
 * - @mentions extraction
 *
 * @see https://tanstack.com/query/latest
 */

import {
  useQuery,
  useMutation,
  useQueryClient,
  useInfiniteQuery,
  UseQueryResult,
  UseMutationResult,
  UseInfiniteQueryResult,
} from '@tanstack/react-query'
import { useAuthStore, User } from '@/stores/auth-store'
import { queryKeys } from '@/lib/query-client'

// ============================================================================
// Types
// ============================================================================

export interface Mention {
  id: string
  user_id: string
  user_name: string | null
  created_at: string
}

export interface CommentAttachment {
  id: string
  file_name: string
  file_type: string | null
  file_size: number | null
  created_at: string
}

export interface Comment {
  id: string
  task_id: string
  author_id: string
  author_name: string | null
  author_avatar_url: string | null
  body_json: Record<string, unknown> | null
  body_text: string | null
  is_deleted: boolean
  created_at: string
  updated_at: string | null
  mentions: Mention[]
  attachments: CommentAttachment[]
  // For optimistic updates
  isOptimistic?: boolean
}

export interface CommentCreate {
  body_json?: Record<string, unknown>
  body_text?: string
  attachment_ids?: string[]
}

export interface CommentUpdate {
  body_json?: Record<string, unknown>
  body_text?: string
}

export interface CommentListResponse {
  items: Comment[]
  next_cursor: string | null
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
      return { message: 'Invalid request. Please check your input.' }
    case 401:
      return { message: 'Authentication required. Please log in again.' }
    case 403:
      return { message: 'Access denied.' }
    case 404:
      return { message: 'Comment not found.' }
    case 422:
      return { message: 'Validation error. Please check your input.' }
    case 500:
      return { message: 'Server error. Please try again later.' }
    default:
      return { message: 'An unexpected error occurred.' }
  }
}

// ============================================================================
// Comment Queries
// ============================================================================

/**
 * Fetch comments for a task with cursor-based pagination.
 * Uses useInfiniteQuery for load-more functionality.
 */
export function useComments(
  taskId: string | undefined
): UseInfiniteQueryResult<CommentListResponse, Error> {
  const token = useAuthStore((s) => s.token)

  return useInfiniteQuery({
    queryKey: queryKeys.comments(taskId || ''),
    queryFn: async ({ pageParam }) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      let url = `/api/tasks/${taskId}/comments`
      if (pageParam) {
        url += `?cursor=${encodeURIComponent(pageParam)}`
      }

      const response = await window.electronAPI.get<CommentListResponse>(
        url,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data || { items: [], next_cursor: null }
    },
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: !!token && !!taskId,
    staleTime: 30 * 1000, // 30 seconds - comments change frequently
    gcTime: 24 * 60 * 60 * 1000,
  })
}

/**
 * Helper to get flat list of comments from infinite query.
 */
export function useCommentsList(taskId: string | undefined): {
  comments: Comment[]
  isLoading: boolean
  isFetchingNextPage: boolean
  hasNextPage: boolean
  fetchNextPage: () => void
  error: Error | null
} {
  const query = useComments(taskId)

  const comments = query.data?.pages.flatMap((page) => page.items) || []

  return {
    comments,
    isLoading: query.isLoading,
    isFetchingNextPage: query.isFetchingNextPage,
    hasNextPage: query.hasNextPage ?? false,
    fetchNextPage: () => query.fetchNextPage(),
    error: query.error,
  }
}

/**
 * Fetch a single comment by ID (rarely needed, but available).
 */
export function useComment(id: string | undefined): UseQueryResult<Comment, Error> {
  const token = useAuthStore((s) => s.token)

  return useQuery({
    queryKey: queryKeys.comment(id || ''),
    queryFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.get<Comment>(
        `/api/comments/${id}`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
    enabled: !!token && !!id,
    staleTime: 30 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
  })
}

// ============================================================================
// Comment Mutations
// ============================================================================

/**
 * Create a new comment with optimistic update.
 */
export function useCreateComment(
  taskId: string
): UseMutationResult<Comment, Error, CommentCreate, { previousData?: CommentListResponse[] }> {
  const token = useAuthStore((s) => s.token)
  const user = useAuthStore((s) => s.user)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: CommentCreate) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.post<Comment>(
        `/api/tasks/${taskId}/comments`,
        data,
        getAuthHeaders(token)
      )

      if (response.status !== 201) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
    // Optimistic update
    onMutate: async (newData) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: queryKeys.comments(taskId) })

      // Snapshot previous value
      const previousData = queryClient.getQueryData<{ pages: CommentListResponse[] }>(
        queryKeys.comments(taskId)
      )

      // Create optimistic comment
      const optimisticComment: Comment = {
        id: `temp-${Date.now()}`,
        task_id: taskId,
        author_id: user?.id || '',
        author_name: user?.display_name || user?.email || 'You',
        author_avatar_url: user?.avatar_url || null,
        body_json: newData.body_json || null,
        body_text: newData.body_text || null,
        is_deleted: false,
        created_at: new Date().toISOString(),
        updated_at: null,
        mentions: [],
        attachments: [],
        isOptimistic: true,
      }

      // Add to first page
      queryClient.setQueryData<{ pages: CommentListResponse[] }>(
        queryKeys.comments(taskId),
        (old) => {
          if (!old) return { pages: [{ items: [optimisticComment], next_cursor: null }] }
          return {
            ...old,
            pages: [
              { ...old.pages[0], items: [optimisticComment, ...old.pages[0].items] },
              ...old.pages.slice(1),
            ],
          }
        }
      )

      return { previousData: previousData?.pages }
    },
    onError: (_err, _vars, context) => {
      // Rollback on error
      if (context?.previousData) {
        queryClient.setQueryData(queryKeys.comments(taskId), { pages: context.previousData })
      }
    },
    onSettled: () => {
      // Refetch to ensure consistency
      queryClient.invalidateQueries({ queryKey: queryKeys.comments(taskId) })
    },
  })
}

/**
 * Update a comment with optimistic update.
 */
export function useUpdateComment(
  commentId: string,
  taskId: string
): UseMutationResult<Comment, Error, CommentUpdate, { previousData?: { pages: CommentListResponse[] } }> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: CommentUpdate) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.put<Comment>(
        `/api/comments/${commentId}`,
        data,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
    // Optimistic update
    onMutate: async (newData) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.comments(taskId) })

      const previousData = queryClient.getQueryData<{ pages: CommentListResponse[] }>(
        queryKeys.comments(taskId)
      )

      // Update in pages
      queryClient.setQueryData<{ pages: CommentListResponse[] }>(
        queryKeys.comments(taskId),
        (old) => {
          if (!old) return old
          return {
            ...old,
            pages: old.pages.map((page) => ({
              ...page,
              items: page.items.map((c) =>
                c.id === commentId
                  ? {
                      ...c,
                      body_json: newData.body_json ?? c.body_json,
                      body_text: newData.body_text ?? c.body_text,
                      updated_at: new Date().toISOString(),
                    }
                  : c
              ),
            })),
          }
        }
      )

      return { previousData }
    },
    onError: (_err, _vars, context) => {
      if (context?.previousData) {
        queryClient.setQueryData(queryKeys.comments(taskId), context.previousData)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.comments(taskId) })
    },
  })
}

/**
 * Delete a comment with optimistic update.
 */
export function useDeleteComment(
  commentId: string,
  taskId: string
): UseMutationResult<void, Error, void, { previousData?: { pages: CommentListResponse[] } }> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.delete<void>(
        `/api/comments/${commentId}`,
        getAuthHeaders(token)
      )

      if (response.status !== 204) {
        throw new Error(parseApiError(response.status, response.data).message)
      }
    },
    // Optimistic delete
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: queryKeys.comments(taskId) })

      const previousData = queryClient.getQueryData<{ pages: CommentListResponse[] }>(
        queryKeys.comments(taskId)
      )

      // Remove from pages
      queryClient.setQueryData<{ pages: CommentListResponse[] }>(
        queryKeys.comments(taskId),
        (old) => {
          if (!old) return old
          return {
            ...old,
            pages: old.pages.map((page) => ({
              ...page,
              items: page.items.filter((c) => c.id !== commentId),
            })),
          }
        }
      )

      return { previousData }
    },
    onError: (_err, _vars, context) => {
      if (context?.previousData) {
        queryClient.setQueryData(queryKeys.comments(taskId), context.previousData)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.comments(taskId) })
    },
  })
}
