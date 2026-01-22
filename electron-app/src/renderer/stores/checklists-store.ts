/**
 * Checklists Store
 *
 * Zustand store for managing task checklists with drag-and-drop reordering.
 * Handles CRUD operations for checklists and their items.
 *
 * Features:
 * - Checklist and item management
 * - Drag-and-drop reordering
 * - Optimistic updates with rollback
 * - Real-time updates via WebSocket
 * - Progress tracking
 */

import { create } from 'zustand'
import { getAuthHeaders } from './auth-store'

// ============================================================================
// Types
// ============================================================================

/**
 * Checklist item data
 */
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

/**
 * Checklist data from the API
 */
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

/**
 * Data for creating a checklist
 */
export interface ChecklistCreate {
  title: string
}

/**
 * Data for creating a checklist item
 */
export interface ChecklistItemCreate {
  content: string
}

/**
 * Error with details
 */
export interface ChecklistError {
  message: string
  code?: string
}

/**
 * Checklists store state
 */
export interface ChecklistsState {
  // State
  checklists: Checklist[]
  currentTaskId: string | null
  isLoading: boolean
  isCreating: boolean
  isUpdating: boolean
  isDeleting: boolean
  error: ChecklistError | null

  // Actions
  fetchChecklists: (token: string | null, taskId: string) => Promise<void>
  createChecklist: (token: string | null, taskId: string, data: ChecklistCreate) => Promise<Checklist | null>
  updateChecklist: (token: string | null, checklistId: string, title: string) => Promise<Checklist | null>
  deleteChecklist: (token: string | null, checklistId: string) => Promise<boolean>

  // Item actions
  createItem: (token: string | null, checklistId: string, data: ChecklistItemCreate) => Promise<ChecklistItem | null>
  updateItem: (token: string | null, itemId: string, text: string) => Promise<ChecklistItem | null>
  toggleItem: (token: string | null, itemId: string) => Promise<ChecklistItem | null>
  deleteItem: (token: string | null, itemId: string) => Promise<boolean>

  // Reordering
  reorderItems: (token: string | null, checklistId: string, itemIds: string[]) => Promise<boolean>
  reorderChecklists: (token: string | null, taskId: string, checklistIds: string[]) => Promise<boolean>

  // Real-time updates (WebSocket handlers)
  handleChecklistCreated: (checklist: Checklist) => void
  handleChecklistUpdated: (checklistId: string, title: string) => void
  handleChecklistDeleted: (checklistId: string) => void
  handleChecklistsReordered: (checklistIds: string[]) => void
  handleItemToggled: (checklistId: string, itemId: string, isDone: boolean) => void
  handleItemAdded: (checklistId: string, item: ChecklistItem) => void
  handleItemUpdated: (itemId: string, content: string) => void
  handleItemDeleted: (checklistId: string, itemId: string) => void
  handleItemsReordered: (checklistId: string, itemIds: string[]) => void

  // Utilities
  setCurrentTask: (taskId: string | null) => void
  getProgress: () => { total: number; done: number; percent: number }
  clearError: () => void
  reset: () => void
}

// ============================================================================
// Helper Functions
// ============================================================================

