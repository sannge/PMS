/**
 * Knowledge Base Context
 *
 * React Context for managing UI-only state for the Notes screen.
 * Handles scope selection, sidebar state, folder expansion, document selection,
 * search query, and active tag filters.
 *
 * Data fetching is NOT handled here - it lives in TanStack Query hooks.
 * This context only manages ephemeral UI state with localStorage persistence
 * for sidebar collapsed state, expanded folders, and scope selection.
 */

import {
  createContext,
  useContext,
  useReducer,
  useCallback,
  useEffect,
  type ReactNode,
} from 'react'

// ============================================================================
// Types
// ============================================================================

export type ScopeType = 'all' | 'personal' | 'application' | 'project'

interface KnowledgeBaseUIState {
  scope: ScopeType
  scopeId: string | null
  isSidebarCollapsed: boolean
  expandedFolderIds: Set<string>
  selectedDocumentId: string | null
  selectedFolderId: string | null
  searchQuery: string
  activeTagIds: string[]
}

interface KnowledgeBaseContextValue extends KnowledgeBaseUIState {
  setScope: (scope: ScopeType, scopeId: string | null) => void
  toggleSidebar: () => void
  toggleFolder: (folderId: string) => void
  expandFolder: (folderId: string) => void
  collapseFolder: (folderId: string) => void
  selectDocument: (documentId: string | null) => void
  selectFolder: (folderId: string | null) => void
  setSearch: (query: string) => void
  toggleTag: (tagId: string) => void
  clearTags: () => void
  resetSelection: () => void
}

// ============================================================================
// Constants
// ============================================================================

const STORAGE_KEY_SIDEBAR = 'kb-sidebar-collapsed'
const STORAGE_KEY_EXPANDED = 'kb-expanded-folders'
const STORAGE_KEY_SCOPE = 'kb-scope'
const STORAGE_KEY_SCOPE_ID = 'kb-scope-id'

// ============================================================================
// Persistence Helpers
// ============================================================================

function loadBoolean(key: string, fallback: boolean): boolean {
  try {
    const stored = localStorage.getItem(key)
    if (stored !== null) return stored === 'true'
  } catch {
    // Ignore storage errors
  }
  return fallback
}

function loadString(key: string, fallback: string): string {
  try {
    const stored = localStorage.getItem(key)
    if (stored !== null) return stored
  } catch {
    // Ignore storage errors
  }
  return fallback
}

function loadStringOrNull(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function loadExpandedFolders(): Set<string> {
  try {
    const stored = localStorage.getItem(STORAGE_KEY_EXPANDED)
    if (stored) {
      const parsed = JSON.parse(stored)
      if (Array.isArray(parsed)) {
        return new Set(parsed)
      }
    }
  } catch {
    // Ignore parsing errors
  }
  return new Set()
}

function persistValue(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    // Ignore storage errors
  }
}

function persistExpandedFolders(ids: Set<string>): void {
  try {
    localStorage.setItem(STORAGE_KEY_EXPANDED, JSON.stringify(Array.from(ids)))
  } catch {
    // Ignore storage errors
  }
}

// ============================================================================
// Reducer
// ============================================================================

type KnowledgeBaseAction =
  | { type: 'SET_SCOPE'; scope: ScopeType; scopeId: string | null }
  | { type: 'TOGGLE_SIDEBAR' }
  | { type: 'SET_SIDEBAR_COLLAPSED'; collapsed: boolean }
  | { type: 'TOGGLE_FOLDER'; folderId: string }
  | { type: 'EXPAND_FOLDER'; folderId: string }
  | { type: 'COLLAPSE_FOLDER'; folderId: string }
  | { type: 'SELECT_DOCUMENT'; documentId: string | null }
  | { type: 'SELECT_FOLDER'; folderId: string | null }
  | { type: 'SET_SEARCH'; query: string }
  | { type: 'TOGGLE_TAG'; tagId: string }
  | { type: 'CLEAR_TAGS' }
  | { type: 'RESET_SELECTION' }

function knowledgeBaseReducer(
  state: KnowledgeBaseUIState,
  action: KnowledgeBaseAction
): KnowledgeBaseUIState {
  switch (action.type) {
    case 'SET_SCOPE':
      return {
        ...state,
        scope: action.scope,
        scopeId: action.scopeId,
        selectedDocumentId: null,
        selectedFolderId: null,
        activeTagIds: [],
      }

    case 'TOGGLE_SIDEBAR':
      return {
        ...state,
        isSidebarCollapsed: !state.isSidebarCollapsed,
      }

    case 'SET_SIDEBAR_COLLAPSED':
      return {
        ...state,
        isSidebarCollapsed: action.collapsed,
      }

    case 'TOGGLE_FOLDER': {
      const next = new Set(state.expandedFolderIds)
      if (next.has(action.folderId)) {
        next.delete(action.folderId)
      } else {
        next.add(action.folderId)
      }
      return { ...state, expandedFolderIds: next }
    }

    case 'EXPAND_FOLDER': {
      const next = new Set(state.expandedFolderIds)
      next.add(action.folderId)
      return { ...state, expandedFolderIds: next }
    }

    case 'COLLAPSE_FOLDER': {
      const next = new Set(state.expandedFolderIds)
      next.delete(action.folderId)
      return { ...state, expandedFolderIds: next }
    }

    case 'SELECT_DOCUMENT':
      return { ...state, selectedDocumentId: action.documentId }

    case 'SELECT_FOLDER':
      return { ...state, selectedFolderId: action.folderId }

    case 'SET_SEARCH':
      return { ...state, searchQuery: action.query }

    case 'TOGGLE_TAG': {
      const idx = state.activeTagIds.indexOf(action.tagId)
      const next =
        idx >= 0
          ? state.activeTagIds.filter((id) => id !== action.tagId)
          : [...state.activeTagIds, action.tagId]
      return { ...state, activeTagIds: next }
    }

    case 'CLEAR_TAGS':
      return { ...state, activeTagIds: [] }

    case 'RESET_SELECTION':
      return {
        ...state,
        selectedDocumentId: null,
        selectedFolderId: null,
      }

    default:
      return state
  }
}

