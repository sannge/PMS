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

import { useState, useCallback, useEffect, useRef, useMemo } from 'react'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth-store'
import {
  useNotesStore,
  type Note,
  type NoteTree,
  type NoteCreate,
  type NoteUpdate,
} from '@/stores/notes-store'
import { useApplications, type Application } from '@/hooks/use-queries'
import { NotesSidebar } from '@/components/notes/notes-sidebar'
import { NotesTabBar } from '@/components/notes/notes-tab-bar'
import {
  StickyNote,
  FolderKanban,
  X,
  AlertCircle,
  Check,
  FileText,
  Search,
  Layers,
  Clock,
  ChevronRight,
  Loader2,
} from 'lucide-react'
import { Skeleton, PulseIndicator } from '@/components/ui/skeleton'

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
// Application Selector Component - Command Palette Style
// ============================================================================

interface ApplicationSelectorProps {
  applications: Application[]
  selectedApplication: Application | null
  isLoading: boolean
  onSelect: (application: Application) => void
}

function formatRelativeTime(dateString: string): string {
  // Handle UTC timestamps properly
  let dateStr = dateString
  if (!dateStr.endsWith('Z') && !dateStr.includes('+') && !dateStr.includes('-', 10)) {
    dateStr = dateStr + 'Z'
  }

  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()

  // Handle future dates or very recent (within margin of error)
  if (diffMs < 0 || diffMs < 60000) return 'Just now'

  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

  if (diffDays === 0) {
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60))
    if (diffHours === 0) {
      const diffMinutes = Math.floor(diffMs / (1000 * 60))
      return `${diffMinutes}m ago`
    }
    return `${diffHours}h ago`
  }
  if (diffDays === 1) return 'Yesterday'
  if (diffDays < 7) return `${diffDays}d ago`
  if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function ApplicationSelector({
  applications,
  selectedApplication,
  isLoading,
  onSelect,
}: ApplicationSelectorProps): JSX.Element {
  const [isOpen, setIsOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  // Filter applications by search
  const filteredApps = useMemo(() => {
    if (!searchQuery.trim()) return applications
    const query = searchQuery.toLowerCase()
    return applications.filter(
      (app) =>
        app.name.toLowerCase().includes(query) ||
        app.description?.toLowerCase().includes(query)
    )
  }, [applications, searchQuery])

  // Focus input when opened
  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus()
    }
  }, [isOpen])

  // Handle keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        setIsOpen(false)
        setSearchQuery('')
      }
      // Cmd/Ctrl + K to open
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setIsOpen(true)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen])

  return (
    <>
      {/* Compact trigger button */}
      <button
        onClick={() => setIsOpen(true)}
        className={cn(
          'group flex items-center gap-2 rounded-md border border-border/60 bg-muted/30 px-2.5 py-1.5 text-xs',
          'hover:bg-muted/50 hover:border-border',
          'focus:outline-none focus:ring-1 focus:ring-ring',
          'transition-all duration-150'
        )}
      >
        <FolderKanban className="h-3.5 w-3.5 text-amber-500" />
        <span className="max-w-[160px] truncate text-foreground font-medium">
          {selectedApplication?.name || 'Select App'}
        </span>
        {selectedApplication && (
          <span className="text-muted-foreground/60">
            <Layers className="h-3 w-3 inline mr-0.5" />
            {selectedApplication.projects_count}
          </span>
        )}
        <span className="ml-1 rounded bg-muted px-1 py-0.5 text-[10px] text-muted-foreground font-mono">
          ⌘K
        </span>
      </button>

      {/* Command Palette Modal */}
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-background/60 backdrop-blur-sm"
            onClick={() => {
              setIsOpen(false)
              setSearchQuery('')
            }}
          />

          {/* Modal */}
          <div className={cn(
            'relative w-full max-w-md rounded-xl border border-border bg-card shadow-2xl',
            'animate-in fade-in-0 zoom-in-95 slide-in-from-top-2 duration-200'
          )}>
            {/* Search Input */}
            <div className="flex items-center gap-3 border-b border-border px-4 py-3">
              <Search className="h-4 w-4 text-muted-foreground" />
              <input
                ref={inputRef}
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search applications..."
                className={cn(
                  'flex-1 bg-transparent text-sm text-foreground outline-none',
                  'placeholder:text-muted-foreground'
                )}
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="text-muted-foreground hover:text-foreground"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>

            {/* Results */}
            <div className="max-h-[320px] overflow-auto p-2">
              {isLoading ? (
                <div className="space-y-2 p-2">
                  {[1, 2, 3].map((i) => (
                    <div key={i} className="flex items-center gap-3 p-2">
                      <Skeleton className="h-8 w-8 rounded-lg" />
                      <div className="flex-1 space-y-1.5">
                        <Skeleton className="h-3.5 w-32" />
                        <Skeleton className="h-2.5 w-24" />
                      </div>
                    </div>
                  ))}
                </div>
              ) : filteredApps.length === 0 ? (
                <div className="py-8 text-center text-sm text-muted-foreground">
                  {searchQuery ? 'No applications match your search' : 'No applications found'}
                </div>
              ) : (
                <div className="space-y-1">
                  {filteredApps.map((app) => (
                    <button
                      key={app.id}
                      onClick={() => {
                        onSelect(app)
                        setIsOpen(false)
                        setSearchQuery('')
                      }}
                      className={cn(
                        'group flex w-full items-start gap-3 rounded-lg p-2.5 text-left',
                        'hover:bg-accent/50 transition-colors',
                        selectedApplication?.id === app.id && 'bg-primary/5 ring-1 ring-primary/20'
                      )}
                    >
                      {/* App Icon */}
                      <div className={cn(
                        'flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg',
                        'bg-amber-500/10 text-amber-600 dark:text-amber-400'
                      )}>
                        <FolderKanban className="h-4 w-4" />
                      </div>

                      {/* App Info */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-sm text-foreground truncate">
                            {app.name}
                          </span>
                          {selectedApplication?.id === app.id && (
                            <Check className="h-3.5 w-3.5 text-primary flex-shrink-0" />
                          )}
                        </div>
                        {app.description && (
                          <p className="text-xs text-muted-foreground truncate mt-0.5">
                            {app.description}
                          </p>
                        )}
                        <div className="flex items-center gap-3 mt-1.5 text-[10px] text-muted-foreground/70">
                          <span className="flex items-center gap-1">
                            <Layers className="h-2.5 w-2.5" />
                            {app.projects_count} projects
                          </span>
                          <span className="flex items-center gap-1">
                            <Clock className="h-2.5 w-2.5" />
                            {formatRelativeTime(app.updated_at)}
                          </span>
                        </div>
                      </div>

                      {/* Arrow */}
                      <ChevronRight className={cn(
                        'h-4 w-4 text-muted-foreground/40 flex-shrink-0 mt-1',
                        'opacity-0 group-hover:opacity-100 transition-opacity'
                      )} />
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Footer hint */}
            <div className="border-t border-border px-4 py-2 text-[10px] text-muted-foreground flex items-center justify-between">
              <span>
                <kbd className="px-1 py-0.5 rounded bg-muted font-mono">↑↓</kbd> navigate
                <span className="mx-2">·</span>
                <kbd className="px-1 py-0.5 rounded bg-muted font-mono">↵</kbd> select
                <span className="mx-2">·</span>
                <kbd className="px-1 py-0.5 rounded bg-muted font-mono">esc</kbd> close
              </span>
              <span>{filteredApps.length} apps</span>
            </div>
          </div>
        </div>
      )}
    </>
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

  // Applications state - using TanStack Query
  const { data: applications = [], isLoading: isLoadingApps } = useApplications()

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
    currentApplicationId: _currentApplicationId,
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
    saveSession,
    restoreSession,
    restoreTabs,
  } = useNotesStore()

  // Local state
  const [selectedApplication, setSelectedApplication] = useState<Application | null>(null)
  const [modalMode, setModalMode] = useState<ModalMode>(null)
  const [editingNote, setEditingNote] = useState<Note | NoteTree | null>(null)
  const [deletingNote, setDeletingNote] = useState<Note | NoteTree | null>(null)
  const [parentIdForCreate, setParentIdForCreate] = useState<string | null>(null)
  const [sessionRestored, setSessionRestored] = useState(false)
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState<boolean>(() => {
    const saved = localStorage.getItem('pm-notes-sidebar-collapsed')
    return saved === 'true'
  })

  // Save sidebar collapsed state
  useEffect(() => {
    localStorage.setItem('pm-notes-sidebar-collapsed', String(isSidebarCollapsed))
  }, [isSidebarCollapsed])

  // Save session whenever tabs change
  useEffect(() => {
    if (selectedApplication && openTabs.length >= 0) {
      saveSession()
    }
  }, [openTabs, activeTabId, selectedApplication, saveSession])

  // Handle sidebar collapse change
  const handleSidebarCollapsedChange = useCallback((collapsed: boolean) => {
    setIsSidebarCollapsed(collapsed)
  }, [])

  // Note: Applications are auto-fetched by TanStack Query

  // Restore session or set initial application when applications are loaded
  useEffect(() => {
    if (applications.length === 0 || sessionRestored) return

    // Try to restore from saved session first
    const savedSession = restoreSession()

    if (savedSession?.applicationId && !initialAppId) {
      const app = applications.find((a) => a.id === savedSession.applicationId)
      if (app) {
        setSelectedApplication(app)
        setSessionRestored(true)
        // Restore tabs after fetching notes
        if (savedSession.tabIds.length > 0) {
          restoreTabs(token, savedSession.tabIds, savedSession.activeTabId)
        }
        return
      }
    }

    // Otherwise use initialAppId if provided
    if (initialAppId) {
      const app = applications.find((a) => a.id === initialAppId)
      if (app) {
        setSelectedApplication(app)
        setSessionRestored(true)
        return
      }
    }

    setSessionRestored(true)
  }, [applications, initialAppId, sessionRestored, restoreSession, restoreTabs, token])

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
      {/* Compact Header */}
      <div className="flex h-10 items-center justify-between border-b border-border px-3">
        <div className="flex items-center gap-3">
          {/* Notes Icon + Title */}
          <div className="flex items-center gap-1.5">
            <StickyNote className="h-4 w-4 text-primary" />
            <span className="text-sm font-semibold text-foreground">Notes</span>
          </div>

          {/* Divider */}
          <span className="h-4 w-px bg-border" />

          {/* Application Selector */}
          <ApplicationSelector
            applications={applications}
            selectedApplication={selectedApplication}
            isLoading={isLoadingApps}
            onSelect={handleSelectApplication}
          />

          {/* Inline operation indicator */}
          {(isCreating || isUpdating || isDeleting) && (
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <PulseIndicator color="primary" />
              <span>{isCreating ? 'Creating' : isUpdating ? 'Saving' : 'Deleting'}...</span>
            </span>
          )}
        </div>

        {/* Error Display - Compact */}
        {error && (
          <div className="flex items-center gap-1.5 rounded border border-destructive/40 bg-destructive/5 px-2 py-0.5 text-xs text-destructive">
            <AlertCircle className="h-3 w-3" />
            <span className="max-w-[200px] truncate">{error.message}</span>
            <button onClick={clearError} className="ml-0.5 hover:text-destructive/70">
              <X className="h-3 w-3" />
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
            isCollapsed={isSidebarCollapsed}
            onCollapsedChange={handleSidebarCollapsedChange}
            onSelectNote={handleSelectNote}
            onCreateNote={handleCreateNote}
            onEditNote={handleEditNote}
            onDeleteNote={handleDeleteClick}
            className={cn(
              'flex-shrink-0 border-r border-border transition-all duration-200',
              isSidebarCollapsed ? 'w-10' : 'w-52'
            )}
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
