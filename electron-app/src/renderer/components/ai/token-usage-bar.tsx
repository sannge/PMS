/**
 * Token Usage Bar
 *
 * Displays a thin progress bar showing context window utilization
 * with color coding: green < 50%, amber 50-75%, orange 75-90%, red > 90%.
 */

import { useAiSidebar } from './use-ai-sidebar'
import { cn } from '@/lib/utils'

function formatTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
  return String(n)
}

export function TokenUsageBar(): JSX.Element | null {
  const tokenUsage = useAiSidebar((s) => s.tokenUsage)
  if (!tokenUsage) return null

  const { totalTokens, contextLimit } = tokenUsage
  const pct = contextLimit > 0 ? Math.min((totalTokens / contextLimit) * 100, 100) : 0

  let barColor: string
  if (pct < 50) barColor = 'bg-emerald-500'
  else if (pct < 75) barColor = 'bg-amber-500'
  else if (pct < 90) barColor = 'bg-orange-500'
  else barColor = 'bg-red-500'

  return (
    <div className="shrink-0 px-4 py-1.5 border-t border-border/40">
      {/* Progress bar */}
      <div className="h-1 rounded-full bg-muted/50 overflow-hidden">
        <div
          className={cn('h-full rounded-full transition-all duration-500', barColor)}
          style={{ width: `${pct}%` }}
        />
      </div>
      {/* Label */}
      <div className="flex items-center justify-between mt-1">
        <span className="text-[10px] text-muted-foreground/60">Context</span>
        <span className="text-[10px] text-muted-foreground/60">
          {formatTokens(totalTokens)} / {formatTokens(contextLimit)}
        </span>
      </div>
    </div>
  )
}
