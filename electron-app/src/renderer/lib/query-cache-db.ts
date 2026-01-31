/**
 * IndexedDB Query Cache Store
 *
 * Provides per-query storage with LRU tracking using the `idb` library.
 * Each query is stored as a separate entry for efficient partial updates.
 *
 * Schema:
 * - queryKeyHash: string (primary key) - Hash of the query key
 * - queryKey: string - Original key as JSON
 * - data: string - LZ-compressed query state
 * - dataUpdatedAt: number - Timestamp when data was last updated
 * - accessedAt: number - Timestamp when entry was last accessed (LRU)
 * - size: number - Uncompressed size in bytes
 */

import { openDB, DBSchema, IDBPDatabase } from 'idb'
import { CACHE_CONFIG } from './cache-config'

// ============================================================================
// Types
// ============================================================================

export interface QueryCacheEntry {
  /** Hash of query key (primary key) */
  queryKeyHash: string
  /** Original query key as JSON string */
  queryKey: string
  /** LZ-compressed query state */
  data: string
  /** Timestamp when data was last updated */
  dataUpdatedAt: number
  /** Timestamp when entry was last accessed (for LRU) */
  accessedAt: number
  /** Uncompressed data size in bytes */
  size: number
}

interface QueryCacheDB extends DBSchema {
  queries: {
    key: string
    value: QueryCacheEntry
    indexes: {
      'by-accessed': number
      'by-prefix': string
    }
  }
}

// ============================================================================
// Hash Function
// ============================================================================

/**
 * Generate a stable hash for a query key.
 * Uses a simple but fast hash algorithm.
 */
export function hashQueryKey(queryKey: readonly unknown[]): string {
  const str = JSON.stringify(queryKey)
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i)
    hash = ((hash << 5) - hash) + char
    hash = hash & hash // Convert to 32-bit integer
  }
  return hash.toString(36)
}

/**
 * Extract the prefix (first element) from a query key for indexing.
 */
export function getQueryKeyPrefix(queryKey: readonly unknown[]): string {
  const first = queryKey[0]
  return typeof first === 'string' ? first : JSON.stringify(first)
}

// ============================================================================
// Database Instance
// ============================================================================

let dbPromise: Promise<IDBPDatabase<QueryCacheDB>> | null = null

/**
 * Get or create the IndexedDB database connection.
 */
function getDB(): Promise<IDBPDatabase<QueryCacheDB>> {
  if (!dbPromise) {
    dbPromise = openDB<QueryCacheDB>(CACHE_CONFIG.dbName, CACHE_CONFIG.dbVersion, {
      upgrade(db) {
        // Create the queries store with indexes
        const store = db.createObjectStore('queries', {
          keyPath: 'queryKeyHash',
        })
        // Index for LRU queries (oldest first)
        store.createIndex('by-accessed', 'accessedAt')
        // Index for prefix-based queries (progressive hydration)
        store.createIndex('by-prefix', 'queryKey')
      },
      blocked() {
        console.warn('[QueryCacheDB] Database blocked - close other tabs')
      },
      blocking() {
        console.warn('[QueryCacheDB] This connection is blocking a version upgrade')
      },
      terminated() {
        console.warn('[QueryCacheDB] Database connection terminated')
        dbPromise = null
      },
    })
  }
  return dbPromise
}

// ============================================================================
// Core Operations
// ============================================================================

/**
 * Get a single cache entry by query key.
 * Updates accessedAt for LRU tracking.
 */
export async function getEntry(queryKey: readonly unknown[]): Promise<QueryCacheEntry | undefined> {
  try {
    const db = await getDB()
    const hash = hashQueryKey(queryKey)
    const entry = await db.get('queries', hash)

    if (entry) {
      // Update accessedAt for LRU (non-blocking)
      const updated = { ...entry, accessedAt: Date.now() }
      db.put('queries', updated).catch((err) =>
        console.warn('[QueryCacheDB] Failed to update accessedAt:', err)
      )
    }

    return entry
  } catch (error) {
    console.warn('[QueryCacheDB] Failed to get entry:', error)
    return undefined
  }
}

/**
 * Set a cache entry.
 */
export async function setEntry(entry: QueryCacheEntry): Promise<void> {
  try {
    const db = await getDB()
    await db.put('queries', entry)
  } catch (error) {
    console.warn('[QueryCacheDB] Failed to set entry:', error)
  }
}

/**
 * Delete a cache entry by query key.
 */
export async function deleteEntry(queryKey: readonly unknown[]): Promise<void> {
  try {
    const db = await getDB()
    const hash = hashQueryKey(queryKey)
    await db.delete('queries', hash)
  } catch (error) {
    console.warn('[QueryCacheDB] Failed to delete entry:', error)
  }
}

