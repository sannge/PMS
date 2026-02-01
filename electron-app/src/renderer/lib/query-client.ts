/**
 * TanStack Query Client Configuration
 *
 * Configures the query client with:
 * - Per-query IndexedDB persistence with LZ-string compression
 * - LRU eviction (max 1000 entries, 50MB)
 * - Progressive hydration (critical queries first)
 * - Stale-while-revalidate pattern for instant page loads
 * - Request deduplication built-in
 *
 * @see https://tanstack.com/query/latest
 */

import { QueryClient, focusManager } from '@tanstack/react-query'
import { migrateFromLegacyCache } from './cache-migration'
import {
  initializeHydration,
  subscribeToQueryCache,
  clearPersistedCache,
  forceFlush,
  getPersistedCacheStats,
  isHydrationComplete,
} from './per-query-persister'
import { clearAll as clearQueryCacheDB } from './query-cache-db'

// ============================================================================
// Electron Focus Manager
// ============================================================================
// Electron's document.visibilitychange doesn't fire on window focus/blur
// (only on minimize). Override with window focus/blur events so that
// refetchOnWindowFocus works correctly in the Electron renderer.

focusManager.setEventListener((handleFocus) => {
  const onFocus = () => handleFocus(true)
  const onBlur = () => handleFocus(false)

  window.addEventListener('focus', onFocus)
  window.addEventListener('blur', onBlur)

  return () => {
    window.removeEventListener('focus', onFocus)
    window.removeEventListener('blur', onBlur)
  }
})

// ============================================================================
// Constants
// ============================================================================

/** Default stale time (30 seconds) */
const DEFAULT_STALE_TIME = 30 * 1000

/** Default garbage collection time (24 hours) */
const DEFAULT_GC_TIME = 24 * 60 * 60 * 1000

// ============================================================================
// Query Keys
// ============================================================================

/**
 * Centralized query keys for cache management.
 * Using const assertions for type safety.
 */
export const queryKeys = {
  // Applications
  applications: ['applications'] as const,
  application: (id: string) => ['application', id] as const,

  // Projects
  projects: (appId: string) => ['projects', appId] as const,
  project: (id: string) => ['project', id] as const,
  archivedProjects: (appId: string) => ['projects', appId, 'archived'] as const,

  // Tasks
  tasks: (projectId: string) => ['tasks', projectId] as const,
  task: (id: string) => ['task', id] as const,
  tasksByStatus: (projectId: string, status: string) => ['tasks', projectId, 'status', status] as const,
  archivedTasks: (projectId: string) => ['tasks', projectId, 'archived'] as const,

  // My Tasks (application-level)
  myPendingTasks: (appId: string) => ['myTasks', appId, 'pending'] as const,
  myCompletedTasks: (appId: string) => ['myTasks', appId, 'completed'] as const,
  myArchivedTasks: (appId: string) => ['myTasks', appId, 'archived'] as const,

  // My Projects (application-level, dashboard)
  myProjects: (appId: string) => ['myProjects', appId] as const,

  // Cross-app dashboard
  myProjectsCrossApp: ['myProjects', 'cross-app'] as const,
  myTasksCrossApp: ['myTasks', 'cross-app'] as const,

  // Comments
  comments: (taskId: string) => ['comments', taskId] as const,
  comment: (id: string) => ['comment', id] as const,

  // Checklists
  checklists: (taskId: string) => ['checklists', taskId] as const,

  // Members
  appMembers: (appId: string) => ['appMembers', appId] as const,
  projectMembers: (projectId: string) => ['projectMembers', projectId] as const,

  // Notifications
  notifications: ['notifications'] as const,
  unreadCount: ['notifications', 'unread'] as const,

  // Attachments
  attachments: (taskId: string) => ['attachments', taskId] as const,
  downloadUrl: (attachmentId: string) => ['downloadUrl', attachmentId] as const,
  downloadUrls: (attachmentIds: string[]) => ['downloadUrls', ...attachmentIds.sort()] as const,

  // Invitations
  invitations: ['invitations'] as const,
  pendingInvitations: ['invitations', 'pending'] as const,
  receivedInvitations: (status?: string) => status ? ['invitations', 'received', status] as const : ['invitations', 'received'] as const,
  sentInvitations: (applicationId?: string) => applicationId ? ['invitations', 'sent', applicationId] as const : ['invitations', 'sent'] as const,
  pendingInvitationCount: ['invitations', 'count'] as const,

  // Statuses
  statuses: (projectId: string) => ['statuses', projectId] as const,

  // Documents
  documents: (scope: string, scopeId: string) => ['documents', scope, scopeId] as const,
  document: (id: string) => ['document', id] as const,

  // Document Folders
  documentFolders: (scope: string, scopeId: string) => ['documentFolders', scope, scopeId] as const,

  // Document Tags
  documentTags: (scope: string, scopeId: string) => ['documentTags', scope, scopeId] as const,

  // Document Locks
  documentLock: (documentId: string) => ['documentLock', documentId] as const,
}