function parseApiError(status: number, data: unknown): ChecklistError {
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

// ============================================================================
// Initial State
// ============================================================================

const initialState = {
  checklists: [],
  currentTaskId: null,
  isLoading: false,
  isCreating: false,
  isUpdating: false,
  isDeleting: false,
  error: null,
}

// ============================================================================
// Store
// ============================================================================

export const useChecklistsStore = create<ChecklistsState>((set, get) => ({
  ...initialState,

  /**
   * Fetch checklists for a task
   */
  fetchChecklists: async (token, taskId) => {
    set({ isLoading: true, error: null, currentTaskId: taskId })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.get<Checklist[]>(
        `/api/tasks/${taskId}/checklists`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        const error = parseApiError(response.status, response.data)
        set({ isLoading: false, error })
        return
      }

      // Sort checklists and items by rank on initial load
      const checklists = (response.data || [])
        .sort((a: Checklist, b: Checklist) => a.rank.localeCompare(b.rank))
        .map((checklist: Checklist) => ({
          ...checklist,
          items: [...checklist.items].sort((a, b) => a.rank.localeCompare(b.rank)),
        }))

      set({
        checklists,
        isLoading: false,
      })
    } catch (err) {
      const error: ChecklistError = {
        message: err instanceof Error ? err.message : 'Failed to fetch checklists',
      }
      set({ isLoading: false, error })
    }
  },

  /**
   * Create a new checklist with optimistic update
   */
  createChecklist: async (token, taskId, data) => {
    // Create optimistic checklist
    const tempId = `temp-${Date.now()}`
    const optimisticChecklist: Checklist = {
      id: tempId,
      task_id: taskId,
      title: data.title,
      rank: 'zzz', // Will be at end
      total_items: 0,
      completed_items: 0,
      progress_percent: 0,
      created_at: new Date().toISOString(),
      items: [],
    }

    const previous = get().checklists
    set({
      checklists: [...previous, optimisticChecklist],
      isCreating: true,
      error: null,
    })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.post<Checklist>(
        `/api/tasks/${taskId}/checklists`,
        data,
        getAuthHeaders(token)
      )

      if (response.status !== 201) {
        const error = parseApiError(response.status, response.data)
        // Rollback
        set({ checklists: previous, isCreating: false, error })
        return null
      }

      const checklist = response.data
      // Replace temp with real checklist
      set({
        checklists: get().checklists.map((c) =>
          c.id === tempId ? checklist : c
        ),
        isCreating: false,
      })

      return checklist
    } catch (err) {
      const error: ChecklistError = {
        message: err instanceof Error ? err.message : 'Failed to create checklist',
      }
      // Rollback
      set({ checklists: previous, isCreating: false, error })
      return null
    }
  },

  /**
   * Update a checklist title
   */
  updateChecklist: async (token, checklistId, title) => {
    const previous = get().checklists
    const existing = previous.find((c) => c.id === checklistId)
    if (!existing) return null

    // Optimistic update
    set({
      checklists: previous.map((c) =>
        c.id === checklistId ? { ...c, title } : c
      ),
      isUpdating: true,
      error: null,
    })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.put<Checklist>(
        `/api/checklists/${checklistId}`,
        { title },
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        // Rollback
        set({ checklists: previous, isUpdating: false, error: parseApiError(response.status, response.data) })
        return null
      }

      const checklist = response.data
      set({
        checklists: get().checklists.map((c) =>
          c.id === checklistId ? { ...c, ...checklist } : c
        ),
        isUpdating: false,
      })

      return checklist
    } catch (err) {
      set({
        checklists: previous,
        isUpdating: false,
        error: { message: err instanceof Error ? err.message : 'Failed to update checklist' },
      })
      return null
    }
  },

  /**
   * Delete a checklist
   */
  deleteChecklist: async (token, checklistId) => {
    const previous = get().checklists

    // Optimistic delete
    set({
      checklists: previous.filter((c) => c.id !== checklistId),
      isDeleting: true,
      error: null,
    })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.delete<void>(
        `/api/checklists/${checklistId}`,
        getAuthHeaders(token)
      )

      if (response.status !== 204) {
        // Rollback
        set({ checklists: previous, isDeleting: false, error: parseApiError(response.status, response.data) })
        return false
      }

      set({ isDeleting: false })
      return true
    } catch (err) {
      set({
        checklists: previous,
        isDeleting: false,
        error: { message: err instanceof Error ? err.message : 'Failed to delete checklist' },
      })
      return false
    }
  },

  /**
   * Create a new item in a checklist with optimistic update
   */
  createItem: async (token, checklistId, data) => {
    const checklists = get().checklists
    const checklist = checklists.find((c) => c.id === checklistId)
    if (!checklist) return null

    // Create optimistic item
    const tempId = `temp-${Date.now()}`
    const optimisticItem: ChecklistItem = {
      id: tempId,
      checklist_id: checklistId,
      content: data.content,
      is_done: false,
      completed_by: null,
      completed_by_name: null,
      completed_at: null,
      rank: 'zzz', // Will be at end
      created_at: new Date().toISOString(),
      updated_at: null,
    }

    const previous = checklists
    set({
      checklists: checklists.map((c) =>
        c.id === checklistId
          ? {
              ...c,
              items: [...c.items, optimisticItem],
              total_items: c.total_items + 1,
            }
          : c
      ),
      isCreating: true,
      error: null,
    })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.post<ChecklistItem>(
        `/api/checklists/${checklistId}/items`,
        data,
        getAuthHeaders(token)
      )

      if (response.status !== 201) {
        const error = parseApiError(response.status, response.data)
        // Rollback
        set({ checklists: previous, isCreating: false, error })
        return null
      }

      const item = response.data
      // Replace temp item with real item
      set({
        checklists: get().checklists.map((c) =>
          c.id === checklistId
            ? {
                ...c,
                items: c.items.map((i) => (i.id === tempId ? item : i)),
              }
            : c
        ),
        isCreating: false,
      })

      return item
    } catch (err) {
      const error: ChecklistError = {
        message: err instanceof Error ? err.message : 'Failed to create item',
      }
      // Rollback
      set({ checklists: previous, isCreating: false, error })
      return null
    }
  },

  /**
   * Update an item's content
   */
  updateItem: async (token, itemId, content) => {
    const checklists = get().checklists
    let checklistId: string | null = null
    let existingItem: ChecklistItem | null = null

    for (const c of checklists) {
      const item = c.items.find((i) => i.id === itemId)
      if (item) {
        checklistId = c.id
        existingItem = item
        break
      }
    }

    if (!checklistId || !existingItem) return null

    // Optimistic update
    const previous = checklists
    set({
      checklists: checklists.map((c) =>
        c.id === checklistId
          ? { ...c, items: c.items.map((i) => (i.id === itemId ? { ...i, content } : i)) }
          : c
      ),
      isUpdating: true,
      error: null,
    })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.put<ChecklistItem>(
        `/api/checklist-items/${itemId}`,
        { content },
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        set({ checklists: previous, isUpdating: false, error: parseApiError(response.status, response.data) })
        return null
      }

      const item = response.data
      set({
        checklists: get().checklists.map((c) =>
          c.id === checklistId
            ? { ...c, items: c.items.map((i) => (i.id === itemId ? item : i)) }
            : c
        ),
        isUpdating: false,
      })

      return item
    } catch (err) {
      set({
        checklists: previous,
        isUpdating: false,
        error: { message: err instanceof Error ? err.message : 'Failed to update item' },
      })
      return null
    }
  },

  /**
   * Toggle an item's done status
   */
  toggleItem: async (token, itemId) => {
    const checklists = get().checklists
    let checklistId: string | null = null
    let existingItem: ChecklistItem | null = null

    for (const c of checklists) {
      const item = c.items.find((i) => i.id === itemId)
      if (item) {
        checklistId = c.id
        existingItem = item
        break
      }
    }

    if (!checklistId || !existingItem) return null

    const newIsDone = !existingItem.is_done

    // Optimistic update
    const previous = checklists
    set({
      checklists: checklists.map((c) =>
        c.id === checklistId
          ? {
              ...c,
              items: c.items.map((i) =>
                i.id === itemId ? { ...i, is_done: newIsDone } : i
              ),
              completed_items: newIsDone ? c.completed_items + 1 : Math.max(0, c.completed_items - 1),
            }
          : c
      ),
      isUpdating: true,
      error: null,
    })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.post<ChecklistItem>(
        `/api/checklist-items/${itemId}/toggle`,
        {},
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        set({ checklists: previous, isUpdating: false, error: parseApiError(response.status, response.data) })
        return null
      }

      const item = response.data
      set({
        checklists: get().checklists.map((c) =>
          c.id === checklistId
            ? {
                ...c,
                items: c.items.map((i) => (i.id === itemId ? item : i)),
              }
            : c
        ),
        isUpdating: false,
      })

      return item
    } catch (err) {
      set({
        checklists: previous,
        isUpdating: false,
        error: { message: err instanceof Error ? err.message : 'Failed to toggle item' },
      })
      return null
    }
  },

  /**
   * Delete a checklist item
   */
  deleteItem: async (token, itemId) => {
    const checklists = get().checklists
    let checklistId: string | null = null
    let existingItem: ChecklistItem | null = null

    for (const c of checklists) {
      const item = c.items.find((i) => i.id === itemId)
      if (item) {
        checklistId = c.id
        existingItem = item
        break
      }
    }

    if (!checklistId || !existingItem) return false

    // Optimistic delete
    const previous = checklists
    set({
      checklists: checklists.map((c) =>
        c.id === checklistId
          ? {
              ...c,
              items: c.items.filter((i) => i.id !== itemId),
              total_items: Math.max(0, c.total_items - 1),
              completed_items: existingItem!.is_done ? Math.max(0, c.completed_items - 1) : c.completed_items,
            }
          : c
      ),
      isDeleting: true,
      error: null,
    })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.delete<void>(
        `/api/checklist-items/${itemId}`,
        getAuthHeaders(token)
      )

      if (response.status !== 204) {
        set({ checklists: previous, isDeleting: false, error: parseApiError(response.status, response.data) })
        return false
      }

      set({ isDeleting: false })
      return true
    } catch (err) {
      set({
        checklists: previous,
        isDeleting: false,
        error: { message: err instanceof Error ? err.message : 'Failed to delete item' },
      })
      return false
    }
  },

  /**
   * Reorder items within a checklist
   */
  reorderItems: async (token, checklistId, itemIds) => {
    const checklists = get().checklists
    const checklist = checklists.find((c) => c.id === checklistId)
    if (!checklist) return false

    // Optimistic reorder - keep items but in new order
    const previous = checklists
    const reorderedItems = itemIds
      .map((id) => checklist.items.find((i) => i.id === id))
      .filter((i): i is ChecklistItem => !!i)

    set({
      checklists: checklists.map((c) =>
        c.id === checklistId ? { ...c, items: reorderedItems } : c
      ),
      isUpdating: true,
      error: null,
    })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.put<void>(
        `/api/checklists/${checklistId}/items/reorder`,
        { item_ids: itemIds },
        getAuthHeaders(token)
      )

      if (response.status !== 204) {
        set({ checklists: previous, isUpdating: false, error: parseApiError(response.status, response.data) })
        return false
      }

      set({ isUpdating: false })
      return true
    } catch (err) {
      set({
        checklists: previous,
        isUpdating: false,
        error: { message: err instanceof Error ? err.message : 'Failed to reorder items' },
      })
      return false
    }
  },

  /**
   * Reorder checklists for a task
   */
  reorderChecklists: async (token, taskId, checklistIds) => {
    const checklists = get().checklists

    // Optimistic reorder - keep checklists but in new order
    const previous = checklists
    const reordered = checklistIds
      .map((id) => checklists.find((c) => c.id === id))
      .filter((c): c is Checklist => !!c)

    set({
      checklists: reordered,
      isUpdating: true,
      error: null,
    })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.put<void>(
        `/api/tasks/${taskId}/checklists/reorder`,
        { item_ids: checklistIds },
        getAuthHeaders(token)
      )

      if (response.status !== 204) {
        set({ checklists: previous, isUpdating: false, error: parseApiError(response.status, response.data) })
        return false
      }

      set({ isUpdating: false })
      return true
    } catch (err) {
      set({
        checklists: previous,
        isUpdating: false,
        error: { message: err instanceof Error ? err.message : 'Failed to reorder checklists' },
      })
      return false
    }
  },

  /**
   * Handle real-time checklist created event
   */
  handleChecklistCreated: (checklist) => {
    const { currentTaskId, checklists } = get()
    if (checklist.task_id !== currentTaskId) return
    if (checklists.some((c) => c.id === checklist.id)) return

    set({ checklists: [...checklists, checklist] })
  },

  /**
   * Handle real-time checklist updated event
   */
  handleChecklistUpdated: (checklistId, title) => {
    const checklists = get().checklists
    const checklist = checklists.find((c) => c.id === checklistId)
    if (!checklist) return

    set({
      checklists: checklists.map((c) =>
        c.id === checklistId ? { ...c, title } : c
      ),
    })
  },

  /**
   * Handle real-time checklist deleted event
   */
  handleChecklistDeleted: (checklistId) => {
    const checklists = get().checklists
    set({
      checklists: checklists.filter((c) => c.id !== checklistId),
    })
  },

  /**
   * Handle real-time item toggled event
   */
  handleItemToggled: (checklistId, itemId, isDone) => {
    const checklists = get().checklists
    const checklist = checklists.find((c) => c.id === checklistId)
    if (!checklist) return

    const item = checklist.items.find((i) => i.id === itemId)
    if (!item || item.is_done === isDone) return

    set({
      checklists: checklists.map((c) =>
        c.id === checklistId
          ? {
              ...c,
              items: c.items.map((i) =>
                i.id === itemId ? { ...i, is_done: isDone } : i
              ),
              completed_items: isDone
                ? c.completed_items + 1
                : Math.max(0, c.completed_items - 1),
            }
          : c
      ),
    })
  },

  /**
   * Handle real-time item added event
   */
  handleItemAdded: (checklistId, item) => {
    const checklists = get().checklists
    const checklist = checklists.find((c) => c.id === checklistId)
    if (!checklist) return

    // Avoid duplicates
    if (checklist.items.some((i) => i.id === item.id)) return

    set({
      checklists: checklists.map((c) =>
        c.id === checklistId
          ? {
              ...c,
              items: [...c.items, item],
              total_items: c.total_items + 1,
              completed_items: item.is_done ? c.completed_items + 1 : c.completed_items,
            }
          : c
      ),
    })
  },

  /**
   * Handle real-time item updated event
   */
  handleItemUpdated: (itemId, content) => {
    const checklists = get().checklists

    set({
      checklists: checklists.map((c) => ({
        ...c,
        items: c.items.map((i) =>
          i.id === itemId ? { ...i, content } : i
        ),
      })),
    })
  },

  /**
   * Handle real-time item deleted event
   */
  handleItemDeleted: (checklistId, itemId) => {
    const checklists = get().checklists
    const checklist = checklists.find((c) => c.id === checklistId)
    if (!checklist) return

    const item = checklist.items.find((i) => i.id === itemId)
    if (!item) return

    set({
      checklists: checklists.map((c) =>
        c.id === checklistId
          ? {
              ...c,
              items: c.items.filter((i) => i.id !== itemId),
              total_items: Math.max(0, c.total_items - 1),
              completed_items: item.is_done ? Math.max(0, c.completed_items - 1) : c.completed_items,
            }
          : c
      ),
    })
  },

  /**
   * Handle real-time checklists reordered event
   */
  handleChecklistsReordered: (checklistIds) => {
    const checklists = get().checklists
    // Reorder checklists based on the new order
    const reordered = checklistIds
      .map((id) => checklists.find((c) => c.id === id))
      .filter((c): c is Checklist => !!c)

    // Include any checklists not in the reorder list (shouldn't happen, but be safe)
    const missing = checklists.filter((c) => !checklistIds.includes(c.id))
    set({ checklists: [...reordered, ...missing] })
  },

  /**
   * Handle real-time items reordered event
   */
  handleItemsReordered: (checklistId, itemIds) => {
    const checklists = get().checklists
    const checklist = checklists.find((c) => c.id === checklistId)
    if (!checklist) return

    // Reorder items based on the new order
    const reorderedItems = itemIds
      .map((id) => checklist.items.find((i) => i.id === id))
      .filter((i): i is ChecklistItem => !!i)

    // Include any items not in the reorder list (shouldn't happen, but be safe)
    const missingItems = checklist.items.filter((i) => !itemIds.includes(i.id))

    set({
      checklists: checklists.map((c) =>
        c.id === checklistId
          ? { ...c, items: [...reorderedItems, ...missingItems] }
          : c
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
   * Get overall progress across all checklists
   */
  getProgress: () => {
    const checklists = get().checklists
    const total = checklists.reduce((sum, c) => sum + c.total_items, 0)
    const done = checklists.reduce((sum, c) => sum + c.completed_items, 0)
    const percent = total > 0 ? Math.round((done / total) * 100) : 0
    return { total, done, percent }
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
}))

// ============================================================================
// Selectors
// ============================================================================

export const selectChecklists = (state: ChecklistsState): Checklist[] => state.checklists

export const selectIsLoading = (state: ChecklistsState): boolean => state.isLoading

export const selectError = (state: ChecklistsState): ChecklistError | null => state.error

export default useChecklistsStore
