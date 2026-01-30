/**
 * Project Detail Page
 *
 * Space-efficient project view with compact header.
 * Features:
 * - Ultra-compact breadcrumb header
 * - Full-height Kanban board
 * - Inline actions via dropdown
 */

import { useState, useCallback, useEffect, useRef, useMemo } from 'react'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth-store'
import {
  useProject,
  useUpdateProject,
  useDeleteProject,
  useApplication,
  useTask,
  useCreateTask,
  useUpdateTask,
  useDeleteTask,
  type Project,
  type ProjectUpdate,
  type Task,
  type TaskCreate,
  type TaskUpdate,
  type TaskStatus as TaskStatusObject,
  type TaskStatusValue as TaskStatus,
} from '@/hooks/use-queries'
import { useProjectMembers, type ProjectMember } from '@/hooks/use-members'
import { ProjectForm } from '@/components/projects/project-form'
import { KanbanBoard } from '@/components/kanban/KanbanBoard'
import { TaskForm, type AssigneeOption } from '@/components/tasks/task-form'
import { TaskDetail } from '@/components/tasks/task-detail'
import {
  LayoutDashboard,
  ChevronRight,
  MoreHorizontal,
  Edit2,
  Trash2,
  Loader2,
  AlertCircle,
  Columns,
  RefreshCw,
  Info,
  ArrowLeft,
  Users,
  X,
  Shield,
} from 'lucide-react'
import { SkeletonProjectDetail } from '@/components/ui/skeleton'
import { ProjectMemberPanel } from '@/components/projects/ProjectMemberPanel'
import { ProjectStatusOverride } from '@/components/projects/ProjectStatusOverride'
import { PresenceAvatars } from '@/components/presence'
import { usePresence, useTaskViewers } from '@/hooks'
import { useProjectUpdatedSync, useProjectMemberSync } from '@/hooks/use-websocket'

// ============================================================================
// Types
// ============================================================================

export interface ProjectDetailPageProps {
  /**
   * Project ID to display
   */
  projectId: string
  /**
   * Application ID for permission checks
   */
  applicationId: string
  /**
   * Callback to navigate back to projects list
   */
  onBack?: () => void
  /**
   * Callback when project is deleted
   */
  onDeleted?: () => void
  /**
   * Callback when a task is selected
   */
  onSelectTask?: (task: Task) => void
  /**
   * Task ID to auto-open in the detail panel on mount
   */
  initialTaskId?: string | null
  /**
   * Callback to clear initialTaskId after it has been consumed
   */
  onInitialTaskConsumed?: () => void
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

/**
 * Get project type info
 */
function getProjectTypeInfo(projectType: string): { icon: JSX.Element; label: string } {
  switch (projectType) {
    case 'scrum':
      return {
        icon: <RefreshCw className="h-3.5 w-3.5" />,
        label: 'Scrum',
      }
    case 'kanban':
    default:
      return {
        icon: <Columns className="h-3.5 w-3.5" />,
        label: 'Kanban',
      }
  }
}

// ============================================================================
// Actions Dropdown Component
// ============================================================================

interface ActionsDropdownProps {
  onEdit?: () => void
  onDelete?: () => void
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

