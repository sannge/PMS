/**
 * PresenceAvatars Component
 *
 * Displays avatars of users currently viewing a resource.
 * Features:
 * - Stacked avatar display
 * - Idle state indication
 * - Overflow count
 * - Tooltip with names
 */

import { cn } from '@/lib/utils'
import { Eye } from 'lucide-react'
import type { PresenceUser } from '@/hooks/use-presence'

// ============================================================================
// Types
// ============================================================================

export interface PresenceAvatarsProps {
  viewers: PresenceUser[]
  maxVisible?: number
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

// ============================================================================
// Constants
// ============================================================================

const SIZE_CONFIG = {
  sm: { avatar: 'h-6 w-6', text: 'text-[10px]', overflow: 'h-6 w-6 text-[10px]' },
  md: { avatar: 'h-8 w-8', text: 'text-xs', overflow: 'h-8 w-8 text-xs' },
  lg: { avatar: 'h-10 w-10', text: 'text-sm', overflow: 'h-10 w-10 text-sm' },
}

// ============================================================================
// Helper Functions
// ============================================================================

function getInitials(name: string | null): string {
  if (!name) return '?'
  const parts = name.trim().split(/\s+/)
  if (parts.length === 1) return parts[0].charAt(0).toUpperCase()
  return (parts[0].charAt(0) + parts[parts.length - 1].charAt(0)).toUpperCase()
}

// ============================================================================
// Component
// ============================================================================

export function PresenceAvatars({
  viewers,
  maxVisible = 5,
  size = 'md',
  className,
}: PresenceAvatarsProps): JSX.Element | null {
  if (viewers.length === 0) return null

  const sizeConfig = SIZE_CONFIG[size]
  const visibleViewers = viewers.slice(0, maxVisible)
  const overflowCount = viewers.length - maxVisible

  return (
    <div
      className={cn('flex items-center', className)}
      title={viewers.map((v) => v.user_name).join(', ')}
    >
      {/* Viewing indicator */}
      <div className="flex items-center gap-1 mr-2 text-muted-foreground">
        <Eye className="h-3.5 w-3.5" />
        <span className="text-xs">{viewers.length} viewing</span>
      </div>

      {/* Avatar stack */}
      <div className="flex -space-x-2">
        {visibleViewers.map((viewer, index) => (
          <div
            key={viewer.user_id}
            className={cn(
              'relative rounded-full border-2 border-background',
              'transition-transform hover:z-10 hover:scale-110',
              viewer.idle && 'opacity-50'
            )}
            style={{ zIndex: visibleViewers.length - index }}
            title={`${viewer.user_name}${viewer.idle ? ' (idle)' : ''}`}
          >
            {viewer.avatar_url ? (
              <img
                src={viewer.avatar_url}
                alt={viewer.user_name}
                className={cn('rounded-full object-cover', sizeConfig.avatar)}
              />
            ) : (
              <div
                className={cn(
                  'flex items-center justify-center rounded-full',
                  'bg-primary/10 text-primary font-medium',
                  sizeConfig.avatar,
                  sizeConfig.text
                )}
              >
                {getInitials(viewer.user_name)}
              </div>
            )}

            {/* Idle indicator */}
            {viewer.idle && (
              <div
                className={cn(
                  'absolute bottom-0 right-0 w-2 h-2 rounded-full',
                  'bg-amber-500 border border-background'
                )}
                title="Idle"
              />
            )}

            {/* Online indicator */}
            {!viewer.idle && (
              <div
                className={cn(
                  'absolute bottom-0 right-0 w-2 h-2 rounded-full',
                  'bg-green-500 border border-background'
                )}
                title="Active"
              />
            )}
          </div>
        ))}

        {/* Overflow count */}
        {overflowCount > 0 && (
          <div
            className={cn(
              'flex items-center justify-center rounded-full',
              'bg-muted text-muted-foreground border-2 border-background font-medium',
              sizeConfig.overflow
            )}
            title={viewers
              .slice(maxVisible)
              .map((v) => v.user_name)
              .join(', ')}
          >
            +{overflowCount}
          </div>
        )}
      </div>
    </div>
  )
}

export default PresenceAvatars
