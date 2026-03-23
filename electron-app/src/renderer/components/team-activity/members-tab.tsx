/**
 * Members Tab
 *
 * Shows member summary cards with expand/collapse for detailed breakdowns.
 * Uses lazy-loaded detail queries (enabled only when expanded).
 */

import { useState, useCallback } from 'react'
import { cn } from '@/lib/utils'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'
import {
  useTeamActivityMembers,
  useTeamActivityMemberDetail,
} from '@/hooks/use-team-activity'
import type { MemberSummary } from '@/hooks/use-team-activity'

// ============================================================================
// Types
// ============================================================================

interface MembersTabProps {
  appId: string
  dateFrom: string
  dateTo: string
}

// ============================================================================
// Helpers
// ============================================================================

function getInitials(name: string): string {
  return name
    .split(' ')
    .map((n) => n[0])
    .filter(Boolean)
    .slice(0, 2)
    .join('')
    .toUpperCase()
}

function getRoleBadgeClass(role: string): string {
  switch (role.toLowerCase()) {
    case 'owner':
      return 'bg-amber-500/10 text-amber-500 border-amber-500/20'
    case 'editor':
      return 'bg-blue-500/10 text-blue-500 border-blue-500/20'
    case 'viewer':
      return 'bg-slate-500/10 text-slate-500 border-slate-500/20'
    default:
      return 'bg-muted text-muted-foreground border-border'
  }
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

// ============================================================================
// Member Detail Panel
// ============================================================================

interface MemberDetailPanelProps {
  userId: string
  appId: string
  dateFrom: string
  dateTo: string
}

function MemberDetailPanel({ userId, appId, dateFrom, dateTo }: MemberDetailPanelProps): JSX.Element {
  const { data, isLoading } = useTeamActivityMemberDetail(userId, appId, dateFrom, dateTo, true)

  if (isLoading) {
    return (
      <div className="space-y-3 p-4">
        <Skeleton className="h-4 w-20" />
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-8 w-full" />
        ))}
      </div>
    )
  }

  if (!data) {
    return (
      <div className="p-4 text-sm text-muted-foreground">No detail data available.</div>
    )
  }

  return (
    <div className="space-y-4 border-t border-border bg-muted/30 p-4">
      {/* Tasks table */}
      {data.tasks.length > 0 && (
        <div>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Tasks ({data.tasks.length})
          </h4>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">Title</th>
                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">Project</th>
                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">Status</th>
                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">Priority</th>
                  <th className="px-3 py-2 text-right font-medium text-muted-foreground">SP</th>
                </tr>
              </thead>
              <tbody>
                {data.tasks.map((task) => (
                  <tr key={task.task_id} className="border-b border-border/50 last:border-0">
                    <td className="max-w-[200px] truncate px-3 py-1.5 text-foreground">{task.title}</td>
                    <td className="whitespace-nowrap px-3 py-1.5 text-muted-foreground">
                      {task.project_name}
                    </td>
                    <td className="whitespace-nowrap px-3 py-1.5">
                      <StatusBadge category={task.status_category} name={task.status_name} />
                    </td>
                    <td className="whitespace-nowrap px-3 py-1.5 capitalize text-muted-foreground">
                      {task.priority}
                    </td>
                    <td className="whitespace-nowrap px-3 py-1.5 text-right text-muted-foreground">
                      {task.story_points ?? '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Documents table */}
      {data.documents.length > 0 && (
        <div>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Documents ({data.documents.length})
          </h4>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">Title</th>
                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">Scope</th>
                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">Created</th>
                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">Updated</th>
                </tr>
              </thead>
              <tbody>
                {data.documents.map((doc) => (
                  <tr key={doc.document_id} className="border-b border-border/50 last:border-0">
                    <td className="max-w-[200px] truncate px-3 py-1.5 text-foreground">{doc.title}</td>
                    <td className="whitespace-nowrap px-3 py-1.5 text-muted-foreground">{doc.scope_name}</td>
                    <td className="whitespace-nowrap px-3 py-1.5 text-muted-foreground">{formatDate(doc.created_at)}</td>
                    <td className="whitespace-nowrap px-3 py-1.5 text-muted-foreground">{formatDate(doc.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Comment count */}
      <div className="text-xs text-muted-foreground">
        Comments in period: <span className="font-medium text-foreground">{data.comments_count}</span>
      </div>
    </div>
  )
}

// ============================================================================
// Status Badge
// ============================================================================

function StatusBadge({ category, name }: { category: string; name: string }): JSX.Element {
  const colorMap: Record<string, string> = {
    done: 'bg-emerald-500/10 text-emerald-500',
    in_progress: 'bg-blue-500/10 text-blue-500',
    in_review: 'bg-yellow-500/10 text-yellow-500',
    issue: 'bg-red-500/10 text-red-500',
    todo: 'bg-slate-500/10 text-slate-500',
  }
  const classes = colorMap[category.toLowerCase()] ?? 'bg-muted text-muted-foreground'
  return (
    <span className={cn('inline-flex rounded-full px-2 py-0.5 text-[10px] font-medium', classes)}>
      {name}
    </span>
  )
}

// ============================================================================
// Member Card
// ============================================================================

interface MemberCardProps {
  member: MemberSummary
  isExpanded: boolean
  onToggle: () => void
  appId: string
  dateFrom: string
  dateTo: string
}

function MemberCard({ member, isExpanded, onToggle, appId, dateFrom, dateTo }: MemberCardProps): JSX.Element {
  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden">
      {/* Summary row */}
      <button
        onClick={onToggle}
        className="flex w-full items-center gap-4 p-4 text-left transition-colors hover:bg-muted/30"
      >
        {/* Expand icon */}
        {isExpanded ? (
          <ChevronDown className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
        )}

        {/* Avatar */}
        <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
          {getInitials(member.display_name)}
        </div>

        {/* Name + role */}
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-foreground">{member.display_name}</p>
          <p className="truncate text-xs text-muted-foreground">{member.email}</p>
        </div>

        {/* Role badge */}
        <span className={cn('rounded-full border px-2 py-0.5 text-[10px] font-medium capitalize', getRoleBadgeClass(member.role))}>
          {member.role}
        </span>

        {/* Stat boxes */}
        <div className="hidden gap-3 sm:flex">
          <StatBox label="Done" value={member.done_count} color="text-emerald-500" />
          <StatBox label="Active" value={member.in_progress_count + member.in_review_count} color="text-blue-500" />
          <StatBox label="Points" value={member.story_points_sum} color="text-violet-500" />
          <StatBox label="Docs" value={member.docs_count} color="text-amber-500" />
        </div>
      </button>

      {/* Detail panel */}
      {isExpanded && (
        <MemberDetailPanel userId={member.user_id} appId={appId} dateFrom={dateFrom} dateTo={dateTo} />
      )}
    </div>
  )
}

// ============================================================================
// Stat Box
// ============================================================================

function StatBox({ label, value, color }: { label: string; value: number; color: string }): JSX.Element {
  return (
    <div className="flex flex-col items-center rounded-lg bg-muted/40 px-3 py-1.5">
      <span className={cn('text-sm font-bold', color)}>{value}</span>
      <span className="text-[10px] text-muted-foreground">{label}</span>
    </div>
  )
}

// ============================================================================
// Loading skeleton
// ============================================================================

function MembersSkeleton(): JSX.Element {
  return (
    <div className="space-y-3">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="rounded-xl border border-border bg-card p-4">
          <div className="flex items-center gap-4">
            <Skeleton className="h-4 w-4" />
            <Skeleton className="h-9 w-9 rounded-full" />
            <div className="flex-1 space-y-1.5">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-3 w-48" />
            </div>
            <Skeleton className="h-5 w-14 rounded-full" />
            <div className="hidden gap-3 sm:flex">
              {Array.from({ length: 4 }).map((_, j) => (
                <Skeleton key={j} className="h-10 w-14 rounded-lg" />
              ))}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

// ============================================================================
// Component
// ============================================================================

export function MembersTab({ appId, dateFrom, dateTo }: MembersTabProps): JSX.Element {
  const { data, isLoading, isError } = useTeamActivityMembers(appId, dateFrom, dateTo)
  const [expandedUserId, setExpandedUserId] = useState<string | null>(null)

  const handleToggle = useCallback((userId: string) => {
    setExpandedUserId((prev) => (prev === userId ? null : userId))
  }, [])

  if (isLoading) return <MembersSkeleton />

  if (isError || !data) {
    return (
      <div className="flex h-64 items-center justify-center">
        <p className="text-sm text-muted-foreground">Failed to load member data.</p>
      </div>
    )
  }

  if (data.members.length === 0) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-2">
        <p className="text-sm font-medium text-foreground">No members found</p>
        <p className="text-xs text-muted-foreground">No team members with activity in the selected date range.</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {data.members.map((member) => (
        <MemberCard
          key={member.user_id}
          member={member}
          isExpanded={expandedUserId === member.user_id}
          onToggle={() => handleToggle(member.user_id)}
          appId={appId}
          dateFrom={dateFrom}
          dateTo={dateTo}
        />
      ))}
    </div>
  )
}
