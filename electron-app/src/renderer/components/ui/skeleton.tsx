/**
 * Skeleton Loading Components
 *
 * Modern shimmer-effect skeleton loaders for graceful loading states.
 * Features:
 * - Subtle animated shimmer effect
 * - Various preset shapes (text, avatar, card, row)
 * - Composable building blocks
 * - Maintains layout during loading
 */

import { cn } from '@/lib/utils'

// ============================================================================
// Base Skeleton Component
// ============================================================================

interface SkeletonProps {
  className?: string
  animate?: boolean
}

export function Skeleton({ className, animate = true }: SkeletonProps): JSX.Element {
  return (
    <div
      className={cn(
        'rounded-md bg-muted/60',
        animate && 'animate-pulse',
        className
      )}
    />
  )
}

// ============================================================================
// Skeleton Presets
// ============================================================================

/**
 * Text line skeleton
 */
export function SkeletonText({
  width = 'w-full',
  className
}: {
  width?: string
  className?: string
}): JSX.Element {
  return <Skeleton className={cn('h-3.5', width, className)} />
}

/**
 * Small text/label skeleton
 */
export function SkeletonLabel({
  width = 'w-16',
  className
}: {
  width?: string
  className?: string
}): JSX.Element {
  return <Skeleton className={cn('h-2.5', width, className)} />
}

/**
 * Avatar/icon skeleton
 */
export function SkeletonAvatar({
  size = 'md',
  className
}: {
  size?: 'sm' | 'md' | 'lg'
  className?: string
}): JSX.Element {
  const sizeClasses = {
    sm: 'h-6 w-6',
    md: 'h-8 w-8',
    lg: 'h-10 w-10',
  }
  return <Skeleton className={cn('rounded-full', sizeClasses[size], className)} />
}

/**
 * Badge skeleton
 */
export function SkeletonBadge({ className }: { className?: string }): JSX.Element {
  return <Skeleton className={cn('h-5 w-12 rounded-full', className)} />
}

/**
 * Button skeleton
 */
export function SkeletonButton({
  size = 'md',
  className
}: {
  size?: 'sm' | 'md' | 'lg'
  className?: string
}): JSX.Element {
  const sizeClasses = {
    sm: 'h-7 w-16',
    md: 'h-9 w-20',
    lg: 'h-11 w-24',
  }
  return <Skeleton className={cn('rounded-md', sizeClasses[size], className)} />
}

// ============================================================================
// Compound Skeleton Components
// ============================================================================

/**
 * Note tree item skeleton
 */
export function SkeletonNoteItem({
  level = 0,
  className
}: {
  level?: number
  className?: string
}): JSX.Element {
  return (
    <div
      className={cn('flex items-center gap-2 py-1.5 px-2', className)}
      style={{ paddingLeft: `${8 + level * 16}px` }}
    >
      {/* Expand icon placeholder */}
      <Skeleton className="h-4 w-4 rounded" />
      {/* Note icon */}
      <Skeleton className="h-4 w-4 rounded" />
      {/* Title */}
      <Skeleton className="h-3 flex-1 max-w-[120px]" />
    </div>
  )
}

/**
 * Notes sidebar skeleton
 */
export function SkeletonNotesSidebar({ className }: { className?: string }): JSX.Element {
  return (
    <div className={cn('space-y-1 p-1.5', className)}>
      <SkeletonNoteItem />
      <SkeletonNoteItem level={1} />
      <SkeletonNoteItem level={1} />
      <SkeletonNoteItem />
      <SkeletonNoteItem level={1} />
      <SkeletonNoteItem />
      <SkeletonNoteItem />
    </div>
  )
}

/**
 * Compact row card skeleton (for projects, applications, tasks)
 */
export function SkeletonRowCard({ className }: { className?: string }): JSX.Element {
  return (
    <div className={cn(
      'flex h-11 items-center gap-3 rounded-lg border border-border/40 bg-card/50 px-3',
      className
    )}>
      {/* Icon */}
      <Skeleton className="h-7 w-7 rounded-md" />
      {/* Name */}
      <Skeleton className="h-3.5 w-28" />
      {/* Badge */}
      <Skeleton className="h-4 w-14 rounded" />
      {/* Spacer */}
      <div className="flex-1" />
      {/* Meta info */}
      <Skeleton className="h-3 w-8" />
      <Skeleton className="h-3 w-6" />
    </div>
  )
}

/**
 * List of row cards skeleton
 */