/**
 * Get all entries (for debugging/stats).
 */
export async function getAllEntries(): Promise<QueryCacheEntry[]> {
  try {
    const db = await getDB()
    return await db.getAll('queries')
  } catch (error) {
    console.warn('[QueryCacheDB] Failed to get all entries:', error)
    return []
  }
}

/**
 * Get entries whose query key starts with one of the given prefixes.
 * Used for progressive hydration.
 */
export async function getEntriesByPrefixes(prefixes: readonly string[]): Promise<QueryCacheEntry[]> {
  try {
    const db = await getDB()
    const allEntries = await db.getAll('queries')

    // Filter entries whose first query key element matches a prefix
    return allEntries.filter((entry) => {
      try {
        const queryKey = JSON.parse(entry.queryKey) as unknown[]
        const first = queryKey[0]
        const keyPrefix = typeof first === 'string' ? first : String(first)
        return prefixes.includes(keyPrefix)
      } catch {
        return false
      }
    })
  } catch (error) {
    console.warn('[QueryCacheDB] Failed to get entries by prefix:', error)
    return []
  }
}

/**
 * Get the oldest N entries by accessedAt (for LRU eviction).
 */
export async function getOldestEntries(count: number): Promise<QueryCacheEntry[]> {
  try {
    const db = await getDB()
    const tx = db.transaction('queries', 'readonly')
    const index = tx.store.index('by-accessed')

    const entries: QueryCacheEntry[] = []
    let cursor = await index.openCursor()

    while (cursor && entries.length < count) {
      entries.push(cursor.value)
      cursor = await cursor.continue()
    }

    return entries
  } catch (error) {
    console.warn('[QueryCacheDB] Failed to get oldest entries:', error)
    return []
  }
}

/**
 * Delete multiple entries by their hashes.
 */
export async function deleteEntries(hashes: string[]): Promise<void> {
  if (hashes.length === 0) return

  try {
    const db = await getDB()
    const tx = db.transaction('queries', 'readwrite')

    await Promise.all([
      ...hashes.map((hash) => tx.store.delete(hash)),
      tx.done,
    ])
  } catch (error) {
    console.warn('[QueryCacheDB] Failed to delete entries:', error)
  }
}

/**
 * Clear all entries from the cache.
 */
export async function clearAll(): Promise<void> {
  try {
    const db = await getDB()
    await db.clear('queries')
  } catch (error) {
    console.warn('[QueryCacheDB] Failed to clear cache:', error)
  }
}

// ============================================================================
// Statistics
// ============================================================================

export interface CacheStats {
  entryCount: number
  totalSize: number
  oldestAccess: number | null
  newestAccess: number | null
}

/**
 * Get cache statistics for monitoring.
 */
export async function getCacheStats(): Promise<CacheStats> {
  try {
    const entries = await getAllEntries()

    let totalSize = 0
    let oldestAccess: number | null = null
    let newestAccess: number | null = null

    for (const entry of entries) {
      totalSize += entry.size
      if (oldestAccess === null || entry.accessedAt < oldestAccess) {
        oldestAccess = entry.accessedAt
      }
      if (newestAccess === null || entry.accessedAt > newestAccess) {
        newestAccess = entry.accessedAt
      }
    }

    return {
      entryCount: entries.length,
      totalSize,
      oldestAccess,
      newestAccess,
    }
  } catch (error) {
    console.warn('[QueryCacheDB] Failed to get stats:', error)
    return {
      entryCount: 0,
      totalSize: 0,
      oldestAccess: null,
      newestAccess: null,
    }
  }
}

// ============================================================================
// LRU Eviction
// ============================================================================

/**
 * Perform LRU eviction if cache exceeds limits.
 * Returns the number of entries evicted.
 */
export async function performLRUEviction(): Promise<number> {
  const stats = await getCacheStats()
  const { maxEntries, maxSizeBytes, cleanupThreshold, cleanupTarget } = CACHE_CONFIG

  // Check if eviction is needed
  const entryThreshold = maxEntries * cleanupThreshold
  const sizeThreshold = maxSizeBytes * cleanupThreshold

  if (stats.entryCount < entryThreshold && stats.totalSize < sizeThreshold) {
    return 0 // No eviction needed
  }

  // Calculate how many entries to remove
  const targetEntries = Math.floor(maxEntries * cleanupTarget)
  const entriesToRemove = stats.entryCount - targetEntries

  if (entriesToRemove <= 0) {
    return 0
  }

  // Get and delete oldest entries
  const oldest = await getOldestEntries(entriesToRemove)
  const hashes = oldest.map((e) => e.queryKeyHash)
  await deleteEntries(hashes)

  console.log(`[QueryCacheDB] LRU eviction: removed ${hashes.length} entries`)
  return hashes.length
}
