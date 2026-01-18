/**
 * Member List Component
 *
 * Displays a scrollable list of application members with empty state,
 * loading state, and actions.
 *
 * Features:
 * - Empty state with icon
 * - Loading skeleton
 * - Scrollable member list
 * - Header with member count
 * - Role badges with manager indicator
 * - Role edit and remove actions (for owners)
 * - Footer with view all link
 */

import { useCallback } from 'react'
import { cn } from '@/lib/utils'
import {
  Users,
  UserCircle2,
  Shield,
  Crown,
  Eye,
  Edit2,
  Trash2,
  Star,
} from 'lucide-react'
import type { MemberWithUser, ApplicationRole } from '@/stores/members-store'

// ============================================================================
// Types
// ============================================================================

export interface MemberListProps {
  /**
   * Array of members to display
   */
  members: MemberWithUser[]
  /**
   * Whether members are loading
   */
  isLoading?: boolean
  /**
   * Total member count
   */
  totalCount?: number
  /**
   * Current user's ID to highlight their row
   */
  currentUserId?: string
  /**
   * Whether current user can edit members (is owner)
   */
  canEdit?: boolean
  /**
   * Whether current user is the application creator (can assign managers)
   */
  isCreator?: boolean
  /**
   * Callback when a member is clicked
   */
  onMemberClick?: (member: MemberWithUser) => void
  /**
   * Callback when edit role is clicked
   */
  onEditRole?: (member: MemberWithUser) => void
  /**
   * Callback when remove member is clicked
   */
  onRemoveMember?: (member: MemberWithUser) => void
  /**
   * Callback when toggle manager is clicked
   */
  onToggleManager?: (member: MemberWithUser) => void
  /**
   * Callback when view all is clicked
   */
  onViewAll?: () => void
  /**
   * Maximum height of the list
   */
  maxHeight?: number | string
  /**
   * Whether to show the header
   */
  showHeader?: boolean
  /**
   * Whether to show the footer
   */
  showFooter?: boolean
  /**
   * Additional CSS classes
   */
  className?: string
}

interface RoleConfig {
  label: string
  icon: JSX.Element
  colorClass: string
}

// ============================================================================
// Constants
// ============================================================================

