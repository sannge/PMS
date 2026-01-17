/**
 * Project Detail Page
 *
 * Displays detailed view of a single project with its tasks in a board or list view.
 * Allows editing project settings and managing tasks.
 *
 * Features:
 * - Project header with edit capability
 * - Kanban board view for tasks
 * - List view for tasks
 * - Navigation back to projects list
 * - Loading and error states
 */

import { useState, useCallback, useEffect } from 'react'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth-store'
import {
  useProjectsStore,
  type Project,
  type ProjectUpdate,
} from '@/stores/projects-store'
import { ProjectForm } from '@/components/projects/project-form'
import { ProjectBoard, type Task, type TaskStatus } from '@/components/projects/project-board'
import {
  LayoutDashboard,
  ArrowLeft,
  Edit2,
  Trash2,
  Plus,
  Loader2,
  AlertCircle,
  Calendar,
  ListTodo,
  Columns,
  RefreshCw,
  Settings,
} from 'lucide-react'

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
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
}

/**
 * Get project type info
 */
function getProjectTypeInfo(projectType: string): { icon: JSX.Element; label: string } {
  switch (projectType) {
    case 'scrum':
      return {
        icon: <RefreshCw className="h-4 w-4" />,
        label: 'Scrum',
      }
    case 'kanban':
    default:
      return {
        icon: <Columns className="h-4 w-4" />,
        label: 'Kanban',
      }
  }
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

  // Local state
  const [isEditing, setIsEditing] = useState(false)
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)

  // Fetch project on mount
  useEffect(() => {
    fetchProject(token, projectId)
  }, [token, projectId, fetchProject])

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

  // Handle add task (placeholder for now)
  const handleAddTask = useCallback((status?: TaskStatus) => {
    // TODO: Implement task creation modal in subtask-4-7
  }, [])

  // Handle task click
  const handleTaskClick = useCallback(
    (task: Task) => {
      onSelectTask?.(task)
    },
    [onSelectTask]
  )

  // Loading state
  if (isLoading && !selectedProject) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="mt-4 text-muted-foreground">Loading project...</p>
      </div>
    )
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

  // Not found state
  if (!selectedProject) {
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

  const project = selectedProject
  const typeInfo = getProjectTypeInfo(project.project_type)

  return (
    <div className="flex flex-col h-full space-y-6">
      {/* Back Button */}
      {onBack && (
        <button
          onClick={onBack}
          className={cn(
            'inline-flex items-center gap-2 text-sm font-medium text-muted-foreground w-fit',
            'hover:text-foreground focus:outline-none focus:text-foreground',
            'transition-colors duration-200'
          )}
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Projects
        </button>
      )}

      {/* Project Header */}
      <div className="rounded-lg border border-border bg-card">
        <div className="p-6">
          <div className="flex items-start justify-between gap-4">
            {/* Icon and Details */}
            <div className="flex items-start gap-4">
              <div className="flex h-14 w-14 flex-shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <LayoutDashboard className="h-7 w-7" />
              </div>
              <div>
                <div className="flex items-center gap-3">
                  <h1 className="text-2xl font-bold text-foreground">
                    {project.name}
                  </h1>
                  <span className="rounded bg-muted px-2 py-1 text-sm font-mono font-medium text-muted-foreground">
                    {project.key}
                  </span>
                </div>
                {project.description && (
                  <p className="mt-2 text-muted-foreground">
                    {project.description}
                  </p>
                )}
              </div>
            </div>

            {/* Action Buttons */}
            <div className="flex items-center gap-2">
              <button
                onClick={handleEdit}
                className={cn(
                  'inline-flex items-center gap-2 rounded-md border border-input bg-background px-3 py-2 text-sm font-medium text-foreground',
                  'hover:bg-accent hover:text-accent-foreground',
                  'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
                  'transition-colors duration-200'
                )}
              >
                <Settings className="h-4 w-4" />
                Settings
              </button>
              <button
                onClick={handleDeleteClick}
                className={cn(
                  'inline-flex items-center gap-2 rounded-md border border-destructive/50 bg-background px-3 py-2 text-sm font-medium text-destructive',
                  'hover:bg-destructive/10',
                  'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
                  'transition-colors duration-200'
                )}
              >
                <Trash2 className="h-4 w-4" />
                Delete
              </button>
            </div>
          </div>

          {/* Meta Information */}
          <div className="mt-6 flex flex-wrap items-center gap-6 text-sm text-muted-foreground">
            <div className="flex items-center gap-2">
              {typeInfo.icon}
              <span>{typeInfo.label}</span>
            </div>
            <div className="flex items-center gap-2">
              <ListTodo className="h-4 w-4" />
              <span>
                {project.tasks_count}{' '}
                {project.tasks_count === 1 ? 'task' : 'tasks'}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <Calendar className="h-4 w-4" />
              <span>Created {formatDate(project.created_at)}</span>
            </div>
            <div className="flex items-center gap-2">
              <Calendar className="h-4 w-4" />
              <span>Updated {formatDate(project.updated_at)}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Board / Tasks Section */}
      <div className="flex-1 min-h-0">
        <ProjectBoard
          projectId={project.id}
          projectKey={project.key}
          onTaskClick={handleTaskClick}
          onAddTask={handleAddTask}
          className="h-full"
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
    </div>
  )
}

export default ProjectDetailPage
