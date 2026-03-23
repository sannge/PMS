/**
 * Overview Tab
 *
 * KPI cards + charts for the Team Activity overview.
 * Uses recharts for data visualization.
 */

import { useId } from 'react'
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts'
import { cn } from '@/lib/utils'
import { useTeamActivityOverview } from '@/hooks/use-team-activity'
import { Skeleton } from '@/components/ui/skeleton'
import {
  CheckCircle2,
  PlayCircle,
  Eye,
  AlertTriangle,
  Sigma,
} from 'lucide-react'

// ============================================================================
// Types
// ============================================================================

interface OverviewTabProps {
  appId: string
  dateFrom: string
  dateTo: string
}

// ============================================================================
// Chart colors (dark-theme friendly)
// ============================================================================

const CHART_COLORS = {
  completed: 'hsl(142, 71%, 45%)',
  inProgress: 'hsl(217, 91%, 60%)',
  inReview: 'hsl(48, 96%, 53%)',
  overdue: 'hsl(0, 84%, 60%)',
  issue: 'hsl(0, 84%, 60%)',
}

// ============================================================================
// KPI Card
// ============================================================================

interface KPICardProps {
  icon: React.ReactNode
  label: string
  value: number
  color: string
  bgColor: string
}

function KPICard({ icon, label, value, color, bgColor }: KPICardProps): JSX.Element {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="flex items-center gap-3">
        <div className={cn('flex h-10 w-10 items-center justify-center rounded-lg', bgColor)}>
          <span className={color}>{icon}</span>
        </div>
        <div>
          <p className="text-2xl font-bold text-foreground">{value}</p>
          <p className="text-xs text-muted-foreground">{label}</p>
        </div>
      </div>
    </div>
  )
}

// ============================================================================
// Loading skeleton
// ============================================================================

function OverviewSkeleton(): JSX.Element {
  return (
    <div className="space-y-6">
      {/* KPI cards */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="rounded-xl border border-border bg-card p-4">
            <div className="flex items-center gap-3">
              <Skeleton className="h-10 w-10 rounded-lg" />
              <div className="space-y-1.5">
                <Skeleton className="h-6 w-12" />
                <Skeleton className="h-3 w-16" />
              </div>
            </div>
          </div>
        ))}
      </div>
      {/* Charts */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Skeleton className="h-64 rounded-xl" />
        <Skeleton className="h-64 rounded-xl" />
      </div>
    </div>
  )
}

// ============================================================================
// Custom tooltip
// ============================================================================

interface TooltipPayloadItem {
  name: string
  value: number
  color: string
}

interface CustomTooltipProps {
  active?: boolean
  payload?: TooltipPayloadItem[]
  label?: string
}

function ChartTooltip({ active, payload, label }: CustomTooltipProps): JSX.Element | null {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-border bg-popover px-3 py-2 shadow-md">
      <p className="mb-1 text-xs font-medium text-foreground">{label}</p>
      {payload.map((entry, i) => (
        <p key={i} className="text-xs text-muted-foreground">
          <span className="inline-block h-2 w-2 rounded-full mr-1.5" style={{ backgroundColor: entry.color }} />
          {entry.name}: {entry.value}
        </p>
      ))}
    </div>
  )
}

// ============================================================================
// Formatters
// ============================================================================

