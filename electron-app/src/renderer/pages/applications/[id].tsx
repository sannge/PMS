/**
 * Application Detail Page
 *
 * Space-efficient detail view with compact inline header.
 * Features:
 * - Ultra-compact header with inline actions
 * - Breadcrumb navigation
 * - Projects grid with search
 * - Minimal footprint design
 */

import { useState, useCallback, useEffect, useRef, useMemo } from 'react'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth-store'
import { useWebSocket, MessageType, type MemberAddedEventData, type MemberRemovedEventData, type RoleUpdatedEventData } from '@/hooks/use-websocket'
import { WebSocketClient } from '@/lib/websocket'
import {
  useApplication,
  useUpdateApplication,
  useDeleteApplication,
  useProjects,
  useCreateProject,
  useUpdateProject,
  useDeleteProject,
  useAppMembers,
  useUpdateAppMemberRole,
  useRemoveAppMember,
  type Application,
  type ApplicationUpdate,
  type Project,
  type ProjectCreate,
  type ProjectUpdate,
} from '@/hooks/use-queries'
import type { ApplicationMember, ApplicationRole } from '@/hooks/use-members'
import { MessageType, type WebSocketEventData } from '@/hooks/use-websocket'

// Define the event data type for project status changed
interface ProjectStatusChangedEventData extends WebSocketEventData {
  project_id?: string
  application_id?: string
  project?: Project
}
import { ApplicationForm } from '@/components/applications/application-form'
import { ProjectCard } from '@/components/projects/project-card'
import { ProjectForm } from '@/components/projects/project-form'
import { ProjectKanbanBoard } from '@/components/projects/project-kanban-board'
import { MemberAvatarGroup, MemberManagementModal } from '@/components/members'
import { InvitationModal } from '@/components/invitations/invitation-modal'
import { SkeletonProjectGrid, SkeletonProjectKanbanBoard } from '@/components/ui/skeleton'
import {
  FolderKanban,
  ChevronRight,
  MoreHorizontal,
  Edit2,
  Trash2,
  Plus,
  Loader2,
  AlertCircle,
  LayoutDashboard,
  Search,
  X,
  Info,
  ArrowLeft,
  UserPlus,
  LayoutGrid,
  Columns,
} from 'lucide-react'

// ============================================================================
// Types
// ============================================================================

