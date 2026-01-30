/**
 * Notes Context
 *
 * React Context for managing notes state.
 * Handles CRUD operations for notes with API integration and tab management.
 *
 * Features:
 * - Note list with hierarchy support
 * - Create, read, update, delete operations
 * - Tab management for open notes
 * - Loading and error states
 * - Tree structure for note hierarchy
 */

import {
  createContext,
  useContext,
  useReducer,
  useCallback,
  type ReactNode,
} from 'react'
import { getAuthHeaders } from './auth-context'

// ============================================================================
// Types
// ============================================================================

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

export interface NoteTree extends Note {
  children: NoteTree[]
}

export interface NoteCreate {
  title: string
  content?: string | null
  tab_order?: number
  parent_id?: string | null
}

export interface NoteUpdate {
  title?: string
  content?: string | null
  tab_order?: number
  parent_id?: string | null
}

export interface NoteTab {
  id: string
  title: string
  isDirty: boolean
  content: string | null
}

export interface NoteError {
  message: string
  code?: string
  field?: string
}

interface NotesState {
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
  currentApplicationId: string | null
}

interface NotesContextValue extends NotesState {
  fetchNotes: (token: string | null, applicationId: string) => Promise<void>
  fetchNoteTree: (token: string | null, applicationId: string) => Promise<void>
  fetchNote: (token: string | null, noteId: string) => Promise<Note | null>
  createNote: (token: string | null, applicationId: string, data: NoteCreate) => Promise<Note | null>
  updateNote: (token: string | null, noteId: string, data: NoteUpdate) => Promise<Note | null>
  deleteNote: (token: string | null, noteId: string, cascade?: boolean) => Promise<boolean>
  reorderNote: (token: string | null, noteId: string, newOrder: number) => Promise<boolean>
  openTab: (note: Note) => void
  closeTab: (tabId: string) => void
  setActiveTab: (tabId: string) => void
  updateTabContent: (tabId: string, content: string) => void
  markTabDirty: (tabId: string, isDirty: boolean) => void
  closeAllTabs: () => void
  closeOtherTabs: (tabId: string) => void
  selectNote: (note: Note | null) => void
  setCurrentApplication: (applicationId: string | null) => void
  saveSession: () => void
  restoreSession: () => { tabIds: string[]; activeTabId: string | null; applicationId: string | null } | null
  restoreTabs: (token: string | null, tabIds: string[], activeTabId: string | null) => Promise<void>
  clearError: () => void
  reset: () => void
}

// ============================================================================
// Helper Functions
// ============================================================================

