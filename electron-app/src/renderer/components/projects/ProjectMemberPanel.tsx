/**
 * ProjectMemberPanel Component
 *
 * Panel for managing project-level member assignments.
 * Shows which application members can work on a specific project.
 *
 * Features:
 * - List of current project members
 * - Add members from available application members
 * - Remove members (owners only)
 * - User avatars and role badges
 */

import { useEffect, useCallback, useState, useRef, useMemo } from 'react'
import { cn } from '@/lib/utils'
import {
  Users,
  Plus,
  X,
  Loader2,
  AlertCircle,
  UserPlus,
  UserMinus,
  Shield,
  Edit3,
  Crown,
  User,
  ChevronDown,
  Check,
} from 'lucide-react'
import {
  useProjectMembers,
  useAppMembers,
  useAddProjectMember,
  useRemoveProjectMember,
  useUpdateProjectMemberRole,
  type ProjectMember,
  type ApplicationMember,
  type ProjectRole as ProjectMemberRole,
} from '@/hooks/use-members'
import { useAuthStore } from '@/stores/auth-store'

// ============================================================================
// Types
// ============================================================================

export interface ProjectMemberPanelProps {
  projectId: string
  applicationId: string
  isOwner?: boolean
  /** The user ID of the project creator - cannot be removed */
  creatorId?: string | null
  className?: string
}

// ============================================================================
// Helper Functions
// ============================================================================

function getInitials(name: string | null, email?: string): string {
  if (name) {
    const parts = name.trim().split(/\s+/)
    if (parts.length === 1) return parts[0].charAt(0).toUpperCase()
    return (parts[0].charAt(0) + parts[parts.length - 1].charAt(0)).toUpperCase()
  }
  if (email) return email.charAt(0).toUpperCase()
  return '?'
}

function getDisplayName(user: { display_name?: string | null; email?: string } | null): string {
  if (!user) return 'Unknown user'
  return user.display_name || user.email || 'Unknown user'
}

// ============================================================================
// Component
// ============================================================================

