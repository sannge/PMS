/**
 * Projects Tab
 *
 * Shows project summary rows with expand/collapse for detailed breakdowns.
 * Uses lazy-loaded detail queries (enabled only when expanded).
 */

import { useState, useCallback } from 'react'
import { cn } from '@/lib/utils'
import { ChevronDown, ChevronRight, Archive, User } from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'
import {
  useTeamActivityProjects,
  useTeamActivityProjectDetail,
} from '@/hooks/use-team-activity'
import type { ProjectSummary } from '@/hooks/use-team-activity'

// ============================================================================
// Types
// ============================================================================

interface ProjectsTabProps {
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
// Progress Bar
// ============================================================================

function ProgressBar({ pct }: { pct: number }): JSX.Element {
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-emerald-500 transition-all duration-300"
          style={{ width: `${Math.min(Math.max(pct, 0), 100)}%` }}
        />
      </div>
      <span className="text-[10px] tabular-nums text-muted-foreground">{Math.round(pct)}%</span>
    </div>
  )
}

// ============================================================================
// Project Detail Panel
// ============================================================================

interface ProjectDetailPanelProps {
  projectId: string
  appId: string
  dateFrom: string
  dateTo: string
}

function ProjectDetailPanel({ projectId, appId, dateFrom, dateTo }: ProjectDetailPanelProps): JSX.Element {
  const { data, isLoading } = useTeamActivityProjectDetail(projectId, appId, dateFrom, dateTo, true)

  if (isLoading) {
    return (
      <div className="space-y-3 p-4">
        <Skeleton className="h-4 w-28" />
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
      {/* Member breakdown */}
      {data.member_breakdown.length > 0 && (
        <div>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Member Breakdown
          </h4>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">Member</th>
                  <th className="px-3 py-2 text-right font-medium text-muted-foreground">Done</th>
                  <th className="px-3 py-2 text-right font-medium text-muted-foreground">Prog</th>
                  <th className="px-3 py-2 text-right font-medium text-muted-foreground">Revw</th>
                  <th className="px-3 py-2 text-right font-medium text-muted-foreground">Issue</th>
                  <th className="px-3 py-2 text-right font-medium text-muted-foreground">Todo</th>
                  <th className="px-3 py-2 text-right font-medium text-muted-foreground">SP</th>
                </tr>
              </thead>
              <tbody>
                {data.member_breakdown.map((m) => (
                  <tr key={m.user_id} className="border-b border-border/50 last:border-0">
                    <td className="whitespace-nowrap px-3 py-1.5 text-foreground">{m.display_name}</td>
                    <td className="whitespace-nowrap px-3 py-1.5 text-right text-emerald-500">{m.done}</td>
                    <td className="whitespace-nowrap px-3 py-1.5 text-right text-blue-500">{m.in_progress}</td>
                    <td className="whitespace-nowrap px-3 py-1.5 text-right text-yellow-500">{m.in_review}</td>
                    <td className="whitespace-nowrap px-3 py-1.5 text-right text-red-500">{m.issue}</td>
                    <td className="whitespace-nowrap px-3 py-1.5 text-right text-muted-foreground">{m.todo}</td>
                    <td className="whitespace-nowrap px-3 py-1.5 text-right text-violet-500">{m.story_points}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

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
                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">Status</th>
                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">Priority</th>
                  <th className="px-3 py-2 text-left font-medium text-muted-foreground">Assignee</th>
                </tr>
              </thead>
              <tbody>
                {data.tasks.map((task) => (
                  <tr
                    key={task.task_id}
                    className={cn(
                      'border-b border-border/50 last:border-0',
                      task.is_archived && 'opacity-50',
                    )}
                  >
                    <td className="max-w-[200px] truncate px-3 py-1.5 text-foreground">{task.title}</td>
                    <td className="whitespace-nowrap px-3 py-1.5">
                      <StatusBadge category={task.status_category} name={task.status_name} />
                    </td>
                    <td className="whitespace-nowrap px-3 py-1.5 capitalize text-muted-foreground">
                      {task.priority}
                    </td>
                    <td className="whitespace-nowrap px-3 py-1.5 text-muted-foreground">
                      {task.assignee_name ?? '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Stat Pill
// ============================================================================

function StatPill({ label, value, color }: { label: string; value: number; color: string }): JSX.Element {
  if (value === 0) return <></>
  return (
    <span className={cn('inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium', color)}>
      {value} {label}
    </span>
  )
}

// ============================================================================
// Project Card
// ============================================================================

interface ProjectCardProps {
  project: ProjectSummary
  isExpanded: boolean
  onToggle: () => void
  appId: string
  dateFrom: string
  dateTo: string
}

function ProjectCard({ project, isExpanded, onToggle, appId, dateFrom, dateTo }: ProjectCardProps): JSX.Element {
  return (
    <div className={cn('rounded-xl border border-border bg-card overflow-hidden', project.is_archived && 'opacity-60')}>
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

        {/* Project info */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">{project.application_name}</span>
            <span className="text-muted-foreground/40">/</span>
            <span className="truncate text-sm font-medium text-foreground">{project.project_name}</span>
            {project.is_archived && (
              <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">
                <Archive className="h-3 w-3" />
                Archived
              </span>
            )}
          </div>
          {/* Progress bar */}
          <div className="mt-2 max-w-[200px]">
            <ProgressBar pct={project.progress_pct} />
          </div>
        </div>

        {/* Status pills */}
        <div className="hidden flex-wrap gap-1.5 lg:flex">
          <StatPill label="Done" value={project.done} color="bg-emerald-500/10 text-emerald-500" />
          <StatPill label="Prog" value={project.in_progress} color="bg-blue-500/10 text-blue-500" />
          <StatPill label="Revw" value={project.in_review} color="bg-yellow-500/10 text-yellow-500" />
          <StatPill label="Issue" value={project.issue} color="bg-red-500/10 text-red-500" />
          <StatPill label="Todo" value={project.todo} color="bg-slate-500/10 text-slate-500" />
          {project.archived > 0 && (
            <StatPill label="Arch" value={project.archived} color="bg-muted text-muted-foreground" />
          )}
          {project.unassigned > 0 && (
            <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">
              <User className="h-3 w-3" />
              {project.unassigned}
            </span>
          )}
        </div>

        {/* Total count */}
        <div className="flex flex-col items-center">
          <span className="text-lg font-bold text-foreground">{project.total}</span>
          <span className="text-[10px] text-muted-foreground">Total</span>
        </div>

        {/* Member avatars */}
        <div className="hidden items-center -space-x-2 md:flex">
          {project.members.slice(0, 4).map((name, idx) => (
            <div
              key={`${name}-${idx}`}
              className="flex h-7 w-7 items-center justify-center rounded-full border-2 border-card bg-primary/10 text-[9px] font-semibold text-primary"
              title={name}
            >
              {getInitials(name)}
            </div>
          ))}
          {project.members.length > 4 && (
            <div className="flex h-7 w-7 items-center justify-center rounded-full border-2 border-card bg-muted text-[9px] font-semibold text-muted-foreground">
              +{project.members.length - 4}
            </div>
          )}
        </div>
      </button>

      {/* Detail panel */}
      {isExpanded && (
        <ProjectDetailPanel projectId={project.project_id} appId={appId} dateFrom={dateFrom} dateTo={dateTo} />
      )}
    </div>
  )
}

// ============================================================================
// Loading skeleton
// ============================================================================

function ProjectsSkeleton(): JSX.Element {
  return (
    <div className="space-y-3">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="rounded-xl border border-border bg-card p-4">
          <div className="flex items-center gap-4">
            <Skeleton className="h-4 w-4" />
            <div className="flex-1 space-y-2">
              <div className="flex items-center gap-2">
                <Skeleton className="h-3 w-20" />
                <Skeleton className="h-4 w-32" />
                <Skeleton className="h-3 w-12" />
              </div>
              <Skeleton className="h-1.5 w-48 rounded-full" />
            </div>
            <div className="hidden gap-1.5 lg:flex">
              {Array.from({ length: 4 }).map((_, j) => (
                <Skeleton key={j} className="h-5 w-14 rounded-full" />
              ))}
            </div>
            <Skeleton className="h-8 w-10" />
          </div>
        </div>
      ))}
    </div>
  )
}

// ============================================================================
// Component
// ============================================================================

export function ProjectsTab({ appId, dateFrom, dateTo }: ProjectsTabProps): JSX.Element {
  const { data, isLoading, isError } = useTeamActivityProjects(appId, dateFrom, dateTo)
  const [expandedProjectId, setExpandedProjectId] = useState<string | null>(null)

  const handleToggle = useCallback((projectId: string) => {
    setExpandedProjectId((prev) => (prev === projectId ? null : projectId))
  }, [])

  if (isLoading) return <ProjectsSkeleton />

  if (isError || !data) {
    return (
      <div className="flex h-64 items-center justify-center">
        <p className="text-sm text-muted-foreground">Failed to load project data.</p>
      </div>
    )
  }

  if (data.projects.length === 0) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-2">
        <p className="text-sm font-medium text-foreground">No projects found</p>
        <p className="text-xs text-muted-foreground">No projects with activity in the selected date range.</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {data.projects.map((project) => (
        <ProjectCard
          key={project.project_id}
          project={project}
          isExpanded={expandedProjectId === project.project_id}
          onToggle={() => handleToggle(project.project_id)}
          appId={appId}
          dateFrom={dateFrom}
          dateTo={dateTo}
        />
      ))}
    </div>
  )
}
