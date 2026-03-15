/**
 * Per-Query Persister for TanStack Query
 *
 * A custom persister that stores each query as a separate IndexedDB entry
 * with LZ-string compression. Features:
 *
 * - Per-query storage: Only modified queries are written (vs entire cache)
 * - LZ-string compression: 60-80% storage reduction
 * - Debounced writes: Batches updates (1s debounce)
 * - LRU eviction: Automatic cleanup when limits exceeded
 * - Progressive hydration: Critical queries loaded first
 */

import { compressToUTF16, decompressFromUTF16 } from 'lz-string'
import { Query, QueryClient, QueryKey, QueryState, hydrate } from '@tanstack/react-query'
import {
  QueryCacheEntry,
  getEntry,
  setEntry,
  deleteEntry,
  getEntriesByPrefixes,
  getAllEntries,
  clearAll,
  performLRUEviction,
  hashQueryKey,
  getCacheStats,
} from './query-cache-db'
import { CACHE_CONFIG, HYDRATION_PRIORITY, NON_PERSISTENT_KEYS } from './cache-config'

// ============================================================================
// Types
// ============================================================================

interface PersistedQuery {
  queryKey: QueryKey
  queryHash: string
  state: QueryState<unknown, unknown>
}

interface PendingWrite {
  queryKey: QueryKey
  state: QueryState<unknown, unknown>
}

// ============================================================================
// State
// ============================================================================

/** Pending writes waiting to be flushed */
const pendingWrites = new Map<string, PendingWrite>()

/** Debounce timer for batch writes */
let writeTimer: ReturnType<typeof setTimeout> | null = null

/** Flag to track if initial hydration is complete */
let hydrationComplete = false

/**
 * In-memory estimate of IndexedDB entry count.
 * Used to skip expensive IndexedDB eviction checks when well below threshold.
 * Initialized from first getCacheStats call, then maintained by writes/deletes.
 */
let entryCountEstimate = 0
let entryCountEstimateInitialized = false

// ============================================================================
// Helpers
// ============================================================================

/**
 * Check if a query key should be persisted.
 */
function shouldPersistQuery(queryKey: QueryKey): boolean {
  const firstKey = queryKey[0]
  if (typeof firstKey !== 'string') return true
  return !NON_PERSISTENT_KEYS.includes(firstKey as (typeof NON_PERSISTENT_KEYS)[number])
}

/**
 * Compress query state for storage.
 */
function compressState(state: QueryState<unknown, unknown>): string {
  const json = JSON.stringify(state)
  return compressToUTF16(json)
}

/**
 * Decompress query state from storage.
 */
function decompressState(compressed: string): QueryState<unknown, unknown> | null {
  try {
    const json = decompressFromUTF16(compressed)
    if (!json) return null
    return JSON.parse(json) as QueryState<unknown, unknown>
  } catch {
    return null
  }
}

/**
 * Check if query data is still valid (not expired).
 */
function isEntryValid(entry: QueryCacheEntry): boolean {
  const age = Date.now() - entry.dataUpdatedAt
  return age < CACHE_CONFIG.maxAge
}

// ============================================================================
// Write Operations (Debounced)
// ============================================================================

/**
 * Schedule a query to be persisted.
 * Writes are debounced to batch multiple updates.
 */
export function persistQuery(queryKey: QueryKey, state: QueryState<unknown, unknown>): void {
  if (!shouldPersistQuery(queryKey)) return

  const hash = hashQueryKey(queryKey)
  pendingWrites.set(hash, { queryKey, state })

  // Debounce the write
  if (writeTimer) {
    clearTimeout(writeTimer)
  }

  writeTimer = setTimeout(() => {
    flushPendingWrites()
  }, CACHE_CONFIG.debounceMs)
}

/**
 * Flush all pending writes to IndexedDB.
 */
