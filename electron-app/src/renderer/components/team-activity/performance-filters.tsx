/**
 * Performance Filters
 *
 * Combined workspace selector + date range picker for the Team Activity page.
 * Uses Radix Select for the workspace dropdown and native date inputs.
 */

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

// ============================================================================
// Types
// ============================================================================

interface PerformanceFiltersProps {
  applications: Array<{ id: string; name: string }>
  selectedAppId: string // 'all' or specific UUID
  onAppChange: (appId: string) => void
  dateFrom: string // YYYY-MM-DD
  dateTo: string
  onDateFromChange: (date: string) => void
  onDateToChange: (date: string) => void
}

// ============================================================================
// Component
// ============================================================================

export function PerformanceFilters({
  applications,
  selectedAppId,
  onAppChange,
  dateFrom,
  dateTo,
  onDateFromChange,
  onDateToChange,
}: PerformanceFiltersProps): JSX.Element {
  return (
    <div className="flex items-center gap-3">
      {/* Workspace selector */}
      <Select value={selectedAppId} onValueChange={onAppChange}>
        <SelectTrigger className="w-[180px] h-8 text-xs">
          <SelectValue placeholder="All Workspaces" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All Workspaces</SelectItem>
          {applications.map((app) => (
            <SelectItem key={app.id} value={app.id}>
              {app.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* Date range */}
      <div className="flex items-center gap-1.5">
        <input
          type="date"
          value={dateFrom}
          onChange={(e) => onDateFromChange(e.target.value)}
          className="h-8 rounded-md border border-input bg-transparent px-2 text-xs text-foreground shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
        />
        <span className="text-xs text-muted-foreground">to</span>
        <input
          type="date"
          value={dateTo}
          onChange={(e) => onDateToChange(e.target.value)}
          className="h-8 rounded-md border border-input bg-transparent px-2 text-xs text-foreground shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
        />
      </div>
    </div>
  )
}
