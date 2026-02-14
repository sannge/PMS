/**
 * Knowledge Base Context
 *
 * React Context for managing UI-only state for the Notes screen.
 * Handles scope selection, sidebar state, folder expansion, document selection,
 * search query, active tab, and active tag filters.
 *
 * Data fetching is NOT handled here - it lives in TanStack Query hooks.
 * This context only manages ephemeral UI state with localStorage persistence
 * for sidebar collapsed state, expanded folders, scope selection, and active tab.
 *
 * Supports storagePrefix prop to avoid localStorage conflicts when multiple
 * KnowledgeBaseProvider instances are mounted simultaneously.
 */

import {
  createContext,
  useContext,
  useReducer,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  type ReactNode,
} from 'react'

// ============================================================================
// Types
// ============================================================================

export type ScopeType = 'personal' | 'application' | 'project'

interface KnowledgeBaseUIState {
  scope: ScopeType
  scopeId: string | null
  activeTab: string
  isSidebarCollapsed: boolean
  expandedFolderIds: Set<string>
  selectedDocumentId: string | null
  selectedFolderId: string | null
  searchQuery: string
  activeTagIds: string[]
  searchHighlightTerms: string[]
  /** Which occurrence to scroll to after highlights are applied (0-based). -1 = no scroll. */
  searchScrollToOccurrence: number
}

/** Navigation guard callback. Returns true to allow navigation, false to block.
 *  `proceed` is the action to run after the user confirms discard. */
export type NavigationGuard = (targetDocId: string | null, proceed: () => void) => boolean

interface KnowledgeBaseContextValue extends KnowledgeBaseUIState {
  setScope: (scope: ScopeType, scopeId: string | null) => void
  setActiveTab: (tab: string) => void
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
  registerNavigationGuard: (guard: NavigationGuard) => void
  unregisterNavigationGuard: () => void
  navigateToDocument: (targetTab: string, documentId: string, searchTerms?: string[], folderId?: string, scrollToOccurrence?: number) => void
}

// ============================================================================
// Storage Key Helper
// ============================================================================

function getStorageKey(prefix: string, key: string): string {
  return `${prefix}${key}`
}

interface StorageKeys {
  sidebar: string
  expanded: string
  scope: string
  scopeId: string
  activeTab: string
}

function buildStorageKeys(prefix: string): StorageKeys {
  return {
    sidebar: getStorageKey(prefix, 'sidebar-collapsed'),
    expanded: getStorageKey(prefix, 'expanded-folders'),
    scope: getStorageKey(prefix, 'scope'),
    scopeId: getStorageKey(prefix, 'scope-id'),
    activeTab: getStorageKey(prefix, 'active-tab'),
  }
}

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