function formatWeek(dateStr: string): string {
  const d = new Date(dateStr + 'T12:00:00Z')
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

// ============================================================================
// Component
// ============================================================================

export function OverviewTab({ appId, dateFrom, dateTo }: OverviewTabProps): JSX.Element {
  const { data, isLoading, isError } = useTeamActivityOverview(appId, dateFrom, dateTo)
  const gradientId = useId()
  const safeGradientId = `overview-gradient-${gradientId.replace(/:/g, '')}`

  if (isLoading) return <OverviewSkeleton />

  if (isError || !data) {
    return (
      <div className="flex h-64 items-center justify-center">
        <p className="text-sm text-muted-foreground">Failed to load overview data. Try adjusting the date range.</p>
      </div>
    )
  }

  const { kpi, completion_trend, by_project, by_member } = data

  const hasNoData =
    kpi.completed === 0 &&
    kpi.in_progress === 0 &&
    kpi.in_review === 0 &&
    kpi.overdue === 0 &&
    kpi.total_story_points === 0

  if (hasNoData && completion_trend.length === 0 && by_project.length === 0 && by_member.length === 0) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-2">
        <p className="text-sm font-medium text-foreground">No activity data</p>
        <p className="text-xs text-muted-foreground">No tasks or activity found for the selected date range.</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <KPICard
          icon={<CheckCircle2 className="h-5 w-5" />}
          label="Completed"
          value={kpi.completed}
          color="text-emerald-500"
          bgColor="bg-emerald-500/10"
        />
        <KPICard
          icon={<PlayCircle className="h-5 w-5" />}
          label="In Progress"
          value={kpi.in_progress}
          color="text-blue-500"
          bgColor="bg-blue-500/10"
        />
        <KPICard
          icon={<Eye className="h-5 w-5" />}
          label="In Review"
          value={kpi.in_review}
          color="text-yellow-500"
          bgColor="bg-yellow-500/10"
        />
        <KPICard
          icon={<AlertTriangle className="h-5 w-5" />}
          label="Overdue"
          value={kpi.overdue}
          color="text-red-500"
          bgColor="bg-red-500/10"
        />
        <KPICard
          icon={<Sigma className="h-5 w-5" />}
          label="Story Points"
          value={kpi.total_story_points}
          color="text-violet-500"
          bgColor="bg-violet-500/10"
        />
      </div>

      {/* Completion Trend Chart */}
      {completion_trend.length > 0 && (
        <div className="rounded-xl border border-border bg-card p-5">
          <h3 className="mb-4 text-sm font-semibold text-foreground">Weekly Completion Trend</h3>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={completion_trend} margin={{ top: 5, right: 10, bottom: 5, left: -15 }}>
                <defs>
                  <linearGradient id={safeGradientId} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={CHART_COLORS.completed} stopOpacity={0.3} />
                    <stop offset="95%" stopColor={CHART_COLORS.completed} stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} />
                <XAxis
                  dataKey="week"
                  tickFormatter={formatWeek}
                  tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  allowDecimals={false}
                  tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip content={<ChartTooltip />} />
                <Area
                  type="monotone"
                  dataKey="count"
                  name="Completed"
                  stroke={CHART_COLORS.completed}
                  fill={`url(#${safeGradientId})`}
                  strokeWidth={2}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Breakdowns */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* By Project */}
        {by_project.length > 0 && (
          <div className="rounded-xl border border-border bg-card p-5">
            <h3 className="mb-4 text-sm font-semibold text-foreground">By Project</h3>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={by_project} layout="vertical" margin={{ top: 5, right: 10, bottom: 5, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} horizontal={false} />
                  <XAxis
                    type="number"
                    allowDecimals={false}
                    tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    dataKey="project_key"
                    type="category"
                    width={70}
                    tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip content={<ChartTooltip />} />
                  <Bar dataKey="completed" name="Completed" stackId="a" fill={CHART_COLORS.completed} radius={0} />
                  <Bar dataKey="in_progress" name="In Progress" stackId="a" fill={CHART_COLORS.inProgress} radius={0} />
                  <Bar dataKey="in_review" name="In Review" stackId="a" fill={CHART_COLORS.inReview} radius={0} />
                  <Bar dataKey="overdue" name="Overdue" stackId="a" fill={CHART_COLORS.overdue} radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* By Member */}
        {by_member.length > 0 && (
          <div className="rounded-xl border border-border bg-card p-5">
            <h3 className="mb-4 text-sm font-semibold text-foreground">By Member</h3>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={by_member} layout="vertical" margin={{ top: 5, right: 10, bottom: 5, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} horizontal={false} />
                  <XAxis
                    type="number"
                    allowDecimals={false}
                    tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    dataKey="display_name"
                    type="category"
                    width={90}
                    tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip content={<ChartTooltip />} />
                  <Bar dataKey="completed" name="Completed" stackId="a" fill={CHART_COLORS.completed} radius={0} />
                  <Bar dataKey="in_progress" name="In Progress" stackId="a" fill={CHART_COLORS.inProgress} radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