export function SkeletonRowCardList({
  count = 5,
  className
}: {
  count?: number
  className?: string
}): JSX.Element {
  return (
    <div className={cn('space-y-2', className)}>
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonRowCard key={i} />
      ))}
    </div>
  )
}

/**
 * Tab bar skeleton
 */
export function SkeletonTabBar({
  count = 3,
  className
}: {
  count?: number
  className?: string
}): JSX.Element {
  return (
    <div className={cn('flex items-center gap-1 border-b border-border px-2 py-1', className)}>
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} className="h-7 w-24 rounded-t-md" />
      ))}
    </div>
  )
}

/**
 * Note content skeleton
 */
export function SkeletonNoteContent({ className }: { className?: string }): JSX.Element {
  return (
    <div className={cn('space-y-4 p-6', className)}>
      {/* Title */}
      <div className="space-y-2">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-3 w-32" />
      </div>
      {/* Content lines */}
      <div className="space-y-2.5 pt-4">
        <Skeleton className="h-3.5 w-full" />
        <Skeleton className="h-3.5 w-[90%]" />
        <Skeleton className="h-3.5 w-[75%]" />
        <Skeleton className="h-3.5 w-[85%]" />
        <Skeleton className="h-3.5 w-[60%]" />
      </div>
      {/* More content */}
      <div className="space-y-2.5 pt-2">
        <Skeleton className="h-3.5 w-[80%]" />
        <Skeleton className="h-3.5 w-full" />
        <Skeleton className="h-3.5 w-[70%]" />
      </div>
    </div>
  )
}

// ============================================================================
// Inline Loading Indicators
// ============================================================================

/**
 * Subtle inline loading dot animation
 */
export function LoadingDots({ className }: { className?: string }): JSX.Element {
  return (
    <span className={cn('inline-flex items-center gap-0.5', className)}>
      <span className="h-1 w-1 rounded-full bg-current animate-bounce" style={{ animationDelay: '0ms' }} />
      <span className="h-1 w-1 rounded-full bg-current animate-bounce" style={{ animationDelay: '150ms' }} />
      <span className="h-1 w-1 rounded-full bg-current animate-bounce" style={{ animationDelay: '300ms' }} />
    </span>
  )
}

/**
 * Subtle pulse indicator for background operations
 */
export function PulseIndicator({
  color = 'primary',
  className
}: {
  color?: 'primary' | 'success' | 'warning' | 'destructive'
  className?: string
}): JSX.Element {
  const colorClasses = {
    primary: 'bg-primary',
    success: 'bg-emerald-500',
    warning: 'bg-amber-500',
    destructive: 'bg-destructive',
  }

  return (
    <span className={cn('relative inline-flex h-2 w-2', className)}>
      <span className={cn(
        'absolute inline-flex h-full w-full animate-ping rounded-full opacity-75',
        colorClasses[color]
      )} />
      <span className={cn(
        'relative inline-flex h-2 w-2 rounded-full',
        colorClasses[color]
      )} />
    </span>
  )
}

/**
 * Inline saving indicator
 */
export function SavingIndicator({
  isSaving,
  className
}: {
  isSaving: boolean
  className?: string
}): JSX.Element {
  if (!isSaving) return <></>

  return (
    <span className={cn(
      'inline-flex items-center gap-1.5 text-xs text-muted-foreground',
      className
    )}>
      <PulseIndicator color="primary" />
      <span>Saving</span>
    </span>
  )
}

/**
 * Subtle progress bar for operations
 */
export function ProgressBar({
  isActive,
  className
}: {
  isActive: boolean
  className?: string
}): JSX.Element {
  if (!isActive) return <></>

  return (
    <div className={cn('h-0.5 w-full overflow-hidden bg-muted/30', className)}>
      <div
        className="h-full w-1/3 bg-primary/60 animate-slide-right"
        style={{
          animation: 'slideRight 1s ease-in-out infinite',
        }}
      />
      <style>{`
        @keyframes slideRight {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(400%); }
        }
      `}</style>
    </div>
  )
}

// ============================================================================
// Project & Kanban Skeletons
// ============================================================================

/**
 * Task card skeleton for kanban board
 */
