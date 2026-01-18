/**
 * Member Management Modal Component
 *
 * Full-featured modal for managing application members.
 * Includes search, lazy loading, role editing, and member removal.
 *
 * Features:
 * - Search members by name or email
 * - Lazy loading with "Load more" button
 * - Role editing (based on permissions)
 * - Member removal (based on permissions)
 * - Invite new members button
 */

import { useState, useCallback, useMemo, useEffect, useRef } from 'react'
import { cn } from '@/lib/utils'
import {
  X,
  Search,
  UserPlus,
  Crown,
  Edit2,
  Eye,
  MoreVertical,
  Trash2,
  Loader2,
  Users,
  Check,
} from 'lucide-react'
import type { MemberWithUser, ApplicationRole } from '@/stores/members-store'

// ============================================================================
// Types
// ============================================================================

export interface MemberManagementModalProps {
  /**
   * Whether the modal is open
   */
  isOpen: boolean
  /**
   * Callback to close the modal
   */
  onClose: () => void
  /**
   * Array of members to display
   */
  members: MemberWithUser[]
  /**
   * Whether members are loading
   */
  isLoading?: boolean
  /**
   * Total count of members
   */
  totalCount?: number
  /**
   * Current user's ID
   */
  currentUserId?: string
  /**
   * Current user's role
   */
  currentUserRole?: ApplicationRole
  /**
   * Original application owner's user ID
   */
  originalOwnerId?: string
  /**
   * Whether role update is in progress
   */
  isUpdatingRole?: boolean
  /**
   * Whether member removal is in progress
   */
  isRemovingMember?: boolean
  /**
   * Whether there are more members to load
   */
  hasMore?: boolean
  /**
   * Callback to load more members
   */
  onLoadMore?: () => void
  /**
   * Callback when search query changes
   */
  onSearch?: (query: string) => void
  /**
   * Callback when role edit is requested
   */
  onEditRole?: (member: MemberWithUser) => void
  /**
   * Callback when member removal is requested
   */
  onRemoveMember?: (member: MemberWithUser) => void
  /**
   * Callback to open invite modal
   */
  onInvite?: () => void
  /**
   * Application name for the title
   */
  applicationName?: string
}

// ============================================================================
// Constants
// ============================================================================

const ROLE_CONFIG: Record<ApplicationRole, { icon: JSX.Element; label: string; colorClass: string }> = {
  owner: {
    icon: <Crown className="h-3 w-3" />,
    label: 'Owner',
    colorClass: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  },
  editor: {
    icon: <Edit2 className="h-3 w-3" />,
    label: 'Editor',
    colorClass: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  },
  viewer: {
    icon: <Eye className="h-3 w-3" />,
    label: 'Viewer',
    colorClass: 'bg-slate-100 text-slate-700 dark:bg-slate-900/30 dark:text-slate-400',
  },
}

// ============================================================================
// Helper Functions
// ============================================================================

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

function getMemberDisplayName(member: MemberWithUser): string {
  return member.user?.full_name || member.user?.email || 'Unknown'
}

// ============================================================================
// Member Item Component
// ============================================================================

interface MemberItemProps {
  member: MemberWithUser
  isCurrentUser: boolean
  canEdit: boolean
  canRemove: boolean
  onEditRole?: () => void
  onRemove?: () => void
}