// ============================================================================
// Query Client Configuration
// ============================================================================

/**
 * Create and configure the QueryClient with optimal defaults.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Data is fresh for 30 seconds by default
      staleTime: DEFAULT_STALE_TIME,

      // Keep unused data in cache for 24 hours (for offline support)
      gcTime: DEFAULT_GC_TIME,

      // Refresh data when window regains focus
      refetchOnWindowFocus: true,

      // Refresh data when network reconnects
      refetchOnReconnect: true,

      // Retry failed requests twice with exponential backoff
      retry: 2,
      retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 4000),

      // Don't throw errors, handle them in components
      throwOnError: false,

      // Don't refetch on mount if data is fresh
      refetchOnMount: true,
    },
    mutations: {
      // Retry mutations once
      retry: 1,

      // Don't throw errors
      throwOnError: false,
    },
  },
})

// ============================================================================
// Persistence State
// ============================================================================

/** Unsubscribe function for cache subscription */
let cacheUnsubscribe: (() => void) | null = null

// ============================================================================
// Persistence Initialization
// ============================================================================

/**
 * Initialize persistence with the new per-query storage.
 *
 * This performs:
 * 1. Migration from legacy single-blob cache (if exists)
 * 2. Progressive hydration of cached queries
 * 3. Subscription to cache changes for persistence
 *
 * Call this once in the app initialization.
 */
export async function initializeQueryPersistence(): Promise<void> {
  const startTime = performance.now()

  try {
    // Step 1: Migrate from legacy cache (if exists)
    await migrateFromLegacyCache()

    // Step 2: Hydrate critical queries (blocking)
    await initializeHydration(queryClient)

    // Step 3: Subscribe to cache changes for persistence
    if (cacheUnsubscribe) {
      cacheUnsubscribe()
    }
    cacheUnsubscribe = subscribeToQueryCache(queryClient)

    const duration = performance.now() - startTime
    console.log(`[QueryClient] Persistence initialized in ${duration.toFixed(0)}ms`)
  } catch (error) {
    console.warn('[QueryClient] Persistence init failed:', error)
    // Continue without persistence
  }
}

// ============================================================================
// Cache Management Functions
// ============================================================================

/**
 * Clear all cached queries from memory and IndexedDB.
 * Call this on logout for security.
 */
export async function clearQueryCache(): Promise<void> {
  // Unsubscribe from cache changes
  if (cacheUnsubscribe) {
    cacheUnsubscribe()
    cacheUnsubscribe = null
  }

  // Flush any pending writes
  await forceFlush()

  // Clear in-memory cache
  queryClient.clear()

  // Clear IndexedDB cache
  await clearPersistedCache()

  console.log('[QueryClient] Cache cleared')
}

/**
 * Clear all IndexedDB data (for complete reset).
 */
export async function clearAllIndexedDB(): Promise<void> {
  await clearQueryCacheDB()
  console.log('[QueryClient] All IndexedDB data cleared')
}

/**
 * Invalidate all queries for a specific entity type.
 * Useful for bulk invalidation after major changes.
 */
export function invalidateEntity(entityType: keyof typeof queryKeys): void {
  const key = queryKeys[entityType]
  if (typeof key === 'function') {
    // For factory functions, we can only invalidate with exact key
    console.warn(`[QueryClient] Cannot bulk invalidate factory key: ${entityType}`)
    return
  }
  queryClient.invalidateQueries({ queryKey: key })
}

/**
 * Prefetch a query in the background.
 * Useful for preloading data the user is likely to need.
 */
export async function prefetchQuery<T>(
  queryKey: readonly unknown[],
  queryFn: () => Promise<T>,
  staleTime?: number
): Promise<void> {
  await queryClient.prefetchQuery({
    queryKey,
    queryFn,
    staleTime: staleTime ?? DEFAULT_STALE_TIME,
  })
}

/**
 * Check if persistence hydration is complete.
 */
export function isPersistenceReady(): boolean {
  return isHydrationComplete()
}

/**
 * Get cache statistics for debugging.
 */
export async function getCacheStats(): Promise<{
  entryCount: number
  totalSize: number
  totalSizeMB: string
  pendingWrites: number
}> {
  const stats = await getPersistedCacheStats()
  return {
    ...stats,
    totalSizeMB: (stats.totalSize / (1024 * 1024)).toFixed(2),
  }
}

// ============================================================================
// Export
// ============================================================================

export default queryClient
