/**
 * TanStack Query Client Configuration
 *
 * Configures the query client with:
 * - IndexedDB persistence for offline support
 * - Selective query persistence (excludes download URLs, search results)
 * - Stale-while-revalidate pattern for instant page loads
 * - Request deduplication built-in
 *
 * @see https://tanstack.com/query/latest
 */

import { QueryClient } from '@tanstack/react-query'
import { createAsyncStoragePersister } from '@tanstack/query-async-storage-persister'
import { persistQueryClient, PersistQueryClientOptions } from '@tanstack/react-query-persist-client'
import { get, set, del, clear } from 'idb-keyval'

// ============================================================================
// Constants
// ============================================================================

/** Cache storage key in IndexedDB */
const CACHE_KEY = 'pm-query-cache'

/** Maximum age for persisted cache (24 hours) */
const MAX_AGE = 24 * 60 * 60 * 1000

/** Default stale time (5 minutes) */
const DEFAULT_STALE_TIME = 5 * 60 * 1000

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

  // Tasks
  tasks: (projectId: string) => ['tasks', projectId] as const,
  task: (id: string) => ['task', id] as const,
  tasksByStatus: (projectId: string, status: string) => ['tasks', projectId, 'status', status] as const,

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

  // Statuses
  statuses: (projectId: string) => ['statuses', projectId] as const,
}

// ============================================================================
// IndexedDB Storage Adapter
// ============================================================================

/**
 * Custom IndexedDB storage adapter using idb-keyval.
 * Provides async storage operations for query persistence.
 */
const indexedDBStorage = {
  getItem: async (key: string): Promise<string | null> => {
    try {
      const value = await get(key)
      return value ?? null
    } catch (error) {
      console.warn('[QueryClient] Failed to read from IndexedDB:', error)
      return null
    }
  },

  setItem: async (key: string, value: string): Promise<void> => {
    try {
      await set(key, value)
    } catch (error) {
      console.warn('[QueryClient] Failed to write to IndexedDB:', error)
    }
  },

  removeItem: async (key: string): Promise<void> => {
    try {
      await del(key)
    } catch (error) {
      console.warn('[QueryClient] Failed to delete from IndexedDB:', error)
    }
  },
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
      // Data is fresh for 5 minutes by default
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
// Persistence Configuration
// ============================================================================

/**
 * Filter function to determine which queries should be persisted.
 * Excludes volatile data that shouldn't survive refresh.
 */
function shouldPersistQuery(queryKey: readonly unknown[]): boolean {
  const firstKey = queryKey[0]

  // Don't persist download URLs (presigned URLs expire)
  if (firstKey === 'downloadUrl' || firstKey === 'downloadUrls') {
    return false
  }

  // Don't persist search results (transient)
  if (firstKey === 'search') {
    return false
  }

  // Don't persist presence data (ephemeral)
  if (firstKey === 'presence') {
    return false
  }

  // Persist everything else
  return true
}

/**
 * Create the async storage persister with selective persistence.
 */
const persister = createAsyncStoragePersister({
  storage: indexedDBStorage,
  key: CACHE_KEY,
  serialize: (data) => {
    // Filter out queries that shouldn't be persisted
    const filtered = {
      ...data,
      clientState: {
        ...data.clientState,
        queries: data.clientState.queries.filter((query) =>
          shouldPersistQuery(query.queryKey)
        ),
      },
    }
    return JSON.stringify(filtered)
  },
  deserialize: (str) => JSON.parse(str),
})

/**
 * Initialize persistence after client is created.
 * Call this once in the app initialization.
 */
export async function initializeQueryPersistence(): Promise<void> {
  const persistOptions: PersistQueryClientOptions = {
    queryClient,
    persister,
    maxAge: MAX_AGE,
    buster: '', // Cache buster for version changes
  }

  await persistQueryClient(persistOptions)
  console.log('[QueryClient] Persistence initialized')
}

// ============================================================================
// Cache Management Functions
// ============================================================================

/**
 * Clear all cached queries from memory and IndexedDB.
 * Call this on logout for security.
 */
export async function clearQueryCache(): Promise<void> {
  // Clear in-memory cache
  queryClient.clear()

  // Clear IndexedDB cache
  try {
    await del(CACHE_KEY)
    console.log('[QueryClient] Cache cleared')
  } catch (error) {
    console.warn('[QueryClient] Failed to clear IndexedDB cache:', error)
  }
}

/**
 * Clear all IndexedDB data (for complete reset).
 */
export async function clearAllIndexedDB(): Promise<void> {
  try {
    await clear()
    console.log('[QueryClient] All IndexedDB data cleared')
  } catch (error) {
    console.warn('[QueryClient] Failed to clear IndexedDB:', error)
  }
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

// ============================================================================
// Export
// ============================================================================

export default queryClient