const ROLE_CONFIG: Record<ApplicationRole, RoleConfig> = {
  owner: {
    label: 'Owner',
    icon: <Crown className="h-3 w-3" />,
    colorClass: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  },
  editor: {
    label: 'Editor',
    icon: <Edit2 className="h-3 w-3" />,
    colorClass: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  },
  viewer: {
    label: 'Viewer',
    icon: <Eye className="h-3 w-3" />,
    colorClass: 'bg-slate-100 text-slate-700 dark:bg-slate-900/30 dark:text-slate-400',
  },
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Format relative time
 */
function formatRelativeTime(dateString: string): string {
  // Ensure UTC parsing - append 'Z' if no timezone indicator
  let dateStr = dateString
  if (!dateStr.endsWith('Z') && !dateStr.includes('+') && !dateStr.includes('-', 10)) {
    dateStr = dateStr + 'Z'
  }

  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()

  // Handle future dates or very recent
  if (diffMs < 0 || diffMs < 60000) return 'Just now'

  const diffMin = Math.floor(diffMs / (1000 * 60))
  const diffHour = Math.floor(diffMs / (1000 * 60 * 60))
  const diffDay = Math.floor(diffMs / (1000 * 60 * 60 * 24))
  const diffWeek = Math.floor(diffDay / 7)

  if (diffMin < 60) {
    return `${diffMin}m ago`
  }
  if (diffHour < 24) {
    return `${diffHour}h ago`
  }
  if (diffDay < 7) {
    return `${diffDay}d ago`
  }
  if (diffWeek < 4) {
    return `${diffWeek}w ago`
  }

  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

/**
 * Get member display name
 */
function getMemberDisplayName(member: MemberWithUser): string {
  if (member.user?.full_name) {
    return member.user.full_name
  }
  if (member.user?.email) {
    return member.user.email
  }
  return 'Unknown user'
}

/**
 * Get member initials for avatar
 */
function getMemberInitials(member: MemberWithUser): string {
  if (member.user?.full_name) {
    const parts = member.user.full_name.split(' ')
    if (parts.length >= 2) {
      return `${parts[0][0]}${parts[1][0]}`.toUpperCase()
    }
    return parts[0].slice(0, 2).toUpperCase()
  }
  if (member.user?.email) {
    return member.user.email.slice(0, 2).toUpperCase()
  }
  return 'UN'
}

// ============================================================================
// Loading Skeleton
// ============================================================================

function MemberSkeleton(): JSX.Element {
  return (
    <div className="flex gap-3 p-3 animate-pulse">
      <div className="flex-shrink-0 h-10 w-10 rounded-full bg-muted" />
      <div className="flex-1 space-y-2">
        <div className="h-4 w-1/3 rounded bg-muted" />
        <div className="h-3 w-1/2 rounded bg-muted" />
      </div>
      <div className="flex-shrink-0 h-6 w-16 rounded bg-muted" />
    </div>
  )
}

// ============================================================================
// Empty State
// ============================================================================

function EmptyState(): JSX.Element {
  return (
    <div className="flex flex-col items-center justify-center py-8 px-4 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted mb-3">
        <Users className="h-6 w-6 text-muted-foreground" />
      </div>
      <h4 className="text-sm font-medium text-foreground">
        No members yet
      </h4>
      <p className="mt-1 text-xs text-muted-foreground">
        Invite team members to collaborate on this application.
      </p>
    </div>
  )
}

// ============================================================================
// Member Item
// ============================================================================

interface MemberItemProps {
  member: MemberWithUser
  isCurrentUser?: boolean
  canEdit?: boolean
  isCreator?: boolean
  onMemberClick?: (member: MemberWithUser) => void
  onEditRole?: (member: MemberWithUser) => void
  onRemoveMember?: (member: MemberWithUser) => void
  onToggleManager?: (member: MemberWithUser) => void
}

function MemberItem({
  member,
  isCurrentUser = false,
  canEdit = false,
  isCreator = false,
  onMemberClick,
  onEditRole,
  onRemoveMember,
  onToggleManager,
}: MemberItemProps): JSX.Element {
  const roleConfig = ROLE_CONFIG[member.role]

  // Handle click
  const handleClick = useCallback(() => {
    if (onMemberClick) {
      onMemberClick(member)
    }
  }, [member, onMemberClick])

  // Handle edit role
  const handleEditRole = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation()
      if (onEditRole) {
        onEditRole(member)
      }
    },
    [member, onEditRole]
  )

  // Handle remove member
  const handleRemoveMember = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation()
      if (onRemoveMember) {
        onRemoveMember(member)
      }
    },
    [member, onRemoveMember]
  )

  // Handle toggle manager
  const handleToggleManager = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation()
      if (onToggleManager) {
        onToggleManager(member)
      }
    },
    [member, onToggleManager]
  )

  // Check if we can remove this member (cannot remove self or last owner)
  const canRemove = canEdit && !isCurrentUser && member.role !== 'owner'
  // Check if we can edit this member's role (cannot change owner's role)
  const canEditMember = canEdit && !isCurrentUser && member.role !== 'owner'
  // Can toggle manager only for editors and only if creator
  const canToggleManager = isCreator && member.role === 'editor'

  return (
    <div
      onClick={handleClick}
      role={onMemberClick ? 'button' : undefined}
      tabIndex={onMemberClick ? 0 : undefined}
      onKeyDown={(e) => {
        if (onMemberClick && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault()
          handleClick()
        }
      }}
      className={cn(
        'group relative flex items-center gap-3 p-3 transition-colors',
        isCurrentUser && 'bg-primary/5',
        onMemberClick && 'cursor-pointer hover:bg-accent/50',
        'focus:outline-none focus:bg-accent/50'
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          'flex-shrink-0 flex h-10 w-10 items-center justify-center rounded-full',
          'bg-gradient-to-br from-primary/20 to-primary/10 text-primary font-medium text-sm'
        )}
      >
        {getMemberInitials(member)}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        {/* Name */}
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium text-foreground line-clamp-1">
            {getMemberDisplayName(member)}
          </p>
          {isCurrentUser && (
            <span className="text-[10px] font-medium text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
              You
            </span>
          )}
          {member.is_manager && (
            <span
              className="flex items-center gap-0.5 text-[10px] font-medium text-amber-600 bg-amber-100 dark:bg-amber-900/30 dark:text-amber-400 px-1.5 py-0.5 rounded"
              title="Manager - can assign users to projects"
            >
              <Star className="h-2.5 w-2.5" />
              Manager
            </span>
          )}
        </div>

        {/* Email and joined date */}
        <div className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
          {member.user?.email && (
            <span className="line-clamp-1">{member.user.email}</span>
          )}
          <span className="hidden sm:inline">•</span>
          <span className="hidden sm:inline">Joined {formatRelativeTime(member.created_at)}</span>
        </div>
      </div>

      {/* Role Badge */}
      <div
        className={cn(
          'flex-shrink-0 inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium',
          roleConfig.colorClass
        )}
      >
        {roleConfig.icon}
        {roleConfig.label}
      </div>

      {/* Actions - visible on hover for owners */}
      {(canEditMember || canRemove || canToggleManager) && (
        <div className="flex-shrink-0 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          {/* Toggle Manager (for editors only, by creator) */}
          {canToggleManager && onToggleManager && (
            <button
              onClick={handleToggleManager}
              className={cn(
                'rounded-md p-1.5 text-muted-foreground transition-colors',
                member.is_manager
                  ? 'hover:bg-amber-100 hover:text-amber-600 dark:hover:bg-amber-900/30 dark:hover:text-amber-400'
                  : 'hover:bg-accent hover:text-accent-foreground',
                'focus:outline-none focus:ring-2 focus:ring-ring'
              )}
              title={member.is_manager ? 'Revoke manager role' : 'Grant manager role'}
            >
              <Star className={cn('h-3.5 w-3.5', member.is_manager && 'fill-current')} />
            </button>
          )}

          {/* Edit Role */}
          {canEditMember && onEditRole && (
            <button
              onClick={handleEditRole}
              className={cn(
                'rounded-md p-1.5 text-muted-foreground transition-colors',
                'hover:bg-accent hover:text-accent-foreground',
                'focus:outline-none focus:ring-2 focus:ring-ring'
              )}
              title="Change role"
            >
              <Shield className="h-3.5 w-3.5" />
            </button>
          )}

          {/* Remove Member */}
          {canRemove && onRemoveMember && (
            <button
              onClick={handleRemoveMember}
              className={cn(
                'rounded-md p-1.5 text-muted-foreground transition-colors',
                'hover:bg-destructive/10 hover:text-destructive',
                'focus:outline-none focus:ring-2 focus:ring-ring'
              )}
              title="Remove member"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Component
// ============================================================================

export function MemberList({
  members,
  isLoading = false,
  totalCount,
  currentUserId,
  canEdit = false,
  isCreator = false,
  onMemberClick,
  onEditRole,
  onRemoveMember,
  onToggleManager,
  onViewAll,
  maxHeight = 400,
  showHeader = true,
  showFooter = true,
  className,
}: MemberListProps): JSX.Element {
  // Calculate display count
  const displayCount = totalCount ?? members.length

  // Handle view all
  const handleViewAll = useCallback(() => {
    if (onViewAll) {
      onViewAll()
    }
  }, [onViewAll])

  return (
    <div className={cn('flex flex-col', className)}>
      {/* Header */}
      {showHeader && (
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div className="flex items-center gap-2">
            <Users className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-semibold text-foreground">
              Members
            </h3>
            {displayCount > 0 && (
              <span className="flex h-5 min-w-[20px] items-center justify-center rounded-full bg-muted px-1.5 text-[10px] font-semibold text-muted-foreground">
                {displayCount > 99 ? '99+' : displayCount}
              </span>
            )}
          </div>
        </div>
      )}

      {/* List Content */}
      <div
        className="overflow-y-auto divide-y divide-border"
        style={{ maxHeight }}
      >
        {/* Loading State */}
        {isLoading && (
          <>
            <MemberSkeleton />
            <MemberSkeleton />
            <MemberSkeleton />
          </>
        )}

        {/* Empty State */}
        {!isLoading && members.length === 0 && <EmptyState />}

        {/* Members List */}
        {!isLoading &&
          members.map((member) => (
            <MemberItem
              key={member.id}
              member={member}
              isCurrentUser={member.user_id === currentUserId}
              canEdit={canEdit}
              isCreator={isCreator}
              onMemberClick={onMemberClick}
              onEditRole={onEditRole}
              onRemoveMember={onRemoveMember}
              onToggleManager={onToggleManager}
            />
          ))}
      </div>

      {/* Footer */}
      {showFooter && members.length > 0 && onViewAll && (
        <div className="border-t border-border">
          <button
            onClick={handleViewAll}
            className={cn(
              'flex w-full items-center justify-center gap-2 py-3 text-sm font-medium',
              'text-primary hover:bg-accent/50 transition-colors',
              'focus:outline-none focus:bg-accent/50'
            )}
          >
            View all members
          </button>
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Exports
// ============================================================================

export { EmptyState, MemberSkeleton, MemberItem, ROLE_CONFIG, formatRelativeTime, getMemberDisplayName, getMemberInitials }
export default MemberList
