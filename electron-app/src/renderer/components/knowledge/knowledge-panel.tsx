/**
 * KnowledgePanel
 *
 * Reusable two-panel knowledge base component for embedding in detail pages.
 * Left panel: search, creation buttons, folder/document tree.
 * Right panel: document editor or empty state.
 *
 * Wraps itself in a KnowledgeBaseProvider with a scoped storage prefix
 * so multiple mounted instances don't share localStorage state.
 *
 * Documents open in view mode by default. Users click "Edit" to acquire
 * a lock and enter edit mode, then "Save" to persist or "Cancel" to discard.
 */

import { useCallback, useRef, useEffect, useState, useMemo } from 'react'
import { FileText, FilePlus, FolderPlus, Save, Trash2, AlertTriangle } from 'lucide-react'
import { cn } from '@/lib/utils'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import {
  KnowledgeBaseProvider,
  useKnowledgeBase,
  type ScopeType,
} from '@/contexts/knowledge-base-context'
import { useCreateDocument } from '@/hooks/use-documents'
import { useCreateFolder } from '@/hooks/use-document-folders'
import { useEditMode } from '@/hooks/use-edit-mode'
import { SearchBar } from './search-bar'
import { FolderTree } from './folder-tree'
import { ApplicationTree } from './application-tree'
import { DocumentEditor } from './document-editor'
import { DocumentActionBar } from './document-action-bar'
import { ensureContentHeading } from './content-utils'

// ============================================================================
// Types
// ============================================================================

export interface KnowledgePanelProps {
  scope: ScopeType
  scopeId: string
  /** For application scope: show project sub-folders in tree */
  showProjectFolders?: boolean
  className?: string
}

// ============================================================================
// Skeleton
// ============================================================================

export function EditorSkeleton(): JSX.Element {
  return (
    <div className="flex-1 p-6 space-y-4">
      <div className="h-8 w-48 rounded bg-muted animate-pulse" />
      <div className="space-y-2.5">
        <div className="h-4 rounded bg-muted animate-pulse" style={{ width: '90%' }} />
        <div className="h-4 rounded bg-muted animate-pulse" style={{ width: '75%' }} />
        <div className="h-4 rounded bg-muted animate-pulse" style={{ width: '85%' }} />
        <div className="h-4 rounded bg-muted animate-pulse" style={{ width: '60%' }} />
      </div>
      <div className="space-y-2.5 pt-2">
        <div className="h-4 rounded bg-muted animate-pulse" style={{ width: '80%' }} />
        <div className="h-4 rounded bg-muted animate-pulse" style={{ width: '70%' }} />
      </div>
    </div>
  )
}

// ============================================================================
// Inner panel (must be inside KnowledgeBaseProvider)
// ============================================================================

interface InnerPanelProps {
  scope: ScopeType
  scopeId: string
  showProjectFolders?: boolean
  className?: string
}

/** Resize constraints for tree panel */
const MIN_TREE_WIDTH = 200
const MAX_TREE_WIDTH = 500
const DEFAULT_TREE_WIDTH = 280

