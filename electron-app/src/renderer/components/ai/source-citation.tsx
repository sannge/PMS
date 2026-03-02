/**
 * Source Citation List
 *
 * Renders source citations at the bottom of AI messages.
 * Card-style citations with document title, section, relevance score,
 * source type badge, and hover effects. Clicking navigates to the document.
 */

import { FileText, ExternalLink } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { SourceCitation, NavigationTarget } from './types'

// ============================================================================
// Source Type Badge Colors
// ============================================================================

const SOURCE_TYPE_STYLES: Record<string, string> = {
  semantic: 'bg-blue-500/10 text-blue-600 dark:text-blue-400 ring-blue-500/20',
  keyword: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 ring-emerald-500/20',
  fuzzy: 'bg-yellow-500/10 text-yellow-600 dark:text-yellow-400 ring-yellow-500/20',
  sql: 'bg-purple-500/10 text-purple-600 dark:text-purple-400 ring-purple-500/20',
}

function SourceTypeBadge({ type }: { type: string }): JSX.Element {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-1.5 py-0.5 text-[9px] font-medium ring-1',
        SOURCE_TYPE_STYLES[type] ?? 'bg-muted text-muted-foreground ring-border/30'
      )}
    >
      {type}
    </span>
  )
}

function ScoreBar({ score }: { score: number }): JSX.Element {
  const pct = Math.round(score * 100)
  return (
    <div className="flex items-center gap-1.5">
      <div className="h-1 w-10 rounded-full bg-muted/60 overflow-hidden">
        <div
          className="h-full rounded-full bg-gradient-to-r from-amber-400 to-orange-500 transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-[9px] font-mono text-muted-foreground/60 tabular-nums">
        {pct}%
      </span>
    </div>
  )
}

// ============================================================================
// Component
// ============================================================================

interface SourceCitationListProps {
  sources: SourceCitation[]
  onNavigate?: (target: NavigationTarget) => void
}

export function SourceCitationList({
  sources,
  onNavigate,
}: SourceCitationListProps): JSX.Element {
  return (
    <div className="mt-3 pt-2.5 border-t border-border/20">
      {/* Header */}
      <div className="flex items-center gap-1.5 mb-2 px-0.5">
        <FileText className="h-3 w-3 text-muted-foreground/50" />
        <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground/50">
          Sources
        </span>
      </div>

      {/* Citation cards */}
      <div className="space-y-1.5">
        {sources.map((src, i) => (
          <button
            type="button"
            key={`${src.document_id}-${src.chunk_index}-${i}`}
            onClick={() =>
              onNavigate?.({
                type: 'document',
                documentId: src.document_id,
                applicationId: src.application_id,
                highlight: {
                  headingContext: src.heading_context,
                  chunkText: src.chunk_text,
                  chunkIndex: src.chunk_index,
                },
              })
            }
            className={cn(
              'group flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-left text-xs',
              'border border-border/20 bg-muted/10',
              'hover:bg-muted/30 hover:border-border/40',
              'transition-all duration-150',
              onNavigate ? 'cursor-pointer' : 'cursor-default'
            )}
          >
            {/* Title + section */}
            <div className="flex-1 min-w-0">
              <p className="font-medium text-foreground/80 truncate group-hover:text-foreground transition-colors">
                {src.document_title}
              </p>
              {src.heading_context && (
                <p className="text-[10px] text-muted-foreground/50 truncate mt-0.5">
                  {src.heading_context}
                </p>
              )}
            </div>

            {/* Score bar */}
            <ScoreBar score={src.score} />

            {/* Source type pill */}
            <SourceTypeBadge type={src.source_type} />

            {/* Navigate hint */}
            {onNavigate && (
              <ExternalLink className="h-3 w-3 text-muted-foreground/0 group-hover:text-muted-foreground/40 transition-all shrink-0" />
            )}
          </button>
        ))}
      </div>
    </div>
  )
}
