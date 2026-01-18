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

import { useState, useCallback, useEffect, useRef } from 'react'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth-store'
import {
  useApplicationsStore,
  type Application,
  type ApplicationUpdate,
} from '@/stores/applications-store'
import {
  useProjectsStore,
  type Project,
  type ProjectCreate,
  type ProjectUpdate,
} from '@/stores/projects-store'
import { ApplicationForm } from '@/components/applications/application-form'
import { ProjectCard } from '@/components/projects/project-card'
import { ProjectForm } from '@/components/projects/project-form'
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
  // Auth state
  const token = useAuthStore((state) => state.token)

  // Applications state
  const {
    selectedApplication,
    isLoading,
    isUpdating,
    isDeleting,
    error,
    fetchApplication,
    updateApplication,
    deleteApplication,
    clearError,
  } = useApplicationsStore()

  // Projects state
  const {
    projects,
    isLoading: isLoadingProjects,
    isCreating: isCreatingProject,
    isUpdating: isUpdatingProject,
    isDeleting: isDeletingProject,
    error: projectsError,
    fetchProjects,
    createProject,
    updateProject,
    deleteProject,
    clearError: clearProjectsError,
  } = useProjectsStore()

  // Local state
  const [isEditing, setIsEditing] = useState(false)
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const [projectModalMode, setProjectModalMode] = useState<'create' | 'edit' | null>(null)
  const [editingProject, setEditingProject] = useState<Project | null>(null)
  const [deletingProject, setDeletingProject] = useState<Project | null>(null)
  const [projectSearchQuery, setProjectSearchQuery] = useState('')

  // Fetch application on mount
  useEffect(() => {
    fetchApplication(token, applicationId)
  }, [token, applicationId, fetchApplication])

  // Fetch projects when application is loaded
  useEffect(() => {
    if (selectedApplication?.id === applicationId) {
      fetchProjects(token, applicationId)
    }
  }, [token, applicationId, selectedApplication?.id, fetchProjects])

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
    async (data: ApplicationUpdate) => {
      const result = await updateApplication(token, applicationId, data)
      if (result) {
        setIsEditing(false)
      }
    },
    [token, applicationId, updateApplication]
  )

  // Handle delete click
  const handleDeleteClick = useCallback(() => {
    setShowDeleteDialog(true)
  }, [])

  // Handle confirm delete
  const handleConfirmDelete = useCallback(async () => {
    const success = await deleteApplication(token, applicationId)
    if (success) {
      setShowDeleteDialog(false)
      onDeleted?.()
      onBack?.()
    }
  }, [token, applicationId, deleteApplication, onDeleted, onBack])

  // Handle cancel delete
  const handleCancelDelete = useCallback(() => {
    setShowDeleteDialog(false)
  }, [])

  // ============================================================================
  // Project Handlers
  // ============================================================================

  // Handle create project
  const handleCreateProject = useCallback(() => {
    clearProjectsError()
    setEditingProject(null)
    setProjectModalMode('create')
  }, [clearProjectsError])

  // Handle edit project
  const handleEditProject = useCallback(
    (project: Project) => {
      clearProjectsError()
      setEditingProject(project)
      setProjectModalMode('edit')
    },
    [clearProjectsError]
  )

  // Handle delete project click
  const handleDeleteProjectClick = useCallback((project: Project) => {
    setDeletingProject(project)
  }, [])

  // Handle confirm delete project
  const handleConfirmDeleteProject = useCallback(async () => {
    if (!deletingProject) return

    const success = await deleteProject(token, deletingProject.id)
    if (success) {
      setDeletingProject(null)
    }
  }, [deletingProject, deleteProject, token])

  // Handle cancel delete project
  const handleCancelDeleteProject = useCallback(() => {
    setDeletingProject(null)
  }, [])

  // Handle close project modal
  const handleCloseProjectModal = useCallback(() => {
    setProjectModalMode(null)
    setEditingProject(null)
  }, [])

  // Handle project form submit
  const handleProjectFormSubmit = useCallback(
    async (data: ProjectCreate | ProjectUpdate) => {
      if (projectModalMode === 'create') {
        const project = await createProject(token, applicationId, data as ProjectCreate)
        if (project) {
          handleCloseProjectModal()
        }
      } else if (projectModalMode === 'edit' && editingProject) {
        const project = await updateProject(token, editingProject.id, data as ProjectUpdate)
        if (project) {
          handleCloseProjectModal()
        }
      }
    },
    [projectModalMode, editingProject, createProject, updateProject, token, applicationId, handleCloseProjectModal]
  )

  // Handle project click
  const handleProjectClick = useCallback(
    (project: Project) => {
      onSelectProject?.(project.id)
    },
    [onSelectProject]
  )

  // Handle project search
  const handleProjectSearch = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const query = e.target.value
      setProjectSearchQuery(query)
      fetchProjects(token, applicationId, { search: query || undefined })
    },
    [token, applicationId, fetchProjects]
  )

  // Loading state
  if (isLoading && !selectedApplication) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="mt-4 text-muted-foreground">Loading application...</p>
      </div>
    )
  }

  // Error state
  if (error && !selectedApplication) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <div className="flex h-16 w-16 items-center justify-center rounded-full bg-destructive/10">
          <AlertCircle className="h-8 w-8 text-destructive" />
        </div>
        <h3 className="mt-4 text-lg font-semibold text-foreground">
          Failed to load application
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
            Back to Applications
          </button>
        )}
      </div>
    )
  }

  // Not found state
  if (!selectedApplication) {
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

  const application = selectedApplication

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
          <ActionsDropdown onEdit={handleEdit} onDelete={handleDeleteClick} />
        </div>
      </div>

      {/* Projects Section - Compact Header */}
      <div className="space-y-3">
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
                    onClick={() => {
                      setProjectSearchQuery('')
                      fetchProjects(token, applicationId)
                    }}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    <X className="h-3 w-3" />
                  </button>
                )}
              </div>
            )}
          </div>
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
        </div>

        {/* Projects Error Display */}
        {projectsError && !projectModalMode && (
          <div className="flex items-center gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
            <AlertCircle className="h-4 w-4 flex-shrink-0" />
            <span>{projectsError.message}</span>
            <button
              onClick={clearProjectsError}
              className="ml-auto text-destructive hover:text-destructive/80"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        )}

        {/* Loading Projects State */}
        {isLoadingProjects && projects.length === 0 && (
          <div className="flex flex-col items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-primary" />
            <p className="mt-2 text-sm text-muted-foreground">Loading projects...</p>
          </div>
        )}

        {/* Empty Projects State */}
        {!isLoadingProjects && projects.length === 0 && (
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
            {!projectSearchQuery && (
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

        {/* Projects Grid */}
        {!isLoadingProjects && projects.length > 0 && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {projects.map((project) => (
              <ProjectCard
                key={project.id}
                project={project}
                onClick={onSelectProject ? handleProjectClick : undefined}
                onEdit={handleEditProject}
                onDelete={handleDeleteProjectClick}
                disabled={isDeletingProject}
              />
            ))}
          </div>
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
    </div>
  )
}

export default ApplicationDetailPage