  // Don't render if no actions available
  if (!onEdit && !onDelete) {
    return <></>
  }

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
          {onEdit && (
            <button
              onClick={() => { onEdit(); setIsOpen(false) }}
              className={cn(
                'flex w-full items-center gap-2 px-3 py-1.5 text-sm',
                'text-foreground hover:bg-muted transition-colors'
              )}
            >
              <Edit2 className="h-3.5 w-3.5" />
              Settings
            </button>
          )}
          {onDelete && (
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
          )}
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Info Tooltip Component
// ============================================================================

interface InfoTooltipProps {
  project: Project
}

function InfoTooltip({ project }: InfoTooltipProps): JSX.Element {
  const [isOpen, setIsOpen] = useState(false)
  const tooltipRef = useRef<HTMLDivElement>(null)
  const typeInfo = getProjectTypeInfo(project.project_type)

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
            {project.description && (
              <div>
                <span className="text-muted-foreground">Description</span>
                <p className="text-foreground mt-0.5">{project.description}</p>
              </div>
            )}
            <div className="flex justify-between">
              <span className="text-muted-foreground">Type</span>
              <span className="text-foreground flex items-center gap-1">
                {typeInfo.icon}
                {typeInfo.label}
              </span>
            </div>
            {project.due_date && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Due Date</span>
                <span className="text-foreground">
                  {new Date(project.due_date + 'T00:00:00').toLocaleDateString()}
                </span>
              </div>
            )}
            <div className="flex justify-between">
              <span className="text-muted-foreground">Created</span>
              <span className="text-foreground">{formatDate(project.created_at)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Updated</span>
              <span className="text-foreground">{formatRelativeDate(project.updated_at)}</span>
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
  project: Project
  isDeleting: boolean
  onConfirm: () => void
  onCancel: () => void
}

function DeleteConfirmDialog({
  project,
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
            <h3 className="text-lg font-semibold text-foreground">Delete Project</h3>
            <p className="mt-2 text-sm text-muted-foreground">
              Are you sure you want to delete <strong>{project.name}</strong> ({project.key})?
              This will also delete all tasks within this project.
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

export function ProjectDetailPage({
  projectId,
  applicationId,
  onBack,
  onDeleted,
  onSelectTask,
  initialTaskId,
  onInitialTaskConsumed,
}: ProjectDetailPageProps): JSX.Element {
  // Auth state
  const currentUserId = useAuthStore((state) => state.user?.id)

  // TanStack Query hooks
  const {
    data: project,
    isLoading,
    error: queryError,
  } = useProject(projectId)

  const { data: application } = useApplication(applicationId)
  const { data: projectMembers = [] } = useProjectMembers(projectId)

  // Mutation hooks
  const updateMutation = useUpdateProject(projectId, applicationId)
  const deleteMutation = useDeleteProject(projectId, applicationId)

  // Task mutations - need state for selected task
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  const createTaskMutation = useCreateTask(projectId)
  const updateTaskMutation = useUpdateTask(selectedTaskId || '', projectId)
  const deleteTaskMutation = useDeleteTask(selectedTaskId || '', projectId)

  // Derive loading states from mutations
  const isUpdating = updateMutation.isPending
  const isDeleting = deleteMutation.isPending
  const isCreatingTask = createTaskMutation.isPending
  const isUpdatingTask = updateTaskMutation.isPending
  const isDeletingTask = deleteTaskMutation.isPending

  // Local error state for mutations
  const [mutationError, setMutationError] = useState<string | null>(null)

  // Application state - get user's role for permission checks
  const userRole = application?.user_role || 'viewer'
  const isAppOwner = userRole === 'owner'
  const isAppEditor = userRole === 'editor'

  // Check if current user is a project member
  const currentUserMembership = useMemo(
    () => projectMembers.find((m) => m.user_id === currentUserId),
    [projectMembers, currentUserId]
  )
  const isProjectMember = !!currentUserMembership
  const isProjectAdmin = currentUserMembership?.role === 'admin'

  // Permission checks:
  // - Edit project: App owner can edit any project, OR (app editor AND project member)
  const canEditProject = isAppOwner || (isAppEditor && isProjectMember)
  // - Delete project: Only app owner or project admin can delete
  const canDeleteProject = isAppOwner || isProjectAdmin

  // User can view team if: app owner, or project member
  const canViewTeam = isAppOwner || isProjectMember

  // User can manage team if: app owner, or project admin
  const canManageTeam = isAppOwner || isProjectAdmin

  // User can edit tasks if: app owner, OR (app editor AND project member)
  // Editors need to be project members to edit tasks within a project
  const canEditTasks = isAppOwner || (isAppEditor && isProjectMember)

  // Real-time sync hooks for project updates and member changes
  useProjectUpdatedSync(projectId)
  useProjectMemberSync(projectId)

  // Convert project members to assignee options for task form
  const assigneeOptions: AssigneeOption[] = useMemo(
    () =>
      projectMembers.map((m) => ({
        id: m.user_id,
        display_name: m.user_display_name,
        email: m.user_email,
        avatar_url: m.user_avatar_url,
      })),
    [projectMembers]
  )

  // Combine errors
  const error = queryError?.message || mutationError

  // Clear mutation error helper
  const clearError = useCallback(() => {
    setMutationError(null)
  }, [])

  // Local state
  const [isEditing, setIsEditing] = useState(false)
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const [showTeamPanel, setShowTeamPanel] = useState(false)
  const [showStatusPanel, setShowStatusPanel] = useState(false)
  const [showTaskForm, setShowTaskForm] = useState(false)
  const [initialTaskStatus, setInitialTaskStatus] = useState<TaskStatus | undefined>(undefined)
  const [selectedTask, setSelectedTask] = useState<Task | null>(null)

  // Fetch initial task for auto-open
  const { data: initialTask } = useTask(initialTaskId || undefined)
  const initialTaskConsumedRef = useRef(false)

  // Ref to hold the board refresh function
  const refreshBoardRef = useRef<(() => void) | null>(null)

  // Presence hook for real-time collaboration
  const { viewers: presenceUsers, isConnected: _isConnected } = usePresence({
    roomId: projectId,
    roomType: 'project',
    enabled: true,
  })

  // Task viewers hook for tracking who's viewing which task
  const { getViewers: _getViewers, setViewing } = useTaskViewers({
    projectId,
    enabled: true,
  })

  // Auto-open task detail when initialTaskId is provided
  useEffect(() => {
    if (initialTask && initialTaskId && !initialTaskConsumedRef.current) {
      initialTaskConsumedRef.current = true
      setSelectedTask(initialTask)
      setSelectedTaskId(initialTask.id)
      setViewing(initialTask.id)
      onInitialTaskConsumed?.()
    }
  }, [initialTask, initialTaskId, onInitialTaskConsumed, setViewing])

  // Reset consumed ref when initialTaskId changes
  useEffect(() => {
    if (!initialTaskId) {
      initialTaskConsumedRef.current = false
    }
  }, [initialTaskId])

  // Handle edit
  const handleEdit = useCallback(() => {
    clearError()
    setIsEditing(true)
  }, [clearError])

  // Handle close edit
  const handleCloseEdit = useCallback(() => {
    setIsEditing(false)
  }, [])

  // Handle update
  const handleUpdate = useCallback(
    async (data: ProjectUpdate) => {
      try {
        await updateMutation.mutateAsync(data)
        setIsEditing(false)
      } catch (err) {
        setMutationError(err instanceof Error ? err.message : 'Failed to update project')
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
      setMutationError(err instanceof Error ? err.message : 'Failed to delete project')
    }
  }, [deleteMutation, onDeleted, onBack])

  // Handle cancel delete
  const handleCancelDelete = useCallback(() => {
    setShowDeleteDialog(false)
  }, [])

  // Handle add task
  const handleAddTask = useCallback((status?: TaskStatus) => {
    setMutationError(null)
    setInitialTaskStatus(status)
    setShowTaskForm(true)
  }, [])

  // Handle create task submission
  const handleCreateTask = useCallback(
    async (data: TaskCreate) => {
      try {
        await createTaskMutation.mutateAsync(data)
        setShowTaskForm(false)
        // Board will refresh via cache invalidation
        if (refreshBoardRef.current) {
          refreshBoardRef.current()
        }
      } catch (err) {
        setMutationError(err instanceof Error ? err.message : 'Failed to create task')
      }
    },
    [createTaskMutation]
  )

  // Handle close task form
  const handleCloseTaskForm = useCallback(() => {
    setShowTaskForm(false)
    setMutationError(null)
  }, [])

  // Handle task click
  const handleTaskClick = useCallback(
    (task: Task) => {
      // Notify other users that we're viewing this task
      setViewing(task.id)
      setSelectedTask(task)
      setSelectedTaskId(task.id)
      onSelectTask?.(task)
    },
    [onSelectTask, setViewing]
  )

  // Handle close task detail
  const handleCloseTaskDetail = useCallback(() => {
    setSelectedTask(null)
    setSelectedTaskId(null)
  }, [])

  // Handle task update
  const handleTaskUpdate = useCallback(
    async (data: TaskUpdate) => {
      if (!selectedTask) return
      try {
        const updatedTask = await updateTaskMutation.mutateAsync(data)
        setSelectedTask(updatedTask)
        // Board will refresh via cache invalidation
        if (refreshBoardRef.current) {
          refreshBoardRef.current()
        }
      } catch (err) {
        setMutationError(err instanceof Error ? err.message : 'Failed to update task')
      }
    },
    [selectedTask, updateTaskMutation]
  )

  // Handle task delete
  const handleTaskDelete = useCallback(async () => {
    if (!selectedTask) return
    try {
      await deleteTaskMutation.mutateAsync()
      setSelectedTask(null)
      setSelectedTaskId(null)
      // Board will refresh via cache invalidation
      if (refreshBoardRef.current) {
        refreshBoardRef.current()
      }
    } catch (err) {
      setMutationError(err instanceof Error ? err.message : 'Failed to delete task')
    }
  }, [selectedTask, deleteTaskMutation])

  // Show loading only on first load (no cached data)
  const showLoading = isLoading && !project

  // Loading state - modern skeleton
  if (showLoading) {
    return <SkeletonProjectDetail />
  }

  // Error state
  if (queryError && !project) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <div className="flex h-16 w-16 items-center justify-center rounded-full bg-destructive/10">
          <AlertCircle className="h-8 w-8 text-destructive" />
        </div>
        <h3 className="mt-4 text-lg font-semibold text-foreground">
          Failed to load project
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
            Back to Projects
          </button>
        )}
      </div>
    )
  }