async function flushPendingWrites(): Promise<void> {
  if (pendingWrites.size === 0) return

  // Snapshot pending writes and identify which are genuinely new entries.
  // Keys that were already pending are updates (the key existed in a prior
  // flush or in the current batch), so only count truly new keys toward the
  // entry estimate.
  const writes = Array.from(pendingWrites.entries())
  pendingWrites.clear()
  writeTimer = null

  const now = Date.now()

  // Track new vs update: if entryCountEstimate is initialized, we can infer
  // that a hash already seen in a previous flush is an update. However, we
  // don't maintain a full key set, so after eviction we reset the estimate
  // from actual stats (see below). For the normal path, count new inserts
  // by checking if the entry already exists in IndexedDB.
  let newInserts = 0

  // Process all pending writes
  await Promise.all(
    writes.map(async ([hash, { queryKey, state }]) => {
      // Check if this is a new entry (not already in IndexedDB)
      const existing = await getEntry(queryKey)
      if (!existing) newInserts++

      const compressed = compressState(state)
      const entry: QueryCacheEntry = {
        queryKeyHash: hash,
        queryKey: JSON.stringify(queryKey),
        data: compressed,
        dataUpdatedAt: now,
        accessedAt: now,
        size: JSON.stringify(state).length,
      }
      await setEntry(entry)
    })
  )

  // Only increment by genuinely new entries (not updates to existing keys)
  entryCountEstimate += newInserts

  // Only hit IndexedDB for eviction when in-memory estimate exceeds 90% threshold.
  // This avoids expensive getCacheStats calls on every write flush.
  const evictionThreshold = CACHE_CONFIG.maxEntries * CACHE_CONFIG.cleanupThreshold
  if (entryCountEstimate >= evictionThreshold || !entryCountEstimateInitialized) {
    performLRUEviction()
      .then(async () => {
        // After eviction, reset estimate to actual count from IndexedDB
        // to correct any accumulated drift.
        try {
          const stats = await getCacheStats()
          entryCountEstimate = stats.entryCount
        } catch {
          // If stats fail, leave estimate as-is
        }
        entryCountEstimateInitialized = true
      })
      .catch((err) => console.warn('[Persister] LRU eviction failed:', err))
  }
}

/**
 * Remove a query from persistence.
 */
export async function removeQuery(queryKey: QueryKey): Promise<void> {
  const hash = hashQueryKey(queryKey)

  // Remove from pending writes if present
  pendingWrites.delete(hash)

  // Remove from IndexedDB
  await deleteEntry(queryKey)

  // Update in-memory estimate
  if (entryCountEstimate > 0) entryCountEstimate--
}

// ============================================================================
// Read Operations
// ============================================================================

/**
 * Load a single query from persistence.
 */
export async function loadQuery(queryKey: QueryKey): Promise<PersistedQuery | null> {
  const entry = await getEntry(queryKey)
  if (!entry || !isEntryValid(entry)) return null

  const state = decompressState(entry.data)
  if (!state) return null

  return {
    queryKey: JSON.parse(entry.queryKey) as QueryKey,
    queryHash: entry.queryKeyHash,
    state,
  }
}

/**
 * Load multiple queries by prefix (for progressive hydration).
 */
async function loadQueriesByPrefixes(prefixes: readonly string[]): Promise<PersistedQuery[]> {
  const entries = await getEntriesByPrefixes(prefixes)
  const queries: PersistedQuery[] = []

  for (const entry of entries) {
    if (!isEntryValid(entry)) continue

    const state = decompressState(entry.data)
    if (!state) continue

    try {
      queries.push({
        queryKey: JSON.parse(entry.queryKey) as QueryKey,
        queryHash: entry.queryKeyHash,
        state,
      })
    } catch {
      // Skip invalid entries
    }
  }

  return queries
}

/**
 * Load all valid queries from persistence.
 */
export async function loadAllQueries(): Promise<PersistedQuery[]> {
  const entries = await getAllEntries()
  const queries: PersistedQuery[] = []

  for (const entry of entries) {
    if (!isEntryValid(entry)) continue

    const state = decompressState(entry.data)
    if (!state) continue

    try {
      queries.push({
        queryKey: JSON.parse(entry.queryKey) as QueryKey,
        queryHash: entry.queryKeyHash,
        state,
      })
    } catch {
      // Skip invalid entries
    }
  }

  return queries
}

// ============================================================================
// Hydration
// ============================================================================

/**
 * Hydrate queries into the query client.
 */
