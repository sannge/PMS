/**
 * Task status distribution donut chart.
 */

import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'
import { cn } from '@/lib/utils'
import type { TaskStatusBreakdown } from '@/hooks/use-queries'

const STATUS_COLORS = {
  Todo: '#64748b',         // slate-500
  'In Progress': '#3b82f6', // blue-500
  'In Review': '#8b5cf6',   // violet-500
  Issue: '#ef4444',          // red-500
  Done: '#10b981',           // emerald-500
}

interface TaskDistributionChartProps {
  data: TaskStatusBreakdown
  className?: string
}

export function TaskDistributionChart({ data, className }: TaskDistributionChartProps): JSX.Element {
  const chartData = [
    { name: 'Todo', value: data.todo, color: STATUS_COLORS.Todo },
    { name: 'In Progress', value: data.in_progress, color: STATUS_COLORS['In Progress'] },
    { name: 'In Review', value: data.in_review, color: STATUS_COLORS['In Review'] },
    { name: 'Issue', value: data.issue, color: STATUS_COLORS.Issue },
    { name: 'Done', value: data.done, color: STATUS_COLORS.Done },
  ].filter(d => d.value > 0)

  const total = data.todo + data.in_progress + data.in_review + data.issue + data.done

  if (total === 0) {
    return (
      <div className={cn('rounded-2xl border border-border bg-card p-5', className)}>
        <h3 className="text-sm font-semibold text-foreground mb-4">Task Distribution</h3>
        <div className="flex h-48 items-center justify-center">
          <div className="text-center">
            <div className="mx-auto mb-2 h-24 w-24 rounded-full border-4 border-muted" />
            <p className="text-sm text-muted-foreground">No tasks</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className={cn('rounded-2xl border border-border bg-card p-5', className)}>
      <h3 className="text-sm font-semibold text-foreground mb-4">Task Distribution</h3>
      <div className="relative h-48" role="img" aria-label={`Task distribution: ${total} total tasks`}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={chartData}
              cx="50%"
              cy="50%"
              innerRadius={55}
              outerRadius={80}
              paddingAngle={2}
              dataKey="value"
              stroke="none"
            >
              {chartData.map((entry) => (
                <Cell key={entry.name} fill={entry.color} />
              ))}
            </Pie>
            <Tooltip
              content={({ active, payload }) => {
                if (!active || !payload?.[0]) return null
                const item = payload[0]
                const pct = Math.round(((item.value as number) / total) * 100)
                return (
                  <div className="rounded-lg border border-border bg-popover px-3 py-2 text-sm shadow-md">
                    <p className="font-medium text-foreground">{item.name}</p>
                    <p className="text-muted-foreground">
                      {item.value} tasks ({pct}%)
                    </p>
                  </div>
                )
              }}
            />
          </PieChart>
        </ResponsiveContainer>
        {/* Center text */}
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="text-center">
            <p className="text-2xl font-bold text-foreground">{total}</p>
            <p className="text-xs text-muted-foreground">tasks</p>
          </div>
        </div>
      </div>
      <span className="sr-only">
        {chartData.map(item => `${item.name}: ${item.value}`).join(', ')}
      </span>
      {/* Legend */}
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1">
        {chartData.map(item => (
          <div key={item.name} className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <div className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: item.color }} />
            <span>{item.name}</span>
            <span className="font-medium text-foreground">{item.value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
