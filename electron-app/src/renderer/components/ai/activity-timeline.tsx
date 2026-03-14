/**
 * Activity Timeline
 *
 * Unified timeline showing every step Blair took — pipeline nodes AND
 * tool calls interleaved in execution order. Renders above the response
 * content to give users full visibility into Blair's reasoning process.
 */

import React, { type ComponentType, memo, useState } from 'react'
import { Brain, Check, ChevronDown, ChevronRight, HelpCircle, Inbox, Layers, Loader2, MessageSquare, Search, Wrench } from 'lucide-react'
import { cn } from '@/lib/utils'
import { MarkdownRenderer } from './markdown-renderer'
import type { ActivityItem } from './types'

// ============================================================================
// Tool Labels (shared with ToolExecutionCard)
// ============================================================================

const TOOL_LABELS: Record<string, { label: string; icon: string }> = {
  search_knowledge: { label: 'Searched knowledge base', icon: '\uD83D\uDD0D' },
  sql_query: { label: 'Ran database query', icon: '\uD83D\uDCCA' },
  list_projects: { label: 'Checked projects', icon: '\uD83D\uDCC1' },
  list_tasks: { label: 'Searched tasks', icon: '\u2705' },
  get_task_detail: { label: 'Loaded task details', icon: '\uD83D\uDCCB' },
  get_project_details: { label: 'Checked project details', icon: '\uD83D\uDCC8' },
  get_overdue_tasks: { label: 'Found overdue tasks', icon: '\u26A0\uFE0F' },
  get_application_members: { label: 'Checked team members', icon: '\uD83D\uDC65' },
  get_project_members: { label: 'Checked project members', icon: '\uD83D\uDC65' },
  understand_image: { label: 'Analyzed image', icon: '\uD83D\uDDBC\uFE0F' },
  create_task: { label: 'Creating task', icon: '\u2795' },
  update_task_status: { label: 'Updating task status', icon: '\uD83D\uDD04' },
  assign_task: { label: 'Assigning task', icon: '\uD83D\uDC64' },
  create_document: { label: 'Creating document', icon: '\uD83D\uDCDD' },
  browse_folders: { label: 'Browsing folders', icon: '\uD83D\uDCC2' },
  get_document_details: { label: 'Loaded document details', icon: '\uD83D\uDCC4' },
  list_recent_documents: { label: 'Listed recent documents', icon: '\uD83D\uDDD3\uFE0F' },
  get_my_notes: { label: 'Loaded your notes', icon: '\uD83D\uDCDD' },
  get_my_profile: { label: 'Loaded your profile', icon: '\uD83D\uDC64' },
  get_my_workload: { label: 'Checked your workload', icon: '\uD83D\uDCCB' },
  list_applications: { label: 'Listed applications', icon: '\uD83D\uDCF1' },
  get_application_details: { label: 'Loaded application details', icon: '\uD83D\uDCF1' },
  get_project_timeline: { label: 'Loaded project timeline', icon: '\uD83D\uDCC5' },
  get_blocked_tasks: { label: 'Found blocked tasks', icon: '\uD83D\uDEAB' },
  get_task_comments: { label: 'Loaded task comments', icon: '\uD83D\uDCAC' },
  request_clarification: { label: 'Requesting clarification', icon: '\u2753' },
  export_to_excel: { label: 'Exporting to spreadsheet', icon: '\uD83D\uDCCA' },
}

function getToolLabel(name: string): { label: string; icon: string } {
  return TOOL_LABELS[name] ?? { label: name, icon: '\u2699\uFE0F' }
}

// ============================================================================
// Node Icon Mapping (cognitive pipeline nodes)
// ============================================================================

/** Maps pipeline node names to lucide-react icon components for the activity timeline. */
const NODE_ICONS: Record<string, ComponentType<{ className?: string }>> = {
  intake: Inbox,
  understand: Brain,
  clarify: HelpCircle,
  explore: Search,
  explore_tools: Wrench,
  synthesize: Layers,
  respond: MessageSquare,
}

// ============================================================================
// Node Step Item
// ============================================================================

