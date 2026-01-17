/**
 * Projects List Page
 *
 * Displays a list of all projects within an application with search,
 * create, edit, and delete functionality.
 *
 * Features:
 * - Project list with cards
 * - Search filtering
 * - Create new project modal
 * - Edit project modal
 * - Delete confirmation dialog
 * - Empty state
 * - Loading state
 */

import { useState, useCallback, useEffect } from 'react'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth-store'
import {
  useProjectsStore,
  type Project,
  type ProjectCreate,
  type ProjectUpdate,
} from '@/stores/projects-store'
import { ProjectCard } from '@/components/projects/project-card'
import { ProjectForm } from '@/components/projects/project-form'
import {
  LayoutDashboard,
  Plus,
  Search,
  Loader2,
  AlertCircle,
  X,
  ArrowLeft,
} from 'lucide-react'

// ============================================================================
// Types
// ============================================================================

export interface ProjectsPageProps {
  /**
   * Application ID to show projects for
   */
  applicationId: string
  /**
   * Application name for display
   */
  applicationName?: string
  /**
   * Callback when a project is selected
   */
  onSelectProject?: (project: Project) => void
  /**
   * Callback to navigate back
   */
  onBack?: () => void
}

type ModalMode = 'create' | 'edit' | null

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
  // Close on escape key
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

export function ProjectsPage({
  applicationId,
  applicationName,
  onSelectProject,
  onBack,
}: ProjectsPageProps): JSX.Element {
  // Auth state
  const token = useAuthStore((state) => state.token)

  // Projects state
  const {
    projects,
    isLoading,
    isCreating,
    isUpdating,
    isDeleting,
    error,
    fetchProjects,
    createProject,
    updateProject,
    deleteProject,
    clearError,
  } = useProjectsStore()

  // Local state
  const [searchQuery, setSearchQuery] = useState('')
  const [modalMode, setModalMode] = useState<ModalMode>(null)
  const [editingProject, setEditingProject] = useState<Project | null>(null)
  const [deletingProject, setDeletingProject] = useState<Project | null>(null)

  // Fetch projects on mount
  useEffect(() => {
    fetchProjects(token, applicationId)
  }, [token, applicationId, fetchProjects])

  // Handle search
  const handleSearch = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const query = e.target.value
      setSearchQuery(query)
      fetchProjects(token, applicationId, { search: query || undefined })
    },
    [token, applicationId, fetchProjects]
  )

  // Handle create project
  const handleCreate = useCallback(() => {
    clearError()
    setEditingProject(null)
    setModalMode('create')
  }, [clearError])

  // Handle edit project
  const handleEdit = useCallback(
    (project: Project) => {
      clearError()
      setEditingProject(project)
      setModalMode('edit')
    },
    [clearError]
  )

  // Handle delete project
  const handleDeleteClick = useCallback((project: Project) => {
    setDeletingProject(project)
  }, [])

  // Handle confirm delete
  const handleConfirmDelete = useCallback(async () => {
    if (!deletingProject) return

    const success = await deleteProject(token, deletingProject.id)
    if (success) {
      setDeletingProject(null)
    }
  }, [deletingProject, deleteProject, token])

  // Handle cancel delete
  const handleCancelDelete = useCallback(() => {
    setDeletingProject(null)
  }, [])

  // Handle close modal
  const handleCloseModal = useCallback(() => {
    setModalMode(null)
    setEditingProject(null)
  }, [])

  // Handle form submit
  const handleFormSubmit = useCallback(
    async (data: ProjectCreate | ProjectUpdate) => {
      if (modalMode === 'create') {
        const project = await createProject(token, applicationId, data as ProjectCreate)
        if (project) {
          handleCloseModal()
        }
      } else if (modalMode === 'edit' && editingProject) {
        const project = await updateProject(token, editingProject.id, data as ProjectUpdate)
        if (project) {
          handleCloseModal()
        }
      }
    },
    [modalMode, editingProject, createProject, updateProject, token, applicationId, handleCloseModal]
  )

  // Handle project click
  const handleProjectClick = useCallback(
    (project: Project) => {
      onSelectProject?.(project)
    },
    [onSelectProject]
  )

  // Filter projects based on search (API handles filtering, but keep for local filtering if needed)
  const filteredProjects = projects

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
          {applicationName ? `Back to ${applicationName}` : 'Back'}
        </button>
      )}

      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Projects</h1>
          <p className="mt-1 text-muted-foreground">
            {applicationName
              ? `Manage projects in ${applicationName}`
              : 'Manage your projects and tasks'}
          </p>
        </div>
        <button
          onClick={handleCreate}
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

      {/* Search Bar */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          type="text"
          value={searchQuery}
          onChange={handleSearch}
          placeholder="Search projects..."
          className={cn(
            'w-full rounded-md border border-input bg-background py-2 pl-10 pr-4 text-sm text-foreground placeholder:text-muted-foreground',
            'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background'
          )}
        />
        {searchQuery && (
          <button
            onClick={() => {
              setSearchQuery('')
              fetchProjects(token, applicationId)
            }}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Error Display */}
      {error && !modalMode && (
        <div className="flex items-center gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          <AlertCircle className="h-4 w-4 flex-shrink-0" />
          <span>{error.message}</span>
          <button
            onClick={clearError}
            className="ml-auto text-destructive hover:text-destructive/80"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Loading State */}
      {isLoading && projects.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="mt-4 text-muted-foreground">Loading projects...</p>
        </div>
      )}

      {/* Empty State */}
      {!isLoading && projects.length === 0 && (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border py-12">
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-primary/10">
            <LayoutDashboard className="h-8 w-8 text-primary" />
          </div>
          <h3 className="mt-4 text-lg font-semibold text-foreground">
            {searchQuery ? 'No projects found' : 'No projects yet'}
          </h3>
          <p className="mt-2 text-center text-muted-foreground">
            {searchQuery
              ? `No projects match "${searchQuery}"`
              : 'Create your first project to start organizing your tasks.'}
          </p>
          {!searchQuery && (
            <button
              onClick={handleCreate}
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
      {!isLoading && projects.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filteredProjects.map((project) => (
            <ProjectCard
              key={project.id}
              project={project}
              onClick={onSelectProject ? handleProjectClick : undefined}
              onEdit={handleEdit}
              onDelete={handleDeleteClick}
              disabled={isDeleting}
            />
          ))}
        </div>
      )}

      {/* Loading More Indicator */}
      {isLoading && projects.length > 0 && (
        <div className="flex justify-center py-4">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </div>
      )}

      {/* Create/Edit Modal */}
      {modalMode && (
        <Modal onClose={handleCloseModal}>
          <ProjectForm
            project={editingProject}
            isSubmitting={modalMode === 'create' ? isCreating : isUpdating}
            error={error?.message}
            onSubmit={handleFormSubmit}
            onCancel={handleCloseModal}
          />
        </Modal>
      )}

      {/* Delete Confirmation Dialog */}
      {deletingProject && (
        <DeleteConfirmDialog
          project={deletingProject}
          isDeleting={isDeleting}
          onConfirm={handleConfirmDelete}
          onCancel={handleCancelDelete}
        />
      )}
    </div>
  )
}

export default ProjectsPage
