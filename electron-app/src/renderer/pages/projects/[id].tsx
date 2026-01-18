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
import {
  useProjectsStore,
  type Project,
  type ProjectUpdate,
} from '@/stores/projects-store'
import { ProjectForm } from '@/components/projects/project-form'
import { ProjectBoard, type Task, type TaskStatus } from '@/components/projects/project-board'
import {
  LayoutDashboard,
  ChevronRight,
  MoreHorizontal,
  Edit2,
  Trash2,
  Loader2,
  AlertCircle,
  ListTodo,
  Columns,
  RefreshCw,
  Info,
  ArrowLeft,
} from 'lucide-react'
import { SkeletonProjectDetail, PulseIndicator } from '@/components/ui/skeleton'

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
            Settings
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

  // Loading state - modern skeleton
  if (isLoading && !selectedProject) {
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
        <div className="flex items-center gap-1 flex-shrink-0">
          <InfoTooltip project={project} />
          <ActionsDropdown onEdit={handleEdit} onDelete={handleDeleteClick} />
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
