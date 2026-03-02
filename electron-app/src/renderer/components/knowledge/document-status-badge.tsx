/**
 * DocumentStatusBadge
 *
 * Unified badge merging the former DocumentIndexBadge and DocumentSyncBadge.
 *
 * 4 states:
 * - "indexed" (green): embeddings up-to-date
 * - "indexing" (yellow pulse): reindex or sync in progress
 * - "not-indexed" (gray): never embedded
 * - "stale" (orange): document changed since last embedding
 *
 * Two variants:
 * - "badge": Full badge with text + Radix Popover (for document header)
 * - "dot": Small colored dot indicator (for tree views)
 */

import { useCallback } from 'react'
import { RefreshCw, Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  useDocumentIndexStatus,
  useReindexDocument,
  useSyncDocumentEmbeddings,
} from '@/hooks/use-ai-config'
import { formatRelativeTime, formatAbsoluteTime } from '@/lib/time-utils'
import { cn } from '@/lib/utils'

// ============================================================================
// Types
// ============================================================================

type StatusState = 'indexed' | 'indexing' | 'not-indexed' | 'stale'

interface DocumentStatusBadgeProps {
  documentId: string
  documentUpdatedAt?: string
  isEmbeddingStale?: boolean
  variant: 'badge' | 'dot'
  className?: string
}

// ============================================================================
// State Derivation
// ============================================================================

function deriveStatus(
  embeddingUpdatedAt: string | null | undefined,
  documentUpdatedAt: string | undefined,
  isEmbeddingStale: boolean | undefined,
  isOperationPending: boolean,
): StatusState {
  if (isOperationPending) return 'indexing'
  if (!embeddingUpdatedAt && isEmbeddingStale !== false) return 'not-indexed'

  // Use isEmbeddingStale from the document model if available
  if (isEmbeddingStale === true) return 'stale'
  if (isEmbeddingStale === false) return 'indexed'

  // Fallback: compare timestamps
  if (embeddingUpdatedAt && documentUpdatedAt) {
    const embedDate = new Date(embeddingUpdatedAt).getTime()
    const docDate = new Date(documentUpdatedAt).getTime()
    return docDate > embedDate ? 'stale' : 'indexed'
  }

  return embeddingUpdatedAt ? 'indexed' : 'not-indexed'
}

const STATE_CONFIG: Record<
  StatusState,
  { dotClass: string; label: string; textClass: string; borderClass: string; bgClass: string }
> = {
  indexed: {
    dotClass: 'bg-green-500',
    label: 'Indexed',
    textClass: 'text-green-700 dark:text-green-400',
    borderClass: 'border-green-300/50 dark:border-green-700/50',
    bgClass: 'bg-green-50/80 dark:bg-green-950/30',
  },
  indexing: {
    dotClass: 'bg-yellow-500 animate-pulse',
    label: 'Syncing...',
    textClass: 'text-yellow-700 dark:text-yellow-400',
    borderClass: 'border-yellow-300/50 dark:border-yellow-700/50',
    bgClass: 'bg-yellow-50/80 dark:bg-yellow-950/30',
  },
  'not-indexed': {
    dotClass: 'bg-gray-400',
    label: 'Not indexed',
    textClass: 'text-muted-foreground',
    borderClass: 'border-border/50',
    bgClass: 'bg-background/80',
  },
  stale: {
    dotClass: 'bg-orange-500',
    label: 'Stale',
    textClass: 'text-orange-700 dark:text-orange-400',
    borderClass: 'border-orange-300/50 dark:border-orange-700/50',
    bgClass: 'bg-orange-50/80 dark:bg-orange-950/30',
  },
}

// ============================================================================
// DocumentStatusBadge
// ============================================================================