function MemberItem({
  member,
  isCurrentUser,
  canEdit,
  canRemove,
  onEditRole,
  onRemove,
}: MemberItemProps): JSX.Element {
  const [showMenu, setShowMenu] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  const roleConfig = ROLE_CONFIG[member.role]

  // Close menu when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setShowMenu(false)
      }
    }
    if (showMenu) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [showMenu])

  return (
    <div
      className={cn(
        'flex items-center gap-3 p-3 rounded-lg transition-colors',
        isCurrentUser && 'bg-primary/5',
        'hover:bg-accent/50'
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
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium text-foreground truncate">
            {getMemberDisplayName(member)}
          </p>
          {isCurrentUser && (
            <span className="text-[10px] font-medium text-muted-foreground bg-muted px-1.5 py-0.5 rounded flex-shrink-0">
              You
            </span>
          )}
        </div>
        {member.user?.email && (
          <p className="text-xs text-muted-foreground truncate">{member.user.email}</p>
        )}
      </div>

      {/* Role Badge */}
      <div
        className={cn(
          'flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium flex-shrink-0',
          roleConfig.colorClass
        )}
      >
        {roleConfig.icon}
        <span>{roleConfig.label}</span>
      </div>

      {/* Actions Menu */}
      {(canEdit || canRemove) && (
        <div className="relative flex-shrink-0" ref={menuRef}>
          <button
            onClick={() => setShowMenu(!showMenu)}
            className={cn(
              'p-1.5 rounded-md text-muted-foreground',
              'hover:bg-accent hover:text-foreground',
              'focus:outline-none focus:ring-2 focus:ring-ring'
            )}
          >
            <MoreVertical className="h-4 w-4" />
          </button>

          {showMenu && (
            <div
              className={cn(
                'absolute right-0 top-full mt-1 z-50',
                'min-w-[140px] rounded-md border border-border bg-popover shadow-lg',
                'py-1'
              )}
            >
              {canEdit && (
                <button
                  onClick={() => {
                    setShowMenu(false)
                    onEditRole?.()
                  }}
                  className={cn(
                    'flex w-full items-center gap-2 px-3 py-2 text-sm',
                    'hover:bg-accent text-left'
                  )}
                >
                  <Edit2 className="h-3.5 w-3.5" />
                  Change role
                </button>
              )}
              {canRemove && (
                <button
                  onClick={() => {
                    setShowMenu(false)
                    onRemove?.()
                  }}
                  className={cn(
                    'flex w-full items-center gap-2 px-3 py-2 text-sm',
                    'hover:bg-accent text-left text-destructive'
                  )}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  Remove
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Main Component
// ============================================================================

export function MemberManagementModal({
  isOpen,
  onClose,
  members,
  isLoading = false,
  totalCount,
  currentUserId,
  currentUserRole,
  originalOwnerId,
  isUpdatingRole = false,
  isRemovingMember = false,
  hasMore = false,
  onLoadMore,
  onSearch,
  onEditRole,
  onRemoveMember,
  onInvite,
  applicationName,
}: MemberManagementModalProps): JSX.Element | null {
  const [searchQuery, setSearchQuery] = useState('')
  const searchInputRef = useRef<HTMLInputElement>(null)

  // Focus search input when modal opens
  useEffect(() => {
    if (isOpen && searchInputRef.current) {
      setTimeout(() => searchInputRef.current?.focus(), 100)
    }
  }, [isOpen])

  // Clear search when modal closes
  useEffect(() => {
    if (!isOpen) {
      setSearchQuery('')
    }
  }, [isOpen])

  // Handle search
  const handleSearchChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const query = e.target.value
      setSearchQuery(query)
      onSearch?.(query)
    },
    [onSearch]
  )

  // Filter members locally if no onSearch provided
  const filteredMembers = useMemo(() => {
    if (onSearch || !searchQuery) return members
    const query = searchQuery.toLowerCase()
    return members.filter(
      (member) =>
        member.user?.full_name?.toLowerCase().includes(query) ||
        member.user?.email?.toLowerCase().includes(query)
    )
  }, [members, searchQuery, onSearch])

  // Check permissions for a member
  const canEditMember = useCallback(
    (member: MemberWithUser): boolean => {
      if (!currentUserRole) return false
      const isCurrentUser = member.user_id === currentUserId
      const isOriginalOwner = member.user_id === originalOwnerId
      const isUserOwner = currentUserRole === 'owner'
      const isUserEditor = currentUserRole === 'editor'
      const memberIsViewer = member.role === 'viewer'

      return !isCurrentUser && !isOriginalOwner && (
        isUserOwner || (isUserEditor && memberIsViewer)
      )
    },
    [currentUserId, currentUserRole, originalOwnerId]
  )

  const canRemoveMember = useCallback(
    (member: MemberWithUser): boolean => {
      if (!currentUserRole) return false
      const isCurrentUser = member.user_id === currentUserId
      const isOriginalOwner = member.user_id === originalOwnerId
      const isUserOwner = currentUserRole === 'owner'
      const memberIsOwner = member.role === 'owner'

      return !isCurrentUser && !isOriginalOwner && (isUserOwner || !memberIsOwner)
    },
    [currentUserId, currentUserRole, originalOwnerId]
  )

  // Handle escape key
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape' && isOpen) {
        onClose()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  if (!isOpen) return null

  const displayCount = totalCount ?? members.length
  const canInvite = currentUserRole === 'owner' || currentUserRole === 'editor'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-background/80 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div
        className={cn(
          'relative w-full max-w-lg max-h-[80vh] mx-4',
          'rounded-lg border border-border bg-card shadow-lg',
          'flex flex-col'
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div className="flex items-center gap-2">
            <Users className="h-5 w-5 text-muted-foreground" />
            <div>
              <h2 className="text-lg font-semibold text-foreground">Team Members</h2>
              {applicationName && (
                <p className="text-xs text-muted-foreground">{applicationName}</p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">{displayCount} member{displayCount !== 1 ? 's' : ''}</span>
            <button
              onClick={onClose}
              className={cn(
                'p-1.5 rounded-md text-muted-foreground',
                'hover:bg-accent hover:text-foreground',
                'focus:outline-none focus:ring-2 focus:ring-ring'
              )}
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        {/* Search and Invite */}
        <div className="p-4 border-b border-border space-y-3">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <input
              ref={searchInputRef}
              type="text"
              placeholder="Search members..."
              value={searchQuery}
              onChange={handleSearchChange}
              className={cn(
                'w-full pl-9 pr-4 py-2 rounded-md',
                'bg-background border border-input',
                'text-sm placeholder:text-muted-foreground',
                'focus:outline-none focus:ring-2 focus:ring-ring'
              )}
            />
          </div>

          {/* Invite Button */}
          {canInvite && onInvite && (
            <button
              onClick={onInvite}
              className={cn(
                'flex w-full items-center justify-center gap-2 py-2 px-4 rounded-md',
                'bg-primary text-primary-foreground',
                'hover:bg-primary/90 transition-colors',
                'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
                'text-sm font-medium'
              )}
            >
              <UserPlus className="h-4 w-4" />
              Invite Members
            </button>
          )}
        </div>

        {/* Member List */}
        <div className="flex-1 overflow-y-auto p-2">
          {isLoading && members.length === 0 ? (
            // Loading skeleton
            <div className="space-y-2">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="flex items-center gap-3 p-3">
                  <div className="h-10 w-10 rounded-full bg-muted animate-pulse" />
                  <div className="flex-1 space-y-2">
                    <div className="h-4 w-32 bg-muted animate-pulse rounded" />
                    <div className="h-3 w-48 bg-muted animate-pulse rounded" />
                  </div>
                </div>
              ))}
            </div>
          ) : filteredMembers.length === 0 ? (
            // Empty state
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
              <Users className="h-12 w-12 mb-3 opacity-50" />
              <p className="text-sm">
                {searchQuery ? 'No members found' : 'No members yet'}
              </p>
            </div>
          ) : (
            // Member list
            <div className="space-y-1">
              {filteredMembers.map((member) => (
                <MemberItem
                  key={member.id}
                  member={member}
                  isCurrentUser={member.user_id === currentUserId}
                  canEdit={canEditMember(member)}
                  canRemove={canRemoveMember(member)}
                  onEditRole={() => onEditRole?.(member)}
                  onRemove={() => onRemoveMember?.(member)}
                />
              ))}
            </div>
          )}

          {/* Load More */}
          {hasMore && !isLoading && (
            <div className="pt-4 pb-2">
              <button
                onClick={onLoadMore}
                className={cn(
                  'flex w-full items-center justify-center gap-2 py-2 px-4 rounded-md',
                  'border border-input bg-background',
                  'hover:bg-accent transition-colors',
                  'focus:outline-none focus:ring-2 focus:ring-ring',
                  'text-sm text-muted-foreground'
                )}
              >
                Load more members
              </button>
            </div>
          )}

          {/* Loading indicator for load more */}
          {isLoading && members.length > 0 && (
            <div className="flex items-center justify-center py-4">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          )}
        </div>

        {/* Updating/Removing indicator */}
        {(isUpdatingRole || isRemovingMember) && (
          <div className="absolute inset-0 bg-background/50 flex items-center justify-center rounded-lg">
            <div className="flex items-center gap-2 bg-card px-4 py-2 rounded-md shadow-lg border border-border">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span className="text-sm">
                {isUpdatingRole ? 'Updating role...' : 'Removing member...'}
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default MemberManagementModal
