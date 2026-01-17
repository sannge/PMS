/**
 * Notes Page
 *
 * Main notes management page with OneNote-style interface.
 *
 * Features:
 * - Application selector for note context
 * - Hierarchical note tree sidebar
 * - Multi-tab interface for open notes
 * - Note content area (placeholder for rich editor)
 * - Create/edit/delete note functionality
 * - Note form modal
 */

import { useState, useCallback, useEffect } from 'react'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth-store'
import {
  useNotesStore,
  type Note,
  type NoteTree,
  type NoteCreate,
  type NoteUpdate,
} from '@/stores/notes-store'
import {
  useApplicationsStore,
  type Application,
} from '@/stores/applications-store'
import { NotesSidebar } from '@/components/notes/notes-sidebar'
import { NotesTabBar } from '@/components/notes/notes-tab-bar'
import {
  StickyNote,
  FolderKanban,
  ChevronDown,
  X,
  Loader2,
  AlertCircle,
  Check,
  FileText,
} from 'lucide-react'

// ============================================================================
// Types
// ============================================================================

export interface NotesPageProps {
  /**
   * Pre-selected application ID (optional)
   */
  applicationId?: string | null
  /**
   * Callback when navigating back
   */
  onBack?: () => void
}

type ModalMode = 'create' | 'edit' | null

// ============================================================================
// Note Form Modal Component
// ============================================================================

interface NoteFormProps {
  mode: 'create' | 'edit'
  note?: Note | null
  parentId?: string | null
  isSubmitting: boolean
  error?: string | null
  onSubmit: (data: NoteCreate | NoteUpdate) => void
  onCancel: () => void
}

