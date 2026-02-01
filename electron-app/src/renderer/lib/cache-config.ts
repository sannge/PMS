/**
 * Cache Configuration
 *
 * Configuration constants for IndexedDB query cache with LRU eviction.
 */

export const CACHE_CONFIG = {
  /** Maximum number of cached query entries before LRU eviction */
  maxEntries: 1000,

  /** Maximum total cache size in bytes (50MB) */
  maxSizeBytes: 50 * 1024 * 1024,

  /** Trigger cleanup when cache reaches this percentage of max */
  cleanupThreshold: 0.9,

  /** Clean down to this percentage of max */
  cleanupTarget: 0.7,

  /** Debounce writes by this many milliseconds */
  debounceMs: 1000,

  /** IndexedDB database name */
  dbName: 'pm-query-cache-db',

  /** IndexedDB database version */
  dbVersion: 1,

  /** Store name for query cache entries */
  storeName: 'queries',

  /** Legacy cache key (for migration) */
  legacyCacheKey: 'pm-query-cache',

  /** Migration completed flag key */
  migrationFlagKey: 'pm-cache-migrated-v2',

  /** Maximum age for persisted cache (24 hours) */
  maxAge: 24 * 60 * 60 * 1000,
} as const

/**
 * Query key prefixes for progressive hydration prioritization
 */
export const HYDRATION_PRIORITY = {
  /** Critical queries - loaded immediately (blocking) */
  critical: ['applications', 'projects', 'myProjects', 'myTasks'] as const,

  /** Deferred queries - loaded after 2 seconds */
  deferred: ['notifications', 'appMembers', 'projectMembers', 'documentFolders'] as const,

  /** On-demand queries - loaded when view is opened */
  onDemand: ['tasks', 'comments', 'checklists', 'attachments', 'invitations', 'documents', 'documentTags'] as const,
} as const

/**
 * Query keys that should NOT be persisted (volatile data)
 */
export const NON_PERSISTENT_KEYS = [
  'downloadUrl',
  'downloadUrls',
  'search',
  'presence',
] as const