// ============================================================================
// Context
// ============================================================================

const KnowledgeBaseContext = createContext<KnowledgeBaseContextValue | null>(null)

interface KnowledgeBaseProviderProps {
  children: ReactNode
  initialScope?: ScopeType
  initialScopeId?: string | null
}

export function KnowledgeBaseProvider({
  children,
  initialScope,
  initialScopeId,
}: KnowledgeBaseProviderProps): JSX.Element {
  const [state, dispatch] = useReducer(knowledgeBaseReducer, undefined, () => {
    const storedScope = loadString(STORAGE_KEY_SCOPE, 'all') as ScopeType
    const storedScopeId = loadStringOrNull(STORAGE_KEY_SCOPE_ID)

    return {
      scope: initialScope ?? storedScope,
      scopeId: initialScopeId !== undefined ? (initialScopeId ?? null) : storedScopeId,
      isSidebarCollapsed: loadBoolean(STORAGE_KEY_SIDEBAR, false),
      expandedFolderIds: loadExpandedFolders(),
      selectedDocumentId: null,
      selectedFolderId: null,
      searchQuery: '',
      activeTagIds: [],
    }
  })

  // Persist sidebar collapsed state
  useEffect(() => {
    persistValue(STORAGE_KEY_SIDEBAR, String(state.isSidebarCollapsed))
  }, [state.isSidebarCollapsed])

  // Persist expanded folders
  useEffect(() => {
    persistExpandedFolders(state.expandedFolderIds)
  }, [state.expandedFolderIds])

  // Persist scope
  useEffect(() => {
    persistValue(STORAGE_KEY_SCOPE, state.scope)
    if (state.scopeId) {
      persistValue(STORAGE_KEY_SCOPE_ID, state.scopeId)
    } else {
      try {
        localStorage.removeItem(STORAGE_KEY_SCOPE_ID)
      } catch {
        // Ignore
      }
    }
  }, [state.scope, state.scopeId])

  // Action callbacks
  const setScope = useCallback((scope: ScopeType, scopeId: string | null) => {
    dispatch({ type: 'SET_SCOPE', scope, scopeId })
  }, [])

  const toggleSidebar = useCallback(() => {
    dispatch({ type: 'TOGGLE_SIDEBAR' })
  }, [])

  const toggleFolder = useCallback((folderId: string) => {
    dispatch({ type: 'TOGGLE_FOLDER', folderId })
  }, [])

  const expandFolder = useCallback((folderId: string) => {
    dispatch({ type: 'EXPAND_FOLDER', folderId })
  }, [])

  const collapseFolder = useCallback((folderId: string) => {
    dispatch({ type: 'COLLAPSE_FOLDER', folderId })
  }, [])

  const selectDocument = useCallback((documentId: string | null) => {
    dispatch({ type: 'SELECT_DOCUMENT', documentId })
  }, [])

  const selectFolder = useCallback((folderId: string | null) => {
    dispatch({ type: 'SELECT_FOLDER', folderId })
  }, [])

  const setSearch = useCallback((query: string) => {
    dispatch({ type: 'SET_SEARCH', query })
  }, [])

  const toggleTag = useCallback((tagId: string) => {
    dispatch({ type: 'TOGGLE_TAG', tagId })
  }, [])

  const clearTags = useCallback(() => {
    dispatch({ type: 'CLEAR_TAGS' })
  }, [])

  const resetSelection = useCallback(() => {
    dispatch({ type: 'RESET_SELECTION' })
  }, [])

  const value: KnowledgeBaseContextValue = {
    ...state,
    setScope,
    toggleSidebar,
    toggleFolder,
    expandFolder,
    collapseFolder,
    selectDocument,
    selectFolder,
    setSearch,
    toggleTag,
    clearTags,
    resetSelection,
  }

  return (
    <KnowledgeBaseContext.Provider value={value}>
      {children}
    </KnowledgeBaseContext.Provider>
  )
}

// ============================================================================
// Hook
// ============================================================================

export function useKnowledgeBase(): KnowledgeBaseContextValue {
  const context = useContext(KnowledgeBaseContext)
  if (!context) {
    throw new Error('useKnowledgeBase must be used within a KnowledgeBaseProvider')
  }
  return context
}

export default KnowledgeBaseContext
