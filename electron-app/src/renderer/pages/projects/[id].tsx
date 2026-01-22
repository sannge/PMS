/**
 * Project Detail Page
 *
 * Space-efficient project view with compact header.
 * Features:
 * - Ultra-compact breadcrumb header
 * - Full-height Kanban board
 * - Inline actions via dropdown
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth-store'
import { useApplicationsStore } from '@/stores/applications-store'
import {
  useProjectsStore,
  type Project,
  type ProjectUpdate,
} from '@/stores/projects-store'
import { useTasksStore, type TaskCreate, type TaskUpdate } from '@/stores/tasks-store'
import { useProjectMembersStore } from '@/stores/project-members-store'
import { ProjectForm } from '@/components/projects/project-form'
import { KanbanBoard } from '@/components/kanban/KanbanBoard'
import type { Task, TaskStatus } from '@/stores/tasks-store'
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
  onBack,
  onDeleted,
  onSelectTask,
}: ProjectDetailPageProps): JSX.Element {
  // Auth state
  const token = useAuthStore((state) => state.token)
  const currentUserId = useAuthStore((state) => state.user?.id)

  // Application state - get user's role for permission checks
  const selectedApplication = useApplicationsStore((state) => state.selectedApplication)
  const userRole = selectedApplication?.user_role || 'viewer'
  const isAppOwner = userRole === 'owner'
  const isAppEditor = userRole === 'editor'

  // Project members state - to check if user can view/manage team
  const {
    members: projectMembers,
    fetchMembers: fetchProjectMembers,
    canManageMembers,
  } = useProjectMembersStore()

  // Check if current user is a project member
  const currentUserMembership = projectMembers.find((m) => m.user_id === currentUserId)
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
  const canManageTeam = canManageMembers(currentUserId || '', isAppOwner)

  // User can edit tasks if: app owner, OR (app editor AND project member)
  // Editors need to be project members to edit tasks within a project
  const canEditTasks = isAppOwner || (isAppEditor && isProjectMember)

  // Real-time sync hooks for project updates and member changes
  useProjectUpdatedSync(projectId)
  useProjectMemberSync(projectId)

  // Convert project members to assignee options for task form
  const assigneeOptions: AssigneeOption[] = projectMembers
    .filter((m) => m.user)
    .map((m) => ({
      id: m.user_id,
      display_name: m.user?.display_name,
      email: m.user?.email,
      avatar_url: m.user?.avatar_url,
    }))

  // Projects state
  const {
    selectedProject,
    isLoading,
    isUpdating,
    isDeleting,
    error,
    fetchProject,
    updateProject,
    deleteProject,
    clearError,
  } = useProjectsStore()

  // Tasks state
  const {
    createTask,
    updateTask,
    deleteTask: deleteTaskFromStore,
    isCreating: isCreatingTask,
    isUpdating: isUpdatingTask,
    isDeleting: isDeletingTask,
    error: taskError,
    clearError: clearTaskError,
  } = useTasksStore()

  // Local state
  const [isEditing, setIsEditing] = useState(false)
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const [showTeamPanel, setShowTeamPanel] = useState(false)
  const [showStatusPanel, setShowStatusPanel] = useState(false)
  const [hasFetched, setHasFetched] = useState(false)
  const [showTaskForm, setShowTaskForm] = useState(false)
  const [initialTaskStatus, setInitialTaskStatus] = useState<TaskStatus>('todo')
  const [selectedTask, setSelectedTask] = useState<Task | null>(null)

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

  // Fetch project on mount
  useEffect(() => {
    setHasFetched(false)
    fetchProject(token, projectId).finally(() => {
      setHasFetched(true)
    })
  }, [token, projectId, fetchProject])

  // Fetch project members to check permissions
  useEffect(() => {
    if (projectId) {
      fetchProjectMembers(token, projectId)
    }
  }, [token, projectId, fetchProjectMembers])

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
      const result = await updateProject(token, projectId, data)
      if (result) {
        setIsEditing(false)
      }
    },
    [token, projectId, updateProject]
  )

  // Handle delete click
  const handleDeleteClick = useCallback(() => {
    setShowDeleteDialog(true)
  }, [])

  // Handle confirm delete
  const handleConfirmDelete = useCallback(async () => {
    const success = await deleteProject(token, projectId)
    if (success) {
      setShowDeleteDialog(false)
      onDeleted?.()
      onBack?.()
    }
  }, [token, projectId, deleteProject, onDeleted, onBack])

  // Handle cancel delete
  const handleCancelDelete = useCallback(() => {
    setShowDeleteDialog(false)
  }, [])

  // Handle add task
  const handleAddTask = useCallback((status?: TaskStatus) => {
    clearTaskError()
    setInitialTaskStatus(status || 'todo')
    setShowTaskForm(true)
  }, [clearTaskError])

  // Handle create task submission
  const handleCreateTask = useCallback(
    async (data: TaskCreate) => {
      const task = await createTask(token, projectId, data)
      if (task) {
        setShowTaskForm(false)
        // Refresh the project to update task count
        fetchProject(token, projectId)
        // Refresh the board to show the new task immediately
        if (refreshBoardRef.current) {
          refreshBoardRef.current()
        }
      }
    },
    [token, projectId, createTask, fetchProject]
  )

  // Handle close task form
  const handleCloseTaskForm = useCallback(() => {
    setShowTaskForm(false)
    clearTaskError()
  }, [clearTaskError])

  // Handle task click
  const handleTaskClick = useCallback(
    (task: Task) => {
      // Notify other users that we're viewing this task
      setViewing(task.id)
      setSelectedTask(task)
      onSelectTask?.(task)
    },
    [onSelectTask, setViewing]
  )

  // Handle close task detail
  const handleCloseTaskDetail = useCallback(() => {
    setSelectedTask(null)
  }, [])

  // Handle task update
  const handleTaskUpdate = useCallback(
    async (data: TaskUpdate) => {
      if (!selectedTask) return
      const updatedTask = await updateTask(token, selectedTask.id, data)
      if (updatedTask) {
        setSelectedTask(updatedTask)
        // Refresh board to reflect changes
        if (refreshBoardRef.current) {
          refreshBoardRef.current()
        }
      }
    },
    [token, selectedTask, updateTask]
  )

  // Handle task delete
  const handleTaskDelete = useCallback(async () => {
    if (!selectedTask) return
    const success = await deleteTaskFromStore(token, selectedTask.id)
    if (success) {
      setSelectedTask(null)
      // Refresh project to update task count
      fetchProject(token, projectId)
      // Refresh board to remove the deleted task
      if (refreshBoardRef.current) {
        refreshBoardRef.current()
      }
    }
  }, [token, selectedTask, deleteTaskFromStore, fetchProject, projectId])

  // Show loading if actively loading OR if we haven't fetched yet
  const showLoading = isLoading || !hasFetched

  // Loading state - modern skeleton
  if (showLoading && !selectedProject) {
    return <SkeletonProjectDetail />
  }

  // Error state
  if (error && !selectedProject) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <div className="flex h-16 w-16 items-center justify-center rounded-full bg-destructive/10">
          <AlertCircle className="h-8 w-8 text-destructive" />
        </div>
        <h3 className="mt-4 text-lg font-semibold text-foreground">
          Failed to load project
        </h3>
        <p className="mt-2 text-muted-foreground">{error.message}</p>
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

  // Not found state (only show after fetch completed)
  if (!selectedProject && hasFetched) {
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

  // At this point, selectedProject is guaranteed to be non-null due to early returns above
  const project = selectedProject!
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
            error={error?.message}
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
                applicationId={selectedApplication?.id || ''}
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
                  fetchProject(token, projectId)
                  setShowStatusPanel(false)
                }}
                onOverrideCleared={() => {
                  fetchProject(token, projectId)
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
            error={taskError?.message}
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
          error={taskError?.message}
          onClose={handleCloseTaskDetail}
          onUpdate={canEditTasks ? handleTaskUpdate : undefined}
          onDelete={canEditTasks ? handleTaskDelete : undefined}
          canEdit={canEditTasks}
          applicationId={project.application_id}
          onExternalUpdate={(updatedTask) => {
            setSelectedTask(updatedTask)
            fetchProject(token, projectId)
          }}
          onExternalDelete={() => {
            setSelectedTask(null)
            fetchProject(token, projectId)
          }}
          enableRealtime
        />
      )}
    </div>
  )
}

export default ProjectDetailPage