function InnerPanel({ scope, scopeId, showProjectFolders, className }: InnerPanelProps) {
  const { selectedDocumentId, selectDocument } = useKnowledgeBase()

  // Resizable tree panel state
  const [treeWidth, setTreeWidth] = useState(DEFAULT_TREE_WIDTH)
  const isResizingRef = useRef(false)
  const containerRef = useRef<HTMLDivElement>(null)

  // Edit mode state machine — owns the document query
  const editMode = useEditMode({
    documentId: selectedDocumentId,
    userRole: null,
  })

  const currentDoc = editMode.document
  const isDocError = editMode.isDocError

  // Memoize parsed content — ensure it starts with an h1 heading
  const parsedContent = useMemo(
    () => currentDoc
      ? ensureContentHeading(currentDoc.content_json, currentDoc.title)
      : undefined,
    [currentDoc?.content_json, currentDoc?.title]
  )

  // Creation mutations
  const createDocument = useCreateDocument()
  const createFolder = useCreateFolder()

  const handleCreateDoc = useCallback(() => {
    if (!scopeId) return
    createDocument.mutate(
      {
        title: 'Untitled',
        scope,
        scope_id: scopeId,
        folder_id: null,
      },
      {
        onSuccess: (data) => {
          selectDocument(data.id)
        },
      }
    )
  }, [scope, scopeId, createDocument, selectDocument])

  const handleCreateFolder = useCallback(() => {
    if (!scopeId) return
    createFolder.mutate({
      name: 'New Folder',
      scope,
      scope_id: scopeId,
      parent_id: null,
    })
  }, [scope, scopeId, createFolder])

  // Resize handlers for tree panel
  const handleResizeMouseMove = useCallback((e: MouseEvent) => {
    if (!isResizingRef.current || !containerRef.current) return
    const containerRect = containerRef.current.getBoundingClientRect()
    const newWidth = e.clientX - containerRect.left
    setTreeWidth(Math.max(MIN_TREE_WIDTH, Math.min(MAX_TREE_WIDTH, newWidth)))
  }, [])

  const handleResizeMouseUp = useCallback(() => {
    isResizingRef.current = false
    document.removeEventListener('mousemove', handleResizeMouseMove)
    document.removeEventListener('mouseup', handleResizeMouseUp)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  }, [handleResizeMouseMove])

  const handleResizeMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    isResizingRef.current = true
    document.addEventListener('mousemove', handleResizeMouseMove)
    document.addEventListener('mouseup', handleResizeMouseUp)
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }, [handleResizeMouseMove, handleResizeMouseUp])

  // Cleanup resize listeners on unmount
  useEffect(() => {
    return () => {
      document.removeEventListener('mousemove', handleResizeMouseMove)
      document.removeEventListener('mouseup', handleResizeMouseUp)
    }
  }, [handleResizeMouseMove, handleResizeMouseUp])

  return (
    <div
      ref={containerRef}
      className={cn('flex h-full overflow-hidden', className)}
    >
      {/* Left panel: tree */}
      <div
        style={{ width: treeWidth }}
        className="flex-shrink-0 flex flex-col border-r border-border bg-sidebar"
      >
        {/* Search */}
        <div className="p-2 border-b border-border">
          <SearchBar />
        </div>

        {/* Quick creation buttons */}
        <div className="flex items-center gap-1 px-2 py-1 border-b border-border">
          <button
            onClick={handleCreateDoc}
            className="p-1 rounded hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
            title="New document"
          >
            <FilePlus className="h-4 w-4" />
          </button>
          <button
            onClick={handleCreateFolder}
            className="p-1 rounded hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
            title="New folder"
          >
            <FolderPlus className="h-4 w-4" />
          </button>
        </div>

        {/* Tree */}
        <ScrollArea className="flex-1">
          {scope === 'application' && showProjectFolders ? (
            <ApplicationTree applicationId={scopeId} />
          ) : (
            <FolderTree />
          )}
        </ScrollArea>
      </div>

      {/* Resize handle */}
      <div
        className="w-1 cursor-col-resize bg-border hover:bg-primary/50 transition-colors flex-shrink-0"
        onMouseDown={handleResizeMouseDown}
      />

      {/* Right panel: editor or empty state */}
      <div className="flex-1 flex flex-col min-w-0 min-h-0">
        {selectedDocumentId ? (
          currentDoc ? (
            <>
              {/* Action bar: Edit/Save/Cancel buttons */}
              <DocumentActionBar
                mode={editMode.mode}
                lockHolder={editMode.lockHolder}
                isLockedByOther={editMode.isLockedByOther}
                canForceTake={editMode.canForceTake}
                isDirty={editMode.isDirty}
                isSaving={editMode.isSaving}
                isEntering={editMode.isEntering}
                isExiting={editMode.isExiting}
                onEdit={() => void editMode.enterEditMode()}
                onSave={() => void editMode.save()}
                onCancel={editMode.cancel}
                onForceTake={() => void editMode.forceTake()}
              />

              {/* Document editor */}
              <DocumentEditor
                content={parsedContent}
                onChange={editMode.handleContentChange}
                onBaselineSync={editMode.handleBaselineSync}
                editable={editMode.mode === 'edit'}
                placeholder="Start writing..."
                className="flex-1"
                updatedAt={currentDoc.updated_at}
              />

              {/* Discard changes dialog */}
              <Dialog open={editMode.showDiscardDialog} onOpenChange={(open) => { if (!open) editMode.cancelDiscard() }}>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Discard changes?</DialogTitle>
                    <DialogDescription>
                      You have unsaved changes. Are you sure you want to discard them?
                    </DialogDescription>
                  </DialogHeader>
                  <DialogFooter>
                    <Button variant="outline" onClick={editMode.cancelDiscard}>
                      Keep editing
                    </Button>
                    <Button variant="destructive" onClick={editMode.confirmDiscard}>
                      Discard
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>

              {/* Inactivity dialog */}
              <Dialog open={editMode.showInactivityDialog} onOpenChange={(open) => { if (!open) editMode.inactivityKeepEditing() }}>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Are you still editing?</DialogTitle>
                    <DialogDescription>
                      Your changes will be auto-saved in 60 seconds.
                    </DialogDescription>
                  </DialogHeader>
                  <DialogFooter>
                    <Button variant="destructive" onClick={editMode.inactivityDiscard}>
                      Discard
                    </Button>
                    <Button variant="outline" onClick={() => void editMode.inactivitySave()}>
                      Save
                    </Button>
                    <Button onClick={editMode.inactivityKeepEditing}>
                      Keep Editing
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>

              {/* Quit confirmation dialog */}
              <Dialog open={editMode.showQuitDialog} onOpenChange={(open) => { if (!open) editMode.quitCancel() }}>
                <DialogContent className="sm:max-w-md">
                  <DialogHeader>
                    <div className="mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-full bg-amber-500/10">
                      <AlertTriangle className="h-6 w-6 text-amber-500" />
                    </div>
                    <DialogTitle className="text-center">Unsaved changes</DialogTitle>
                    <DialogDescription className="text-center">
                      You have unsaved changes in your document. What would you like to do before closing?
                    </DialogDescription>
                  </DialogHeader>
                  <div className="flex flex-col gap-2 pt-2">
                    <Button onClick={editMode.quitSave} className="w-full gap-2">
                      <Save className="h-4 w-4" />
                      Save and close
                    </Button>
                    <Button variant="destructive" onClick={editMode.quitDiscard} className="w-full gap-2">
                      <Trash2 className="h-4 w-4" />
                      Discard and close
                    </Button>
                    <Button variant="outline" onClick={editMode.quitCancel} className="w-full">
                      Keep editing
                    </Button>
                  </div>
                </DialogContent>
              </Dialog>
            </>
          ) : isDocError ? (
            <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground gap-3">
              <FileText className="h-12 w-12 text-muted-foreground/30" />
              <p className="text-sm">Document not found</p>
            </div>
          ) : (
            <EditorSkeleton />
          )
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground gap-3">
            <FileText className="h-12 w-12 text-muted-foreground/30" />
            <p className="text-sm">Select a document to start editing</p>
          </div>
        )}
      </div>
    </div>
  )
}

// ============================================================================
// Main component (wraps in provider)
// ============================================================================

export function KnowledgePanel({
  scope,
  scopeId,
  showProjectFolders,
  className,
}: KnowledgePanelProps): JSX.Element {
  return (
    <KnowledgeBaseProvider
      initialScope={scope}
      initialScopeId={scopeId}
      storagePrefix={`kb-${scope}-${scopeId}-`}
    >
      <InnerPanel
        scope={scope}
        scopeId={scopeId}
        showProjectFolders={showProjectFolders}
        className={className}
      />
    </KnowledgeBaseProvider>
  )
}

export default KnowledgePanel
