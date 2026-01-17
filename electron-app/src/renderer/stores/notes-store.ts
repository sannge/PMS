/**
 * Notes Store
 *
 * Zustand store for managing notes state in the renderer process.
 * Handles CRUD operations for notes with API integration and tab management.
 *
 * Features:
 * - Note list with hierarchy support
 * - Create, read, update, delete operations
 * - Tab management for open notes
 * - Loading and error states
 * - Tree structure for note hierarchy
 */

import { create } from 'zustand'
import { getAuthHeaders } from './auth-store'

// ============================================================================
// Types
// ============================================================================

/**
 * Note data from the API
 */
export interface Note {
  id: string
  title: string
  content: string | null
  tab_order: number
  application_id: string
  parent_id: string | null
  created_by: string | null
  created_at: string
  updated_at: string
  children_count?: number
}

/**
 * Note with children for tree structure
 */
export interface NoteTree extends Note {
  children: NoteTree[]
}

/**
 * Data for creating a note
 */
export interface NoteCreate {
  title: string
  content?: string | null
  tab_order?: number
  parent_id?: string | null
}

/**
 * Data for updating a note
 */
export interface NoteUpdate {
  title?: string
  content?: string | null
  tab_order?: number
  parent_id?: string | null
}

/**
 * Open tab state
 */
export interface NoteTab {
  id: string
  title: string
  isDirty: boolean
  content: string | null
}

/**
 * Error with details
 */
export interface NoteError {
  message: string
  code?: string
  field?: string
}

/**
 * Notes store state
 */
export interface NotesState {
  // State
  notes: Note[]
  noteTree: NoteTree[]
  selectedNote: Note | null
  openTabs: NoteTab[]
  activeTabId: string | null
  isLoading: boolean
  isCreating: boolean
  isUpdating: boolean
  isDeleting: boolean
  error: NoteError | null

  // Current application context
  currentApplicationId: string | null

  // Actions
  fetchNotes: (token: string | null, applicationId: string) => Promise<void>
  fetchNoteTree: (token: string | null, applicationId: string) => Promise<void>
  fetchNote: (token: string | null, noteId: string) => Promise<Note | null>
  createNote: (token: string | null, applicationId: string, data: NoteCreate) => Promise<Note | null>
  updateNote: (token: string | null, noteId: string, data: NoteUpdate) => Promise<Note | null>
  deleteNote: (token: string | null, noteId: string, cascade?: boolean) => Promise<boolean>
  reorderNote: (token: string | null, noteId: string, newOrder: number) => Promise<boolean>

  // Tab management
  openTab: (note: Note) => void
  closeTab: (tabId: string) => void
  setActiveTab: (tabId: string) => void
  updateTabContent: (tabId: string, content: string) => void
  markTabDirty: (tabId: string, isDirty: boolean) => void
  closeAllTabs: () => void
  closeOtherTabs: (tabId: string) => void

  // Selection
  selectNote: (note: Note | null) => void
  setCurrentApplication: (applicationId: string | null) => void

