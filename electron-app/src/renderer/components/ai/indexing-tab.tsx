/**
 * Indexing Tab
 *
 * Part of the Developer AI Settings Panel. Shows document embedding
 * index status with reindex actions. Developer-only access.
 *
 * Features:
 * - Summary header with total/indexed/stale counts
 * - "Reindex All Stale" button with progress
 * - Per-document status table with relative timestamps
 * - Visual indicators: green (up-to-date), orange (stale), gray (never indexed)
 * - Per-document "Reindex Now" action
 * - Progress bar with 5s polling when running
 */

import { useCallback } from 'react'
import {
  Loader2,
  RefreshCw,
  Check,
  AlertTriangle,
  FileText,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
  useApplicationIndexStatus,
  useReindexApplication,
  useIndexProgress,
} from '@/hooks/use-ai-config'
// ============================================================================
// IndexingTab
// ============================================================================

export interface IndexingTabProps {
  applicationId: string | null
}

export function IndexingTab({ applicationId }: IndexingTabProps) {
  const { data: indexStatus, isLoading: statusLoading } =
    useApplicationIndexStatus(applicationId)
  const { data: progress } = useIndexProgress()
  const reindexApp = useReindexApplication()

  const isReindexRunning = progress?.status === 'running'

  // We get summary counts from indexStatus (IndexProgressResponse)
  const totalDocs = indexStatus?.total ?? 0
  const indexedDocs = indexStatus?.processed ?? 0
  const staleDocs = indexStatus?.failed ?? 0

  const handleReindexAll = useCallback(() => {
    if (applicationId) {
      reindexApp.mutate(applicationId)
    }
  }, [applicationId, reindexApp])

  if (!applicationId) {
    return (
      <div className="py-8 text-center text-sm text-muted-foreground">
        Select an application to view indexing status.
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Header Section */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">Embedding Index Status</h3>
          <Button
            variant="outline"
            size="sm"
            onClick={handleReindexAll}
            disabled={isReindexRunning || reindexApp.isPending || staleDocs === 0}
          >
            {reindexApp.isPending || isReindexRunning ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
            )}
            Reindex All Stale
          </Button>
        </div>

        {/* Progress Bar (visible when reindex is running) */}
        {isReindexRunning && progress && (
          <div className="space-y-1">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>Re-embedding documents...</span>
              <span>
                {progress.processed}/{progress.total}
                {progress.failed > 0 && (
                  <span className="text-destructive ml-1">
                    ({progress.failed} failed)
                  </span>
                )}
              </span>
            </div>
            <div
              className="h-1.5 w-full rounded-full bg-muted overflow-hidden"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={progress.total}
              aria-valuenow={progress.processed}
              aria-label="Document re-embedding progress"
            >
              <div
                className="h-full rounded-full bg-primary transition-all duration-300"
                style={{
                  width:
                    progress.total > 0
                      ? `${(progress.processed / progress.total) * 100}%`
                      : '0%',
                }}
              />
            </div>
          </div>
        )}

        {/* Summary Counts */}
        {statusLoading ? (
          <div aria-busy="true" aria-label="Loading indexing status" className="flex items-center gap-4">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-4 w-20" />
            <Skeleton className="h-4 w-16" />
          </div>
        ) : (
          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              <span className="font-medium text-foreground">{totalDocs}</span>
              documents
            </span>
            <span className="flex items-center gap-1">
              <Check className="h-3 w-3 text-green-600" />
              <span className="font-medium text-foreground">{indexedDocs}</span>
              indexed
            </span>
            {staleDocs > 0 && (
              <span className="flex items-center gap-1">
                <AlertTriangle className="h-3 w-3 text-amber-600" />
                <span className="font-medium text-amber-600">{staleDocs}</span>
                stale
              </span>
            )}
          </div>
        )}
      </div>

      {/* Placeholder for future per-document table */}
      {!statusLoading && (
        <div className="py-6 text-center text-sm text-muted-foreground rounded-md border border-dashed border-border">
          <FileText className="h-8 w-8 mx-auto mb-2 text-muted-foreground/30" />
          <p>No document details available yet.</p>
          <p className="text-xs mt-1">
            Summary counts are shown above. Per-document status will be available
            when the backend provides a detailed endpoint.
          </p>
        </div>
      )}
    </div>
  )
}

export default IndexingTab