export function SkeletonTaskCard({ className }: { className?: string }): JSX.Element {
  return (
    <div className={cn(
      'rounded-lg border border-border/40 bg-card p-3 space-y-2.5',
      className
    )}>
      {/* Task key and type */}
      <div className="flex items-center gap-2">
        <Skeleton className="h-3.5 w-3.5 rounded" />
        <Skeleton className="h-3 w-16" />
      </div>
      {/* Title */}
      <div className="space-y-1.5">
        <Skeleton className="h-3.5 w-full" />
        <Skeleton className="h-3.5 w-3/4" />
      </div>
      {/* Meta row */}
      <div className="flex items-center justify-between pt-1">
        <div className="flex items-center gap-2">
          <Skeleton className="h-3 w-3 rounded" />
          <Skeleton className="h-4 w-6 rounded-full" />
        </div>
        <Skeleton className="h-6 w-6 rounded-full" />
      </div>
    </div>
  )
}

/**
 * Kanban column skeleton
 */
export function SkeletonKanbanColumn({
  cardCount = 3,
  className
}: {
  cardCount?: number
  className?: string
}): JSX.Element {
  return (
    <div className={cn(
      'flex h-full w-72 flex-shrink-0 flex-col rounded-lg bg-muted/30',
      className
    )}>
      {/* Column Header */}
      <div className="flex items-center justify-between p-3 border-b border-border">
        <div className="flex items-center gap-2">
          <Skeleton className="h-6 w-6 rounded" />
          <Skeleton className="h-4 w-20" />
          <Skeleton className="h-5 w-6 rounded-full" />
        </div>
        <Skeleton className="h-6 w-6 rounded" />
      </div>
      {/* Cards */}
      <div className="flex-1 overflow-hidden p-2 space-y-2">
        {Array.from({ length: cardCount }).map((_, i) => (
          <SkeletonTaskCard key={i} />
        ))}
      </div>
    </div>
  )
}

/**
 * Full kanban board skeleton (4 columns)
 */
export function SkeletonKanbanBoard({ className }: { className?: string }): JSX.Element {
  // Varying card counts per column for realistic look
  const cardCounts = [3, 2, 2, 1]

  return (
    <div className={cn('flex gap-4 pb-4 min-w-max', className)}>
      {cardCounts.map((count, i) => (
        <SkeletonKanbanColumn key={i} cardCount={count} />
      ))}
    </div>
  )
}

/**
 * Project detail header skeleton
 */
export function SkeletonProjectHeader({ className }: { className?: string }): JSX.Element {
  return (
    <div className={cn('flex items-center justify-between gap-4 pb-2 border-b border-border', className)}>
      {/* Left: Breadcrumb + Title */}
      <div className="flex items-center gap-2 min-w-0">
        <Skeleton className="h-3.5 w-14" />
        <Skeleton className="h-3.5 w-3.5" />
        <Skeleton className="h-7 w-7 rounded-md" />
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-5 w-12 rounded" />
        <Skeleton className="h-4 w-16" />
        <Skeleton className="h-5 w-14 rounded" />
      </div>
      {/* Right: Actions */}
      <div className="flex items-center gap-1">
        <Skeleton className="h-7 w-7 rounded-md" />
        <Skeleton className="h-7 w-7 rounded-md" />
      </div>
    </div>
  )
}

/**
 * Full project detail page skeleton
 */
export function SkeletonProjectDetail({ className }: { className?: string }): JSX.Element {
  return (
    <div className={cn('flex flex-col h-full space-y-3', className)}>
      <SkeletonProjectHeader />
      {/* Toolbar skeleton */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Skeleton className="h-9 w-40 rounded-lg" />
          <Skeleton className="h-7 w-16 rounded-md" />
        </div>
        <Skeleton className="h-9 w-24 rounded-md" />
      </div>
      {/* Board skeleton */}
      <div className="flex-1 overflow-x-auto">
        <SkeletonKanbanBoard />
      </div>
    </div>
  )
}

/**
 * Project card skeleton (for grid view)
 */
export function SkeletonProjectCard({ className }: { className?: string }): JSX.Element {
  return (
    <div className={cn(
      'rounded-lg border border-border bg-card p-4 space-y-3',
      className
    )}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Skeleton className="h-8 w-8 rounded-md" />
          <div className="space-y-1">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-3 w-12" />
          </div>
        </div>
        <Skeleton className="h-6 w-6 rounded" />
      </div>
      {/* Description */}
      <div className="space-y-1.5">
        <Skeleton className="h-3 w-full" />
        <Skeleton className="h-3 w-3/4" />
      </div>
      {/* Footer */}
      <div className="flex items-center justify-between pt-2">
        <Skeleton className="h-5 w-16 rounded-full" />
        <div className="flex items-center gap-2">
          <Skeleton className="h-3 w-8" />
          <Skeleton className="h-5 w-5 rounded-full" />
        </div>
      </div>
    </div>
  )
}

/**
 * Project grid skeleton
 */
export function SkeletonProjectGrid({
  count = 6,
  className
}: {
  count?: number
  className?: string
}): JSX.Element {
  return (
    <div className={cn('grid gap-4 sm:grid-cols-2 lg:grid-cols-3', className)}>
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonProjectCard key={i} />
      ))}
    </div>
  )
}

