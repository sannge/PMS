/**
 * DocumentTimestamp
 *
 * Small static timestamp display rendered inside the editor area.
 * Shows the document's last-updated time. Not editable.
 * Optionally shows the embedding index status badge.
 *
 * The document title is rendered as an h1 heading inside the TipTap
 * editor content itself (see ensureContentHeading in content-utils.ts).
 */

import { parseBackendDate } from '@/lib/time-utils'
import { DocumentStatusBadge } from './document-status-badge'

export interface DocumentTimestampProps {
  updatedAt: string
  /** When provided, renders the unified embedding status badge */
  documentId?: string
  /** Backend-managed embedding status */
  embeddingStatus?: 'none' | 'stale' | 'syncing' | 'synced' | 'failed'
}

/** Format an ISO timestamp as "Feb 8, 2026 3:45 PM" */
function formatTimestamp(iso: string): string {
  const date = parseBackendDate(iso)
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  }).format(date)
}

export function DocumentTimestamp({ updatedAt, documentId, embeddingStatus }: DocumentTimestampProps): JSX.Element {
  return (
    <div className="flex items-center gap-2 px-6 pt-3 pb-1">
      <p className="text-xs text-muted-foreground">
        {formatTimestamp(updatedAt)}
      </p>
      {documentId && (
        <DocumentStatusBadge
          documentId={documentId}
          embeddingStatus={embeddingStatus}
          variant="badge"
        />
      )}
    </div>
  )
}
