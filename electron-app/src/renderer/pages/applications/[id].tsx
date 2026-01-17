/**
 * Application Detail Page
 *
 * Displays detailed view of a single application with its projects.
 * Allows editing and managing projects within the application.
 *
 * Features:
 * - Application header with edit capability
 * - Projects list within the application
 * - Navigation back to applications list
 * - Loading and error states
 */

import { useState, useCallback, useEffect } from 'react'
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
  ArrowLeft,
  Edit2,
  Trash2,
  Plus,
  Loader2,
  AlertCircle,
  Calendar,
  User,
  LayoutDashboard,
  Search,
  X,
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
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
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
    <div className="space-y-6">
      {/* Back Button */}
      {onBack && (
        <button
          onClick={onBack}
          className={cn(
            'inline-flex items-center gap-2 text-sm font-medium text-muted-foreground',
            'hover:text-foreground focus:outline-none focus:text-foreground',
            'transition-colors duration-200'
          )}
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Applications
        </button>
      )}

      {/* Application Header */}
      <div className="rounded-lg border border-border bg-card">
        <div className="p-6">
          <div className="flex items-start justify-between gap-4">
            {/* Icon and Details */}
            <div className="flex items-start gap-4">
              <div className="flex h-14 w-14 flex-shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <FolderKanban className="h-7 w-7" />
              </div>
              <div>
                <h1 className="text-2xl font-bold text-foreground">
                  {application.name}
                </h1>
                {application.description && (
                  <p className="mt-2 text-muted-foreground">
                    {application.description}
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
                <Edit2 className="h-4 w-4" />
                Edit
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
              <LayoutDashboard className="h-4 w-4" />
              <span>
                {application.projects_count}{' '}
                {application.projects_count === 1 ? 'project' : 'projects'}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <Calendar className="h-4 w-4" />
              <span>Created {formatDate(application.created_at)}</span>
            </div>
            <div className="flex items-center gap-2">
              <Calendar className="h-4 w-4" />
              <span>Updated {formatDate(application.updated_at)}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Projects Section */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-foreground">Projects</h2>
          <button
            onClick={handleCreateProject}
            className={cn(
              'inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground',
              'hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
              'transition-colors duration-200'
            )}
          >
            <Plus className="h-4 w-4" />
            New Project
          </button>
        </div>

        {/* Project Search Bar */}
        {(projects.length > 0 || projectSearchQuery) && (
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              value={projectSearchQuery}
              onChange={handleProjectSearch}
              placeholder="Search projects..."
              className={cn(
                'w-full rounded-md border border-input bg-background py-2 pl-10 pr-4 text-sm text-foreground placeholder:text-muted-foreground',
                'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background'
              )}
            />
            {projectSearchQuery && (
              <button
                onClick={() => {
                  setProjectSearchQuery('')
                  fetchProjects(token, applicationId)
                }}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
        )}

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
          <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border py-12">
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-muted">
              <LayoutDashboard className="h-8 w-8 text-muted-foreground" />
            </div>
            <h3 className="mt-4 text-lg font-semibold text-foreground">
              {projectSearchQuery ? 'No projects found' : 'No projects yet'}
            </h3>
            <p className="mt-2 text-center text-muted-foreground">
              {projectSearchQuery
                ? `No projects match "${projectSearchQuery}"`
                : 'Create your first project to start organizing your work.'}
            </p>
            {!projectSearchQuery && (
              <button
                onClick={handleCreateProject}
                className={cn(
                  'mt-4 inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground',
                  'hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
                  'transition-colors duration-200'
                )}
              >
                <Plus className="h-4 w-4" />
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