function NoteFormModal({
  mode,
  note,
  parentId,
  isSubmitting,
  error,
  onSubmit,
  onCancel,
}: NoteFormProps): JSX.Element {
  const [title, setTitle] = useState(note?.title || '')
  const [titleError, setTitleError] = useState<string | null>(null)

  // Validate and submit
  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault()

      // Validate
      if (!title.trim()) {
        setTitleError('Title is required')
        return
      }

      if (title.length > 255) {
        setTitleError('Title must be less than 255 characters')
        return
      }

      setTitleError(null)

      if (mode === 'create') {
        const data: NoteCreate = {
          title: title.trim(),
          parent_id: parentId,
        }
        onSubmit(data)
      } else {
        const data: NoteUpdate = {
          title: title.trim(),
        }
        onSubmit(data)
      }
    },
    [title, mode, parentId, onSubmit]
  )

  // Close on escape
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onCancel()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onCancel])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-lg border border-border bg-card p-6 shadow-lg">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-foreground">
            {mode === 'create' ? 'Create New Note' : 'Rename Note'}
          </h3>
          <button
            onClick={onCancel}
            className="text-muted-foreground hover:text-foreground"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Title Field */}
          <div>
            <label
              htmlFor="note-title"
              className="block text-sm font-medium text-foreground mb-1"
            >
              Title
            </label>
            <input
              id="note-title"
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Enter note title..."
              autoFocus
              className={cn(
                'w-full rounded-md border bg-background px-3 py-2 text-foreground',
                'placeholder:text-muted-foreground',
                'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
                titleError ? 'border-destructive' : 'border-input'
              )}
            />
            {titleError && (
              <p className="mt-1 text-sm text-destructive">{titleError}</p>
            )}
          </div>

          {/* Error Display */}
          {error && (
            <div className="flex items-center gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
              <AlertCircle className="h-4 w-4 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onCancel}
              disabled={isSubmitting}
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
              type="submit"
              disabled={isSubmitting}
              className={cn(
                'rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground',
                'hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
                'disabled:cursor-not-allowed disabled:opacity-50',
                'transition-colors duration-200'
              )}
            >
              {isSubmitting ? (
                <span className="flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {mode === 'create' ? 'Creating...' : 'Saving...'}
                </span>
              ) : mode === 'create' ? (
                'Create Note'
              ) : (
                'Save'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ============================================================================
// Delete Confirmation Dialog Component
// ============================================================================

interface DeleteDialogProps {
  note: Note | NoteTree
  isDeleting: boolean
  onConfirm: () => void
  onCancel: () => void
}

function DeleteConfirmDialog({
  note,
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
              Delete Note
            </h3>
            <p className="mt-2 text-sm text-muted-foreground">
              Are you sure you want to delete <strong>{note.title}</strong>?
              {('children_count' in note && note.children_count && note.children_count > 0) ||
              ('children' in note && note.children && note.children.length > 0) ? (
                <span className="block mt-1 text-destructive">
                  This will also delete all child notes.
                </span>
              ) : null}
              <span className="block mt-1">This action cannot be undone.</span>
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
// Application Selector Component
// ============================================================================

interface ApplicationSelectorProps {
  applications: Application[]
  selectedApplication: Application | null
  isLoading: boolean
  onSelect: (application: Application) => void
}

function ApplicationSelector({
  applications,
  selectedApplication,
  isLoading,
  onSelect,
}: ApplicationSelectorProps): JSX.Element {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          'flex items-center gap-2 rounded-md border border-input bg-background px-3 py-2 text-sm',
          'hover:bg-accent hover:text-accent-foreground',
          'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
          'min-w-[200px]'
        )}
      >
        <FolderKanban className="h-4 w-4 text-muted-foreground" />
        <span className="flex-1 text-left truncate">
          {selectedApplication ? selectedApplication.name : 'Select Application'}
        </span>
        <ChevronDown
          className={cn(
            'h-4 w-4 text-muted-foreground transition-transform',
            isOpen && 'rotate-180'
          )}
        />
      </button>

      {isOpen && (
        <>
          <div
            className="fixed inset-0 z-40"
            onClick={() => setIsOpen(false)}
          />
          <div className="absolute top-full left-0 z-50 mt-1 w-full min-w-[200px] rounded-md border border-border bg-popover p-1 shadow-md">
            {isLoading ? (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : applications.length === 0 ? (
              <div className="py-4 text-center text-sm text-muted-foreground">
                No applications found
              </div>
            ) : (
              <div className="max-h-[300px] overflow-auto">
                {applications.map((app) => (
                  <button
                    key={app.id}
                    onClick={() => {
                      onSelect(app)
                      setIsOpen(false)
                    }}
                    className={cn(
                      'flex w-full items-center gap-2 rounded-sm px-2 py-2 text-sm',
                      'hover:bg-accent hover:text-accent-foreground',
                      selectedApplication?.id === app.id && 'bg-accent'
                    )}
                  >
                    <FolderKanban className="h-4 w-4 text-muted-foreground" />
                    <span className="flex-1 text-left truncate">{app.name}</span>
                    {selectedApplication?.id === app.id && (
                      <Check className="h-4 w-4 text-primary" />
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

// ============================================================================
// Note Content Placeholder Component
// ============================================================================

interface NoteContentProps {
  note: Note | null
  content: string | null
  isDirty: boolean
  onContentChange?: (content: string) => void
}

function NoteContentPlaceholder({
  note,
  content,
  isDirty,
}: NoteContentProps): JSX.Element {
  if (!note) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center text-muted-foreground">
        <FileText className="h-16 w-16 opacity-50" />
        <h3 className="mt-4 text-lg font-medium text-foreground">No Note Selected</h3>
        <p className="mt-1 text-sm">Select a note from the sidebar to view its content</p>
      </div>
    )
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* Note Header */}
      <div className="border-b border-border px-6 py-4">
        <div className="flex items-center gap-2">
          <h2 className="text-xl font-semibold text-foreground">{note.title}</h2>
          {isDirty && (
            <span className="text-xs text-muted-foreground">(unsaved changes)</span>
          )}
        </div>
        <p className="mt-1 text-sm text-muted-foreground">
          Last updated: {new Date(note.updated_at).toLocaleString()}
        </p>
      </div>

      {/* Note Content - Placeholder for rich text editor */}
      <div className="flex-1 overflow-auto p-6">
        <div className="mx-auto max-w-3xl">
          <div className="rounded-lg border border-dashed border-border p-8 text-center">
            <StickyNote className="mx-auto h-12 w-12 text-muted-foreground opacity-50" />
            <h3 className="mt-4 text-lg font-medium text-foreground">
              Rich Text Editor Coming Soon
            </h3>
            <p className="mt-2 text-sm text-muted-foreground">
              The note editor will be implemented in the next phase.
            </p>
            {content && (
              <div className="mt-4 rounded-md bg-muted/50 p-4 text-left">
                <p className="text-xs font-medium text-muted-foreground mb-2">
                  Current content preview:
                </p>
                <pre className="text-sm text-foreground whitespace-pre-wrap overflow-auto max-h-[200px]">
                  {content}
                </pre>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// ============================================================================
// Notes Page Component
// ============================================================================

export function NotesPage({
  applicationId: initialAppId,
}: NotesPageProps): JSX.Element {
  // Auth state
  const token = useAuthStore((state) => state.token)

  // Applications state
  const {
    applications,
    isLoading: isLoadingApps,
    fetchApplications,
  } = useApplicationsStore()

  // Notes state
  const {
    noteTree,
    openTabs,
    activeTabId,
    selectedNote,
    isLoading: isLoadingNotes,
    isCreating,
    isUpdating,
    isDeleting,
    error,
    currentApplicationId,
    fetchNoteTree,
    createNote,
    updateNote,
    deleteNote,
    openTab,
    closeTab,
    setActiveTab,
    closeAllTabs,
    closeOtherTabs,
    clearError,
  } = useNotesStore()

  // Local state
  const [selectedApplication, setSelectedApplication] = useState<Application | null>(null)
  const [modalMode, setModalMode] = useState<ModalMode>(null)
  const [editingNote, setEditingNote] = useState<Note | NoteTree | null>(null)
  const [deletingNote, setDeletingNote] = useState<Note | NoteTree | null>(null)
  const [parentIdForCreate, setParentIdForCreate] = useState<string | null>(null)

  // Fetch applications on mount
  useEffect(() => {
    fetchApplications(token)
  }, [token, fetchApplications])

  // Set initial application if provided
  useEffect(() => {
    if (initialAppId && applications.length > 0) {
      const app = applications.find((a) => a.id === initialAppId)
      if (app) {
        setSelectedApplication(app)
      }
    }
  }, [initialAppId, applications])

  // Fetch notes when application changes
  useEffect(() => {
    if (selectedApplication) {
      fetchNoteTree(token, selectedApplication.id)
    }
  }, [token, selectedApplication, fetchNoteTree])

  // Handle application selection
  const handleSelectApplication = useCallback((app: Application) => {
    setSelectedApplication(app)
    closeAllTabs()
  }, [closeAllTabs])

  // Handle note selection from sidebar
  const handleSelectNote = useCallback(
    (note: NoteTree) => {
      openTab(note as Note)
    },
    [openTab]
  )

  // Handle create note
  const handleCreateNote = useCallback((parentId?: string | null) => {
    clearError()
    setEditingNote(null)
    setParentIdForCreate(parentId || null)
    setModalMode('create')
  }, [clearError])

  // Handle edit note
  const handleEditNote = useCallback(
    (note: NoteTree) => {
      clearError()
      setEditingNote(note)
      setModalMode('edit')
    },
    [clearError]
  )

  // Handle delete note click
  const handleDeleteClick = useCallback((note: NoteTree) => {
    setDeletingNote(note)
  }, [])

  // Handle confirm delete
  const handleConfirmDelete = useCallback(async () => {
    if (!deletingNote) return

    const hasChildren =
      ('children_count' in deletingNote && deletingNote.children_count && deletingNote.children_count > 0) ||
      ('children' in deletingNote && deletingNote.children && deletingNote.children.length > 0)

    const success = await deleteNote(token, deletingNote.id, hasChildren)
    if (success) {
      setDeletingNote(null)
    }
  }, [deletingNote, deleteNote, token])

  // Handle cancel delete
  const handleCancelDelete = useCallback(() => {
    setDeletingNote(null)
  }, [])

  // Handle close modal
  const handleCloseModal = useCallback(() => {
    setModalMode(null)
    setEditingNote(null)
    setParentIdForCreate(null)
  }, [])

  // Handle form submit
  const handleFormSubmit = useCallback(
    async (data: NoteCreate | NoteUpdate) => {
      if (!selectedApplication) return

      if (modalMode === 'create') {
        const note = await createNote(token, selectedApplication.id, data as NoteCreate)
        if (note) {
          handleCloseModal()
          openTab(note)
        }
      } else if (modalMode === 'edit' && editingNote) {
        const note = await updateNote(token, editingNote.id, data as NoteUpdate)
        if (note) {
          handleCloseModal()
        }
      }
    },
    [
      modalMode,
      editingNote,
      selectedApplication,
      createNote,
      updateNote,
      token,
      handleCloseModal,
      openTab,
    ]
  )

  // Get active tab content
  const activeTab = openTabs.find((tab) => tab.id === activeTabId)
  const activeNote = selectedNote?.id === activeTabId ? selectedNote : null

  return (
    <div className="flex h-full flex-col bg-background">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <StickyNote className="h-5 w-5 text-primary" />
            <h1 className="text-lg font-semibold text-foreground">Notes</h1>
          </div>

          {/* Application Selector */}
          <ApplicationSelector
            applications={applications}
            selectedApplication={selectedApplication}
            isLoading={isLoadingApps}
            onSelect={handleSelectApplication}
          />
        </div>

        {/* Error Display */}
        {error && (
          <div className="flex items-center gap-2 rounded-md border border-destructive/50 bg-destructive/10 px-3 py-1.5 text-sm text-destructive">
            <AlertCircle className="h-4 w-4" />
            <span>{error.message}</span>
            <button onClick={clearError} className="ml-1 hover:text-destructive/80">
              <X className="h-4 w-4" />
            </button>
          </div>
        )}
      </div>

      {/* No Application Selected */}
      {!selectedApplication ? (
        <div className="flex flex-1 flex-col items-center justify-center text-muted-foreground">
          <FolderKanban className="h-16 w-16 opacity-50" />
          <h2 className="mt-4 text-xl font-semibold text-foreground">
            Select an Application
          </h2>
          <p className="mt-2 text-center">
            Choose an application from the dropdown above to view and manage its notes.
          </p>
        </div>
      ) : (
        <div className="flex flex-1 overflow-hidden">
          {/* Notes Sidebar */}
          <NotesSidebar
            noteTree={noteTree}
            activeNoteId={activeTabId}
            isLoading={isLoadingNotes}
            onSelectNote={handleSelectNote}
            onCreateNote={handleCreateNote}
            onEditNote={handleEditNote}
            onDeleteNote={handleDeleteClick}
            className="w-64 flex-shrink-0 border-r border-border"
          />

          {/* Main Content Area */}
          <div className="flex flex-1 flex-col overflow-hidden">
            {/* Tab Bar */}
            <NotesTabBar
              tabs={openTabs}
              activeTabId={activeTabId}
              onSelectTab={setActiveTab}
              onCloseTab={closeTab}
              onCloseAllTabs={closeAllTabs}
              onCloseOtherTabs={closeOtherTabs}
            />

            {/* Note Content */}
            <NoteContentPlaceholder
              note={activeNote}
              content={activeTab?.content || null}
              isDirty={activeTab?.isDirty || false}
            />
          </div>
        </div>
      )}

      {/* Create/Edit Modal */}
      {modalMode && (
        <NoteFormModal
          mode={modalMode}
          note={editingNote as Note}
          parentId={parentIdForCreate}
          isSubmitting={modalMode === 'create' ? isCreating : isUpdating}
          error={error?.message}
          onSubmit={handleFormSubmit}
          onCancel={handleCloseModal}
        />
      )}

      {/* Delete Confirmation Dialog */}
      {deletingNote && (
        <DeleteConfirmDialog
          note={deletingNote}
          isDeleting={isDeleting}
          onConfirm={handleConfirmDelete}
          onCancel={handleCancelDelete}
        />
      )}
    </div>
  )
}

export default NotesPage