export function ProjectMemberPanel({
  projectId,
  applicationId,
  isOwner = false,
  creatorId = null,
  className,
}: ProjectMemberPanelProps): JSX.Element {
  const currentUserId = useAuthStore((state) => state.user?.id)
  const [showAddDialog, setShowAddDialog] = useState(false)
  const [localError, setLocalError] = useState<Error | null>(null)

  // TanStack Query hooks
  const { data: members = [], isLoading, error: membersError } = useProjectMembers(projectId)
  const { data: appMembers = [], isLoading: isLoadingApplicationMembers } = useAppMembers(showAddDialog ? applicationId : undefined)

  // Mutations
  const addMemberMutation = useAddProjectMember(projectId)
  const removeMemberMutation = useRemoveProjectMember(projectId)
  const updateRoleMutation = useUpdateProjectMemberRole(projectId)

  // Calculate available members (app members not already in project, excluding viewers)
  const memberUserIds = useMemo(() => new Set(members.map(m => m.user_id)), [members])
  const availableMembers = useMemo(
    () => appMembers.filter(m => !memberUserIds.has(m.user_id) && m.role !== 'viewer'),
    [appMembers, memberUserIds]
  )
  const isLoadingAvailable = isLoadingApplicationMembers

  // Combined error state
  const error = localError || membersError

  // Check if current user can manage members (app owner or project admin)
  const canManage = useMemo(() => {
    if (isOwner) return true
    const currentMember = members.find(m => m.user_id === currentUserId)
    return currentMember?.role === 'admin'
  }, [members, currentUserId, isOwner])

  // Clear error function
  const clearError = useCallback(() => {
    setLocalError(null)
  }, [])

  // Handlers
  const handleAddMember = useCallback(
    async (userId: string) => {
      try {
        await addMemberMutation.mutateAsync({ user_id: userId, role: 'member' })
        if (availableMembers.length <= 1) {
          setShowAddDialog(false)
        }
      } catch (err) {
        setLocalError(err instanceof Error ? err : new Error('Failed to add member'))
      }
    },
    [addMemberMutation, availableMembers.length]
  )

  const handleRemoveMember = useCallback(
    async (userId: string) => {
      try {
        await removeMemberMutation.mutateAsync(userId)
      } catch (err) {
        setLocalError(err instanceof Error ? err : new Error('Failed to remove member'))
      }
    },
    [removeMemberMutation]
  )

  const handleRoleChange = useCallback(
    async (userId: string, newRole: ProjectMemberRole) => {
      try {
        await updateRoleMutation.mutateAsync({ userId, newRole })
      } catch (err) {
        setLocalError(err instanceof Error ? err : new Error('Failed to update role'))
      }
    },
    [updateRoleMutation]
  )

  // Track which operations are pending
  const addingUserId = addMemberMutation.isPending ? addMemberMutation.variables?.user_id : null
  const removingUserId = removeMemberMutation.isPending ? removeMemberMutation.variables : null
  const changingRoleUserId = updateRoleMutation.isPending ? updateRoleMutation.variables?.userId : null

  // Loading state with skeleton
  if (isLoading && members.length === 0) {
    return (
      <div className={cn('flex flex-col h-full', className)}>
        {/* Header skeleton */}
        <div className="flex items-center justify-between px-3 py-2 border-b border-border">
          <div className="flex items-center gap-2">
            <div className="h-4 w-4 rounded bg-muted animate-pulse" />
            <div className="h-4 w-24 rounded bg-muted animate-pulse" />
          </div>
        </div>
        {/* Member list skeleton */}
        <div className="flex-1 p-2 space-y-1">
          {[1, 2, 3].map((i) => (
            <div key={i} className="flex items-center gap-3 p-2 rounded-md">
              <div className="h-8 w-8 rounded-full bg-muted animate-pulse" />
              <div className="flex-1 space-y-1.5">
                <div className="h-3.5 w-32 rounded bg-muted animate-pulse" />
                <div className="h-3 w-40 rounded bg-muted animate-pulse" />
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className={cn('flex flex-col h-full', className)}>
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border">
        <div className="flex items-center gap-2">
          <Users className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-medium text-foreground">Project Team</span>
          <span className="text-xs text-muted-foreground">({members.length})</span>
        </div>

        {canManage && (
          <button
            onClick={() => setShowAddDialog(true)}
            className={cn(
              'inline-flex items-center gap-1 px-2 py-1 rounded-md',
              'text-xs font-medium text-primary',
              'hover:bg-primary/10',
              'transition-colors'
            )}
          >
            <UserPlus className="h-3 w-3" />
            Add
          </button>
        )}
      </div>

      {/* Error banner */}
      {error && (
        <div className="flex items-center gap-2 px-3 py-2 bg-destructive/10 border-b border-destructive/20">
          <AlertCircle className="h-4 w-4 text-destructive flex-shrink-0" />
          <p className="text-xs text-destructive flex-1">{error.message}</p>
          <button onClick={clearError} className="text-xs text-destructive underline">
            Dismiss
          </button>
        </div>
      )}

      {/* Member list */}
      <div className="flex-1 overflow-y-auto p-2">
        {members.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 px-4">
            <Users className="h-10 w-10 text-muted-foreground/50 mb-2" />
            <p className="text-sm text-muted-foreground text-center">
              No team members assigned yet.
            </p>
            {canManage && (
              <button
                onClick={() => setShowAddDialog(true)}
                className={cn(
                  'mt-3 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md',
                  'bg-primary text-primary-foreground text-sm font-medium',
                  'hover:bg-primary/90',
                  'transition-colors'
                )}
              >
                <UserPlus className="h-4 w-4" />
                Add team member
              </button>
            )}
          </div>
        ) : (
          <div className="space-y-1">
            {members.map((member) => (
              <MemberItem
                key={member.id}
                member={member}
                canManage={canManage}
                isRemoving={removingUserId === member.user_id}
                isChangingRole={changingRoleUserId === member.user_id}
                onRemove={() => handleRemoveMember(member.user_id)}
                onRoleChange={(newRole) => handleRoleChange(member.user_id, newRole)}
                isCurrentUser={member.user_id === currentUserId}
                isCreator={creatorId === member.user_id}
              />
            ))}
          </div>
        )}
      </div>

      {/* Add member dialog */}
      {showAddDialog && (
        <AddMemberDialog
          availableMembers={availableMembers}
          isLoading={isLoadingAvailable}
          addingUserId={addingUserId}
          onAdd={handleAddMember}
          onClose={() => setShowAddDialog(false)}
        />
      )}
    </div>
  )
}

// ============================================================================
// Sub-components
// ============================================================================

interface MemberItemProps {
  member: ProjectMember
  canManage: boolean
  isRemoving: boolean
  isChangingRole: boolean
  onRemove: () => void
  onRoleChange: (role: ProjectMemberRole) => void
  isCurrentUser: boolean
  isCreator: boolean
}

function MemberItem({
  member,
  canManage,
  isRemoving,
  isChangingRole,
  onRemove,
  onRoleChange,
  isCurrentUser,
  isCreator,
}: MemberItemProps): JSX.Element {
  const [showRoleMenu, setShowRoleMenu] = useState(false)
  const roleMenuRef = useRef<HTMLDivElement>(null)
  const displayName = member.user_display_name || member.user_email || 'Unknown user'
  const hasName = member.user_display_name
  const showEmail = hasName && member.user_email

  // Close menu when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (roleMenuRef.current && !roleMenuRef.current.contains(event.target as Node)) {
        setShowRoleMenu(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleRoleSelect = (role: ProjectMemberRole) => {
    if (role !== member.role) {
      onRoleChange(role)
    }
    setShowRoleMenu(false)
  }

  return (
    <div
      className={cn(
        'flex items-center gap-3 p-2 rounded-md',
        'transition-colors duration-100',
        'hover:bg-muted/30',
        isRemoving && 'opacity-50'
      )}
    >
      {/* Avatar */}
      {member.user_avatar_url ? (
        <img
          src={member.user_avatar_url}
          alt={displayName}
          className="h-8 w-8 rounded-full object-cover"
        />
      ) : (
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10 text-primary text-xs font-medium">
          {getInitials(member.user_display_name || null, member.user_email)}
        </div>
      )}

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-foreground truncate">
            {displayName}
          </span>
          {isCreator && (
            <span className="text-[10px] text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-1 py-0.5 rounded">
              Creator
            </span>
          )}
          {isCurrentUser && (
            <span className="text-[10px] text-muted-foreground">(you)</span>
          )}
        </div>
        {showEmail && (
          <div className="text-xs text-muted-foreground truncate">
            {member.user_email}
          </div>
        )}
      </div>

      {/* Project Role Badge with optional dropdown */}
      <div className="relative" ref={roleMenuRef}>
        {canManage && !isCurrentUser && !isCreator ? (
          <button
            onClick={() => setShowRoleMenu(!showRoleMenu)}
            disabled={isChangingRole}
            className={cn(
              'inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium',
              'transition-all duration-150',
              member.role === 'admin'
                ? 'text-amber-700 bg-amber-500/15 hover:bg-amber-500/25 dark:text-amber-400'
                : 'text-slate-600 bg-slate-500/10 hover:bg-slate-500/20 dark:text-slate-400',
              isChangingRole && 'opacity-50 cursor-wait'
            )}
          >
            {isChangingRole ? (
              <Loader2 className="h-2.5 w-2.5 animate-spin" />
            ) : member.role === 'admin' ? (
              <Crown className="h-2.5 w-2.5" />
            ) : (
              <User className="h-2.5 w-2.5" />
            )}
            <span className="capitalize">{member.role}</span>
            <ChevronDown className="h-2 w-2 opacity-60" />
          </button>
        ) : (
          <ProjectRoleBadge role={member.role} />
        )}

        {/* Role dropdown menu */}
        {showRoleMenu && (
          <div
            className={cn(
              'absolute right-0 top-full z-50 mt-1 min-w-[100px]',
              'rounded-md border border-border bg-popover shadow-lg',
              'animate-in fade-in-0 zoom-in-95 duration-100'
            )}
          >
            <button
              onClick={() => handleRoleSelect('admin')}
              className={cn(
                'flex w-full items-center gap-2 px-2.5 py-1.5 text-xs',
                'text-foreground hover:bg-accent',
                'transition-colors first:rounded-t-md',
                member.role === 'admin' && 'bg-accent/50'
              )}
            >
              <Crown className="h-3 w-3 text-amber-600 dark:text-amber-400" />
              <span>Admin</span>
              {member.role === 'admin' && (
                <Check className="h-3 w-3 ml-auto text-primary" />
              )}
            </button>
            <button
              onClick={() => handleRoleSelect('member')}
              className={cn(
                'flex w-full items-center gap-2 px-2.5 py-1.5 text-xs',
                'text-foreground hover:bg-accent',
                'transition-colors last:rounded-b-md',
                member.role === 'member' && 'bg-accent/50'
              )}
            >
              <User className="h-3 w-3 text-slate-500" />
              <span>Member</span>
              {member.role === 'member' && (
                <Check className="h-3 w-3 ml-auto text-primary" />
              )}
            </button>
          </div>
        )}
      </div>

      {/* Remove button - always visible for managers, hidden for creator and current user */}
      {canManage && !isCurrentUser && !isCreator && (
        <button
          onClick={onRemove}
          disabled={isRemoving}
          className={cn(
            'p-1.5 rounded-md',
            'text-muted-foreground hover:text-destructive hover:bg-destructive/10',
            'transition-colors',
            isRemoving && 'cursor-not-allowed'
          )}
          title="Remove from project"
        >
          {isRemoving ? (
            <Loader2 className="h-4 w-4 animate-spin text-destructive" />
          ) : (
            <UserMinus className="h-4 w-4" />
          )}
        </button>
      )}
    </div>
  )
}

// ============================================================================
// Project Role Badge
// ============================================================================

interface ProjectRoleBadgeProps {
  role: ProjectMemberRole
}

function ProjectRoleBadge({ role }: ProjectRoleBadgeProps): JSX.Element {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium',
        role === 'admin'
          ? 'text-amber-700 bg-amber-500/15 dark:text-amber-400'
          : 'text-slate-600 bg-slate-500/10 dark:text-slate-400'
      )}
    >
      {role === 'admin' ? (
        <Crown className="h-2.5 w-2.5" />
      ) : (
        <User className="h-2.5 w-2.5" />
      )}
      <span className="capitalize">{role}</span>
    </span>
  )
}

interface AddMemberDialogProps {
  availableMembers: ApplicationMember[]
  isLoading: boolean
  addingUserId: string | null
  onAdd: (userId: string) => void
  onClose: () => void
}

function AddMemberDialog({
  availableMembers,
  isLoading,
  addingUserId,
  onAdd,
  onClose,
}: AddMemberDialogProps): JSX.Element {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div
        className={cn(
          'w-full max-w-md mx-4 rounded-lg border border-border bg-card shadow-xl',
          'animate-in fade-in-0 zoom-in-95 duration-150'
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <h3 className="text-sm font-semibold text-foreground">Add Team Member</h3>
          <button
            onClick={onClose}
            className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Content */}
        <div className="p-4 max-h-80 overflow-y-auto">
          {isLoading ? (
            <div className="space-y-2">
              <div className="h-3 w-56 rounded bg-muted animate-pulse mb-3" />
              {[1, 2, 3].map((i) => (
                <div
                  key={i}
                  className="flex items-center gap-3 p-2 rounded-md border border-border"
                >
                  <div className="h-8 w-8 rounded-full bg-muted animate-pulse" />
                  <div className="flex-1 space-y-1.5">
                    <div className="h-3.5 w-28 rounded bg-muted animate-pulse" />
                    <div className="h-3 w-36 rounded bg-muted animate-pulse" />
                  </div>
                  <div className="h-7 w-14 rounded-md bg-muted animate-pulse" />
                </div>
              ))}
            </div>
          ) : availableMembers.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 px-4">
              <Users className="h-10 w-10 text-muted-foreground/50 mb-2" />
              <p className="text-sm text-muted-foreground text-center">
                All editors and owners are already assigned to this project.
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              <p className="text-xs text-muted-foreground mb-3">
                Select application members to add to this project team.
                Only editors and owners can be assigned to projects.
              </p>
              {availableMembers.map((member) => (
                <AvailableMemberItem
                  key={member.id}
                  member={member}
                  isAdding={addingUserId === member.user_id}
                  onAdd={() => onAdd(member.user_id)}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

interface AvailableMemberItemProps {
  member: ApplicationMember
  isAdding: boolean
  onAdd: () => void
}

function AvailableMemberItem({ member, isAdding, onAdd }: AvailableMemberItemProps): JSX.Element {
  const displayName = member.user_display_name || member.user_email || 'Unknown user'
  const hasName = member.user_display_name
  const showEmail = hasName && member.user_email

  return (
    <div
      className={cn(
        'flex items-center gap-3 p-2 rounded-md border border-border',
        'transition-colors duration-100',
        'hover:bg-muted/30'
      )}
    >
      {/* Avatar */}
      {member.user_avatar_url ? (
        <img
          src={member.user_avatar_url}
          alt={displayName}
          className="h-8 w-8 rounded-full object-cover"
        />
      ) : (
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10 text-primary text-xs font-medium">
          {getInitials(member.user_display_name || null, member.user_email)}
        </div>
      )}

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-foreground truncate">
            {displayName}
          </span>
          <RoleBadge role={member.role} />
        </div>
        {showEmail && (
          <div className="text-xs text-muted-foreground truncate">
            {member.user_email}
          </div>
        )}
      </div>

      {/* Add button */}
      <button
        onClick={onAdd}
        disabled={isAdding}
        className={cn(
          'inline-flex items-center gap-1 px-2 py-1 rounded-md',
          'bg-primary text-primary-foreground text-xs font-medium',
          'hover:bg-primary/90',
          'disabled:opacity-50 disabled:cursor-not-allowed',
          'transition-colors'
        )}
      >
        {isAdding ? (
          <Loader2 className="h-3 w-3 animate-spin" />
        ) : (
          <Plus className="h-3 w-3" />
        )}
        Add
      </button>
    </div>
  )
}

interface RoleBadgeProps {
  role: 'owner' | 'editor' | 'viewer'
}

function RoleBadge({ role }: RoleBadgeProps): JSX.Element {
  const config = {
    owner: { icon: Shield, color: 'text-amber-600 bg-amber-500/10' },
    editor: { icon: Edit3, color: 'text-blue-600 bg-blue-500/10' },
    viewer: { icon: Users, color: 'text-gray-600 bg-gray-500/10' },
  }[role]

  const Icon = config.icon

  return (
    <span
      className={cn(
        'inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium capitalize',
        config.color
      )}
    >
      <Icon className="h-2.5 w-2.5" />
      {role}
    </span>
  )
}

// ============================================================================
// Exports
// ============================================================================

export default ProjectMemberPanel