function parseApiError(status: number, data: unknown): NoteError {
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
// Reducer
// ============================================================================

type NotesAction =
  | { type: 'SET_LOADING'; payload: boolean }
  | { type: 'SET_CREATING'; payload: boolean }
  | { type: 'SET_UPDATING'; payload: boolean }
  | { type: 'SET_DELETING'; payload: boolean }
  | { type: 'SET_ERROR'; payload: NoteError | null }
  | { type: 'SET_NOTES'; payload: Note[] }
  | { type: 'SET_NOTE_TREE'; payload: NoteTree[] }
  | { type: 'SET_SELECTED_NOTE'; payload: Note | null }
  | { type: 'SET_CURRENT_APP'; payload: string | null }
  | { type: 'SET_OPEN_TABS'; payload: NoteTab[] }
  | { type: 'SET_ACTIVE_TAB'; payload: string | null }
  | { type: 'ADD_NOTE'; payload: Note }
  | { type: 'UPDATE_NOTE'; payload: Note }
  | { type: 'REMOVE_NOTE'; payload: string }
  | { type: 'RESET' }

const initialState: NotesState = {
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

function notesReducer(state: NotesState, action: NotesAction): NotesState {
  switch (action.type) {
    case 'SET_LOADING':
      return { ...state, isLoading: action.payload }
    case 'SET_CREATING':
      return { ...state, isCreating: action.payload }
    case 'SET_UPDATING':
      return { ...state, isUpdating: action.payload }
    case 'SET_DELETING':
      return { ...state, isDeleting: action.payload }
    case 'SET_ERROR':
      return { ...state, error: action.payload }
    case 'SET_NOTES':
      return { ...state, notes: action.payload }
    case 'SET_NOTE_TREE':
      return { ...state, noteTree: action.payload }
    case 'SET_SELECTED_NOTE':
      return { ...state, selectedNote: action.payload }
    case 'SET_CURRENT_APP':
      return { ...state, currentApplicationId: action.payload }
    case 'SET_OPEN_TABS':
      return { ...state, openTabs: action.payload }
    case 'SET_ACTIVE_TAB':
      return { ...state, activeTabId: action.payload }
    case 'ADD_NOTE':
      return { ...state, notes: [...state.notes, action.payload] }
    case 'UPDATE_NOTE':
      return {
        ...state,
        notes: state.notes.map((n) => (n.id === action.payload.id ? action.payload : n)),
      }
    case 'REMOVE_NOTE':
      return { ...state, notes: state.notes.filter((n) => n.id !== action.payload) }
    case 'RESET':
      return initialState
    default:
      return state
  }
}

// ============================================================================
// Context
// ============================================================================

const NotesContext = createContext<NotesContextValue | null>(null)

export function NotesProvider({ children }: { children: ReactNode }): JSX.Element {
  const [state, dispatch] = useReducer(notesReducer, initialState)

  const fetchNotes = useCallback(async (token: string | null, applicationId: string): Promise<void> => {
    dispatch({ type: 'SET_LOADING', payload: true })
    dispatch({ type: 'SET_ERROR', payload: null })
    dispatch({ type: 'SET_CURRENT_APP', payload: applicationId })

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
        dispatch({ type: 'SET_ERROR', payload: error })
      } else {
        dispatch({ type: 'SET_NOTES', payload: response.data || [] })
      }
    } catch (err) {
      dispatch({
        type: 'SET_ERROR',
        payload: { message: err instanceof Error ? err.message : 'Failed to fetch notes' },
      })
    } finally {
      dispatch({ type: 'SET_LOADING', payload: false })
    }
  }, [])

  const fetchNoteTree = useCallback(async (token: string | null, applicationId: string): Promise<void> => {
    dispatch({ type: 'SET_LOADING', payload: true })
    dispatch({ type: 'SET_ERROR', payload: null })
    dispatch({ type: 'SET_CURRENT_APP', payload: applicationId })

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
        dispatch({ type: 'SET_ERROR', payload: error })
      } else {
        dispatch({ type: 'SET_NOTE_TREE', payload: response.data || [] })
      }
    } catch (err) {
      dispatch({
        type: 'SET_ERROR',
        payload: { message: err instanceof Error ? err.message : 'Failed to fetch note tree' },
      })
    } finally {
      dispatch({ type: 'SET_LOADING', payload: false })
    }
  }, [])

  const fetchNote = useCallback(async (token: string | null, noteId: string): Promise<Note | null> => {
    dispatch({ type: 'SET_LOADING', payload: true })
    dispatch({ type: 'SET_ERROR', payload: null })

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
        dispatch({ type: 'SET_ERROR', payload: error })
        return null
      }

      dispatch({ type: 'SET_SELECTED_NOTE', payload: response.data })
      return response.data
    } catch (err) {
      dispatch({
        type: 'SET_ERROR',
        payload: { message: err instanceof Error ? err.message : 'Failed to fetch note' },
      })
      return null
    } finally {
      dispatch({ type: 'SET_LOADING', payload: false })
    }
  }, [])

  const createNote = useCallback(async (
    token: string | null,
    applicationId: string,
    data: NoteCreate
  ): Promise<Note | null> => {
    dispatch({ type: 'SET_CREATING', payload: true })
    dispatch({ type: 'SET_ERROR', payload: null })

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const payload = { ...data, application_id: applicationId }
      const response = await window.electronAPI.post<Note>(
        `/api/applications/${applicationId}/notes`,
        payload,
        getAuthHeaders(token)
      )

      if (response.status !== 201) {
        const error = parseApiError(response.status, response.data)
        dispatch({ type: 'SET_ERROR', payload: error })
        return null
      }

      dispatch({ type: 'ADD_NOTE', payload: response.data })

      // Refresh tree
      fetchNoteTree(token, applicationId)

      return response.data
    } catch (err) {
      dispatch({
        type: 'SET_ERROR',
        payload: { message: err instanceof Error ? err.message : 'Failed to create note' },
      })
      return null
    } finally {
      dispatch({ type: 'SET_CREATING', payload: false })
    }
  }, [fetchNoteTree])

  const updateNote = useCallback(async (
    token: string | null,
    noteId: string,
    data: NoteUpdate
  ): Promise<Note | null> => {
    dispatch({ type: 'SET_UPDATING', payload: true })
    dispatch({ type: 'SET_ERROR', payload: null })

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
        dispatch({ type: 'SET_ERROR', payload: error })
        return null
      }

      const updatedNote = response.data
      dispatch({ type: 'UPDATE_NOTE', payload: updatedNote })
      dispatch({ type: 'SET_SELECTED_NOTE', payload: updatedNote })

      // Update tab if open
      dispatch({
        type: 'SET_OPEN_TABS',
        payload: state.openTabs.map((tab) =>
          tab.id === noteId ? { ...tab, title: updatedNote.title, isDirty: false } : tab
        ),
      })

      // Refresh tree
      if (state.currentApplicationId) {
        fetchNoteTree(token, state.currentApplicationId)
      }

      return updatedNote
    } catch (err) {
      dispatch({
        type: 'SET_ERROR',
        payload: { message: err instanceof Error ? err.message : 'Failed to update note' },
      })
      return null
    } finally {
      dispatch({ type: 'SET_UPDATING', payload: false })
    }
  }, [state.openTabs, state.currentApplicationId, fetchNoteTree])

  const deleteNote = useCallback(async (
    token: string | null,
    noteId: string,
    cascade = false
  ): Promise<boolean> => {
    dispatch({ type: 'SET_DELETING', payload: true })
    dispatch({ type: 'SET_ERROR', payload: null })

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
        dispatch({ type: 'SET_ERROR', payload: error })
        return false
      }

      dispatch({ type: 'REMOVE_NOTE', payload: noteId })

      // Close tab if open
      const newTabs = state.openTabs.filter((tab) => tab.id !== noteId)
      dispatch({ type: 'SET_OPEN_TABS', payload: newTabs })

      if (state.activeTabId === noteId) {
        dispatch({
          type: 'SET_ACTIVE_TAB',
          payload: newTabs.length > 0 ? newTabs[newTabs.length - 1].id : null,
        })
      }

      dispatch({ type: 'SET_SELECTED_NOTE', payload: null })

      // Refresh tree
      if (state.currentApplicationId) {
        fetchNoteTree(token, state.currentApplicationId)
      }

      return true
    } catch (err) {
      dispatch({
        type: 'SET_ERROR',
        payload: { message: err instanceof Error ? err.message : 'Failed to delete note' },
      })
      return false
    } finally {
      dispatch({ type: 'SET_DELETING', payload: false })
    }
  }, [state.openTabs, state.activeTabId, state.currentApplicationId, fetchNoteTree])

  const reorderNote = useCallback(async (
    token: string | null,
    noteId: string,
    newOrder: number
  ): Promise<boolean> => {
    dispatch({ type: 'SET_UPDATING', payload: true })
    dispatch({ type: 'SET_ERROR', payload: null })

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
        dispatch({ type: 'SET_ERROR', payload: error })
        return false
      }

      // Refresh tree
      if (state.currentApplicationId) {
        fetchNoteTree(token, state.currentApplicationId)
      }

      return true
    } catch (err) {
      dispatch({
        type: 'SET_ERROR',
        payload: { message: err instanceof Error ? err.message : 'Failed to reorder note' },
      })
      return false
    } finally {
      dispatch({ type: 'SET_UPDATING', payload: false })
    }
  }, [state.currentApplicationId, fetchNoteTree])

  const openTab = useCallback((note: Note): void => {
    const existingTab = state.openTabs.find((tab) => tab.id === note.id)
    if (existingTab) {
      dispatch({ type: 'SET_ACTIVE_TAB', payload: note.id })
      return
    }

    const newTab: NoteTab = {
      id: note.id,
      title: note.title,
      isDirty: false,
      content: note.content,
    }

    dispatch({ type: 'SET_OPEN_TABS', payload: [...state.openTabs, newTab] })
    dispatch({ type: 'SET_ACTIVE_TAB', payload: note.id })
    dispatch({ type: 'SET_SELECTED_NOTE', payload: note })
  }, [state.openTabs])

  const closeTab = useCallback((tabId: string): void => {
    const tabIndex = state.openTabs.findIndex((tab) => tab.id === tabId)
    if (tabIndex === -1) return

    const newTabs = state.openTabs.filter((tab) => tab.id !== tabId)
    dispatch({ type: 'SET_OPEN_TABS', payload: newTabs })

    if (state.activeTabId === tabId) {
      if (newTabs.length > 0) {
        const newIndex = Math.min(tabIndex, newTabs.length - 1)
        dispatch({ type: 'SET_ACTIVE_TAB', payload: newTabs[newIndex].id })
      } else {
        dispatch({ type: 'SET_ACTIVE_TAB', payload: null })
      }
    }
  }, [state.openTabs, state.activeTabId])

  const setActiveTab = useCallback((tabId: string): void => {
    const tab = state.openTabs.find((t) => t.id === tabId)
    if (tab) {
      const note = state.notes.find((n) => n.id === tabId)
      dispatch({ type: 'SET_ACTIVE_TAB', payload: tabId })
      dispatch({ type: 'SET_SELECTED_NOTE', payload: note || null })
    }
  }, [state.openTabs, state.notes])

  const updateTabContent = useCallback((tabId: string, content: string): void => {
    dispatch({
      type: 'SET_OPEN_TABS',
      payload: state.openTabs.map((tab) =>
        tab.id === tabId ? { ...tab, content, isDirty: true } : tab
      ),
    })
  }, [state.openTabs])

  const markTabDirty = useCallback((tabId: string, isDirty: boolean): void => {
    dispatch({
      type: 'SET_OPEN_TABS',
      payload: state.openTabs.map((tab) =>
        tab.id === tabId ? { ...tab, isDirty } : tab
      ),
    })
  }, [state.openTabs])

  const closeAllTabs = useCallback((): void => {
    dispatch({ type: 'SET_OPEN_TABS', payload: [] })
    dispatch({ type: 'SET_ACTIVE_TAB', payload: null })
  }, [])

  const closeOtherTabs = useCallback((tabId: string): void => {
    const tab = state.openTabs.find((t) => t.id === tabId)
    if (tab) {
      dispatch({ type: 'SET_OPEN_TABS', payload: [tab] })
      dispatch({ type: 'SET_ACTIVE_TAB', payload: tabId })
    }
  }, [state.openTabs])

  const selectNote = useCallback((note: Note | null): void => {
    dispatch({ type: 'SET_SELECTED_NOTE', payload: note })
  }, [])

  const setCurrentApplication = useCallback((applicationId: string | null): void => {
    dispatch({ type: 'SET_CURRENT_APP', payload: applicationId })
  }, [])

  const saveSession = useCallback((): void => {
    const sessionData = {
      openTabs: state.openTabs.map((tab) => ({ id: tab.id, title: tab.title })),
      activeTabId: state.activeTabId,
      currentApplicationId: state.currentApplicationId,
      savedAt: new Date().toISOString(),
    }
    try {
      localStorage.setItem('pm-notes-session', JSON.stringify(sessionData))
    } catch {
      // Ignore storage errors
    }
  }, [state.openTabs, state.activeTabId, state.currentApplicationId])

  const restoreSession = useCallback((): {
    tabIds: string[]
    activeTabId: string | null
    applicationId: string | null
  } | null => {
    try {
      const saved = localStorage.getItem('pm-notes-session')
      if (!saved) return null

      const sessionData = JSON.parse(saved)
      const savedAt = new Date(sessionData.savedAt)
      const now = new Date()
      const diffDays = (now.getTime() - savedAt.getTime()) / (1000 * 60 * 60 * 24)

      if (diffDays > 7) {
        localStorage.removeItem('pm-notes-session')
        return null
      }

      return {
        tabIds: sessionData.openTabs?.map((t: { id: string }) => t.id) || [],
        activeTabId: sessionData.activeTabId,
        applicationId: sessionData.currentApplicationId,
      }
    } catch {
      return null
    }
  }, [])

  const restoreTabs = useCallback(async (
    token: string | null,
    tabIds: string[],
    activeTabId: string | null
  ): Promise<void> => {
    if (!window.electronAPI || tabIds.length === 0) return

    const openTabs: NoteTab[] = []

    for (const noteId of tabIds) {
      try {
        const response = await window.electronAPI.get<Note>(
          `/api/notes/${noteId}`,
          getAuthHeaders(token)
        )
        if (response.status === 200 && response.data) {
          openTabs.push({
            id: response.data.id,
            title: response.data.title,
            content: response.data.content,
            isDirty: false,
          })
        }
      } catch {
        // Skip notes that can't be fetched
      }
    }

    if (openTabs.length > 0) {
      const validActiveTabId = openTabs.find((t) => t.id === activeTabId)
        ? activeTabId
        : openTabs[0].id

      dispatch({ type: 'SET_OPEN_TABS', payload: openTabs })
      dispatch({ type: 'SET_ACTIVE_TAB', payload: validActiveTabId })
    }
  }, [])

  const clearError = useCallback((): void => {
    dispatch({ type: 'SET_ERROR', payload: null })
  }, [])

  const reset = useCallback((): void => {
    dispatch({ type: 'RESET' })
  }, [])

  const value: NotesContextValue = {
    ...state,
    fetchNotes,
    fetchNoteTree,
    fetchNote,
    createNote,
    updateNote,
    deleteNote,
    reorderNote,
    openTab,
    closeTab,
    setActiveTab,
    updateTabContent,
    markTabDirty,
    closeAllTabs,
    closeOtherTabs,
    selectNote,
    setCurrentApplication,
    saveSession,
    restoreSession,
    restoreTabs,
    clearError,
    reset,
  }

  return <NotesContext.Provider value={value}>{children}</NotesContext.Provider>
}

// ============================================================================
// Hook
// ============================================================================

export function useNotesStore(): NotesContextValue
export function useNotesStore<T>(selector: (state: NotesContextValue) => T): T
export function useNotesStore<T>(selector?: (state: NotesContextValue) => T): NotesContextValue | T {
  const context = useContext(NotesContext)
  if (!context) {
    throw new Error('useNotesStore must be used within a NotesProvider')
  }
  return selector ? selector(context) : context
}

// ============================================================================
// Selectors
// ============================================================================

export const selectNotes = (state: NotesContextValue): Note[] => state.notes
export const selectNoteTree = (state: NotesContextValue): NoteTree[] => state.noteTree
export const selectSelectedNote = (state: NotesContextValue): Note | null => state.selectedNote
export const selectOpenTabs = (state: NotesContextValue): NoteTab[] => state.openTabs
export const selectActiveTabId = (state: NotesContextValue): string | null => state.activeTabId
export const selectActiveTab = (state: NotesContextValue): NoteTab | undefined =>
  state.openTabs.find((tab) => tab.id === state.activeTabId)
export const selectIsLoading = (state: NotesContextValue): boolean => state.isLoading
export const selectError = (state: NotesContextValue): NoteError | null => state.error

export default NotesContext
