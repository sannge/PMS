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
  AlertCircle,
  X,
  ArrowLeft,
} from 'lucide-react'
import { SkeletonRowCardList, ProgressBar, PulseIndicator } from '@/components/ui/skeleton'

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
  const [fetchedAppId, setFetchedAppId] = useState<string | null>(null)

  // Show skeleton: either loading OR we haven't fetched for this app yet
  const showSkeleton = isLoading || fetchedAppId !== applicationId

  // Fetch projects on mount or when applicationId changes
  useEffect(() => {
    setFetchedAppId(null) // Reset to show skeleton immediately
    fetchProjects(token, applicationId).then(() => {
      setFetchedAppId(applicationId)
    })
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
    <div className="space-y-4">
      {/* Compact Header */}
      <div className="flex items-center justify-between gap-3 pb-3 border-b border-border">
        <div className="flex items-center gap-3 flex-1">
          {/* Back button */}
          {onBack && (
            <button
              onClick={onBack}
              className={cn(
                'flex items-center justify-center h-7 w-7 rounded-md',
                'text-muted-foreground hover:text-foreground hover:bg-muted',
                'transition-colors'
              )}
              title={applicationName ? `Back to ${applicationName}` : 'Back'}
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
          )}
          <h1 className="text-sm font-semibold text-foreground">Projects</h1>
          {applicationName && (
            <span className="text-xs text-muted-foreground">in {applicationName}</span>
          )}
          {/* Inline Search */}
          <div className="relative flex-1 max-w-xs">
            <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              value={searchQuery}
              onChange={handleSearch}
              placeholder="Search..."
              className={cn(
                'w-full rounded-md border border-input bg-background py-1.5 pl-8 pr-3 text-xs text-foreground placeholder:text-muted-foreground',
                'focus:outline-none focus:ring-1 focus:ring-ring'
              )}
            />
            {searchQuery && (
              <button
                onClick={() => {
                  setSearchQuery('')
                  fetchProjects(token, applicationId)
                }}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <X className="h-3 w-3" />
              </button>
            )}
          </div>
          {/* Inline operation indicator */}
          {(isCreating || isUpdating || isDeleting) && (
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <PulseIndicator color="primary" />
              <span>{isCreating ? 'Creating' : isUpdating ? 'Saving' : 'Deleting'}...</span>
            </span>
          )}
        </div>
        <button
          onClick={handleCreate}
          className={cn(
            'inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground',
            'hover:bg-primary/90 transition-colors'
          )}
        >
          <Plus className="h-3.5 w-3.5" />
          New
        </button>
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

      {/* Loading State - Skeleton */}
      {showSkeleton && (
        <SkeletonRowCardList count={6} />
      )}

      {/* Empty State: only show when done loading and truly empty */}
      {!showSkeleton && projects.length === 0 && (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border py-8">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
            <LayoutDashboard className="h-5 w-5 text-primary" />
          </div>
          <h3 className="mt-3 text-sm font-medium text-foreground">
            {searchQuery ? 'No projects found' : 'No projects yet'}
          </h3>
          <p className="mt-1 text-xs text-center text-muted-foreground max-w-[200px]">
            {searchQuery
              ? `No matches for "${searchQuery}"`
              : 'Get started by creating your first project.'}
          </p>
          {!searchQuery && (
            <button
              onClick={handleCreate}
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

      {/* Projects List: only show when done loading */}
      {!showSkeleton && projects.length > 0 && (
        <div className="space-y-2">
          {filteredProjects.map((project, index) => (
            <ProjectCard
              key={project.id}
              project={project}
              onClick={onSelectProject ? handleProjectClick : undefined}
              onEdit={handleEdit}
              onDelete={handleDeleteClick}
              disabled={isDeleting}
              index={index}
            />
          ))}
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
