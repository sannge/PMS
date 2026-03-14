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
  /** Backend-managed embedding status */
  embeddingStatus?: 'none' | 'stale' | 'syncing' | 'synced'
  variant: 'badge' | 'dot'
  className?: string
}

// ============================================================================
// State Derivation
// ============================================================================

function mapStatus(embeddingStatus: 'none' | 'stale' | 'syncing' | 'synced' | undefined): StatusState {
  switch (embeddingStatus) {
    case 'synced': return 'indexed'
    case 'syncing': return 'indexing'
    case 'stale': return 'stale'
    default: return 'not-indexed'
  }
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
// StatusDot — lightweight dot variant (no mutation hook)
// ============================================================================

function StatusDot({
  documentId,
  embeddingStatus,
  className,
}: Omit<DocumentStatusBadgeProps, 'variant'>) {
  const syncDoc = useSyncDocumentEmbeddings()
  const state = syncDoc.isPending || embeddingStatus === 'syncing'
    ? 'indexing'
    : mapStatus(embeddingStatus)
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

  if (state === 'indexed' || state === 'not-indexed') return null

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

// ============================================================================
// StatusBadge — full popover variant (owns query + mutation hooks)
// ============================================================================

function StatusBadge({
  documentId,
  embeddingStatus,
  className,
}: Omit<DocumentStatusBadgeProps, 'variant'>) {
  const { data: indexStatus } = useDocumentIndexStatus(documentId)
  const syncDoc = useSyncDocumentEmbeddings()

  const embeddingUpdatedAt = indexStatus?.embedding_updated_at ?? null
  const isOperationPending = syncDoc.isPending || embeddingStatus === 'syncing'
  const state = isOperationPending ? 'indexing' : mapStatus(embeddingStatus)
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
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}

// ============================================================================
// DocumentStatusBadge — delegates to variant-specific component
// ============================================================================

export function DocumentStatusBadge({
  documentId,
  embeddingStatus,
  variant,
  className,
}: DocumentStatusBadgeProps) {
  if (variant === 'dot') {
    return <StatusDot documentId={documentId} embeddingStatus={embeddingStatus} className={className} />
  }
  return <StatusBadge documentId={documentId} embeddingStatus={embeddingStatus} className={className} />
}

export default DocumentStatusBadge