function hydrateQueries(queryClient: QueryClient, queries: PersistedQuery[]): void {
  for (const query of queries) {
    // Use the hydrate function to restore query state
    hydrate(queryClient, {
      mutations: [],
      queries: [
        {
          queryKey: query.queryKey,
          queryHash: query.queryHash,
          state: query.state,
        },
      ],
    })
  }
}

/**
 * Initialize progressive hydration.
 *
 * Phase 1 (blocking): Load critical queries (applications, projects)
 * Phase 2 (deferred): Load deferred queries after 2 seconds
 * Phase 3 (on-demand): Other queries loaded when requested
 */
export async function initializeHydration(queryClient: QueryClient): Promise<void> {
  if (hydrationComplete) return

  const startTime = performance.now()

  // Phase 1: Hydrate critical queries (blocking)
  const criticalQueries = await loadQueriesByPrefixes(HYDRATION_PRIORITY.critical)
  hydrateQueries(queryClient, criticalQueries)

  const phase1Time = performance.now() - startTime
  console.log(`[Persister] Phase 1 hydration: ${criticalQueries.length} queries in ${phase1Time.toFixed(0)}ms`)

  hydrationComplete = true

  // Phase 2: Deferred hydration (non-blocking)
  // Use requestIdleCallback when available so hydration runs during idle time
  // instead of a hard-coded 2s delay. Falls back to setTimeout(2000) if the
  // browser/Electron version doesn't support requestIdleCallback.
  const scheduleDeferred = (cb: () => void) => {
    if (typeof requestIdleCallback === 'function') {
      requestIdleCallback(cb, { timeout: 2000 })
    } else {
      setTimeout(cb, 2000)
    }
  }
  scheduleDeferred(async () => {
    const deferredStart = performance.now()
    const deferredQueries = await loadQueriesByPrefixes(HYDRATION_PRIORITY.deferred)
    hydrateQueries(queryClient, deferredQueries)
    const phase2Time = performance.now() - deferredStart
    console.log(`[Persister] Phase 2 hydration: ${deferredQueries.length} queries in ${phase2Time.toFixed(0)}ms`)
  })
}

/**
 * Check if hydration is complete.
 */
export function isHydrationComplete(): boolean {
  return hydrationComplete
}

// ============================================================================
// Query Client Integration
// ============================================================================

/**
 * Subscribe to query cache changes to persist updates.
 */
export function subscribeToQueryCache(queryClient: QueryClient): () => void {
  const queryCache = queryClient.getQueryCache()

  const unsubscribe = queryCache.subscribe((event) => {
    const query = event.query as Query<unknown, unknown, unknown, QueryKey>
    const queryKey = query.queryKey

    // Handle query removal - delete from IndexedDB
    if (event.type === 'removed') {
      removeQuery(queryKey)
      return
    }

    // Only handle data updates, not other events
    if (event.type !== 'updated') return

    const state = query.state

    // On error state, remove from persistence (don't persist errors)
    if (state.status === 'error') {
      removeQuery(queryKey)
      return
    }

    // If data is undefined (query was reset), remove from persistence
    if (state.data === undefined) {
      removeQuery(queryKey)
      return
    }

    persistQuery(queryKey, state)
  })

  return unsubscribe
}

// ============================================================================
// Cache Management
// ============================================================================

/**
 * Clear all persisted cache data.
 */
export async function clearPersistedCache(): Promise<void> {
  // Clear pending writes
  pendingWrites.clear()
  if (writeTimer) {
    clearTimeout(writeTimer)
    writeTimer = null
  }

  // Clear IndexedDB
  await clearAll()

  hydrationComplete = false
  entryCountEstimate = 0
  entryCountEstimateInitialized = false
  console.log('[Persister] Cache cleared')
}

/**
 * Force flush pending writes (for logout).
 */
export async function forceFlush(): Promise<void> {
  if (writeTimer) {
    clearTimeout(writeTimer)
    writeTimer = null
  }
  await flushPendingWrites()
}

/**
 * Get cache statistics for debugging.
 */
export async function getPersistedCacheStats(): Promise<{
  entryCount: number
  totalSize: number
  pendingWrites: number
}> {
  const stats = await getCacheStats()
  return {
    entryCount: stats.entryCount,
    totalSize: stats.totalSize,
    pendingWrites: pendingWrites.size,
  }
}