function loadExpandedFolders(key: string): Set<string> {
  try {
    const stored = localStorage.getItem(key)
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

function persistExpandedFolders(key: string, ids: Set<string>): void {
  try {
    localStorage.setItem(key, JSON.stringify(Array.from(ids)))
  } catch {
    // Ignore storage errors
  }
}

function removeValue(key: string): void {
  try {
    localStorage.removeItem(key)
  } catch {
    // Ignore storage errors
  }
}

/**
 * Derive scope and scopeId from a tab value.
 * - 'personal' -> scope='personal', scopeId=null
 * - 'app:{id}' -> scope='application', scopeId=id
 */
function deriveFromTab(tab: string): { scope: ScopeType; scopeId: string | null } {
  if (tab.startsWith('app:')) {
    return { scope: 'application', scopeId: tab.slice(4) }
  }
  return { scope: 'personal', scopeId: null }
}

// ============================================================================
// Reducer
// ============================================================================

type KnowledgeBaseAction =
  | { type: 'SET_SCOPE'; scope: ScopeType; scopeId: string | null }
  | { type: 'SET_ACTIVE_TAB'; tab: string }
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
  | { type: 'NAVIGATE_TO_DOCUMENT'; payload: { targetTab: string; documentId: string; searchTerms: string[]; folderId?: string; scrollToOccurrence?: number } }

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
        searchHighlightTerms: [],
        searchScrollToOccurrence: -1,
      }

    case 'SET_ACTIVE_TAB': {
      const { scope, scopeId } = deriveFromTab(action.tab)
      return {
        ...state,
        activeTab: action.tab,
        scope,
        scopeId,
        selectedDocumentId: null,
        selectedFolderId: null,
        activeTagIds: [],
        searchHighlightTerms: [],
        searchScrollToOccurrence: -1,
      }
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
      return { ...state, selectedDocumentId: action.documentId, searchHighlightTerms: [], searchScrollToOccurrence: -1 }

    case 'SELECT_FOLDER':
      return { ...state, selectedFolderId: action.folderId }

    case 'SET_SEARCH':
      return {
        ...state,
        searchQuery: action.query,
        searchHighlightTerms: action.query ? state.searchHighlightTerms : [],
      }

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
        searchHighlightTerms: [],
        searchScrollToOccurrence: -1,
      }

    case 'NAVIGATE_TO_DOCUMENT': {
      const { targetTab, documentId, searchTerms, folderId, scrollToOccurrence } = action.payload
      const expandedFolderIds = folderId
        ? new Set([...state.expandedFolderIds, folderId])
        : state.expandedFolderIds
      return {
        ...state,
        activeTab: targetTab,
        scope: targetTab === 'personal' ? 'personal' : 'application',
        scopeId: targetTab.startsWith('app:') ? targetTab.slice(4) : null,
        selectedDocumentId: documentId,
        selectedFolderId: null,
        searchHighlightTerms: searchTerms,
        searchScrollToOccurrence: scrollToOccurrence ?? 0,
        expandedFolderIds,
      }
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
  storagePrefix?: string
}

export function KnowledgeBaseProvider({
  children,
  initialScope,
  initialScopeId,
  storagePrefix,
}: KnowledgeBaseProviderProps): JSX.Element {
  const prefix = storagePrefix ?? 'kb-'
  const keys = useMemo(() => buildStorageKeys(prefix), [prefix])
  const navigationGuardRef = useRef<NavigationGuard | null>(null)

  const [state, dispatch] = useReducer(knowledgeBaseReducer, keys, (k) => {
    const storedScope = loadString(k.scope, 'personal')
    // Migrate from legacy 'all' scope
    const validScope: ScopeType =
      storedScope === 'personal' || storedScope === 'application' || storedScope === 'project'
        ? storedScope
        : 'personal'
    const storedScopeId = loadStringOrNull(k.scopeId)
    const storedActiveTab = loadString(k.activeTab, 'personal')

    return {
      scope: initialScope ?? validScope,
      scopeId: initialScopeId !== undefined ? (initialScopeId ?? null) : storedScopeId,
      activeTab: storedActiveTab,
      isSidebarCollapsed: loadBoolean(k.sidebar, false),
      expandedFolderIds: loadExpandedFolders(k.expanded),
      selectedDocumentId: null,
      selectedFolderId: null,
      searchQuery: '',
      activeTagIds: [],
      searchHighlightTerms: [],
      searchScrollToOccurrence: -1,
    }
  })

  // Persist sidebar collapsed state
  useEffect(() => {
    persistValue(keys.sidebar, String(state.isSidebarCollapsed))
  }, [keys.sidebar, state.isSidebarCollapsed])

  // Persist expanded folders
  useEffect(() => {
    persistExpandedFolders(keys.expanded, state.expandedFolderIds)
  }, [keys.expanded, state.expandedFolderIds])

  // Persist scope
  useEffect(() => {
    persistValue(keys.scope, state.scope)
    if (state.scopeId) {
      persistValue(keys.scopeId, state.scopeId)
    } else {
      removeValue(keys.scopeId)
    }
  }, [keys.scope, keys.scopeId, state.scope, state.scopeId])

  // Persist active tab
  useEffect(() => {
    persistValue(keys.activeTab, state.activeTab)
  }, [keys.activeTab, state.activeTab])

  // Action callbacks
  const setScope = useCallback((scope: ScopeType, scopeId: string | null) => {
    dispatch({ type: 'SET_SCOPE', scope, scopeId })
  }, [])

  const setActiveTab = useCallback((tab: string) => {
    // Tab change clears document selection — guard if editing
    const guard = navigationGuardRef.current
    if (guard && !guard(null, () => dispatch({ type: 'SET_ACTIVE_TAB', tab }))) return
    dispatch({ type: 'SET_ACTIVE_TAB', tab })
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
    // Check navigation guard before dispatching
    const guard = navigationGuardRef.current
    if (guard && !guard(documentId, () => dispatch({ type: 'SELECT_DOCUMENT', documentId }))) return
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

  const navigateToDocument = useCallback((targetTab: string, documentId: string, searchTerms?: string[], folderId?: string, scrollToOccurrence?: number) => {
    const guard = navigationGuardRef.current
    const payload = { targetTab, documentId, searchTerms: searchTerms ?? [], folderId, scrollToOccurrence }
    if (guard && !guard(documentId, () => dispatch({ type: 'NAVIGATE_TO_DOCUMENT', payload }))) return
    dispatch({ type: 'NAVIGATE_TO_DOCUMENT', payload })
  }, [])

  const registerNavigationGuard = useCallback((guard: NavigationGuard) => {
    navigationGuardRef.current = guard
  }, [])

  const unregisterNavigationGuard = useCallback(() => {
    navigationGuardRef.current = null
  }, [])

  const value: KnowledgeBaseContextValue = {
    ...state,
    setScope,
    setActiveTab,
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
    registerNavigationGuard,
    unregisterNavigationGuard,
    navigateToDocument,
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
