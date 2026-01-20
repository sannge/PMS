/**
 * Comments Store
 *
 * Zustand store for managing task comments with @mentions support.
 * Handles CRUD operations for comments with cursor-based pagination.
 *
 * Features:
 * - Comment list with cursor-based pagination
 * - Create, read, update, delete operations
 * - TipTap JSON content support
 * - @mentions extraction and display
 * - Optimistic updates with rollback
 * - Loading and error states
 */

import { create } from 'zustand'
import { getAuthHeaders } from './auth-store'

// ============================================================================
// Types
// ============================================================================

/**
 * Mention data embedded in a comment
 */
export interface Mention {
  id: string
  user_id: string
  user_name: string | null
  created_at: string
}

/**
 * Comment data from the API
 */
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
}

/**
 * Data for creating a comment
 */
export interface CommentCreate {
  body_json?: Record<string, unknown>
  body_text?: string
}

/**
 * Data for updating a comment
 */
export interface CommentUpdate {
  body_json?: Record<string, unknown>
  body_text?: string
}

/**
 * API response for comment list
 */
export interface CommentListResponse {
  items: Comment[]
  next_cursor: string | null
}

/**
 * Error with details
 */
export interface CommentError {
  message: string
  code?: string
  field?: string
}

/**
 * Comments store state
 */
export interface CommentsState {
  // State
  comments: Comment[]
  currentTaskId: string | null
  nextCursor: string | null
  hasMore: boolean
  isLoading: boolean
  isLoadingMore: boolean
  isCreating: boolean
  isUpdating: boolean
  isDeleting: boolean
  error: CommentError | null

  // Actions
  fetchComments: (token: string | null, taskId: string, reset?: boolean) => Promise<void>
  loadMore: (token: string | null) => Promise<void>
  createComment: (token: string | null, taskId: string, data: CommentCreate) => Promise<Comment | null>
  updateComment: (token: string | null, commentId: string, data: CommentUpdate) => Promise<Comment | null>
  deleteComment: (token: string | null, commentId: string) => Promise<boolean>

  // Real-time updates
  handleCommentAdded: (comment: Comment) => void
  handleCommentUpdated: (commentId: string, comment: Comment) => void
  handleCommentDeleted: (commentId: string) => void

