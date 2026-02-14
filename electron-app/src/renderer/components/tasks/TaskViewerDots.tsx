/**
 * TaskViewerDots Component
 *
 * Shows small colored dots indicating other users viewing the same task.
 * Displays up to 3 dots with a +N indicator for overflow.
 */

import { cn } from '@/lib/utils'
import type { TaskViewer } from '@/hooks/use-task-viewers'

// ============================================================================
// Types
// ============================================================================

export interface TaskViewerDotsProps {
  viewers: TaskViewer[]
  maxDots?: number
  className?: string
}

// ============================================================================
// Constants
// ============================================================================

const COLORS = [
  'bg-blue-500',
  'bg-green-500',
  'bg-purple-500',
  'bg-orange-500',
  'bg-pink-500',
  'bg-cyan-500',
]

// Get consistent color for a user
function getUserColor(userId: string): string {
  let hash = 0
  for (let i = 0; i < userId.length; i++) {
    hash = ((hash << 5) - hash) + userId.charCodeAt(i)
    hash = hash & hash
  }
  return COLORS[Math.abs(hash) % COLORS.length]
}

// ============================================================================
// Component
// ============================================================================

export function TaskViewerDots({
  viewers,
  maxDots = 3,
  className,
}: TaskViewerDotsProps): JSX.Element | null {
  if (viewers.length === 0) return null

  const visibleViewers = viewers.slice(0, maxDots)
  const overflowCount = viewers.length - maxDots

  return (
    <div
      className={cn(
        'flex items-center gap-0.5',
        className
      )}
      title={viewers.map((v) => v.user_name).join(', ')}
    >
      {visibleViewers.map((viewer) => (
        <div
          key={viewer.user_id}
          className={cn(
            'w-2 h-2 rounded-full',
            'ring-1 ring-background',
            'animate-pulse',
            getUserColor(viewer.user_id)
          )}
          title={`${viewer.user_name} is viewing`}
        />
      ))}
      {overflowCount > 0 && (
        <span className="text-[8px] text-muted-foreground font-medium ml-0.5">
          +{overflowCount}
        </span>
      )}
    </div>
  )
}

export default TaskViewerDots
