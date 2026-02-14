/**
 * EditorPanel
 *
 * Shared document editor panel used by both the Notes page and KnowledgePanel.
 * Owns the edit-mode state machine (view/edit/save lifecycle) and renders
 * the action bar, TipTap editor, and confirmation dialogs.
 *
 * Must be rendered inside a KnowledgeBaseProvider.
 */

import { useMemo } from 'react'
import { FileText, Save, Trash2, AlertTriangle } from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { useKnowledgeBase } from '@/contexts/knowledge-base-context'
import { useEditMode } from '@/hooks/use-edit-mode'
import { DocumentEditor } from './document-editor'
import { DocumentActionBar } from './document-action-bar'
import { ensureContentHeading } from './content-utils'

// ============================================================================
// Types
// ============================================================================

export interface EditorPanelProps {
  /** Force remount of DocumentEditor on document switch (Notes page needs this) */
  keyByDocumentId?: boolean
  /** Whether the current user has edit permission (defaults to true) */
  canEdit?: boolean
  /** Whether the current user is an application owner (for force-take locks) */
  isOwner?: boolean
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
// EditorPanel
// ============================================================================

export function EditorPanel({ keyByDocumentId, canEdit: canEditProp, isOwner: isOwnerProp, className }: EditorPanelProps): JSX.Element {
  const { selectedDocumentId, searchHighlightTerms, searchScrollToOccurrence } = useKnowledgeBase()

  // Edit mode state machine — owns the document query
  const editMode = useEditMode({
    documentId: selectedDocumentId,
    canEdit: canEditProp ?? true,
    isOwner: isOwnerProp ?? false,
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

  // No document selected
  if (!selectedDocumentId) {
    return (
      <div className={cn('flex-1 flex flex-col items-center justify-center text-muted-foreground gap-3', className)}>
        <FileText className="h-12 w-12 text-muted-foreground/30" />
        <p className="text-sm">Select a document to start editing</p>
      </div>
    )
  }

  // Document not found (query error)
  if (!currentDoc && isDocError) {
    return (
      <div className={cn('flex-1 flex flex-col items-center justify-center text-muted-foreground gap-3', className)}>
        <FileText className="h-12 w-12 text-muted-foreground/30" />
        <p className="text-sm">Document not found</p>
      </div>
    )
  }

  // Document loading skeleton
  if (!currentDoc) {
    return <EditorSkeleton />
  }

  return (
    <div className={cn('flex-1 flex flex-col min-w-0 min-h-0', className)}>
      {/* Action bar: Edit/Save/Cancel buttons */}
      <DocumentActionBar
        mode={editMode.mode}
        lockHolder={editMode.lockHolder}
        isLockedByOther={editMode.isLockedByOther}
        canForceTake={editMode.canForceTake}
        canEdit={editMode.canEdit}
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
        key={keyByDocumentId ? selectedDocumentId : undefined}
        content={parsedContent}
        onChange={editMode.handleContentChange}
        onBaselineSync={editMode.handleBaselineSync}
        editable={editMode.mode === 'edit'}
        placeholder="Start writing..."
        className="flex-1"
        updatedAt={currentDoc.updated_at}
        documentId={selectedDocumentId}
        searchTerms={searchHighlightTerms}
        scrollToOccurrence={searchScrollToOccurrence}
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
    </div>
  )
}

export default EditorPanel