export interface ApplicationDetailPageProps {
  /**
   * Application ID to display
   */
  applicationId: string
  /**
   * Callback to navigate back to applications list
   */
  onBack?: () => void
  /**
   * Callback when application is deleted
   */
  onDeleted?: () => void
  /**
   * Callback when a project is selected
   */
  onSelectProject?: (projectId: string) => void
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Format a date string to a readable format
 */
function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

/**
 * Compact relative date format
 */
function formatRelativeDate(dateString: string): string {
  // Ensure UTC parsing - append 'Z' if no timezone indicator
  let dateStr = dateString
  if (!dateStr.endsWith('Z') && !dateStr.includes('+') && !dateStr.includes('-', 10)) {
    dateStr = dateStr + 'Z'
  }

  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()

  // Handle future dates or very recent (within 1 minute)
  if (diffMs < 0 || diffMs < 60000) return 'Just now'

  const diffMins = Math.floor(diffMs / (1000 * 60))
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60))
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays === 1) return 'Yesterday'
  if (diffDays < 7) return `${diffDays}d ago`
  if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`
  return formatDate(dateString)
}

// ============================================================================
// Actions Dropdown Component
// ============================================================================

interface ActionsDropdownProps {
  onEdit: () => void
  onDelete: () => void
}

function ActionsDropdown({ onEdit, onDelete }: ActionsDropdownProps): JSX.Element {
  const [isOpen, setIsOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
    }
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [isOpen])

  return (
    <div ref={dropdownRef} className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          'flex h-7 w-7 items-center justify-center rounded-md transition-colors',
          'text-muted-foreground hover:text-foreground hover:bg-muted',
          isOpen && 'bg-muted text-foreground'
        )}
      >
        <MoreHorizontal className="h-4 w-4" />
      </button>

      {isOpen && (
        <div className={cn(
          'absolute right-0 top-full mt-1 z-50 min-w-[140px]',
          'rounded-lg border border-border bg-card shadow-lg',
          'animate-fade-in py-1'
        )}>
          <button
            onClick={() => { onEdit(); setIsOpen(false) }}
            className={cn(
              'flex w-full items-center gap-2 px-3 py-1.5 text-sm',
              'text-foreground hover:bg-muted transition-colors'
            )}
          >
            <Edit2 className="h-3.5 w-3.5" />
            Edit
          </button>
          <button
            onClick={() => { onDelete(); setIsOpen(false) }}
            className={cn(
              'flex w-full items-center gap-2 px-3 py-1.5 text-sm',
              'text-destructive hover:bg-destructive/10 transition-colors'
            )}
          >
            <Trash2 className="h-3.5 w-3.5" />
            Delete
          </button>
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Info Tooltip Component
// ============================================================================

interface InfoTooltipProps {
  application: Application
}

function InfoTooltip({ application }: InfoTooltipProps): JSX.Element {
  const [isOpen, setIsOpen] = useState(false)
  const tooltipRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (tooltipRef.current && !tooltipRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
    }
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [isOpen])

  return (
    <div ref={tooltipRef} className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          'flex h-7 w-7 items-center justify-center rounded-md transition-colors',
          'text-muted-foreground hover:text-foreground hover:bg-muted',
          isOpen && 'bg-muted text-foreground'
        )}
        title="Details"
      >
        <Info className="h-4 w-4" />
      </button>

      {isOpen && (
        <div className={cn(
          'absolute right-0 top-full mt-1 z-50 w-64',
          'rounded-lg border border-border bg-card shadow-lg p-3',
          'animate-fade-in'
        )}>
          <div className="space-y-2 text-xs">
            {application.description && (
              <div>
                <span className="text-muted-foreground">Description</span>
                <p className="text-foreground mt-0.5">{application.description}</p>
              </div>
            )}
            <div className="flex justify-between">
              <span className="text-muted-foreground">Created</span>
              <span className="text-foreground">{formatDate(application.created_at)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Updated</span>
              <span className="text-foreground">{formatRelativeDate(application.updated_at)}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Delete Confirmation Dialog Component
// ============================================================================

interface DeleteDialogProps {
  application: Application
  isDeleting: boolean
  onConfirm: () => void
  onCancel: () => void
}

function DeleteConfirmDialog({
  application,
  isDeleting,
  onConfirm,
  onCancel,
}: DeleteDialogProps): JSX.Element {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-lg border border-border bg-card p-6 shadow-lg">
        <div className="flex items-start gap-4">
          <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-destructive/10 text-destructive">
            <AlertCircle className="h-5 w-5" />
          </div>
          <div className="flex-1">
            <h3 className="text-lg font-semibold text-foreground">
              Delete Application
            </h3>
            <p className="mt-2 text-sm text-muted-foreground">
              Are you sure you want to delete <strong>{application.name}</strong>?
              This will also delete all projects and tasks within this application.
              This action cannot be undone.
            </p>
          </div>
        </div>
        <div className="mt-6 flex items-center justify-end gap-3">
          <button
            onClick={onCancel}
            disabled={isDeleting}
            className={cn(
              'rounded-md border border-input bg-background px-4 py-2 text-sm font-medium text-foreground',
              'hover:bg-accent hover:text-accent-foreground',
              'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
              'disabled:cursor-not-allowed disabled:opacity-50',
              'transition-colors duration-200'
            )}
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={isDeleting}
            className={cn(
              'rounded-md bg-destructive px-4 py-2 text-sm font-medium text-destructive-foreground',
              'hover:bg-destructive/90 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
              'disabled:cursor-not-allowed disabled:opacity-50',
              'transition-colors duration-200'
            )}
          >
            {isDeleting ? (
              <span className="flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" />
                Deleting...
              </span>
            ) : (
              'Delete'
            )}
          </button>
        </div>
      </div>
    </div>
  )
}

// ============================================================================
// Modal Component
// ============================================================================

interface ModalProps {
  children: React.ReactNode
  onClose: () => void
}

function Modal({ children, onClose }: ModalProps): JSX.Element {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
      <div className="w-full max-w-lg mx-4">{children}</div>
    </div>
  )
}

// ============================================================================
// Component
// ============================================================================

export function ApplicationDetailPage({
  applicationId,
  onBack,
  onDeleted,
  onSelectProject,
}: ApplicationDetailPageProps): JSX.Element {
  // Get current user ID
  const currentUserId = useAuthStore((state) => state.user?.id)

  // TanStack Query hooks for application
  const {
    data: application,
    isLoading,
    error: queryError,
  } = useApplication(applicationId)

  // Track editing application ID for update mutation
  const [editingAppId, setEditingAppId] = useState<string | null>(null)
  const updateMutation = useUpdateApplication(editingAppId || applicationId)
  const deleteMutation = useDeleteApplication(applicationId)

  // TanStack Query hooks for projects
  const {
    data: projects = [],
    isLoading: isLoadingProjects,
    error: projectsQueryError,
  } = useProjects(applicationId)

  const createProjectMutation = useCreateProject(applicationId)
  const [editingProjectId, setEditingProjectId] = useState<string | null>(null)
  const updateProjectMutation = useUpdateProject(editingProjectId || '', applicationId)
  const [deletingProjectId, setDeletingProjectId] = useState<string | null>(null)
  const deleteProjectMutation = useDeleteProject(deletingProjectId || '', applicationId)

  // TanStack Query hooks for members
  const {
    data: members = [],
    isLoading: isLoadingMembers,
  } = useAppMembers(applicationId)

  const updateMemberRoleMutation = useUpdateAppMemberRole(applicationId)
  const removeMemberMutation = useRemoveAppMember(applicationId)

  // Derive loading states from mutations
  const isUpdating = updateMutation.isPending
  const isDeleting = deleteMutation.isPending
  const isCreatingProject = createProjectMutation.isPending
  const isUpdatingProject = updateProjectMutation.isPending
  const isDeletingProject = deleteProjectMutation.isPending
  const isUpdatingMemberRole = updateMemberRoleMutation.isPending
  const isRemovingMember = removeMemberMutation.isPending

  // Error states
  const error = queryError?.message || updateMutation.error?.message || deleteMutation.error?.message
  const projectsError = projectsQueryError?.message || createProjectMutation.error?.message || updateProjectMutation.error?.message || deleteProjectMutation.error?.message

  // Permission checks based on user role
  const userRole = application?.user_role || 'viewer'
  const isOwner = userRole === 'owner'
  const isEditor = userRole === 'editor'
  // Owners and editors can edit projects
  const canEditProjects = isOwner || isEditor
  // Only owners can delete projects from application view
  // (Project admins can delete from project detail page)
  const canDeleteProjects = isOwner

  // Local state
  const [isEditing, setIsEditing] = useState(false)
  const [isInviteModalOpen, setIsInviteModalOpen] = useState(false)
  const [isMemberModalOpen, setIsMemberModalOpen] = useState(false)
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const [projectModalMode, setProjectModalMode] = useState<'create' | 'edit' | null>(null)
  const [editingProject, setEditingProject] = useState<Project | null>(null)
  const [deletingProject, setDeletingProject] = useState<Project | null>(null)
  const [projectSearchQuery, setProjectSearchQuery] = useState('')
  const [projectViewMode, setProjectViewMode] = useState<'kanban' | 'grid'>('kanban')
  // Member management state
  const [editingMember, setEditingMember] = useState<ApplicationMember | null>(null)
  const [removingMember, setRemovingMember] = useState<ApplicationMember | null>(null)
  const [mutationError, setMutationError] = useState<string | null>(null)

  // Filter projects by search query (client-side)
  const filteredProjects = useMemo(() => {
    if (!projectSearchQuery.trim()) return projects
    const query = projectSearchQuery.toLowerCase()
    return projects.filter(
      (p) =>
        p.name.toLowerCase().includes(query) ||
        p.key.toLowerCase().includes(query) ||
        p.description?.toLowerCase().includes(query)
    )
  }, [projects, projectSearchQuery])

  // Show loading skeleton only on first load (no cached data)
  const showLoading = isLoading && !application

  // Join application room for real-time member updates
  const { joinRoom, leaveRoom, subscribe, status: wsStatus } = useWebSocket()

  // Store current user ID in ref for WebSocket handlers
  const currentUserIdRef = useRef(currentUserId)

  // Keep ref up to date
  useEffect(() => {
    currentUserIdRef.current = currentUserId
  })

  // Join application room for real-time updates
  // Cache invalidation is handled globally by useWebSocketCacheInvalidation in App.tsx
  useEffect(() => {
    if (!applicationId || !wsStatus.isConnected) {
      return
    }

    const roomId = WebSocketClient.getApplicationRoom(applicationId)
    joinRoom(roomId)

    return () => {
      leaveRoom(roomId)
    }
  }, [applicationId, wsStatus.isConnected, joinRoom, leaveRoom])

  // Handle invite modal
  const handleOpenInviteModal = useCallback(() => {
    setIsInviteModalOpen(true)
  }, [])

  const handleCloseInviteModal = useCallback(() => {
    setIsInviteModalOpen(false)
  }, [])

  const handleInvitationSent = useCallback(() => {
    // Members list will be invalidated by WebSocket cache hook when member is added
  }, [])

  // ============================================================================
  // Member Handlers
  // ============================================================================

  // Handle edit member role - convert ApplicationMember to expected format
  const handleEditMemberRole = useCallback(
    (member: ApplicationMember) => {
      setEditingMember(member)
    },
    []
  )

  // Handle remove member click
  const handleRemoveMemberClick = useCallback(
    (member: ApplicationMember) => {
      setRemovingMember(member)
    },
    []
  )

  // Handle confirm role change
  const handleConfirmRoleChange = useCallback(
    async (newRole: ApplicationRole) => {
      if (!editingMember) return

      try {
        await updateMemberRoleMutation.mutateAsync({ userId: editingMember.user_id, newRole })
        setEditingMember(null)
      } catch (err) {
        setMutationError(err instanceof Error ? err.message : 'Failed to update role')
      }
    },
    [editingMember, updateMemberRoleMutation]
  )

  // Handle cancel role change
  const handleCancelRoleChange = useCallback(() => {
    setEditingMember(null)
  }, [])

  // Handle confirm remove member
  const handleConfirmRemoveMember = useCallback(async () => {
    if (!removingMember) return

    try {
      await removeMemberMutation.mutateAsync(removingMember.user_id)
      setRemovingMember(null)
    } catch (err) {
      setMutationError(err instanceof Error ? err.message : 'Failed to remove member')
    }
  }, [removingMember, removeMemberMutation])

  // Handle cancel remove member
  const handleCancelRemoveMember = useCallback(() => {
    setRemovingMember(null)
  }, [])

  // Handle edit
  const handleEdit = useCallback(() => {
    setMutationError(null)
    setEditingAppId(applicationId)
    setIsEditing(true)
  }, [applicationId])

  // Handle close edit
  const handleCloseEdit = useCallback(() => {
    setIsEditing(false)
    setEditingAppId(null)
  }, [])

  // Handle update
  const handleUpdate = useCallback(
    async (data: ApplicationUpdate) => {
      try {
        await updateMutation.mutateAsync(data)
        setIsEditing(false)
        setEditingAppId(null)
      } catch (err) {
        setMutationError(err instanceof Error ? err.message : 'Failed to update application')
      }
    },
    [updateMutation]
  )

  // Handle delete click
  const handleDeleteClick = useCallback(() => {
    setShowDeleteDialog(true)
  }, [])

  // Handle confirm delete
  const handleConfirmDelete = useCallback(async () => {
    try {
      await deleteMutation.mutateAsync()
      setShowDeleteDialog(false)
      onDeleted?.()
      onBack?.()
    } catch (err) {
      setMutationError(err instanceof Error ? err.message : 'Failed to delete application')
    }
  }, [deleteMutation, onDeleted, onBack])

  // Handle cancel delete
  const handleCancelDelete = useCallback(() => {
    setShowDeleteDialog(false)
  }, [])

  // ============================================================================
  // Project Handlers
  // ============================================================================

  // Handle create project
  const handleCreateProject = useCallback(() => {
    setMutationError(null)
    setEditingProject(null)
    setProjectModalMode('create')
  }, [])

  // Handle edit project
  const handleEditProject = useCallback(
    (project: Project) => {
      setMutationError(null)
      setEditingProject(project)
      setEditingProjectId(project.id)
      setProjectModalMode('edit')
    },
    []
  )

  // Handle delete project click
  const handleDeleteProjectClick = useCallback((project: Project) => {
    setDeletingProject(project)
    setDeletingProjectId(project.id)
  }, [])

  // Handle confirm delete project
  const handleConfirmDeleteProject = useCallback(async () => {
    if (!deletingProject) return

    try {
      await deleteProjectMutation.mutateAsync()
      setDeletingProject(null)
      setDeletingProjectId(null)
    } catch (err) {
      setMutationError(err instanceof Error ? err.message : 'Failed to delete project')
    }
  }, [deletingProject, deleteProjectMutation])

  // Handle cancel delete project
  const handleCancelDeleteProject = useCallback(() => {
    setDeletingProject(null)
    setDeletingProjectId(null)
  }, [])

  // Handle close project modal
  const handleCloseProjectModal = useCallback(() => {
    setProjectModalMode(null)
    setEditingProject(null)
    setEditingProjectId(null)
  }, [])

  // Handle project form submit
  const handleProjectFormSubmit = useCallback(
    async (data: ProjectCreate | ProjectUpdate) => {
      try {
        if (projectModalMode === 'create') {
          await createProjectMutation.mutateAsync(data as ProjectCreate)
          handleCloseProjectModal()
        } else if (projectModalMode === 'edit' && editingProject) {
          await updateProjectMutation.mutateAsync(data as ProjectUpdate)
          handleCloseProjectModal()
        }
      } catch (err) {
        setMutationError(err instanceof Error ? err.message : 'An error occurred')
      }
    },
    [projectModalMode, editingProject, createProjectMutation, updateProjectMutation, handleCloseProjectModal]
  )

  // Handle project click
  const handleProjectClick = useCallback(
    (project: Project) => {
      onSelectProject?.(project.id)
    },
    [onSelectProject]
  )

  // Handle project search (client-side filtering)
  const handleProjectSearch = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setProjectSearchQuery(e.target.value)
    },
    []
  )

  // Clear error handler
  const clearError = useCallback(() => {
    setMutationError(null)
  }, [])

  // Loading state - show skeleton only on first load
  if (showLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="mt-4 text-muted-foreground">Loading application...</p>
      </div>
    )
  }

  // Error state
  if (queryError && !application) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <div className="flex h-16 w-16 items-center justify-center rounded-full bg-destructive/10">
          <AlertCircle className="h-8 w-8 text-destructive" />
        </div>
        <h3 className="mt-4 text-lg font-semibold text-foreground">
          Failed to load application
        </h3>
        <p className="mt-2 text-muted-foreground">{queryError.message}</p>
        {onBack && (
          <button
            onClick={onBack}
            className={cn(
              'mt-4 inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground',
              'hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2'
            )}
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Applications
          </button>
        )}
      </div>
    )
  }

  // Not found state
  if (!application && !isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <div className="flex h-16 w-16 items-center justify-center rounded-full bg-muted">
          <FolderKanban className="h-8 w-8 text-muted-foreground" />
        </div>
        <h3 className="mt-4 text-lg font-semibold text-foreground">
          Application not found
        </h3>
        <p className="mt-2 text-muted-foreground">
          The application you're looking for doesn't exist or has been deleted.
        </p>
        {onBack && (
          <button
            onClick={onBack}
            className={cn(
              'mt-4 inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground',
              'hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2'
            )}
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Applications
          </button>
        )}
      </div>
    )
  }

  // At this point, application is guaranteed to be non-null due to early returns above
  if (!application) return null

  return (
    <div className="space-y-4">
      {/* Compact Header Bar */}
      <div className="flex items-center justify-between gap-4 pb-3 border-b border-border">
        {/* Left: Breadcrumb + Title */}
        <div className="flex items-center gap-2 min-w-0">
          {onBack && (
            <>
              <button
                onClick={onBack}
                className={cn(
                  'text-xs font-medium text-muted-foreground hover:text-foreground',
                  'transition-colors flex-shrink-0'
                )}
              >
                Applications
              </button>
              <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/50 flex-shrink-0" />
            </>
          )}
          <div className="flex items-center gap-2 min-w-0">
            <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
              <FolderKanban className="h-4 w-4" />
            </div>
            <h1 className="text-base font-semibold text-foreground truncate">
              {application.name}
            </h1>
            <span className="text-xs text-muted-foreground flex-shrink-0 bg-muted px-1.5 py-0.5 rounded">
              {application.projects_count} {application.projects_count === 1 ? 'project' : 'projects'}
            </span>
          </div>
        </div>

        {/* Right: Actions */}
        <div className="flex items-center gap-1 flex-shrink-0">
          <InfoTooltip application={application} />
          {isOwner && (
            <ActionsDropdown onEdit={handleEdit} onDelete={handleDeleteClick} />
          )}
        </div>
      </div>

      {/* Team Section - Compact display with avatar group */}
      <div className="flex items-center justify-between gap-3 py-2">
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium text-muted-foreground">Team</span>
          <MemberAvatarGroup
            members={members}
            totalCount={members.length}
            maxDisplay={5}
            size="sm"
            onClick={() => setIsMemberModalOpen(true)}
            isLoading={isLoadingMembers}
          />
        </div>
        {canEditProjects && (
          <button
            onClick={handleOpenInviteModal}
            className={cn(
              'flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium',
              'text-primary hover:bg-primary/10 transition-colors',
              'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2'
            )}
          >
            <UserPlus className="h-3.5 w-3.5" />
            Invite
          </button>
        )}
      </div>

      {/* Projects Section - Compact Header */}
      <div className="space-y-3 flex-1 flex flex-col min-h-0">
        <div className="flex items-center justify-between gap-3">
          {/* Search inline with title */}
          <div className="flex items-center gap-3 flex-1">
            <h2 className="text-sm font-medium text-foreground flex-shrink-0">Projects</h2>
            {(projects.length > 0 || projectSearchQuery) && (
              <div className="relative flex-1 max-w-xs">
                <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                <input
                  type="text"
                  value={projectSearchQuery}
                  onChange={handleProjectSearch}
                  placeholder="Search..."
                  className={cn(
                    'w-full rounded-md border border-input bg-background py-1.5 pl-8 pr-3 text-xs text-foreground placeholder:text-muted-foreground',
                    'focus:outline-none focus:ring-1 focus:ring-ring'
                  )}
                />
                {projectSearchQuery && (
                  <button
                    onClick={() => setProjectSearchQuery('')}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    <X className="h-3 w-3" />
                  </button>
                )}
              </div>
            )}
          </div>
          {/* View Toggle + New Project */}
          <div className="flex items-center gap-2">
            {/* View Toggle */}
            <div className="flex items-center rounded-md border border-input bg-background p-0.5">
              <button
                onClick={() => setProjectViewMode('kanban')}
                className={cn(
                  'flex h-7 w-7 items-center justify-center rounded transition-colors',
                  projectViewMode === 'kanban'
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:text-foreground'
                )}
                title="Kanban view"
              >
                <Columns className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => setProjectViewMode('grid')}
                className={cn(
                  'flex h-7 w-7 items-center justify-center rounded transition-colors',
                  projectViewMode === 'grid'
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:text-foreground'
                )}
                title="Grid view"
              >
                <LayoutGrid className="h-3.5 w-3.5" />
              </button>
            </div>
            {canEditProjects && (
              <button
                onClick={handleCreateProject}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground',
                  'hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
                  'transition-colors flex-shrink-0'
                )}
              >
                <Plus className="h-3.5 w-3.5" />
                New Project
              </button>
            )}
          </div>
        </div>

        {/* Projects Error Display */}
        {(projectsError || mutationError) && !projectModalMode && (
          <div className="flex items-center gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
            <AlertCircle className="h-4 w-4 flex-shrink-0" />
            <span>{projectsError || mutationError}</span>
            <button
              onClick={clearError}
              className="ml-auto text-destructive hover:text-destructive/80"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        )}

        {/* Loading Projects State - Skeleton */}
        {isLoadingProjects && filteredProjects.length === 0 && (
          projectViewMode === 'kanban' ? (
            <div className="flex-1 overflow-x-auto">
              <SkeletonProjectKanbanBoard />
            </div>
          ) : (
            <SkeletonProjectGrid count={6} />
          )
        )}

        {/* Empty Projects State */}
        {!isLoadingProjects && filteredProjects.length === 0 && (
          <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border py-8">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted">
              <LayoutDashboard className="h-5 w-5 text-muted-foreground" />
            </div>
            <h3 className="mt-3 text-sm font-medium text-foreground">
              {projectSearchQuery ? 'No projects found' : 'No projects yet'}
            </h3>
            <p className="mt-1 text-xs text-center text-muted-foreground max-w-[200px]">
              {projectSearchQuery
                ? `No matches for "${projectSearchQuery}"`
                : 'Get started by creating your first project.'}
            </p>
            {!projectSearchQuery && canEditProjects && (
              <button
                onClick={handleCreateProject}
                className={cn(
                  'mt-3 inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground',
                  'hover:bg-primary/90 transition-colors'
                )}
              >
                <Plus className="h-3.5 w-3.5" />
                Create Project
              </button>
            )}
          </div>
        )}

        {/* Projects View */}
        {!isLoadingProjects && filteredProjects.length > 0 && (
          projectViewMode === 'kanban' ? (
            <div className="flex-1 overflow-x-auto">
              <ProjectKanbanBoard
                projects={filteredProjects}
                isLoading={isLoadingProjects}
                onProjectClick={onSelectProject ? handleProjectClick : undefined}
                onEdit={canEditProjects ? handleEditProject : undefined}
                onDelete={canDeleteProjects ? handleDeleteProjectClick : undefined}
                onAddProject={canEditProjects ? handleCreateProject : undefined}
                disabled={isDeletingProject}
                canEditProjects={canEditProjects}
                canDeleteProjects={canDeleteProjects}
              />
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {filteredProjects.map((project) => (
                <ProjectCard
                  key={project.id}
                  project={project}
                  onClick={onSelectProject ? handleProjectClick : undefined}
                  disabled={isDeletingProject}
                />
              ))}
            </div>
          )
        )}
      </div>

      {/* Edit Modal */}
      {isEditing && (
        <Modal onClose={handleCloseEdit}>
          <ApplicationForm
            application={application}
            isSubmitting={isUpdating}
            error={error?.message}
            onSubmit={handleUpdate}
            onCancel={handleCloseEdit}
          />
        </Modal>
      )}

      {/* Delete Confirmation Dialog */}
      {showDeleteDialog && (
        <DeleteConfirmDialog
          application={application}
          isDeleting={isDeleting}
          onConfirm={handleConfirmDelete}
          onCancel={handleCancelDelete}
        />
      )}

      {/* Create/Edit Project Modal */}
      {projectModalMode && (
        <Modal onClose={handleCloseProjectModal}>
          <ProjectForm
            project={editingProject}
            isSubmitting={projectModalMode === 'create' ? isCreatingProject : isUpdatingProject}
            error={projectsError?.message}
            onSubmit={handleProjectFormSubmit}
            onCancel={handleCloseProjectModal}
          />
        </Modal>
      )}

      {/* Delete Project Confirmation Dialog */}
      {deletingProject && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-lg border border-border bg-card p-6 shadow-lg">
            <div className="flex items-start gap-4">
              <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-destructive/10 text-destructive">
                <AlertCircle className="h-5 w-5" />
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-foreground">Delete Project</h3>
                <p className="mt-2 text-sm text-muted-foreground">
                  Are you sure you want to delete <strong>{deletingProject.name}</strong> ({deletingProject.key})?
                  This will also delete all tasks within this project.
                  This action cannot be undone.
                </p>
              </div>
            </div>
            <div className="mt-6 flex items-center justify-end gap-3">
              <button
                onClick={handleCancelDeleteProject}
                disabled={isDeletingProject}
                className={cn(
                  'rounded-md border border-input bg-background px-4 py-2 text-sm font-medium text-foreground',
                  'hover:bg-accent hover:text-accent-foreground',
                  'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
                  'disabled:cursor-not-allowed disabled:opacity-50',
                  'transition-colors duration-200'
                )}
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmDeleteProject}
                disabled={isDeletingProject}
                className={cn(
                  'rounded-md bg-destructive px-4 py-2 text-sm font-medium text-destructive-foreground',
                  'hover:bg-destructive/90 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
                  'disabled:cursor-not-allowed disabled:opacity-50',
                  'transition-colors duration-200'
                )}
              >
                {isDeletingProject ? (
                  <span className="flex items-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Deleting...
                  </span>
                ) : (
                  'Delete'
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Member Management Modal */}
      <MemberManagementModal
        isOpen={isMemberModalOpen}
        onClose={() => setIsMemberModalOpen(false)}
        members={members}
        isLoading={isLoadingMembers}
        totalCount={members.length}
        currentUserId={currentUserId}
        currentUserRole={userRole ?? undefined}
        originalOwnerId={application?.owner_id ?? undefined}
        isUpdatingRole={isUpdatingMemberRole}
        isRemovingMember={isRemovingMember}
        onEditRole={(m) => handleEditMemberRole(members.find((am) => am.user_id === m.user_id)!)}
        onRemoveMember={(m) => handleRemoveMemberClick(members.find((am) => am.user_id === m.user_id)!)}
        onInvite={() => {
          setIsMemberModalOpen(false)
          handleOpenInviteModal()
        }}
        applicationName={application?.name}
      />

      {/* Edit Member Role Dialog */}
      {editingMember && (() => {
        // Determine which roles can be selected based on current user's role and member being edited
        const isUserOwner = userRole === 'owner'
        const isUserEditor = userRole === 'editor'
        const memberIsViewer = editingMember.role === 'viewer'

        // Editors can only change viewers to editors (promotion only)
        // Owners can change to any role
        let availableRoles: Array<'owner' | 'editor' | 'viewer'> = []
        if (isUserOwner) {
          availableRoles = ['owner', 'editor', 'viewer']
        } else if (isUserEditor && memberIsViewer) {
          // Editors can only promote viewers to editor
          availableRoles = ['editor', 'viewer']
        }

        return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
          <div className="w-full max-w-sm rounded-lg border border-border bg-card p-6 shadow-lg">
            <h3 className="text-lg font-semibold text-foreground">Change Role</h3>
            <p className="mt-2 text-sm text-muted-foreground">
              Select a new role for <strong>{editingMember.user_display_name || editingMember.user_email}</strong>
            </p>
            <div className="mt-4 space-y-2">
              {availableRoles.map((role) => (
                <button
                  key={role}
                  onClick={() => handleConfirmRoleChange(role)}
                  disabled={isUpdatingMemberRole}
                  className={cn(
                    'flex w-full items-center justify-between rounded-md border px-4 py-3 text-sm transition-colors',
                    'disabled:cursor-not-allowed disabled:opacity-50',
                    editingMember.role === role
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-input hover:bg-accent hover:text-accent-foreground'
                  )}
                >
                  <span className="font-medium capitalize">{role}</span>
                  {editingMember.role === role && (
                    <span className="text-xs text-muted-foreground">Current</span>
                  )}
                </button>
              ))}
            </div>
            {isUpdatingMemberRole && (
              <div className="mt-3 flex items-center justify-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Updating role...
              </div>
            )}
            <div className="mt-6 flex items-center justify-end">
              <button
                onClick={handleCancelRoleChange}
                disabled={isUpdatingMemberRole}
                className={cn(
                  'rounded-md border border-input bg-background px-4 py-2 text-sm font-medium text-foreground',
                  'hover:bg-accent hover:text-accent-foreground',
                  'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
                  'disabled:cursor-not-allowed disabled:opacity-50',
                  'transition-colors duration-200'
                )}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
        )
      })()}

      {/* Remove Member Confirmation Dialog */}
      {removingMember && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-lg border border-border bg-card p-6 shadow-lg">
            <div className="flex items-start gap-4">
              <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-destructive/10 text-destructive">
                <AlertCircle className="h-5 w-5" />
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-foreground">Remove Member</h3>
                <p className="mt-2 text-sm text-muted-foreground">
                  Are you sure you want to remove <strong>{removingMember.user_display_name || removingMember.user_email}</strong> from this application?
                  They will lose access to all projects and tasks.
                </p>
              </div>
            </div>
            <div className="mt-6 flex items-center justify-end gap-3">
              <button
                onClick={handleCancelRemoveMember}
                disabled={isRemovingMember}
                className={cn(
                  'rounded-md border border-input bg-background px-4 py-2 text-sm font-medium text-foreground',
                  'hover:bg-accent hover:text-accent-foreground',
                  'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
                  'disabled:cursor-not-allowed disabled:opacity-50',
                  'transition-colors duration-200'
                )}
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmRemoveMember}
                disabled={isRemovingMember}
                className={cn(
                  'rounded-md bg-destructive px-4 py-2 text-sm font-medium text-destructive-foreground',
                  'hover:bg-destructive/90 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
                  'disabled:cursor-not-allowed disabled:opacity-50',
                  'transition-colors duration-200'
                )}
              >
                {isRemovingMember ? (
                  <span className="flex items-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Removing...
                  </span>
                ) : (
                  'Remove'
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Invitation Modal */}
      <InvitationModal
        isOpen={isInviteModalOpen}
        applicationId={applicationId}
        applicationName={application.name}
        onClose={handleCloseInviteModal}
        onInvitationSent={handleInvitationSent}
      />
    </div>
  )
}

export default ApplicationDetailPage
