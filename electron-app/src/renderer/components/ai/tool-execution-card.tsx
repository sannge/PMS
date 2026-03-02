/**
 * Tool Execution Card
 *
 * Collapsible card showing what Blair did during reasoning.
 * Glassmorphism style with animated status indicators:
 * running (ripple pulse), complete (green dot), error (red dot).
 */

import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ToolCallInfo } from './types'

// ============================================================================
// Tool Labels
// ============================================================================

const TOOL_LABELS: Record<string, { label: string; icon: string }> = {
  query_knowledge: { label: 'Searched knowledge base', icon: '\uD83D\uDD0D' },
  sql_query: { label: 'Ran database query', icon: '\uD83D\uDCCA' },
  get_projects: { label: 'Checked projects', icon: '\uD83D\uDCC1' },
  get_tasks: { label: 'Searched tasks', icon: '\u2705' },
  get_task_detail: { label: 'Loaded task details', icon: '\uD83D\uDCCB' },
  get_project_status: { label: 'Checked project status', icon: '\uD83D\uDCC8' },
  get_overdue_tasks: { label: 'Found overdue tasks', icon: '\u26A0\uFE0F' },
  get_team_members: { label: 'Checked team members', icon: '\uD83D\uDC65' },
  understand_image: { label: 'Analyzed image', icon: '\uD83D\uDDBC\uFE0F' },
  create_task: { label: 'Creating task', icon: '\u2795' },
  update_task_status: { label: 'Updating task status', icon: '\uD83D\uDD04' },
  assign_task: { label: 'Assigning task', icon: '\uD83D\uDC64' },
  create_document: { label: 'Creating document', icon: '\uD83D\uDCDD' },
}

function getToolLabel(name: string): { label: string; icon: string } {
  return TOOL_LABELS[name] ?? { label: name, icon: '\u2699\uFE0F' }
}

// ============================================================================
// Component
// ============================================================================

interface ToolExecutionCardProps {
  tool: ToolCallInfo
}

export function ToolExecutionCard({ tool }: ToolExecutionCardProps): JSX.Element {
  const [expanded, setExpanded] = useState(false)
  const { label, icon } = getToolLabel(tool.name)

  const isRunning = tool.status === 'running'
  const isError = tool.status === 'error'
  const hasDetails = !!(tool.details || tool.error)

  return (
    <div
      className={cn(
        'rounded-xl text-xs overflow-hidden',
        'backdrop-blur-sm transition-colors',
        isError
          ? 'border border-red-500/20 bg-red-500/5'
          : isRunning
            ? 'border border-amber-400/20 bg-amber-500/5'
            : 'border border-border/30 bg-muted/20'
      )}
    >
      {/* Header row */}
      <button
        type="button"
        onClick={() => hasDetails && setExpanded(!expanded)}
        disabled={!hasDetails}
        aria-expanded={hasDetails ? expanded : undefined}
        className={cn(
          'flex w-full items-center gap-2 px-2.5 py-2 min-w-0',
          hasDetails && 'cursor-pointer hover:bg-muted/30 transition-colors',
          !hasDetails && 'cursor-default'
        )}
      >
        {/* Status indicator */}
        {isRunning && (
          <span className="relative flex h-3 w-3 items-center justify-center shrink-0">
            <span className="blair-tool-ripple absolute h-2 w-2 rounded-full bg-amber-400/50" />
            <span className="relative h-1.5 w-1.5 rounded-full bg-gradient-to-r from-amber-400 to-orange-500" />
          </span>
        )}
        {tool.status === 'complete' && (
          <span className="h-2 w-2 rounded-full bg-emerald-500 shrink-0 shadow-sm shadow-emerald-500/30" />
        )}
        {isError && (
          <span className="h-2 w-2 rounded-full bg-red-500 shrink-0 shadow-sm shadow-red-500/30" />
        )}

        {/* Icon + label */}
        <span className="shrink-0">{icon}</span>
        <span className={cn('font-medium truncate min-w-0', isRunning && 'text-amber-600 dark:text-amber-400')}>
          {isRunning ? `${label}...` : label}
        </span>

        {/* Summary */}
        {tool.summary && !isRunning && (
          <span className="text-muted-foreground/70 truncate min-w-0 ml-auto mr-1">
            {tool.summary}
          </span>
        )}

        {/* Expand chevron */}
        {hasDetails && (
          <span className="shrink-0 text-muted-foreground/50">
            {expanded ? (
              <ChevronDown className="h-3 w-3" />
            ) : (
              <ChevronRight className="h-3 w-3" />
            )}
          </span>
        )}
      </button>

      {/* Expanded details */}
      {expanded && hasDetails && (
        <div className="border-t border-border/20 px-2.5 py-2 bg-muted/10 overflow-hidden">
          {tool.error && (
            <p className="text-red-500 whitespace-pre-wrap break-words [overflow-wrap:anywhere] text-[11px]">
              {tool.error}
            </p>
          )}
          {tool.details && !tool.error && (
            <pre className="text-muted-foreground/70 whitespace-pre-wrap break-words [overflow-wrap:anywhere] font-mono text-[11px]">
              {tool.details}
            </pre>
          )}
        </div>
      )}
    </div>
  )
}
