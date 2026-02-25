/**
 * Completion trend area chart showing tasks completed per day over 14 days.
 */

import { useId } from 'react'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { cn } from '@/lib/utils'
import type { CompletionDataPoint } from '@/hooks/use-queries'

interface CompletionTrendChartProps {
  data: CompletionDataPoint[]
  className?: string
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr + 'T12:00:00Z')
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

export function CompletionTrendChart({ data, className }: CompletionTrendChartProps): JSX.Element {
  const gradientId = useId()
  const safeGradientId = `completion-gradient-${gradientId.replace(/:/g, '')}`
  const maxCount = Math.max(...data.map(d => d.count), 1)
  const allZero = data.every(d => d.count === 0)

  return (
    <div className={cn('rounded-2xl border border-border bg-card p-5', className)}>
      <h3 className="text-sm font-semibold text-foreground mb-4">Completion Trend</h3>
      {allZero ? (
        <div className="flex h-48 items-center justify-center">
          <p className="text-sm text-muted-foreground">No completions in the last 14 days</p>
        </div>
      ) : (
        <>
          <div className="h-48" role="img" aria-label="Completion trend over 14 days">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data} margin={{ top: 5, right: 5, bottom: 5, left: -20 }}>
                <defs>
                  <linearGradient id={safeGradientId} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis
                  dataKey="date"
                  tickFormatter={formatDate}
                  tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }}
                  axisLine={false}
                  tickLine={false}
                  interval="preserveStartEnd"
                />
                <YAxis
                  allowDecimals={false}
                  domain={[0, maxCount + 1]}
                  tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }}
                  axisLine={false}
                  tickLine={false}
                  width={30}
                />
                <Tooltip
                  content={({ active, payload }) => {
                    if (!active || !payload?.[0]) return null
                    const item = payload[0].payload as CompletionDataPoint
                    return (
                      <div className="rounded-lg border border-border bg-popover px-3 py-2 text-sm shadow-md">
                        <p className="font-medium text-foreground">{formatDate(item.date)}</p>
                        <p className="text-muted-foreground">
                          {item.count} task{item.count !== 1 ? 's' : ''} completed
                        </p>
                      </div>
                    )
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="count"
                  stroke="#10b981"
                  strokeWidth={2}
                  fill={`url(#${safeGradientId})`}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <span className="sr-only">
            Completions: {data.map(d => `${formatDate(d.date)}: ${d.count}`).join(', ')}
          </span>
        </>
      )}
    </div>
  )
}