  // Utilities
  setCurrentTask: (taskId: string | null) => void
  clearError: () => void
  reset: () => void
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Parse API error response
 */
function parseApiError(status: number, data: unknown): CommentError {
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
// Initial State
// ============================================================================

const initialState = {
  comments: [],
  currentTaskId: null,
  nextCursor: null,
  hasMore: false,
  isLoading: false,
  isLoadingMore: false,
  isCreating: false,
  isUpdating: false,
  isDeleting: false,
  error: null,
}

// ============================================================================
// Store
// ============================================================================

export const useCommentsStore = create<CommentsState>((set, get) => ({
  ...initialState,

  /**
   * Fetch comments for a task with cursor-based pagination
   */
  fetchComments: async (token, taskId, reset = true) => {
    if (reset) {
      set({ isLoading: true, error: null, currentTaskId: taskId, comments: [], nextCursor: null })
    } else {
      set({ isLoading: true, error: null, currentTaskId: taskId })
    }

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.get<CommentListResponse>(
        `/api/tasks/${taskId}/comments`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        const error = parseApiError(response.status, response.data)
        set({ isLoading: false, error })
        return
      }

      const data = response.data
      set({
        comments: data?.items || [],
        nextCursor: data?.next_cursor || null,
        hasMore: !!data?.next_cursor,
        isLoading: false,
      })
    } catch (err) {
      const error: CommentError = {
        message: err instanceof Error ? err.message : 'Failed to fetch comments',
      }
      set({ isLoading: false, error })
    }
  },

  /**
   * Load more comments using cursor
   */
  loadMore: async (token) => {
    const { currentTaskId, nextCursor, isLoadingMore } = get()

    if (!currentTaskId || !nextCursor || isLoadingMore) return

    set({ isLoadingMore: true, error: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.get<CommentListResponse>(
        `/api/tasks/${currentTaskId}/comments?cursor=${encodeURIComponent(nextCursor)}`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        const error = parseApiError(response.status, response.data)
        set({ isLoadingMore: false, error })
        return
      }

      const data = response.data
      set({
        comments: [...get().comments, ...(data?.items || [])],
        nextCursor: data?.next_cursor || null,
        hasMore: !!data?.next_cursor,
        isLoadingMore: false,
      })
    } catch (err) {
      const error: CommentError = {
        message: err instanceof Error ? err.message : 'Failed to load more comments',
      }
      set({ isLoadingMore: false, error })
    }
  },

  /**
   * Create a new comment with optimistic update
   */
  createComment: async (token, taskId, data) => {
    const tempId = `temp-${Date.now()}`
    const now = new Date().toISOString()

    // Create optimistic comment
    const optimisticComment: Comment = {
      id: tempId,
      task_id: taskId,
      author_id: '',
      author_name: 'You',
      author_avatar_url: null,
      body_json: data.body_json || null,
      body_text: data.body_text || '',
      is_deleted: false,
      created_at: now,
      updated_at: null,
      mentions: [],
    }

    // Optimistically add to the beginning (newest first)
    const previousComments = get().comments
    set({
      comments: [optimisticComment, ...previousComments],
      isCreating: true,
      error: null,
    })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.post<Comment>(
        `/api/tasks/${taskId}/comments`,
        data,
        getAuthHeaders(token)
      )

      if (response.status !== 201) {
        // Rollback
        const error = parseApiError(response.status, response.data)
        set({
          comments: previousComments,
          isCreating: false,
          error,
        })
        return null
      }

      const comment = response.data

      // Replace temp comment with real one
      set({
        comments: get().comments.map((c) => (c.id === tempId ? comment : c)),
        isCreating: false,
      })

      return comment
    } catch (err) {
      // Rollback
      const error: CommentError = {
        message: err instanceof Error ? err.message : 'Failed to create comment',
      }
      set({
        comments: previousComments,
        isCreating: false,
        error,
      })
      return null
    }
  },

  /**
   * Update an existing comment with optimistic update
   */
  updateComment: async (token, commentId, data) => {
    const previousComments = get().comments
    const existingComment = previousComments.find((c) => c.id === commentId)

    if (!existingComment) {
      set({ error: { message: 'Comment not found' } })
      return null
    }

    // Optimistic update
    const optimisticComment: Comment = {
      ...existingComment,
      body_json: data.body_json ?? existingComment.body_json,
      body_text: data.body_text ?? existingComment.body_text,
      updated_at: new Date().toISOString(),
    }

    set({
      comments: previousComments.map((c) => (c.id === commentId ? optimisticComment : c)),
      isUpdating: true,
      error: null,
    })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.put<Comment>(
        `/api/comments/${commentId}`,
        data,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        // Rollback
        const error = parseApiError(response.status, response.data)
        set({
          comments: previousComments,
          isUpdating: false,
          error,
        })
        return null
      }

      const comment = response.data

      // Update with server response
      set({
        comments: get().comments.map((c) => (c.id === commentId ? comment : c)),
        isUpdating: false,
      })

      return comment
    } catch (err) {
      // Rollback
      const error: CommentError = {
        message: err instanceof Error ? err.message : 'Failed to update comment',
      }
      set({
        comments: previousComments,
        isUpdating: false,
        error,
      })
      return null
    }
  },

  /**
   * Delete a comment with optimistic update
   */
  deleteComment: async (token, commentId) => {
    const previousComments = get().comments

    // Optimistic delete (mark as deleted)
    set({
      comments: previousComments.map((c) =>
        c.id === commentId ? { ...c, is_deleted: true, body_text: '[deleted]' } : c
      ),
      isDeleting: true,
      error: null,
    })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.delete<void>(
        `/api/comments/${commentId}`,
        getAuthHeaders(token)
      )

      if (response.status !== 204) {
        // Rollback
        const error = parseApiError(response.status, response.data)
        set({
          comments: previousComments,
          isDeleting: false,
          error,
        })
        return false
      }

      set({ isDeleting: false })
      return true
    } catch (err) {
      // Rollback
      const error: CommentError = {
        message: err instanceof Error ? err.message : 'Failed to delete comment',
      }
      set({
        comments: previousComments,
        isDeleting: false,
        error,
      })
      return false
    }
  },

  /**
   * Handle real-time comment added event
   */
  handleCommentAdded: (comment) => {
    const { currentTaskId, comments } = get()

    // Only add if it's for the current task and doesn't already exist
    if (comment.task_id !== currentTaskId) return
    if (comments.some((c) => c.id === comment.id)) return

    // Add to the beginning (newest first)
    set({ comments: [comment, ...comments] })
  },

  /**
   * Handle real-time comment updated event
   */
  handleCommentUpdated: (commentId, comment) => {
    const { comments } = get()

    set({
      comments: comments.map((c) => (c.id === commentId ? comment : c)),
    })
  },

  /**
   * Handle real-time comment deleted event
   */
  handleCommentDeleted: (commentId) => {
    const { comments } = get()

    set({
      comments: comments.map((c) =>
        c.id === commentId ? { ...c, is_deleted: true, body_text: '[deleted]' } : c
      ),
    })
  },

  /**
   * Set the current task ID
   */
  setCurrentTask: (taskId) => {
    if (taskId !== get().currentTaskId) {
      set({ ...initialState, currentTaskId: taskId })
    }
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

export const selectComments = (state: CommentsState): Comment[] => state.comments

export const selectIsLoading = (state: CommentsState): boolean => state.isLoading

export const selectHasMore = (state: CommentsState): boolean => state.hasMore

export const selectError = (state: CommentsState): CommentError | null => state.error

export default useCommentsStore
