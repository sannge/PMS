/**
 * Member Avatar Group Component
 *
 * Displays a compact group of member avatars with overflow indicator.
 * Click to open the full member management modal.
 *
 * Features:
 * - Shows up to N avatars (default 5)
 * - "+X more" overflow indicator
 * - Click to open member management
 * - Hover tooltips with member names
 */

import { useCallback } from 'react'
import { cn } from '@/lib/utils'
import { Users } from 'lucide-react'
import type { MemberWithUser } from '@/stores/members-store'

// ============================================================================
// Types
// ============================================================================

export interface MemberAvatarGroupProps {
  /**
   * Array of members to display
   */
  members: MemberWithUser[]
  /**
   * Total count of members (may be more than members array if paginated)
   */
  totalCount?: number
  /**
   * Maximum number of avatars to display before showing overflow
   */
  maxDisplay?: number
  /**
   * Size of avatars
   */
  size?: 'sm' | 'md' | 'lg'
  /**
   * Callback when the group is clicked
   */
  onClick?: () => void
  /**
   * Whether the component is in a loading state
   */
  isLoading?: boolean
  /**
   * Additional CSS classes
   */
  className?: string
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Get initials from member data
 */
function getMemberInitials(member: MemberWithUser): string {
  if (member.user?.full_name) {
    const names = member.user.full_name.split(' ')
    if (names.length >= 2) {
      return `${names[0][0]}${names[names.length - 1][0]}`.toUpperCase()
    }
    return names[0].substring(0, 2).toUpperCase()
  }
  if (member.user?.email) {
    return member.user.email.substring(0, 2).toUpperCase()
  }
  return '??'
}

/**
 * Get display name for tooltip
 */
function getMemberDisplayName(member: MemberWithUser): string {
  return member.user?.full_name || member.user?.email || 'Unknown'
}

// ============================================================================
// Size Configuration
// ============================================================================

const SIZE_CONFIG = {
  sm: {
    avatar: 'h-6 w-6 text-[10px]',
    overlap: '-ml-1.5',
    overflow: 'h-6 min-w-6 px-1.5 text-[10px]',
  },
  md: {
    avatar: 'h-8 w-8 text-xs',
    overlap: '-ml-2',
    overflow: 'h-8 min-w-8 px-2 text-xs',
  },
  lg: {
    avatar: 'h-10 w-10 text-sm',
    overlap: '-ml-2.5',
    overflow: 'h-10 min-w-10 px-2.5 text-sm',
  },
}

// ============================================================================
// Component
// ============================================================================

export function MemberAvatarGroup({
  members,
  totalCount,
  maxDisplay = 5,
  size = 'md',
  onClick,
  isLoading = false,
  className,
}: MemberAvatarGroupProps): JSX.Element {
  const config = SIZE_CONFIG[size]
  const displayMembers = members.slice(0, maxDisplay)
  const actualTotal = totalCount ?? members.length
  const overflowCount = actualTotal - maxDisplay

  const handleClick = useCallback(() => {
    if (onClick) {
      onClick()
    }
  }, [onClick])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (onClick && (e.key === 'Enter' || e.key === ' ')) {
        e.preventDefault()
        onClick()
      }
    },
    [onClick]
  )

  // Loading state
  if (isLoading) {
    return (
      <div className={cn('flex items-center', className)}>
        <div className="flex items-center -space-x-2">
          {[...Array(3)].map((_, i) => (
            <div
              key={i}
              className={cn(
                'rounded-full bg-muted animate-pulse ring-2 ring-background',
                config.avatar
              )}
            />
          ))}
        </div>
      </div>
    )
  }

  // Empty state
  if (members.length === 0) {
    return (
      <button
        onClick={handleClick}
        onKeyDown={handleKeyDown}
        className={cn(
          'flex items-center gap-1.5 text-muted-foreground hover:text-foreground transition-colors',
          'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 rounded-md px-2 py-1',
          className
        )}
      >
        <Users className={size === 'sm' ? 'h-3.5 w-3.5' : 'h-4 w-4'} />
        <span className={size === 'sm' ? 'text-xs' : 'text-sm'}>No members</span>
      </button>
    )
  }

  return (
    <button
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      className={cn(
        'flex items-center group',
        'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 rounded-full',
        'hover:opacity-90 transition-opacity',
        className
      )}
      aria-label={`View ${actualTotal} team member${actualTotal !== 1 ? 's' : ''}`}
    >
      <div className="flex items-center">
        {displayMembers.map((member, index) => (
          <div
            key={member.id}
            className={cn(
              'relative rounded-full ring-2 ring-background',
              'bg-gradient-to-br from-primary/20 to-primary/10 text-primary font-medium',
              'flex items-center justify-center',
              config.avatar,
              index > 0 && config.overlap
            )}
            style={{ zIndex: maxDisplay - index }}
            title={getMemberDisplayName(member)}
          >
            {getMemberInitials(member)}
          </div>
        ))}

        {overflowCount > 0 && (
          <div
            className={cn(
              'relative rounded-full ring-2 ring-background',
              'bg-muted text-muted-foreground font-medium',
              'flex items-center justify-center',
              config.overflow,
              config.overlap
            )}
            style={{ zIndex: 0 }}
          >
            +{overflowCount}
          </div>
        )}
      </div>
    </button>
  )
}

export default MemberAvatarGroup
