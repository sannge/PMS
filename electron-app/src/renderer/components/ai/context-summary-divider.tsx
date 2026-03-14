/**
 * Context Summary Divider
 *
 * Horizontal line with "Context summarized" label that can be expanded
 * to show the summary text.
 */

import { useState } from 'react'
import { Sparkles, ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ContextSummaryDividerProps {
  summary: string
}

export function ContextSummaryDivider({ summary }: ContextSummaryDividerProps): JSX.Element {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="my-3">
      {/* Divider line with label */}
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
        className="flex items-center gap-2 w-full group"
      >
        <div className="flex-1 h-px bg-border/60" />
        <div className="flex items-center gap-1.5 shrink-0 px-2 py-0.5 rounded-full bg-muted/50 border border-border/40">
          <Sparkles className="h-2.5 w-2.5 text-amber-500" />
          <span className="text-[10px] font-medium text-muted-foreground">Context summarized</span>
          <ChevronDown
            className={cn(
              'h-2.5 w-2.5 text-muted-foreground/60 transition-transform duration-200',
              expanded && 'rotate-180'
            )}
          />
        </div>
        <div className="flex-1 h-px bg-border/60" />
      </button>

      {/* Expanded summary */}
      {expanded && (
        <div className="mt-2 mx-2 p-3 rounded-lg bg-muted/30 border border-border/30">
          <p className="text-xs text-muted-foreground leading-relaxed">{summary}</p>
        </div>
      )}
    </div>
  )
}
