/**
 * Applications List Page
 *
 * Displays a list of all applications with search, create, edit, and delete functionality.
 *
 * Features:
 * - Application list with cards
 * - Search filtering
 * - Create new application modal
 * - Edit application modal
 * - Delete confirmation dialog
 * - Empty state
 * - Loading state
 */

import { useState, useCallback, useEffect } from 'react'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth-store'
import {
  useApplicationsStore,
  type Application,
  type ApplicationCreate,
  type ApplicationUpdate,
} from '@/stores/applications-store'
import { ApplicationCard } from '@/components/applications/application-card'
import { ApplicationForm } from '@/components/applications/application-form'
import {
  FolderKanban,
  Plus,
  Search,
  Loader2,
  AlertCircle,
  X,
} from 'lucide-react'

// ============================================================================
// Types
// ============================================================================

export interface ApplicationsPageProps {
  /**
   * Callback when an application is selected
   */
  onSelectApplication?: (application: Application) => void
}

type ModalMode = 'create' | 'edit' | null

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

export function ApplicationsPage({
  onSelectApplication,
}: ApplicationsPageProps): JSX.Element {
  // Auth state
  const token = useAuthStore((state) => state.token)

  // Applications state
  const {
    applications,
    isLoading,
    isCreating,
    isUpdating,
    isDeleting,
    error,
    fetchApplications,
    createApplication,
    updateApplication,
    deleteApplication,
    clearError,
  } = useApplicationsStore()

  // Local state
  const [searchQuery, setSearchQuery] = useState('')
  const [modalMode, setModalMode] = useState<ModalMode>(null)
  const [editingApplication, setEditingApplication] = useState<Application | null>(null)
  const [deletingApplication, setDeletingApplication] = useState<Application | null>(null)

  // Fetch applications on mount
  useEffect(() => {
    fetchApplications(token)
  }, [token, fetchApplications])

  // Handle search
  const handleSearch = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const query = e.target.value
      setSearchQuery(query)
      // Debounce search would be better, but for simplicity we'll search on every change
      fetchApplications(token, { search: query || undefined })
    },
    [token, fetchApplications]
  )

  // Handle create application
  const handleCreate = useCallback(() => {
    clearError()
    setEditingApplication(null)
    setModalMode('create')
  }, [clearError])

  // Handle edit application
  const handleEdit = useCallback(
    (application: Application) => {
      clearError()
      setEditingApplication(application)
      setModalMode('edit')
    },
    [clearError]
  )

  // Handle delete application
  const handleDeleteClick = useCallback((application: Application) => {
    setDeletingApplication(application)
  }, [])

  // Handle confirm delete
  const handleConfirmDelete = useCallback(async () => {
    if (!deletingApplication) return

    const success = await deleteApplication(token, deletingApplication.id)
    if (success) {
      setDeletingApplication(null)
    }
  }, [deletingApplication, deleteApplication, token])

  // Handle cancel delete
  const handleCancelDelete = useCallback(() => {
    setDeletingApplication(null)
  }, [])

  // Handle close modal
  const handleCloseModal = useCallback(() => {
    setModalMode(null)
    setEditingApplication(null)
  }, [])

  // Handle form submit
  const handleFormSubmit = useCallback(
    async (data: ApplicationCreate | ApplicationUpdate) => {
      if (modalMode === 'create') {
        const application = await createApplication(token, data as ApplicationCreate)
        if (application) {
          handleCloseModal()
        }
      } else if (modalMode === 'edit' && editingApplication) {
        const application = await updateApplication(token, editingApplication.id, data as ApplicationUpdate)
        if (application) {
          handleCloseModal()
        }
      }
    },
    [modalMode, editingApplication, createApplication, updateApplication, token, handleCloseModal]
  )

  // Handle application click
  const handleApplicationClick = useCallback(
    (application: Application) => {
      onSelectApplication?.(application)
    },
    [onSelectApplication]
  )

  // Filter applications based on search
  const filteredApplications = applications

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Applications</h1>
          <p className="mt-1 text-muted-foreground">
            Manage your application portfolios and projects
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
          New Application
        </button>
      </div>

      {/* Search Bar */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          type="text"
          value={searchQuery}
          onChange={handleSearch}
          placeholder="Search applications..."
          className={cn(
            'w-full rounded-md border border-input bg-background py-2 pl-10 pr-4 text-sm text-foreground placeholder:text-muted-foreground',
            'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background'
          )}
        />
        {searchQuery && (
          <button
            onClick={() => {
              setSearchQuery('')
              fetchApplications(token)
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
      {isLoading && applications.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="mt-4 text-muted-foreground">Loading applications...</p>
        </div>
      )}

      {/* Empty State */}
      {!isLoading && applications.length === 0 && (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border py-12">
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-primary/10">
            <FolderKanban className="h-8 w-8 text-primary" />
          </div>
          <h3 className="mt-4 text-lg font-semibold text-foreground">
            {searchQuery ? 'No applications found' : 'No applications yet'}
          </h3>
          <p className="mt-2 text-center text-muted-foreground">
            {searchQuery
              ? `No applications match "${searchQuery}"`
              : 'Create your first application to get started organizing your projects.'}
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
              Create Application
            </button>
          )}
        </div>
      )}

      {/* Applications Grid */}
      {!isLoading && applications.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filteredApplications.map((application) => (
            <ApplicationCard
              key={application.id}
              application={application}
              onClick={onSelectApplication ? handleApplicationClick : undefined}
              onEdit={handleEdit}
              onDelete={handleDeleteClick}
              disabled={isDeleting}
            />
          ))}
        </div>
      )}

      {/* Loading More Indicator */}
      {isLoading && applications.length > 0 && (
        <div className="flex justify-center py-4">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </div>
      )}

      {/* Create/Edit Modal */}
      {modalMode && (
        <Modal onClose={handleCloseModal}>
          <ApplicationForm
            application={editingApplication}
            isSubmitting={modalMode === 'create' ? isCreating : isUpdating}
            error={error?.message}
            onSubmit={handleFormSubmit}
            onCancel={handleCloseModal}
          />
        </Modal>
      )}

      {/* Delete Confirmation Dialog */}
      {deletingApplication && (
        <DeleteConfirmDialog
          application={deletingApplication}
          isDeleting={isDeleting}
          onConfirm={handleConfirmDelete}
          onCancel={handleCancelDelete}
        />
      )}
    </div>
  )
}

export default ApplicationsPage