  // Utilities
  clearError: () => void
  reset: () => void
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Parse API error response
 */
function parseApiError(status: number, data: unknown): NoteError {
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
      return { message: 'Note not found.' }
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
  notes: [],
  noteTree: [],
  selectedNote: null,
  openTabs: [],
  activeTabId: null,
  isLoading: false,
  isCreating: false,
  isUpdating: false,
  isDeleting: false,
  error: null,
  currentApplicationId: null,
}

// ============================================================================
// Store
// ============================================================================

/**
 * Notes store using zustand
 */
export const useNotesStore = create<NotesState>((set, get) => ({
  // Initial state
  ...initialState,

  /**
   * Fetch flat list of notes for an application
   */
  fetchNotes: async (token, applicationId) => {
    set({ isLoading: true, error: null, currentApplicationId: applicationId })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.get<Note[]>(
        `/api/applications/${applicationId}/notes`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        const error = parseApiError(response.status, response.data)
        set({ isLoading: false, error })
        return
      }

      const notes = response.data || []
      set({ notes, isLoading: false })
    } catch (err) {
      const error: NoteError = {
        message: err instanceof Error ? err.message : 'Failed to fetch notes',
      }
      set({ isLoading: false, error })
    }
  },

  /**
   * Fetch hierarchical note tree for an application
   */
  fetchNoteTree: async (token, applicationId) => {
    set({ isLoading: true, error: null, currentApplicationId: applicationId })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.get<NoteTree[]>(
        `/api/applications/${applicationId}/notes/tree`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        const error = parseApiError(response.status, response.data)
        set({ isLoading: false, error })
        return
      }

      const noteTree = response.data || []
      set({ noteTree, isLoading: false })
    } catch (err) {
      const error: NoteError = {
        message: err instanceof Error ? err.message : 'Failed to fetch note tree',
      }
      set({ isLoading: false, error })
    }
  },

  /**
   * Fetch a single note by ID
   */
  fetchNote: async (token, noteId) => {
    set({ isLoading: true, error: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.get<Note>(
        `/api/notes/${noteId}`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        const error = parseApiError(response.status, response.data)
        set({ isLoading: false, error })
        return null
      }

      const note = response.data
      set({ selectedNote: note, isLoading: false })
      return note
    } catch (err) {
      const error: NoteError = {
        message: err instanceof Error ? err.message : 'Failed to fetch note',
      }
      set({ isLoading: false, error })
      return null
    }
  },

  /**
   * Create a new note
   */
  createNote: async (token, applicationId, data) => {
    set({ isCreating: true, error: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const payload = {
        ...data,
        application_id: applicationId,
      }

      const response = await window.electronAPI.post<Note>(
        `/api/applications/${applicationId}/notes`,
        payload,
        getAuthHeaders(token)
      )

      if (response.status !== 201) {
        const error = parseApiError(response.status, response.data)
        set({ isCreating: false, error })
        return null
      }

      const note = response.data
      // Add the new note to the list
      set({
        notes: [...get().notes, note],
        isCreating: false,
      })

      // Refresh the tree to reflect changes
      const currentAppId = get().currentApplicationId
      if (currentAppId) {
        get().fetchNoteTree(token, currentAppId)
      }

      return note
    } catch (err) {
      const error: NoteError = {
        message: err instanceof Error ? err.message : 'Failed to create note',
      }
      set({ isCreating: false, error })
      return null
    }
  },

  /**
   * Update an existing note
   */
  updateNote: async (token, noteId, data) => {
    set({ isUpdating: true, error: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.put<Note>(
        `/api/notes/${noteId}`,
        data,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        const error = parseApiError(response.status, response.data)
        set({ isUpdating: false, error })
        return null
      }

      const note = response.data
      // Update the note in the list
      const notes = get().notes.map((n) => (n.id === noteId ? note : n))

      // Update open tab if exists
      const openTabs = get().openTabs.map((tab) =>
        tab.id === noteId ? { ...tab, title: note.title, isDirty: false } : tab
      )

      set({
        notes,
        openTabs,
        selectedNote: note,
        isUpdating: false,
      })

      // Refresh the tree to reflect changes
      const currentAppId = get().currentApplicationId
      if (currentAppId) {
        get().fetchNoteTree(token, currentAppId)
      }

      return note
    } catch (err) {
      const error: NoteError = {
        message: err instanceof Error ? err.message : 'Failed to update note',
      }
      set({ isUpdating: false, error })
      return null
    }
  },

  /**
   * Delete a note
   */
  deleteNote: async (token, noteId, cascade = false) => {
    set({ isDeleting: true, error: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const params = cascade ? '?cascade=true' : ''
      const response = await window.electronAPI.delete<void>(
        `/api/notes/${noteId}${params}`,
        getAuthHeaders(token)
      )

      if (response.status !== 204 && response.status !== 200) {
        const error = parseApiError(response.status, response.data)
        set({ isDeleting: false, error })
        return false
      }

      // Remove the note from the list
      const notes = get().notes.filter((n) => n.id !== noteId)

      // Close the tab if open
      const openTabs = get().openTabs.filter((tab) => tab.id !== noteId)
      const activeTabId = get().activeTabId === noteId
        ? (openTabs.length > 0 ? openTabs[openTabs.length - 1].id : null)
        : get().activeTabId

      set({
        notes,
        openTabs,
        activeTabId,
        selectedNote: null,
        isDeleting: false,
      })

      // Refresh the tree to reflect changes
      const currentAppId = get().currentApplicationId
      if (currentAppId) {
        get().fetchNoteTree(token, currentAppId)
      }

      return true
    } catch (err) {
      const error: NoteError = {
        message: err instanceof Error ? err.message : 'Failed to delete note',
      }
      set({ isDeleting: false, error })
      return false
    }
  },

  /**
   * Reorder a note
   */
  reorderNote: async (token, noteId, newOrder) => {
    set({ isUpdating: true, error: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.put<Note>(
        `/api/notes/${noteId}/reorder`,
        { new_order: newOrder },
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        const error = parseApiError(response.status, response.data)
        set({ isUpdating: false, error })
        return false
      }

      // Refresh the tree to reflect changes
      const currentAppId = get().currentApplicationId
      if (currentAppId) {
        get().fetchNoteTree(token, currentAppId)
      }

      set({ isUpdating: false })
      return true
    } catch (err) {
      const error: NoteError = {
        message: err instanceof Error ? err.message : 'Failed to reorder note',
      }
      set({ isUpdating: false, error })
      return false
    }
  },

  /**
   * Open a note in a tab
   */
  openTab: (note) => {
    const { openTabs } = get()

    // Check if tab already exists
    const existingTab = openTabs.find((tab) => tab.id === note.id)
    if (existingTab) {
      set({ activeTabId: note.id })
      return
    }

    // Create new tab
    const newTab: NoteTab = {
      id: note.id,
      title: note.title,
      isDirty: false,
      content: note.content,
    }

    set({
      openTabs: [...openTabs, newTab],
      activeTabId: note.id,
      selectedNote: note,
    })
  },

  /**
   * Close a tab
   */
  closeTab: (tabId) => {
    const { openTabs, activeTabId } = get()
    const tabIndex = openTabs.findIndex((tab) => tab.id === tabId)

    if (tabIndex === -1) return

    const newTabs = openTabs.filter((tab) => tab.id !== tabId)

    // Determine new active tab
    let newActiveTabId: string | null = null
    if (activeTabId === tabId) {
      if (newTabs.length > 0) {
        // Select previous tab, or next if it's the first
        const newIndex = Math.min(tabIndex, newTabs.length - 1)
        newActiveTabId = newTabs[newIndex].id
      }
    } else {
      newActiveTabId = activeTabId
    }

    set({
      openTabs: newTabs,
      activeTabId: newActiveTabId,
    })
  },

  /**
   * Set active tab
   */
  setActiveTab: (tabId) => {
    const tab = get().openTabs.find((t) => t.id === tabId)
    if (tab) {
      const note = get().notes.find((n) => n.id === tabId)
      set({ activeTabId: tabId, selectedNote: note || null })
    }
  },

  /**
   * Update tab content (locally, without saving)
   */
  updateTabContent: (tabId, content) => {
    const openTabs = get().openTabs.map((tab) =>
      tab.id === tabId ? { ...tab, content, isDirty: true } : tab
    )
    set({ openTabs })
  },

  /**
   * Mark tab as dirty or clean
   */
  markTabDirty: (tabId, isDirty) => {
    const openTabs = get().openTabs.map((tab) =>
      tab.id === tabId ? { ...tab, isDirty } : tab
    )
    set({ openTabs })
  },

  /**
   * Close all tabs
   */
  closeAllTabs: () => {
    set({ openTabs: [], activeTabId: null })
  },

  /**
   * Close all tabs except the specified one
   */
  closeOtherTabs: (tabId) => {
    const tab = get().openTabs.find((t) => t.id === tabId)
    if (tab) {
      set({ openTabs: [tab], activeTabId: tabId })
    }
  },

  /**
   * Select a note
   */
  selectNote: (note) => {
    set({ selectedNote: note })
  },

  /**
   * Set current application context
   */
  setCurrentApplication: (applicationId) => {
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

export const selectNotes = (state: NotesState): Note[] => state.notes

export const selectNoteTree = (state: NotesState): NoteTree[] => state.noteTree

export const selectSelectedNote = (state: NotesState): Note | null => state.selectedNote

export const selectOpenTabs = (state: NotesState): NoteTab[] => state.openTabs

export const selectActiveTabId = (state: NotesState): string | null => state.activeTabId

export const selectActiveTab = (state: NotesState): NoteTab | undefined =>
  state.openTabs.find((tab) => tab.id === state.activeTabId)

export const selectIsLoading = (state: NotesState): boolean => state.isLoading

export const selectError = (state: NotesState): NoteError | null => state.error

export default useNotesStore
