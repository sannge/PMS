/**
 * Project health horizontal stacked bar chart.
 */

import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { cn } from '@/lib/utils'
import type { ProjectHealthItem } from '@/hooks/use-queries'

interface ProjectHealthChartProps {
  data: ProjectHealthItem[]
  onProjectClick?: (projectId: string, applicationId: string, applicationName: string) => void
  className?: string
}

export function ProjectHealthChart({ data, onProjectClick, className }: ProjectHealthChartProps): JSX.Element {
  if (data.length === 0) {
    return (
      <div className={cn('rounded-2xl border border-border bg-card p-5', className)}>
        <h3 className="text-sm font-semibold text-foreground mb-4">Project Health</h3>
        <div className="flex h-48 items-center justify-center">
          <p className="text-sm text-muted-foreground">No projects yet</p>
        </div>
      </div>
    )
  }

  const chartData = data.map(p => ({
    name: p.key.length > 8 ? p.key.slice(0, 8) + '...' : p.key,
    fullName: p.name,
    id: p.id,
    applicationId: p.application_id,
    applicationName: p.application_name,
    done: p.done_tasks,
    active: p.active_tasks,
    review: p.review_tasks ?? 0,
    issue: p.issue_tasks,
    todo: Math.max(0, p.total_tasks - p.done_tasks - p.active_tasks - (p.review_tasks ?? 0) - p.issue_tasks),
    pct: p.completion_pct,
  }))

  return (
    <div className={cn('rounded-2xl border border-border bg-card p-5', className)}>
      <h3 className="text-sm font-semibold text-foreground mb-4">Project Health</h3>
      <div className="h-48" role="img" aria-label={`Project health for ${data.length} projects`}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={chartData}
            layout="vertical"
            margin={{ top: 0, right: 40, bottom: 0, left: 0 }}
            onClick={(state: Record<string, unknown> | null) => {
              const activePayload = state?.activePayload as Array<{ payload: Record<string, string> }> | undefined
              const item = activePayload?.[0]?.payload
              if (item?.id && item?.applicationId) {
                onProjectClick?.(item.id, item.applicationId, item.applicationName ?? '')
              }
            }}
            style={{ cursor: onProjectClick ? 'pointer' : undefined }}
          >
            <XAxis type="number" hide />
            <YAxis
              type="category"
              dataKey="name"
              tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }}
              axisLine={false}
              tickLine={false}
              width={60}
            />
            <Tooltip
              content={({ active, payload }) => {
                if (!active || !payload?.[0]) return null
                const item = payload[0].payload
                return (
                  <div className="rounded-lg border border-border bg-popover px-3 py-2 text-sm shadow-md">
                    <p className="font-medium text-foreground">{item.fullName}</p>
                    <p className="text-muted-foreground">{item.pct}% complete</p>
                    <div className="mt-1 space-y-0.5 text-xs text-muted-foreground">
                      {item.done > 0 && <p>Done: {item.done}</p>}
                      {item.active > 0 && <p>Active: {item.active}</p>}
                      {item.review > 0 && <p>In Review: {item.review}</p>}
                      {item.issue > 0 && <p>Issue: {item.issue}</p>}
                      {item.todo > 0 && <p>Todo: {item.todo}</p>}
                    </div>
                  </div>
                )
              }}
            />
            <Bar dataKey="done" stackId="a" fill="#10b981" radius={[0, 0, 0, 0]} />
            <Bar dataKey="active" stackId="a" fill="#3b82f6" />
            <Bar dataKey="review" stackId="a" fill="#8b5cf6" />
            <Bar dataKey="issue" stackId="a" fill="#ef4444" />
            <Bar dataKey="todo" stackId="a" fill="#64748b" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <span className="sr-only">
        {chartData.map(d => `${d.fullName}: ${d.done} done, ${d.active} active, ${d.review} review, ${d.issue} issue, ${d.todo} todo`).join('. ')}
      </span>
      {/* Legend */}
      <div className="mt-3 flex gap-4 text-xs text-muted-foreground">
        <div className="flex items-center gap-1.5"><div className="h-2.5 w-2.5 rounded-full bg-emerald-500" /> Done</div>
        <div className="flex items-center gap-1.5"><div className="h-2.5 w-2.5 rounded-full bg-blue-500" /> Active</div>
        <div className="flex items-center gap-1.5"><div className="h-2.5 w-2.5 rounded-full bg-violet-500" /> In Review</div>
        <div className="flex items-center gap-1.5"><div className="h-2.5 w-2.5 rounded-full bg-red-500" /> Issue</div>
        <div className="flex items-center gap-1.5"><div className="h-2.5 w-2.5 rounded-full bg-slate-500" /> Todo</div>
      </div>
    </div>
  )
}
