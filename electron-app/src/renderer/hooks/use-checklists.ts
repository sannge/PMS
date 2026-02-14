/**
 * TanStack Query Hooks for Checklists
 *
 * Provides React Query hooks for checklist CRUD operations with:
 * - Checklists and items management
 * - Drag-and-drop reordering
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

export interface ChecklistItem {
  id: string
  checklist_id: string
  content: string
  is_done: boolean
  completed_by?: string | null
  completed_by_name?: string | null
  completed_at?: string | null
  rank: string
  created_at: string
  updated_at: string | null
}

export interface Checklist {
  id: string
  task_id: string
  title: string
  rank: string
  total_items: number
  completed_items: number
  progress_percent: number
  created_at: string
  items: ChecklistItem[]
}

export interface ChecklistCreate {
  title: string
}

export interface ChecklistItemCreate {
  content: string
}

export interface ApiError {
  message: string
  code?: string
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
  }

  switch (status) {
    case 400:
      return { message: 'Invalid request.' }
    case 401:
      return { message: 'Authentication required.' }
    case 403:
      return { message: 'Access denied.' }
    case 404:
      return { message: 'Not found.' }
    case 500:
      return { message: 'Server error.' }
    default:
      return { message: 'An unexpected error occurred.' }
  }
}

function sortByRank<T extends { rank: string }>(items: T[]): T[] {
  return [...items].sort((a, b) => a.rank.localeCompare(b.rank))
}

// ============================================================================
// Checklist Queries
// ============================================================================

/**
 * Fetch checklists for a task.
 */
export function useChecklists(taskId: string | undefined): UseQueryResult<Checklist[], Error> {
  const token = useAuthStore((s) => s.token)

  return useQuery({
    queryKey: queryKeys.checklists(taskId || ''),
    queryFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.get<Checklist[]>(
        `/api/tasks/${taskId}/checklists`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      // Sort checklists and items by rank
      const checklists = (response.data || []).map((checklist) => ({
        ...checklist,
        items: sortByRank(checklist.items),
      }))

      return sortByRank(checklists)
    },
    enabled: !!token && !!taskId,
    staleTime: 30 * 1000, // 30 seconds
    gcTime: 24 * 60 * 60 * 1000, // 24 hours for offline
  })
}

/**
 * Get checklist progress across all checklists for a task.
 */
export function useChecklistProgress(taskId: string | undefined): {
  total: number
  done: number
  percent: number
} {
  const { data: checklists = [] } = useChecklists(taskId)

  const total = checklists.reduce((sum, c) => sum + c.total_items, 0)
  const done = checklists.reduce((sum, c) => sum + c.completed_items, 0)
  const percent = total > 0 ? Math.round((done / total) * 100) : 0

  return { total, done, percent }
}

// ============================================================================
// Checklist Mutations
// ============================================================================

/**
 * Create a new checklist.
 */
export function useCreateChecklist(
  taskId: string
): UseMutationResult<Checklist, Error, ChecklistCreate, { previous?: Checklist[] }> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: ChecklistCreate) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.post<Checklist>(
        `/api/tasks/${taskId}/checklists`,
        data,
        getAuthHeaders(token)
      )

      if (response.status !== 201) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
    onMutate: async (newData) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.checklists(taskId) })

      const previous = queryClient.getQueryData<Checklist[]>(queryKeys.checklists(taskId))

      // Optimistic checklist
      const optimistic: Checklist = {
        id: `temp-${Date.now()}`,
        task_id: taskId,
        title: newData.title,
        rank: 'zzz',
        total_items: 0,
        completed_items: 0,
        progress_percent: 0,
        created_at: new Date().toISOString(),
        items: [],
      }

      queryClient.setQueryData<Checklist[]>(queryKeys.checklists(taskId), (old) => [
        ...(old || []),
        optimistic,
      ])

      return { previous }
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.checklists(taskId), context.previous)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.checklists(taskId) })
    },
  })
}

/**
 * Update a checklist title.
 */
export function useUpdateChecklist(
  taskId: string
): UseMutationResult<
  Checklist,
  Error,
  { checklistId: string; title: string },
  { previous?: Checklist[] }
> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ checklistId, title }) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.put<Checklist>(
        `/api/checklists/${checklistId}`,
        { title },
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
    onMutate: async ({ checklistId, title }) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.checklists(taskId) })

      const previous = queryClient.getQueryData<Checklist[]>(queryKeys.checklists(taskId))

      queryClient.setQueryData<Checklist[]>(queryKeys.checklists(taskId), (old) =>
        old?.map((c) => (c.id === checklistId ? { ...c, title } : c))
      )

      return { previous }
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.checklists(taskId), context.previous)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.checklists(taskId) })
    },
  })
}

/**
 * Delete a checklist.
 */
export function useDeleteChecklist(
  taskId: string
): UseMutationResult<void, Error, string, { previous?: Checklist[] }> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (checklistId: string) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.delete<void>(
        `/api/checklists/${checklistId}`,
        getAuthHeaders(token)
      )

      if (response.status !== 204) {
        throw new Error(parseApiError(response.status, response.data).message)
      }
    },
    onMutate: async (checklistId) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.checklists(taskId) })

      const previous = queryClient.getQueryData<Checklist[]>(queryKeys.checklists(taskId))

      queryClient.setQueryData<Checklist[]>(queryKeys.checklists(taskId), (old) =>
        old?.filter((c) => c.id !== checklistId)
      )

      return { previous }
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.checklists(taskId), context.previous)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.checklists(taskId) })
    },
  })
}

/**
 * Reorder checklists.
 */
export function useReorderChecklists(
  taskId: string
): UseMutationResult<void, Error, string[], { previous?: Checklist[] }> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (checklistIds: string[]) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.put<void>(
        `/api/tasks/${taskId}/checklists/reorder`,
        { item_ids: checklistIds },
        getAuthHeaders(token)
      )

      if (response.status !== 204) {
        throw new Error(parseApiError(response.status, response.data).message)
      }
    },
    onMutate: async (checklistIds) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.checklists(taskId) })

      const previous = queryClient.getQueryData<Checklist[]>(queryKeys.checklists(taskId))

      // Reorder optimistically
      queryClient.setQueryData<Checklist[]>(queryKeys.checklists(taskId), (old) => {
        if (!old) return old
        return checklistIds
          .map((id) => old.find((c) => c.id === id))
          .filter((c): c is Checklist => !!c)
      })

      return { previous }
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.checklists(taskId), context.previous)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.checklists(taskId) })
    },
  })
}

// ============================================================================
// Checklist Item Mutations
// ============================================================================

/**
 * Create a new checklist item.
 */
export function useCreateChecklistItem(
  taskId: string
): UseMutationResult<
  ChecklistItem,
  Error,
  { checklistId: string; data: ChecklistItemCreate },
  { previous?: Checklist[] }
> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ checklistId, data }) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.post<ChecklistItem>(
        `/api/checklists/${checklistId}/items`,
        data,
        getAuthHeaders(token)
      )

      if (response.status !== 201) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
    onMutate: async ({ checklistId, data }) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.checklists(taskId) })

      const previous = queryClient.getQueryData<Checklist[]>(queryKeys.checklists(taskId))

      const optimisticItem: ChecklistItem = {
        id: `temp-${Date.now()}`,
        checklist_id: checklistId,
        content: data.content,
        is_done: false,
        completed_by: null,
        completed_by_name: null,
        completed_at: null,
        rank: 'zzz',
        created_at: new Date().toISOString(),
        updated_at: null,
      }

      queryClient.setQueryData<Checklist[]>(queryKeys.checklists(taskId), (old) =>
        old?.map((c) =>
          c.id === checklistId
            ? { ...c, items: [...(c.items || []), optimisticItem], total_items: (c.total_items || 0) + 1 }
            : c
        )
      )

      return { previous }
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.checklists(taskId), context.previous)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.checklists(taskId) })
    },
  })
}

/**
 * Update a checklist item content.
 */
export function useUpdateChecklistItem(
  taskId: string
): UseMutationResult<
  ChecklistItem,
  Error,
  { itemId: string; content: string },
  { previous?: Checklist[] }
> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ itemId, content }) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.put<ChecklistItem>(
        `/api/checklist-items/${itemId}`,
        { content },
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
    onMutate: async ({ itemId, content }) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.checklists(taskId) })

      const previous = queryClient.getQueryData<Checklist[]>(queryKeys.checklists(taskId))

      queryClient.setQueryData<Checklist[]>(queryKeys.checklists(taskId), (old) =>
        old?.map((c) => ({
          ...c,
          items: (c.items || []).map((i) => (i.id === itemId ? { ...i, content } : i)),
        }))
      )

      return { previous }
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.checklists(taskId), context.previous)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.checklists(taskId) })
    },
  })
}

/**
 * Toggle a checklist item's done status.
 */
export function useToggleChecklistItem(
  taskId: string
): UseMutationResult<ChecklistItem, Error, string, { previous?: Checklist[] }> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (itemId: string) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.post<ChecklistItem>(
        `/api/checklist-items/${itemId}/toggle`,
        {},
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        throw new Error(parseApiError(response.status, response.data).message)
      }

      return response.data
    },
    onMutate: async (itemId) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.checklists(taskId) })

      const previous = queryClient.getQueryData<Checklist[]>(queryKeys.checklists(taskId))

      queryClient.setQueryData<Checklist[]>(queryKeys.checklists(taskId), (old) =>
        old?.map((c) => {
          const items = c.items || []
          const item = items.find((i) => i.id === itemId)
          if (!item) return c

          const newIsDone = !item.is_done
          return {
            ...c,
            items: items.map((i) => (i.id === itemId ? { ...i, is_done: newIsDone } : i)),
            completed_items: newIsDone ? (c.completed_items || 0) + 1 : Math.max(0, (c.completed_items || 0) - 1),
          }
        })
      )

      return { previous }
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.checklists(taskId), context.previous)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.checklists(taskId) })
    },
  })
}

/**
 * Delete a checklist item.
 */
export function useDeleteChecklistItem(
  taskId: string
): UseMutationResult<void, Error, string, { previous?: Checklist[] }> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (itemId: string) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.delete<void>(
        `/api/checklist-items/${itemId}`,
        getAuthHeaders(token)
      )

      if (response.status !== 204) {
        throw new Error(parseApiError(response.status, response.data).message)
      }
    },
    onMutate: async (itemId) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.checklists(taskId) })

      const previous = queryClient.getQueryData<Checklist[]>(queryKeys.checklists(taskId))

      queryClient.setQueryData<Checklist[]>(queryKeys.checklists(taskId), (old) =>
        old?.map((c) => {
          const items = c.items || []
          const item = items.find((i) => i.id === itemId)
          if (!item) return c

          return {
            ...c,
            items: items.filter((i) => i.id !== itemId),
            total_items: Math.max(0, (c.total_items || 0) - 1),
            completed_items: item.is_done ? Math.max(0, (c.completed_items || 0) - 1) : (c.completed_items || 0),
          }
        })
      )

      return { previous }
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.checklists(taskId), context.previous)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.checklists(taskId) })
    },
  })
}

/**
 * Reorder checklist items within a checklist.
 */
export function useReorderChecklistItems(
  taskId: string
): UseMutationResult<
  void,
  Error,
  { checklistId: string; itemIds: string[] },
  { previous?: Checklist[] }
> {
  const token = useAuthStore((s) => s.token)
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ checklistId, itemIds }) => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.put<void>(
        `/api/checklists/${checklistId}/items/reorder`,
        { item_ids: itemIds },
        getAuthHeaders(token)
      )

      if (response.status !== 204) {
        throw new Error(parseApiError(response.status, response.data).message)
      }
    },
    onMutate: async ({ checklistId, itemIds }) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.checklists(taskId) })

      const previous = queryClient.getQueryData<Checklist[]>(queryKeys.checklists(taskId))

      queryClient.setQueryData<Checklist[]>(queryKeys.checklists(taskId), (old) =>
        old?.map((c) => {
          if (c.id !== checklistId) return c

          const items = c.items || []
          const reorderedItems = itemIds
            .map((id) => items.find((i) => i.id === id))
            .filter((i): i is ChecklistItem => !!i)

          return { ...c, items: reorderedItems }
        })
      )

      return { previous }
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.checklists(taskId), context.previous)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.checklists(taskId) })
    },
  })
}