export function DocumentStatusBadge({
  documentId,
  documentUpdatedAt,
  isEmbeddingStale,
  variant,
  className,
}: DocumentStatusBadgeProps) {
  const { data: indexStatus } = useDocumentIndexStatus(
    variant === 'badge' ? documentId : null
  )
  const reindexDoc = useReindexDocument()
  const syncDoc = useSyncDocumentEmbeddings()

  const embeddingUpdatedAt = indexStatus?.embedding_updated_at ?? null
  const isOperationPending = reindexDoc.isPending || syncDoc.isPending
  const state = deriveStatus(embeddingUpdatedAt, documentUpdatedAt, isEmbeddingStale, isOperationPending)
  const config = STATE_CONFIG[state]

  const handleSync = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation()
      syncDoc.mutate(documentId, {
        onSuccess: () => toast.success('Embedding sync started'),
        onError: (err) => toast.error('Sync failed', { description: err.message }),
      })
    },
    [documentId, syncDoc]
  )

  const handleReindex = useCallback(() => {
    reindexDoc.mutate(documentId)
  }, [documentId, reindexDoc])

  // ---- Dot variant ----
  if (variant === 'dot') {
    if (state === 'indexed') return null
    if (state === 'not-indexed') return null

    if (state === 'stale') {
      return (
        <button
          type="button"
          className={cn(
            'inline-block h-1.5 w-1.5 rounded-full shrink-0 cursor-pointer',
            config.dotClass,
            'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring focus-visible:ring-offset-1',
            className,
          )}
          title="Stale - click to sync embeddings"
          aria-label="Embedding stale - click to sync"
          onClick={handleSync}
        />
      )
    }

    return (
      <span
        className={cn(
          'inline-block h-1.5 w-1.5 rounded-full shrink-0',
          config.dotClass,
          className,
        )}
        title="Syncing embeddings..."
        aria-label="Syncing embeddings"
      />
    )
  }

  // ---- Badge variant ----
  const relativeLabel =
    state === 'indexed' && embeddingUpdatedAt
      ? `Synced ${formatRelativeTime(embeddingUpdatedAt).replace(' ago', '')} ago`
      : config.label

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            'inline-flex items-center gap-1.5 rounded-full px-2 py-0.5',
            'text-[10px] font-medium leading-none',
            'border',
            config.borderClass,
            config.bgClass,
            'hover:bg-muted/60 transition-colors cursor-pointer',
            'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring',
            config.textClass,
            className,
          )}
          aria-label={`Index status: ${relativeLabel}`}
          aria-live="polite"
          aria-busy={state === 'indexing'}
        >
          <span
            className={cn('h-1.5 w-1.5 rounded-full shrink-0', config.dotClass)}
            aria-hidden="true"
          />
          {relativeLabel}
        </button>
      </PopoverTrigger>

      <PopoverContent side="bottom" align="start" className="w-64 p-3">
        <div className="space-y-3">
          <h4 className="text-xs font-semibold">Embedding Index</h4>

          <div className="space-y-1.5 text-xs">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Last synced</span>
              <span className="font-medium">
                {embeddingUpdatedAt
                  ? formatAbsoluteTime(embeddingUpdatedAt)
                  : 'Never'}
              </span>
            </div>
            {indexStatus && 'chunk_count' in indexStatus && (
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Chunks</span>
                <span className="font-medium">
                  {(indexStatus as unknown as { chunk_count: number }).chunk_count}
                </span>
              </div>
            )}
          </div>

          {state === 'indexing' && (
            <div className="flex items-center gap-1.5 text-xs text-yellow-700 dark:text-yellow-400">
              <Loader2 className="h-3 w-3 animate-spin" />
              Embedding in progress...
            </div>
          )}

          {state !== 'indexing' && (
            <div className="flex flex-col gap-1.5">
              <Button
                variant={state === 'stale' ? 'default' : 'outline'}
                size="sm"
                className={cn(
                  'w-full h-7 text-xs',
                  state === 'stale' && 'bg-gradient-to-br from-amber-400 to-orange-500 text-white hover:from-amber-500 hover:to-orange-600'
                )}
                onClick={handleSync}
                disabled={syncDoc.isPending}
              >
                {syncDoc.isPending ? (
                  <Loader2 className="h-3 w-3 animate-spin mr-1.5" />
                ) : (
                  <RefreshCw className="h-3 w-3 mr-1.5" />
                )}
                Sync Now
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="w-full h-7 text-xs"
                onClick={handleReindex}
                disabled={reindexDoc.isPending}
              >
                {reindexDoc.isPending ? (
                  <Loader2 className="h-3 w-3 animate-spin mr-1.5" />
                ) : (
                  <RefreshCw className="h-3 w-3 mr-1.5" />
                )}
                Reindex Now
              </Button>
            </div>
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}

export default DocumentStatusBadge