/**
 * Project kanban column skeleton
 */
export function SkeletonProjectKanbanColumn({
  cardCount = 2,
  className
}: {
  cardCount?: number
  className?: string
}): JSX.Element {
  return (
    <div className={cn(
      'flex h-full w-64 flex-shrink-0 flex-col rounded-lg bg-muted/30',
      className
    )}>
      {/* Column Header */}
      <div className="flex items-center justify-between p-3 border-b border-border">
        <div className="flex items-center gap-2">
          <Skeleton className="h-5 w-5 rounded" />
          <Skeleton className="h-4 w-20" />
          <Skeleton className="h-5 w-6 rounded-full" />
        </div>
      </div>
      {/* Cards */}
      <div className="flex-1 overflow-hidden p-2 space-y-2">
        {Array.from({ length: cardCount }).map((_, i) => (
          <SkeletonProjectCard key={i} />
        ))}
      </div>
    </div>
  )
}

/**
 * Project kanban board skeleton (5 columns)
 */
export function SkeletonProjectKanbanBoard({ className }: { className?: string }): JSX.Element {
  const cardCounts = [2, 3, 1, 1, 2]

  return (
    <div className={cn('flex gap-4 pb-4 min-w-max', className)}>
      {cardCounts.map((count, i) => (
        <SkeletonProjectKanbanColumn key={i} cardCount={count} />
      ))}
    </div>
  )
}

/**
 * List view row skeleton
 */
export function SkeletonListRow({ className }: { className?: string }): JSX.Element {
  return (
    <div className={cn(
      'flex items-center gap-4 p-3 border-b border-border/50',
      className
    )}>
      <Skeleton className="h-3.5 w-3.5 rounded" />
      <Skeleton className="h-3 w-16" />
      <Skeleton className="h-3.5 flex-1 max-w-[300px]" />
      <Skeleton className="h-3 w-3 rounded" />
      <Skeleton className="h-5 w-8 rounded-full" />
      <Skeleton className="h-6 w-6 rounded-full" />
    </div>
  )
}

/**
 * List view group skeleton
 */
export function SkeletonListViewGroup({
  rowCount = 3,
  className
}: {
  rowCount?: number
  className?: string
}): JSX.Element {
  return (
    <div className={cn('rounded-lg border border-border bg-card', className)}>
      {/* Group header */}
      <div className="flex items-center gap-3 p-3 border-b border-border">
        <Skeleton className="h-4 w-4" />
        <Skeleton className="h-6 w-6 rounded" />
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-5 w-6 rounded-full" />
      </div>
      {/* Rows */}
      {Array.from({ length: rowCount }).map((_, i) => (
        <SkeletonListRow key={i} />
      ))}
    </div>
  )
}

/**
 * Full list view skeleton
 */
export function SkeletonListView({ className }: { className?: string }): JSX.Element {
  return (
    <div className={cn('space-y-4', className)}>
      <SkeletonListViewGroup rowCount={2} />
      <SkeletonListViewGroup rowCount={3} />
      <SkeletonListViewGroup rowCount={1} />
      <SkeletonListViewGroup rowCount={2} />
    </div>
  )
}

// ============================================================================
// Attachment, Checklist & Comment Skeletons
// ============================================================================

/**
 * Attachment grid item skeleton
 */
export function SkeletonAttachmentGrid({ className }: { className?: string }): JSX.Element {
  return (
    <div className={cn(
      'rounded-lg border border-border/40 bg-card overflow-hidden',
      className
    )}>
      {/* Thumbnail */}
      <Skeleton className="h-32 w-full rounded-none" />
      {/* Info */}
      <div className="p-3 space-y-1.5">
        <Skeleton className="h-3.5 w-3/4" />
        <Skeleton className="h-2.5 w-12" />
      </div>
    </div>
  )
}

/**
 * Attachment list item skeleton
 */
