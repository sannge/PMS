/**
 * IndexedDB Draft Persistence Store
 *
 * Provides crash-recovery draft persistence for document editing.
 * Unsaved editor content is auto-buffered to IndexedDB every ~2 seconds
 * of inactivity. On document open, if a draft newer than the server version
 * exists, the user sees a restore/discard prompt.
 *
 * Uses a separate `pm-drafts-db` database (not the query cache).
 */

import { openDB, DBSchema, IDBPDatabase } from 'idb'

// ============================================================================
// Types
// ============================================================================

export interface DraftEntry {
  /** Document ID (primary key) */
  documentId: string
  /** TipTap JSON content as a string */
  contentJson: string
  /** Document title at draft time */
  title: string
  /** Server's updated_at timestamp when doc was loaded (epoch ms) */
  serverUpdatedAt: number
  /** When this draft was written (epoch ms) */
  draftedAt: number
}

interface DraftDBSchema extends DBSchema {
  drafts: {
    key: string
    value: DraftEntry
    indexes: {
      'by-drafted-at': number
    }
  }
}

// ============================================================================
// Database Instance
// ============================================================================

let dbPromise: Promise<IDBPDatabase<DraftDBSchema>> | null = null
let cleanupRan = false

/**
 * Get or create the IndexedDB database connection for drafts.
 * On first open, runs cleanup of old drafts (>7 days).
 */
export function getDraftDB(): Promise<IDBPDatabase<DraftDBSchema>> {
  if (!dbPromise) {
    dbPromise = openDB<DraftDBSchema>('pm-drafts-db', 1, {
      upgrade(db) {
        const store = db.createObjectStore('drafts', {
          keyPath: 'documentId',
        })
        store.createIndex('by-drafted-at', 'draftedAt')
      },
      blocked() {
        console.warn('[DraftDB] Database blocked - close other tabs')
      },
      blocking() {
        console.warn('[DraftDB] This connection is blocking a version upgrade')
      },
      terminated() {
        console.warn('[DraftDB] Database connection terminated')
        dbPromise = null
      },
    })

    // Run cleanup once on first DB open
    if (!cleanupRan) {
      cleanupRan = true
      dbPromise.then(() => {
        cleanupOldDrafts(7).catch((err) =>
          console.warn('[DraftDB] Startup cleanup failed:', err)
        )
      })
    }
  }
  return dbPromise
}

// ============================================================================
// CRUD Operations
// ============================================================================

/**
 * Save a draft entry (upsert by documentId).
 */
export async function saveDraft(entry: DraftEntry): Promise<void> {
  try {
    const db = await getDraftDB()
    await db.put('drafts', entry)
  } catch (error) {
    console.warn('[DraftDB] Failed to save draft:', error)
  }
}

/**
 * Get a draft by document ID.
 */
export async function getDraft(documentId: string): Promise<DraftEntry | undefined> {
  try {
    const db = await getDraftDB()
    return await db.get('drafts', documentId)
  } catch (error) {
    console.warn('[DraftDB] Failed to get draft:', error)
    return undefined
  }
}

/**
 * Delete a draft by document ID.
 */
export async function deleteDraft(documentId: string): Promise<void> {
  try {
    const db = await getDraftDB()
    await db.delete('drafts', documentId)
  } catch (error) {
    console.warn('[DraftDB] Failed to delete draft:', error)
  }
}

/**
 * Delete drafts older than maxAgeDays.
 * Uses cursor on by-drafted-at index for efficient scanning.
 * Returns the number of entries deleted.
 */
export async function cleanupOldDrafts(maxAgeDays: number = 7): Promise<number> {
  try {
    const db = await getDraftDB()
    const cutoff = Date.now() - maxAgeDays * 86_400_000
    const tx = db.transaction('drafts', 'readwrite')
    const index = tx.store.index('by-drafted-at')

    let deleted = 0
    let cursor = await index.openCursor()

    while (cursor) {
      if (cursor.value.draftedAt < cutoff) {
        await cursor.delete()
        deleted++
        cursor = await cursor.continue()
      } else {
        // Index is ordered ascending, so all remaining are newer
        break
      }
    }

    await tx.done

    if (deleted > 0) {
      console.log(`[DraftDB] Cleaned up ${deleted} old drafts (>${maxAgeDays} days)`)
    }

    return deleted
  } catch (error) {
    console.warn('[DraftDB] Failed to cleanup old drafts:', error)
    return 0
  }
}
