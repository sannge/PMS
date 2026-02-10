/**
 * DocumentTimestamp
 *
 * Small static timestamp display rendered inside the editor area.
 * Shows the document's last-updated time. Not editable.
 *
 * The document title is rendered as an h1 heading inside the TipTap
 * editor content itself (see ensureContentHeading in content-utils.ts).
 */

export interface DocumentTimestampProps {
  updatedAt: string
}

/** Format an ISO timestamp as "Feb 8, 2026 3:45 PM" */
function formatTimestamp(iso: string): string {
  const date = new Date(iso)
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  }).format(date)
}

export function DocumentTimestamp({ updatedAt }: DocumentTimestampProps): JSX.Element {
  return (
    <p className="px-6 pt-3 pb-1 text-xs text-muted-foreground">
      {formatTimestamp(updatedAt)}
    </p>
  )
}