export function SkeletonAttachmentList({ className }: { className?: string }): JSX.Element {
  return (
    <div className={cn(
      'flex items-center gap-3 rounded-md border border-border/40 bg-card p-3',
      className
    )}>
      <Skeleton className="h-5 w-5 rounded" />
      <div className="flex-1 space-y-1">
        <Skeleton className="h-3.5 w-48" />
        <Skeleton className="h-2.5 w-24" />
      </div>
    </div>
  )
}

/**
 * Attachments section skeleton
 */
export function SkeletonAttachments({
  viewMode = 'list',
  count = 3,
  className,
}: {
  viewMode?: 'grid' | 'list'
  count?: number
  className?: string
}): JSX.Element {
  if (viewMode === 'grid') {
    return (
      <div className={cn('grid grid-cols-2 gap-3 sm:grid-cols-3', className)}>
        {Array.from({ length: count }).map((_, i) => (
          <SkeletonAttachmentGrid key={i} />
        ))}
      </div>
    )
  }

  return (
    <div className={cn('space-y-2', className)}>
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonAttachmentList key={i} />
      ))}
    </div>
  )
}

/**
 * Checklist item skeleton
 */
export function SkeletonChecklistItem({ className }: { className?: string }): JSX.Element {
  return (
    <div className={cn('flex items-center gap-3 py-1.5', className)}>
      <Skeleton className="h-4 w-4 rounded" />
      <Skeleton className="h-3.5 flex-1 max-w-[200px]" />
    </div>
  )
}

/**
 * Checklist card skeleton
 */
export function SkeletonChecklistCard({
  itemCount = 3,
  className,
}: {
  itemCount?: number
  className?: string
}): JSX.Element {
  return (
    <div className={cn(
      'rounded-lg border border-border/40 bg-card p-3',
      className
    )}>
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Skeleton className="h-4 w-4 rounded" />
          <Skeleton className="h-4 w-24" />
        </div>
        <Skeleton className="h-3 w-12" />
      </div>
      {/* Progress bar */}
      <Skeleton className="h-1.5 w-full rounded-full mb-3" />
      {/* Items */}
      <div className="space-y-1">
        {Array.from({ length: itemCount }).map((_, i) => (
          <SkeletonChecklistItem key={i} />
        ))}
      </div>
    </div>
  )
}

/**
 * Checklists section skeleton
 */
export function SkeletonChecklists({
  count = 2,
  className,
}: {
  count?: number
  className?: string
}): JSX.Element {
  return (
    <div className={cn('space-y-3', className)}>
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonChecklistCard key={i} itemCount={i === 0 ? 3 : 2} />
      ))}
    </div>
  )
}

/**
 * Comment skeleton
 */
export function SkeletonComment({ className }: { className?: string }): JSX.Element {
  return (
    <div className={cn('flex gap-3', className)}>
      {/* Avatar */}
      <Skeleton className="h-8 w-8 rounded-full flex-shrink-0" />
      {/* Content */}
      <div className="flex-1 space-y-2">
        {/* Header */}
        <div className="flex items-center gap-2">
          <Skeleton className="h-3.5 w-24" />
          <Skeleton className="h-2.5 w-16" />
        </div>
        {/* Body */}
        <div className="space-y-1.5">
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-4/5" />
          <Skeleton className="h-3 w-2/3" />
        </div>
      </div>
    </div>
  )
}

/**
 * Comments section skeleton
 */
export function SkeletonComments({
  count = 3,
  className,
}: {
  count?: number
  className?: string
}): JSX.Element {
  return (
    <div className={cn('space-y-4', className)}>
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonComment key={i} />
      ))}
    </div>
  )
}

// ============================================================================
// Overlay States
// ============================================================================

/**
 * Subtle overlay for operations on existing content
 */
export function OperationOverlay({
  isActive,
  message,
  className
}: {
  isActive: boolean
  message?: string
  className?: string
}): JSX.Element {
  if (!isActive) return <></>

  return (
    <div className={cn(
      'absolute inset-0 z-10 flex items-center justify-center',
      'bg-background/40 backdrop-blur-[1px]',
      'animate-in fade-in-0 duration-150',
      className
    )}>
      {message && (
        <span className="flex items-center gap-2 rounded-md bg-card/90 px-3 py-1.5 text-sm text-muted-foreground shadow-sm border border-border/50">
          <PulseIndicator />
          {message}
        </span>
      )}
    </div>
  )
}

export default Skeleton
