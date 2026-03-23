/**
 * Team Activity Hooks
 *
 * TanStack Query hooks for the Team Activity page.
 * All queries use 5-minute stale time since analytics data changes slowly,
 * and refetchOnMount: 'always' since components fully unmount on screen switch.
 */

import { useQuery } from '@tanstack/react-query'
import { authGet, getAccessToken, API_BASE } from '@/lib/api-client'
import { queryKeys } from '@/lib/query-client'

// ============================================================================
// Shared query config
// ============================================================================

const TEAM_ACTIVITY_STALE_TIME = 5 * 60_000 // 5 minutes
const TEAM_ACTIVITY_GC_TIME = 24 * 60 * 60 * 1000 // 24 hours

// ============================================================================
// Types (matching backend Pydantic schemas)
// ============================================================================

// -- Overview tab --

export interface KPICards {
  completed: number
  in_progress: number
  in_review: number
  overdue: number
  total_story_points: number
}

export interface WeeklyCompletion {
  week: string // ISO date of Monday
  count: number
}

export interface ProjectBreakdown {
  project_id: string
  project_name: string
  project_key: string
  completed: number
  in_progress: number
  in_review: number
  overdue: number
  todo: number
}

export interface MemberBreakdown {
  user_id: string
  display_name: string
  email: string
  completed: number
  in_progress: number
}

export interface OverviewResponse {
  kpi: KPICards
  completion_trend: WeeklyCompletion[]
  by_project: ProjectBreakdown[]
  by_member: MemberBreakdown[]
}

// -- Members tab --

export interface MemberSummary {
  user_id: string
  display_name: string
  email: string
  avatar_url: string | null
  role: string
  done_count: number
  in_progress_count: number
  in_review_count: number
  story_points_sum: number
  docs_count: number
  comments_count: number
}

export interface MembersSummaryResponse {
  members: MemberSummary[]
}

export interface MemberTaskDetail {
  task_id: string
  task_key: string
  title: string
  project_name: string
  project_key: string
  status_name: string
  status_category: string
  priority: string
  story_points: number | null
  completed_at: string | null
  created_at: string
}

export interface MemberDocDetail {
  document_id: string
  title: string
  scope: string
  scope_name: string
  created_at: string
  updated_at: string
}

export interface MemberDetailResponse {
  user_id: string
  tasks: MemberTaskDetail[]
  documents: MemberDocDetail[]
  comments_count: number
}

// -- Projects tab --

export interface ProjectSummary {
  project_id: string
  project_name: string
  project_key: string
  application_name: string
  due_date: string | null
  total: number
  done: number
  in_progress: number
  in_review: number
  issue: number
  todo: number
  archived: number
  unassigned: number
  is_archived: boolean
  archived_at: string | null
  members: string[] // display names
  progress_pct: number
}

export interface ProjectsSummaryResponse {
  projects: ProjectSummary[]
}

export interface ProjectMemberBreakdown {
  user_id: string
  display_name: string
  done: number
  in_progress: number
  in_review: number
  issue: number
  todo: number
  story_points: number
}

export interface ProjectTaskRow {
  task_id: string
  task_key: string
  title: string
  status_name: string
  status_category: string
  priority: string
  assignee_name: string | null
  completed_at: string | null
  is_archived: boolean
}

export interface ProjectDetailResponse {
  project_id: string
  member_breakdown: ProjectMemberBreakdown[]
  tasks: ProjectTaskRow[]
}

// ============================================================================
// Hooks
// ============================================================================

function buildParams(appId: string, dateFrom: string, dateTo: string): string {
  const params = new URLSearchParams({
    application_id: appId,
    date_from: dateFrom,
    date_to: dateTo,
  })
  return params.toString()
}

/**
 * Fetch overview KPIs, completion trend, and breakdowns.
 */
export function useTeamActivityOverview(appId: string, dateFrom: string, dateTo: string) {
  return useQuery({
    queryKey: queryKeys.teamActivityOverview(appId, dateFrom, dateTo),
    queryFn: async () => {
      const qs = buildParams(appId, dateFrom, dateTo)
      const res = await authGet<OverviewResponse>(`/api/team-activity/overview?${qs}`)
      if (res.status !== 200 || !res.data) {
        throw new Error(`Failed to fetch overview: ${res.status}`)
      }
      return res.data
    },
    staleTime: TEAM_ACTIVITY_STALE_TIME,
    gcTime: TEAM_ACTIVITY_GC_TIME,
    refetchOnMount: 'always' as const,
  })
}

