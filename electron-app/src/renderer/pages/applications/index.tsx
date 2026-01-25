/**
 * Applications List Page
 *
 * Displays a list of all applications with search, create, edit, and delete functionality.
 * Uses TanStack Query for data fetching with stale-while-revalidate pattern.
 *
 * Features:
 * - Application list with cards
 * - Search filtering (client-side)
 * - Create new application modal
 * - Edit application modal
 * - Delete confirmation dialog
 * - Empty state
 * - Loading state with skeleton
 * - Instant page loads from cache
 */

import { useState, useCallback, useEffect, useMemo } from 'react'
import { cn } from '@/lib/utils'
import {
  useApplications,
  useCreateApplication,
  useUpdateApplication,
  useDeleteApplication,
  type Application,
  type ApplicationCreate,
  type ApplicationUpdate,
} from '@/hooks/use-queries'
import { ApplicationCard } from '@/components/applications/application-card'
import { ApplicationForm } from '@/components/applications/application-form'
import {
  FolderKanban,
  Plus,
  Search,
  AlertCircle,
  X,
  Loader2,
} from 'lucide-react'
import { SkeletonRowCardList, ProgressBar, PulseIndicator } from '@/components/ui/skeleton'

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
  // TanStack Query hooks
  const {
    data: applications = [],
    isLoading,
    isFetching,
    error: queryError,
  } = useApplications()

  const createMutation = useCreateApplication()
  const [editingAppId, setEditingAppId] = useState<string | null>(null)
  const updateMutation = useUpdateApplication(editingAppId || '')
  const [deletingAppId, setDeletingAppId] = useState<string | null>(null)
  const deleteMutation = useDeleteApplication(deletingAppId || '')

  // Local state
  const [searchQuery, setSearchQuery] = useState('')
  const [modalMode, setModalMode] = useState<ModalMode>(null)
  const [editingApplication, setEditingApplication] = useState<Application | null>(null)
  const [deletingApplication, setDeletingApplication] = useState<Application | null>(null)
  const [mutationError, setMutationError] = useState<string | null>(null)

  // Derive loading states
  const isCreating = createMutation.isPending
  const isUpdating = updateMutation.isPending
  const isDeleting = deleteMutation.isPending

  // Show loading skeleton only on first load (no cached data)
  const showLoading = isLoading && applications.length === 0

  // Filter applications based on search (client-side)
  const filteredApplications = useMemo(() => {
    if (!searchQuery.trim()) return applications
    const query = searchQuery.toLowerCase()
    return applications.filter(
      (app) =>
        app.name.toLowerCase().includes(query) ||
        app.description?.toLowerCase().includes(query)
    )
  }, [applications, searchQuery])

  // Clear mutation error when modal closes
  useEffect(() => {
    if (!modalMode) {
      setMutationError(null)
    }
  }, [modalMode])

  // Handle search
  const handleSearch = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchQuery(e.target.value)
  }, [])

  // Handle create application
  const handleCreate = useCallback(() => {
    setMutationError(null)
    setEditingApplication(null)
    setModalMode('create')
  }, [])

  // Handle edit application
  const handleEdit = useCallback((application: Application) => {
    setMutationError(null)
    setEditingApplication(application)
    setEditingAppId(application.id)
    setModalMode('edit')
  }, [])

  // Handle delete application
  const handleDeleteClick = useCallback((application: Application) => {
    setDeletingApplication(application)
    setDeletingAppId(application.id)
  }, [])

  // Handle confirm delete
  const handleConfirmDelete = useCallback(async () => {
    if (!deletingApplication) return

    try {
      await deleteMutation.mutateAsync()
      setDeletingApplication(null)
      setDeletingAppId(null)
    } catch (err) {
      // Error is handled by mutation state
    }
  }, [deletingApplication, deleteMutation])

  // Handle cancel delete
  const handleCancelDelete = useCallback(() => {
    setDeletingApplication(null)
    setDeletingAppId(null)
  }, [])

  // Handle close modal
  const handleCloseModal = useCallback(() => {
    setModalMode(null)
    setEditingApplication(null)
    setEditingAppId(null)
  }, [])

  // Handle form submit
  const handleFormSubmit = useCallback(
    async (data: ApplicationCreate | ApplicationUpdate) => {
      try {
        if (modalMode === 'create') {
          await createMutation.mutateAsync(data as ApplicationCreate)
          handleCloseModal()
        } else if (modalMode === 'edit' && editingApplication) {
          await updateMutation.mutateAsync(data as ApplicationUpdate)
          handleCloseModal()
        }
      } catch (err) {
        setMutationError(err instanceof Error ? err.message : 'An error occurred')
      }
    },
    [modalMode, editingApplication, createMutation, updateMutation, handleCloseModal]
  )

  // Handle application click
  const handleApplicationClick = useCallback(
    (application: Application) => {
      onSelectApplication?.(application)
    },
    [onSelectApplication]
  )

  // Clear error handler
  const clearError = useCallback(() => {
    setMutationError(null)
  }, [])

  // Combine errors
  const error = mutationError || (queryError ? queryError.message : null)

  return (
    <div className="space-y-4">
      {/* Compact Header */}
      <div className="flex items-center justify-between gap-3 pb-3 border-b border-border">
        <div className="flex items-center gap-3 flex-1">
          <h1 className="text-sm font-semibold text-foreground">Applications</h1>
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
                onClick={() => setSearchQuery('')}
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
          <span>{error}</span>
          <button
            onClick={clearError}
            className="ml-auto text-destructive hover:text-destructive/80"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Loading State - Skeleton */}
      {showLoading && (
        <SkeletonRowCardList count={6} />
      )}

      {/* Empty State */}
      {!showLoading && applications.length === 0 && (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border py-8">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
            <FolderKanban className="h-5 w-5 text-primary" />
          </div>
          <h3 className="mt-3 text-sm font-medium text-foreground">
            {searchQuery ? 'No applications found' : 'No applications yet'}
          </h3>
          <p className="mt-1 text-xs text-center text-muted-foreground max-w-[200px]">
            {searchQuery
              ? `No matches for "${searchQuery}"`
              : 'Get started by creating your first application.'}
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
              Create Application
            </button>
          )}
        </div>
      )}

      {/* Subtle loading progress bar when refreshing in background */}
      <ProgressBar isActive={isFetching && applications.length > 0} />

      {/* Applications List */}
      {filteredApplications.length > 0 && (
        <div className="space-y-2">
          {filteredApplications.map((application, index) => (
            <ApplicationCard
              key={application.id}
              application={application}
              onClick={onSelectApplication ? handleApplicationClick : undefined}
              onEdit={handleEdit}
              onDelete={handleDeleteClick}
              disabled={isDeleting || isLoading}
              index={index}
            />
          ))}
        </div>
      )}

      {/* Empty search results */}
      {!showLoading && applications.length > 0 && filteredApplications.length === 0 && searchQuery && (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border py-8">
          <Search className="h-8 w-8 text-muted-foreground/50" />
          <h3 className="mt-3 text-sm font-medium text-foreground">
            No matches found
          </h3>
          <p className="mt-1 text-xs text-center text-muted-foreground max-w-[200px]">
            No applications match "{searchQuery}"
          </p>
          <button
            onClick={() => setSearchQuery('')}
            className="mt-3 text-xs text-primary hover:underline"
          >
            Clear search
          </button>
        </div>
      )}

      {/* Create/Edit Modal */}
      {modalMode && (
        <Modal onClose={handleCloseModal}>
          <ApplicationForm
            application={editingApplication}
            isSubmitting={modalMode === 'create' ? isCreating : isUpdating}
            error={mutationError || undefined}
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
