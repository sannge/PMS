/**
 * Cache Migration
 *
 * Handles migration from the legacy single-blob cache format to the new
 * per-query storage format. This ensures users don't lose their cached
 * data when upgrading.
 *
 * Legacy format:
 * - Single JSON blob under key 'pm-query-cache' in idb-keyval store
 * - Contains all queries in one object
 *
 * New format:
 * - Each query stored separately in 'pm-query-cache-db' database
 * - LZ-string compressed
 * - LRU tracking per entry
 */

import { get, del } from 'idb-keyval'
import { compressToUTF16, decompressFromUTF16 } from 'lz-string'
import { QueryState, QueryKey } from '@tanstack/react-query'
import { CACHE_CONFIG, NON_PERSISTENT_KEYS } from './cache-config'
import { QueryCacheEntry, setEntry, hashQueryKey } from './query-cache-db'

// ============================================================================
// Types
// ============================================================================

interface LegacyCacheData {
  timestamp: number
  buster: string
  clientState: {
    mutations: unknown[]
    queries: Array<{
      queryKey: QueryKey
      queryHash: string
      state: QueryState<unknown, unknown>
    }>
  }
}

// ============================================================================
// Migration Logic
// ============================================================================

/**
 * Check if migration has already been completed.
 */
async function isMigrationCompleted(): Promise<boolean> {
  try {
    const flag = await get<boolean>(CACHE_CONFIG.migrationFlagKey)
    return flag === true
  } catch {
    return false
  }
}

/**
 * Set the migration completed flag.
 */
async function setMigrationCompleted(): Promise<void> {
  try {
    const { set } = await import('idb-keyval')
    await set(CACHE_CONFIG.migrationFlagKey, true)
  } catch (error) {
    console.warn('[Migration] Failed to set migration flag:', error)
  }
}

/**
 * Check if a query key should be migrated.
 */
function shouldMigrateQuery(queryKey: QueryKey): boolean {
  const firstKey = queryKey[0]
  if (typeof firstKey !== 'string') return true
  return !NON_PERSISTENT_KEYS.includes(firstKey as (typeof NON_PERSISTENT_KEYS)[number])
}

/**
 * Read the legacy cache data.
 * Tries to decompress first (in case it was compressed), then plain JSON.
 */
async function readLegacyCache(): Promise<LegacyCacheData | null> {
  try {
    const raw = await get<string>(CACHE_CONFIG.legacyCacheKey)
    if (!raw) return null

    // Try to decompress (in case compression was added as a quick win)
    let json: string | null = null
    try {
      json = decompressFromUTF16(raw)
    } catch {
      // Not compressed
    }

    // If decompression didn't work, try plain JSON
    if (!json) {
      json = raw
    }

    return JSON.parse(json) as LegacyCacheData
  } catch (error) {
    console.warn('[Migration] Failed to read legacy cache:', error)
    return null
  }
}

/**
 * Delete the legacy cache after successful migration.
 */
async function deleteLegacyCache(): Promise<void> {
  try {
    await del(CACHE_CONFIG.legacyCacheKey)
  } catch (error) {
    console.warn('[Migration] Failed to delete legacy cache:', error)
  }
}

/**
 * Migrate a single query to the new format.
 */
async function migrateQuery(
  query: { queryKey: QueryKey; queryHash: string; state: QueryState<unknown, unknown> }
): Promise<boolean> {
  try {
    if (!shouldMigrateQuery(query.queryKey)) {
      return false
    }

    const now = Date.now()
    const stateJson = JSON.stringify(query.state)
    const compressed = compressToUTF16(stateJson)

    const entry: QueryCacheEntry = {
      queryKeyHash: hashQueryKey(query.queryKey),
      queryKey: JSON.stringify(query.queryKey),
      data: compressed,
      dataUpdatedAt: query.state.dataUpdatedAt ?? now,
      accessedAt: now,
      size: stateJson.length,
    }

    await setEntry(entry)
    return true
  } catch (error) {
    console.warn('[Migration] Failed to migrate query:', query.queryKey, error)
    return false
  }
}

/**
 * Perform the migration from legacy to new format.
 * Returns the number of queries migrated.
 */
export async function migrateFromLegacyCache(): Promise<number> {
  // Check if already migrated
  if (await isMigrationCompleted()) {
    console.log('[Migration] Already completed, skipping')
    return 0
  }

  const startTime = performance.now()

  // Read legacy cache
  const legacyData = await readLegacyCache()
  if (!legacyData) {
    // No legacy cache to migrate, mark as complete
    await setMigrationCompleted()
    console.log('[Migration] No legacy cache found')
    return 0
  }

  // Check if legacy data is too old
  const cacheAge = Date.now() - legacyData.timestamp
  if (cacheAge > CACHE_CONFIG.maxAge) {
    console.log('[Migration] Legacy cache expired, discarding')
    await deleteLegacyCache()
    await setMigrationCompleted()
    return 0
  }

  // Migrate each query
  const queries = legacyData.clientState?.queries ?? []
  let migratedCount = 0

  for (const query of queries) {
    const migrated = await migrateQuery(query)
    if (migrated) {
      migratedCount++
    }
  }

  // Clean up legacy cache
  await deleteLegacyCache()

  // Mark migration as complete
  await setMigrationCompleted()

  const duration = performance.now() - startTime
  console.log(
    `[Migration] Completed: migrated ${migratedCount}/${queries.length} queries in ${duration.toFixed(0)}ms`
  )

  return migratedCount
}

/**
 * Force re-run migration (for debugging).
 */
export async function forceMigration(): Promise<number> {
  try {
    await del(CACHE_CONFIG.migrationFlagKey)
  } catch {
    // Ignore errors
  }
  return migrateFromLegacyCache()
}