/**
 * Fetch member summary table.
 */
export function useTeamActivityMembers(appId: string, dateFrom: string, dateTo: string) {
  return useQuery({
    queryKey: queryKeys.teamActivityMembers(appId, dateFrom, dateTo),
    queryFn: async () => {
      const qs = buildParams(appId, dateFrom, dateTo)
      const res = await authGet<MembersSummaryResponse>(`/api/team-activity/members?${qs}`)
      if (res.status !== 200 || !res.data) {
        throw new Error(`Failed to fetch members: ${res.status}`)
      }
      return res.data
    },
    staleTime: TEAM_ACTIVITY_STALE_TIME,
    gcTime: TEAM_ACTIVITY_GC_TIME,
    refetchOnMount: 'always' as const,
  })
}

/**
 * Fetch detailed task/doc breakdown for a single member.
 * Enabled only when expanded (enabled=true).
 */
export function useTeamActivityMemberDetail(
  userId: string,
  appId: string,
  dateFrom: string,
  dateTo: string,
  enabled: boolean,
) {
  return useQuery({
    queryKey: queryKeys.teamActivityMemberDetail(userId, appId, dateFrom, dateTo),
    queryFn: async () => {
      const qs = buildParams(appId, dateFrom, dateTo)
      const res = await authGet<MemberDetailResponse>(`/api/team-activity/members/${userId}?${qs}`)
      if (res.status !== 200 || !res.data) {
        throw new Error(`Failed to fetch member detail: ${res.status}`)
      }
      return res.data
    },
    enabled,
    staleTime: TEAM_ACTIVITY_STALE_TIME,
    gcTime: TEAM_ACTIVITY_GC_TIME,
    refetchOnMount: 'always' as const,
  })
}

/**
 * Fetch project summary table.
 */
export function useTeamActivityProjects(appId: string, dateFrom: string, dateTo: string) {
  return useQuery({
    queryKey: queryKeys.teamActivityProjects(appId, dateFrom, dateTo),
    queryFn: async () => {
      const qs = buildParams(appId, dateFrom, dateTo)
      const res = await authGet<ProjectsSummaryResponse>(`/api/team-activity/projects?${qs}`)
      if (res.status !== 200 || !res.data) {
        throw new Error(`Failed to fetch projects: ${res.status}`)
      }
      return res.data
    },
    staleTime: TEAM_ACTIVITY_STALE_TIME,
    gcTime: TEAM_ACTIVITY_GC_TIME,
    refetchOnMount: 'always' as const,
  })
}

/**
 * Fetch member breakdown + task list for a single project.
 * Enabled only when expanded (enabled=true).
 */
export function useTeamActivityProjectDetail(
  projectId: string,
  appId: string,
  dateFrom: string,
  dateTo: string,
  enabled: boolean,
) {
  return useQuery({
    queryKey: queryKeys.teamActivityProjectDetail(projectId, appId, dateFrom, dateTo),
    queryFn: async () => {
      const qs = buildParams(appId, dateFrom, dateTo)
      const res = await authGet<ProjectDetailResponse>(`/api/team-activity/projects/${projectId}?${qs}`)
      if (res.status !== 200 || !res.data) {
        throw new Error(`Failed to fetch project detail: ${res.status}`)
      }
      return res.data
    },
    enabled,
    staleTime: TEAM_ACTIVITY_STALE_TIME,
    gcTime: TEAM_ACTIVITY_GC_TIME,
    refetchOnMount: 'always' as const,
  })
}

// ============================================================================
// Export function (not a hook)
// ============================================================================

/**
 * Download an Excel export of team activity data.
 */
export async function exportTeamActivity(
  tab: string,
  appId: string,
  dateFrom: string,
  dateTo: string,
): Promise<void> {
  const token = getAccessToken()
  const params = new URLSearchParams({
    tab,
    application_id: appId,
    date_from: dateFrom,
    date_to: dateTo,
  })
  const res = await fetch(`${API_BASE}/api/team-activity/export?${params}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) {
    const ct = res.headers.get('content-type') ?? ''
    const message = ct.includes('application/json')
      ? (await res.json() as { detail?: string }).detail ?? `Export failed (${res.status})`
      : `Export failed (${res.status})`
    throw new Error(message)
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `Team_Activity_${tab}_${new Date().toISOString().split('T')[0]}.xlsx`
  a.click()
  URL.revokeObjectURL(url)
}
