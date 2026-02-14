import { cn } from '@/lib/utils'
import { ArrowUpDown, Filter, Search, X } from 'lucide-react'

// ============================================================================
// Types
// ============================================================================

export type SortField = 'due_date' | 'name' | 'updated_at'
export type SortOrder = 'asc' | 'desc'

export interface SortFilterState {
  sortBy: SortField
  sortOrder: SortOrder
  statusFilter?: string
  search: string
}

interface SortFilterControlsProps {
  state: SortFilterState
  onChange: (state: SortFilterState) => void
  className?: string
}

// ============================================================================
// Constants
// ============================================================================

const SORT_OPTIONS: { value: SortField; label: string }[] = [
  { value: 'due_date', label: 'Due Date' },
  { value: 'name', label: 'Name' },
  { value: 'updated_at', label: 'Last Updated' },
]

const STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: 'Todo', label: 'Todo' },
  { value: 'In Progress', label: 'In Progress' },
  { value: 'Issue', label: 'Issue' },
  { value: 'Done', label: 'Done' },
]

// ============================================================================
// Component
// ============================================================================

export function SortFilterControls({
  state,
  onChange,
  className,
}: SortFilterControlsProps) {
  const hasActiveFilters = !!state.statusFilter

  return (
    <div className={cn('flex flex-wrap items-center gap-2', className)}>
      {/* Search */}
      <div className="relative flex-1 min-w-[180px] max-w-xs">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
        <input
          type="text"
          placeholder="Search projects and tasks..."
          value={state.search}
          onChange={(e) => onChange({ ...state, search: e.target.value })}
          className={cn(
            'w-full rounded-lg border border-border bg-background pl-8 pr-3 py-1.5',
            'text-sm placeholder:text-muted-foreground',
            'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1',
            'transition-colors'
          )}
        />
        {state.search && (
          <button
            onClick={() => onChange({ ...state, search: '' })}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* Sort */}
      <div className="flex items-center gap-1">
        <ArrowUpDown className="h-3.5 w-3.5 text-muted-foreground" />
        <select
          value={state.sortBy}
          onChange={(e) => onChange({ ...state, sortBy: e.target.value as SortField })}
          className={cn(
            'rounded-lg border border-border bg-background px-2 py-1.5',
            'text-xs font-medium text-foreground',
            'focus:outline-none focus:ring-2 focus:ring-ring',
            'cursor-pointer'
          )}
        >
          {SORT_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <button
          onClick={() =>
            onChange({ ...state, sortOrder: state.sortOrder === 'asc' ? 'desc' : 'asc' })
          }
          className={cn(
            'rounded-lg border border-border bg-background px-2 py-1.5',
            'text-xs font-medium text-foreground',
            'hover:bg-accent/10 transition-colors',
            'focus:outline-none focus:ring-2 focus:ring-ring'
          )}
          title={state.sortOrder === 'asc' ? 'Ascending' : 'Descending'}
        >
          {state.sortOrder === 'asc' ? 'Asc' : 'Desc'}
        </button>
      </div>

      {/* Status filter */}
      <Filter className="h-3.5 w-3.5 text-muted-foreground" />
      <select
        value={state.statusFilter || ''}
        onChange={(e) =>
          onChange({ ...state, statusFilter: e.target.value || undefined })
        }
        className={cn(
          'rounded-lg border border-border bg-background px-2 py-1.5',
          'text-xs font-medium text-foreground',
          'focus:outline-none focus:ring-2 focus:ring-ring',
          'cursor-pointer',
          state.statusFilter && 'border-accent/50'
        )}
      >
        <option value="">All statuses</option>
        {STATUS_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>

      {/* Clear filters */}
      {hasActiveFilters && (
        <button
          onClick={() =>
            onChange({ ...state, statusFilter: undefined })
          }
          className={cn(
            'rounded-lg px-2 py-1.5 text-xs font-medium',
            'text-muted-foreground hover:text-foreground',
            'transition-colors'
          )}
        >
          Clear filters
        </button>
      )}
    </div>
  )
}
