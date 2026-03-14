/**
 * Search Selection Card
 *
 * Inline selection card rendered when Blair's search_knowledge tool returns
 * 5+ results. All items are checked by default — user unchecks noisy ones
 * before the agent synthesizes an answer from the approved chunks.
 */

import { memo, useCallback, useMemo } from 'react'
import { Search, CheckSquare, Square } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { SearchSelectionItem } from './types'

// ============================================================================
// Types
// ============================================================================

export interface SearchSelectionCardProps {
  prompt: string
  items: SearchSelectionItem[]
  status: 'pending' | 'submitted' | 'skipped'
  selectedIndices: Set<number>
  onToggle: (index: number) => void
  onToggleAll: () => void
  onSubmit: () => void
  onSkip: () => void
}

// ============================================================================
// Helpers
// ============================================================================

function formatScore(score: number): string {
  if (!Number.isFinite(score)) return '0%'
  return `${Math.min(100, Math.max(0, Math.round(score * 100)))}%`
}

// ============================================================================
// Memoized row item (Issue 8 — FE-004, QE-001, CR1-004)
// ============================================================================

const SearchResultItem = memo(function SearchResultItem({
  item,
  isChecked,
  isPending,
  onToggle,
}: {
  item: SearchSelectionItem
  isChecked: boolean
  isPending: boolean
  onToggle: (index: number) => void
}): JSX.Element {
  const CheckIcon = isChecked ? CheckSquare : Square

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (isPending && (e.key === 'Enter' || e.key === ' ')) {
      e.preventDefault()
      onToggle(item.index)
    }
  }, [isPending, onToggle, item.index])

  return (
    <div
      role="checkbox"
      aria-checked={isChecked}
      aria-disabled={!isPending}
      aria-label={`${item.title}, score ${formatScore(item.score)}`}
      tabIndex={isPending ? 0 : -1}
      onClick={() => isPending && onToggle(item.index)}
      onKeyDown={handleKeyDown}
      className={cn(
        'flex items-start gap-2 rounded-md px-2 py-1.5 transition-colors',
        isPending && 'cursor-pointer hover:bg-muted/50',
        !isChecked && 'opacity-50',
        !isPending && 'pointer-events-none'
      )}
    >
      <CheckIcon className="h-4 w-4 mt-0.5 text-primary shrink-0" aria-hidden="true" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-medium truncate">{item.title}</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-primary/20 text-primary font-medium shrink-0">
            {formatScore(item.score)}
          </span>
        </div>
        {item.heading && (
          <p className="text-xs text-muted-foreground truncate">
            &gt; {item.heading}
          </p>
        )}
        <p className="text-xs text-muted-foreground line-clamp-2 mt-0.5">
          {item.snippet}
        </p>
      </div>
    </div>
  )
})

// ============================================================================
// Component
// ============================================================================

export const SearchSelectionCard = memo(function SearchSelectionCard({
  prompt,
  items,
  status,
  selectedIndices,
  onToggle,
  onToggleAll,
  onSubmit,
  onSkip,
}: SearchSelectionCardProps): JSX.Element {
  const isPending = status === 'pending'
  const selectedCount = selectedIndices.size

  // Issue 12 (QE-006) — defensive cap at 20 items
  const displayItems = useMemo(() => items.slice(0, 20), [items])
  const allSelected = useMemo(
    () => displayItems.length > 0 && displayItems.every(item => selectedIndices.has(item.index)),
    [displayItems, selectedIndices]
  )

  return (
    <div
      role="region"
      aria-label="Search result selection"
      className={cn(
        'mt-2 rounded-lg border border-border bg-background/80 p-3',
        isPending && 'ring-1 ring-primary/20'
      )}
    >
      {/* Header */}
      <div className="flex items-start gap-2 mb-1">
        <Search className="h-4 w-4 mt-0.5 text-primary shrink-0" aria-hidden="true" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs font-medium">{prompt}</p>
            <span className="text-[10px] text-muted-foreground shrink-0" aria-live="polite">
              {selectedCount} of {displayItems.length} selected
            </span>
          </div>
        </div>
      </div>

      {/* Toggle all */}
      {isPending && (
        <div className="pl-6 mb-1">
          <button
            type="button"
            onClick={onToggleAll}
            aria-label={allSelected ? 'Deselect all results' : 'Select all results'}
            className="text-[10px] text-primary cursor-pointer hover:underline"
          >
            {allSelected ? 'Deselect All' : 'Select All'}
          </button>
        </div>
      )}

      {/* Scrollable list */}
      <div
        role="group"
        aria-label="Search results"
        className="max-h-80 overflow-y-auto space-y-1 mt-2 pl-6"
      >
        {displayItems.map((item) => (
          <SearchResultItem
            key={item.index}
            item={item}
            isChecked={selectedIndices.has(item.index)}
            isPending={isPending}
            onToggle={onToggle}
          />
        ))}
      </div>

      {/* Buttons */}
      <div className="flex items-center gap-2 mt-3 pl-6">
        <Button
          size="sm"
          onClick={onSubmit}
          disabled={selectedCount === 0 || !isPending}
          className="text-xs"
        >
          {status === 'submitted' ? 'Submitted' : `Continue with ${selectedCount} selected`}
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={onSkip}
          disabled={!isPending}
          className="text-xs"
        >
          {status === 'skipped' ? 'Skipped' : 'None of these'}
        </Button>
      </div>
    </div>
  )
})