const NodeStepItem = memo(function NodeStepItem({ item }: { item: Extract<ActivityItem, { type: 'node' }> }) {
  const [expanded, setExpanded] = useState(false)
  const isActive = item.status === 'active'
  const hasDetails = !!item.details
  const NodeIcon = NODE_ICONS[item.node]

  return (
    <div className="animate-in fade-in duration-200">
      <button
        type="button"
        onClick={() => hasDetails && setExpanded(!expanded)}
        disabled={!hasDetails}
        aria-expanded={hasDetails ? expanded : undefined}
        className={cn(
          'flex w-full items-center gap-1.5 py-0.5 text-xs text-muted-foreground min-w-0',
          hasDetails && 'cursor-pointer hover:text-foreground/70 transition-colors',
          !hasDetails && 'cursor-default',
        )}
      >
        {/* Status icon — use node-specific icon when available */}
        {isActive ? (
          NodeIcon
            ? <NodeIcon className="h-3 w-3 shrink-0 animate-pulse text-primary/60" />
            : <Loader2 className="h-3 w-3 shrink-0 animate-spin text-primary/60" />
        ) : (
          NodeIcon
            ? <NodeIcon className="h-3 w-3 shrink-0 text-muted-foreground/60" />
            : <Check className="h-3 w-3 shrink-0 text-muted-foreground/60" />
        )}

        {/* Label */}
        <span className={cn('truncate min-w-0', isActive && 'text-foreground/70')}>
          {item.label}
        </span>

        {/* Expand chevron */}
        {hasDetails && (
          <span className="shrink-0 ml-auto text-muted-foreground/40">
            {expanded ? (
              <ChevronDown className="h-3 w-3" />
            ) : (
              <ChevronRight className="h-3 w-3" />
            )}
          </span>
        )}
      </button>

      {/* Expanded details */}
      {expanded && item.details && (
        <div className="ml-[18px] mt-0.5 mb-1 text-[11px] text-muted-foreground/60 border-l border-border/30 pl-2 max-h-24 overflow-y-auto">
          <MarkdownRenderer content={item.details} className="text-[11px] [&_p]:leading-snug [&_strong]:text-muted-foreground/80" />
        </div>
      )}
    </div>
  )
})

// ============================================================================
// Tool Call Item
// ============================================================================

const ToolCallItem = memo(function ToolCallItem({ item }: { item: Extract<ActivityItem, { type: 'tool' }> }) {
  const [expanded, setExpanded] = useState(false)
  const { label, icon } = getToolLabel(item.name)
  const isRunning = item.status === 'running'
  const isError = item.status === 'error'
  const hasDetails = !!(item.details || item.error)

  return (
    <div
      className={cn(
        'rounded-xl text-xs overflow-hidden',
        'backdrop-blur-sm transition-colors',
        isError
          ? 'border border-red-500/20 bg-red-500/5'
          : isRunning
            ? 'border border-amber-400/20 bg-amber-500/5'
            : 'border border-border/30 bg-muted/20',
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
          !hasDetails && 'cursor-default',
        )}
      >
        {/* Status indicator */}
        {isRunning && (
          <span className="relative flex h-3 w-3 items-center justify-center shrink-0">
            <span className="blair-tool-ripple absolute h-2 w-2 rounded-full bg-amber-400/50" />
            <span className="relative h-1.5 w-1.5 rounded-full bg-gradient-to-r from-amber-400 to-orange-500" />
          </span>
        )}
        {item.status === 'complete' && (
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
        {item.summary && !isRunning && (
          <span className="text-muted-foreground/70 truncate min-w-0 ml-auto mr-1">
            {item.summary}
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
          {item.error && (
            <p className="text-red-500 whitespace-pre-wrap break-words [overflow-wrap:anywhere] text-[11px]">
              {item.error}
            </p>
          )}
          {item.details && !item.error && (
            <div className="text-muted-foreground/70 [overflow-wrap:anywhere]">
              <MarkdownRenderer content={item.details} className="text-[11px] [&_p]:leading-snug [&_strong]:text-muted-foreground/80 [&_pre]:text-[10px]" />
            </div>
          )}
        </div>
      )}
    </div>
  )
})

// ============================================================================
// ActivityTimeline
// ============================================================================

interface ActivityTimelineProps {
  items: ActivityItem[]
}

export const ActivityTimeline = React.memo(function ActivityTimeline({ items }: ActivityTimelineProps): JSX.Element {
  return (
    <div role="log" aria-label="Blair activity timeline" className="space-y-1 mb-2">
      {items.map((item) => {
        if (item.type === 'node') {
          return <NodeStepItem key={`node-${item.node}`} item={item} />
        }
        return <ToolCallItem key={`tool-${item.id}`} item={item} />
      })}
    </div>
  )
})