  // Not found state (only show after loading completes without data)
  if (!project && !isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <div className="flex h-16 w-16 items-center justify-center rounded-full bg-muted">
          <LayoutDashboard className="h-8 w-8 text-muted-foreground" />
        </div>
        <h3 className="mt-4 text-lg font-semibold text-foreground">
          Project not found
        </h3>
        <p className="mt-2 text-muted-foreground">
          The project you're looking for doesn't exist or has been deleted.
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
            Back to Projects
          </button>
        )}
      </div>
    )
  }

  // Safety check - should not happen but TypeScript needs this
  if (!project) {
    return <SkeletonProjectDetail />
  }
  const typeInfo = getProjectTypeInfo(project.project_type)

  return (
    <div className="flex flex-col h-full space-y-3">
      {/* Compact Header Bar */}
      <div className="flex items-center justify-between gap-4 pb-2 border-b border-border">
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
                Projects
              </button>
              <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/50 flex-shrink-0" />
            </>
          )}
          <div className="flex items-center gap-2 min-w-0">
            <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
              <LayoutDashboard className="h-4 w-4" />
            </div>
            <h1 className="text-base font-semibold text-foreground truncate">
              {project.name}
            </h1>
            <span className="text-[10px] font-mono text-muted-foreground bg-muted px-1.5 py-0.5 rounded flex-shrink-0">
              {project.key}
            </span>
            <span className="text-xs text-muted-foreground flex-shrink-0 flex items-center gap-1">
              {typeInfo.icon}
              {typeInfo.label}
            </span>
            <span className="text-xs text-muted-foreground flex-shrink-0 bg-muted px-1.5 py-0.5 rounded">
              {project.tasks_count} {project.tasks_count === 1 ? 'task' : 'tasks'}
            </span>
            {project.due_date && (
              <span className="text-xs text-muted-foreground flex-shrink-0 flex items-center gap-1">
                Due {new Date(project.due_date + 'T00:00:00').toLocaleDateString()}
              </span>
            )}
          </div>
        </div>

        {/* Right: Actions */}
        <div className="flex items-center gap-2 flex-shrink-0">
          {/* Presence Avatars */}
          {presenceUsers.length > 0 && (
            <PresenceAvatars viewers={presenceUsers} maxVisible={4} size="sm" />
          )}

          {/* Divider */}
          {presenceUsers.length > 0 && (
            <div className="h-5 w-px bg-border" />
          )}

          {/* Team Button (visible to app owners and project members) */}
          {canViewTeam && (
            <button
              onClick={() => setShowTeamPanel(true)}
              className={cn(
                'flex h-7 items-center gap-1.5 px-2 rounded-md transition-colors',
                'text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted'
              )}
              title={canManageTeam ? 'Manage Team' : 'View Team'}
            >
              <Users className="h-3.5 w-3.5" />
              Team
            </button>
          )}

          {/* Status Button (Owners only) */}
          {userRole === 'owner' && (
            <button
              onClick={() => setShowStatusPanel(true)}
              className={cn(
                'flex h-7 items-center gap-1.5 px-2 rounded-md transition-colors',
                'text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted'
              )}
              title="Status Override"
            >
              <Shield className="h-3.5 w-3.5" />
              Status
            </button>
          )}

          <InfoTooltip project={project} />
          {(canEditProject || canDeleteProject) && (
            <ActionsDropdown
              onEdit={canEditProject ? handleEdit : undefined}
              onDelete={canDeleteProject ? handleDeleteClick : undefined}
            />
          )}
        </div>
      </div>

      {/* Board / Tasks Section */}
      <div className="flex-1 min-h-0">
        <KanbanBoard
          projectId={project.id}
          projectKey={project.key}
          onTaskClick={handleTaskClick}
          onAddTask={canEditTasks ? handleAddTask : undefined}
          canEdit={canEditTasks}
          className="h-full"
          enableRealtime
          onRefresh={(refreshFn) => {
            refreshBoardRef.current = refreshFn
          }}
        />
      </div>

      {/* Edit Modal */}
      {isEditing && (
        <Modal onClose={handleCloseEdit}>
          <ProjectForm
            project={project}
            isSubmitting={isUpdating}
            error={error || undefined}
            onSubmit={handleUpdate}
            onCancel={handleCloseEdit}
          />
        </Modal>
      )}

      {/* Delete Confirmation Dialog */}
      {showDeleteDialog && (
        <DeleteConfirmDialog
          project={project}
          isDeleting={isDeleting}
          onConfirm={handleConfirmDelete}
          onCancel={handleCancelDelete}
        />
      )}

      {/* Team Panel Slide-over */}
      {showTeamPanel && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/50"
            onClick={() => setShowTeamPanel(false)}
          />
          <div
            className={cn(
              'fixed right-0 top-0 z-50 h-full w-full max-w-sm',
              'bg-background shadow-xl border-l border-border',
              'transform transition-transform duration-200 ease-out'
            )}
          >
            <div className="flex items-center justify-between px-4 py-3 border-b border-border">
              <h2 className="text-sm font-semibold text-foreground">Manage Team</h2>
              <button
                onClick={() => setShowTeamPanel(false)}
                className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="h-[calc(100%-52px)] overflow-y-auto">
              <ProjectMemberPanel
                projectId={project.id}
                applicationId={applicationId}
                isOwner={isAppOwner}
                creatorId={project.created_by}
              />
            </div>
          </div>
        </>
      )}

      {/* Status Override Panel Slide-over */}
      {showStatusPanel && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/50"
            onClick={() => setShowStatusPanel(false)}
          />
          <div
            className={cn(
              'fixed right-0 top-0 z-50 h-full w-full max-w-sm',
              'bg-background shadow-xl border-l border-border',
              'transform transition-transform duration-200 ease-out'
            )}
          >
            <div className="flex items-center justify-between px-4 py-3 border-b border-border">
              <h2 className="text-sm font-semibold text-foreground">Status Override</h2>
              <button
                onClick={() => setShowStatusPanel(false)}
                className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="p-4">
              <ProjectStatusOverride
                project={{
                  id: project.id,
                  name: project.name,
                  derived_status_id: project.derived_status_id || null,
                  override_status_id: project.override_status_id || null,
                  override_reason: project.override_reason || null,
                  override_by_user_id: project.override_by_user_id || null,
                  override_expires_at: project.override_expires_at || null,
                }}
                statuses={[]}
                isOwner={userRole === 'owner'}
                onOverrideSet={() => {
                  // Query will auto-refetch via cache invalidation
                  setShowStatusPanel(false)
                }}
                onOverrideCleared={() => {
                  // Query will auto-refetch via cache invalidation
                  setShowStatusPanel(false)
                }}
              />
            </div>
          </div>
        </>
      )}

      {/* Task Creation Modal */}
      {showTaskForm && (
        <Modal onClose={handleCloseTaskForm}>
          <TaskForm
            initialStatus={initialTaskStatus}
            assignees={assigneeOptions}
            isSubmitting={isCreatingTask}
            error={error || undefined}
            onSubmit={handleCreateTask as (data: TaskCreate | TaskUpdate) => void}
            onCancel={handleCloseTaskForm}
          />
        </Modal>
      )}

      {/* Task Detail Slide-over */}
      {selectedTask && (
        <TaskDetail
          task={selectedTask}
          isOpen={true}
          isUpdating={isUpdatingTask}
          isDeleting={isDeletingTask}
          error={error || undefined}
          onClose={handleCloseTaskDetail}
          onUpdate={canEditTasks ? handleTaskUpdate : undefined}
          onDelete={canEditTasks ? handleTaskDelete : undefined}
          canEdit={canEditTasks}
          applicationId={project.application_id}
          onExternalUpdate={(updatedTask) => {
            setSelectedTask(updatedTask)
            // Project query will auto-refetch via cache invalidation
          }}
          onExternalDelete={() => {
            setSelectedTask(null)
            setSelectedTaskId(null)
            // Project query will auto-refetch via cache invalidation
          }}
          onRevertTaskSelection={(revertToTask) => {
            // Restore previous task selection when user wants to keep editing
            setSelectedTask(revertToTask)
            setSelectedTaskId(revertToTask.id)
          }}
          enableRealtime
        />
      )}
    </div>
  )
}

export default ProjectDetailPage
