/**
 * EditorPanel
 *
 * Shared document editor panel used by both the Notes page and KnowledgePanel.
 * Owns the edit-mode state machine (view/edit/save lifecycle) and renders
 * the action bar, TipTap editor, and confirmation dialogs.
 *
 * Must be rendered inside a KnowledgeBaseProvider.
 */

import { useState, useMemo, useCallback } from 'react'
import { FileText, Save, Trash2, AlertTriangle, Loader2 } from 'lucide-react'
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
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { useKnowledgeBase } from '@/contexts/knowledge-base-context'
import { queryKeys } from '@/lib/query-client'
import { useSaveDocumentContent } from '@/hooks/use-queries'
import { useEditMode } from '@/hooks/use-edit-mode'
import type { Document } from '@/hooks/use-documents'
import { DocumentEditor } from './document-editor'
import { DocumentActionBar } from './document-action-bar'
import { ensureContentHeading } from './content-utils'
import { isCanvasDocument, convertToCanvas } from './canvas-types'
import type { CanvasDocument } from './canvas-types'
import { CanvasEditor } from './canvas-editor'

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

  // Detect canvas format BEFORE ensureContentHeading (canvas docs skip heading injection)
  const rawParsed = useMemo(() => {
    if (!currentDoc?.content_json) return null
    try { return JSON.parse(currentDoc.content_json) } catch { return null }
  }, [currentDoc?.content_json])

  const isCanvas = rawParsed != null && isCanvasDocument(rawParsed)

  // Convert to canvas state
  const [showConvertDialog, setShowConvertDialog] = useState(false)
  const [isConverting, setIsConverting] = useState(false)
  const saveContent = useSaveDocumentContent()
  const queryClient = useQueryClient()

  const handleConvertToCanvas = useCallback(() => {
    setShowConvertDialog(true)
  }, [])

  const confirmConvertToCanvas = useCallback(async () => {
    if (!selectedDocumentId) return
    setIsConverting(true)
    try {
      // FIX 8: Guard malformed content — only use rawParsed if it's a valid TipTap doc object
      const content = (rawParsed && typeof rawParsed === 'object' && (rawParsed as Record<string, unknown>).type === 'doc')
        ? rawParsed
        : { type: 'doc', content: [{ type: 'paragraph' }] }
      const canvasDoc = convertToCanvas(content)
      // FIX 7: Prefetch fresh row_version before saving
      const freshDoc = await queryClient.fetchQuery<Document>({
        queryKey: queryKeys.document(selectedDocumentId),
        staleTime: 0,
      })
      const result = await saveContent.mutateAsync({
        documentId: selectedDocumentId,
        content_json: JSON.stringify(canvasDoc),
        row_version: freshDoc.row_version,
      })
      // FIX 6: Optimistic cache update before invalidation
      queryClient.setQueryData<Document>(
        queryKeys.document(selectedDocumentId),
        (old) => old ? { ...old, content_json: JSON.stringify(canvasDoc), row_version: result.row_version } : old
      )
      queryClient.invalidateQueries({ queryKey: queryKeys.document(selectedDocumentId) })
      setShowConvertDialog(false)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Conversion failed'
      toast.error(`Convert to canvas failed: ${message}`)
    } finally {
      setIsConverting(false)
    }
  }, [rawParsed, selectedDocumentId, saveContent, queryClient])

  // Memoize parsed content — ensure it starts with an h1 heading (skipped for canvas)
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
        <FileText className="h-12 w-12 text-muted-foreground/30" aria-hidden="true" />
        <p className="text-sm">Select a document to start editing</p>
      </div>
    )
  }

  // Document not found (query error)
  if (!currentDoc && isDocError) {
    return (
      <div className={cn('flex-1 flex flex-col items-center justify-center text-muted-foreground gap-3', className)}>
        <FileText className="h-12 w-12 text-muted-foreground/30" aria-hidden="true" />
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
        isCanvas={isCanvas}
        onEdit={() => void editMode.enterEditMode()}
        onSave={() => void editMode.save()}
        onCancel={editMode.cancel}
        onForceTake={() => void editMode.forceTake()}
        onConvertToCanvas={editMode.mode === 'view' ? handleConvertToCanvas : undefined}
      />

      {/* Document editor — canvas or traditional */}
      {isCanvas ? (
        <CanvasEditor
          key={keyByDocumentId ? selectedDocumentId : undefined}
          canvasData={rawParsed as CanvasDocument}
          onChange={editMode.handleContentChange}
          onBaselineSync={editMode.handleBaselineSync}
          editable={editMode.mode === 'edit'}
          className="flex-1"
          documentId={selectedDocumentId}
          title={currentDoc.title}
          updatedAt={currentDoc.updated_at}
          isEmbeddingStale={currentDoc.is_embedding_stale}
        />
      ) : (
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
          isEmbeddingStale={currentDoc.is_embedding_stale}
        />
      )}

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

      {/* Convert to canvas confirmation dialog */}
      <Dialog open={showConvertDialog} onOpenChange={(open) => { if (!isConverting && !open) setShowConvertDialog(false) }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <div className="mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-full bg-amber-500/10">
              <AlertTriangle className="h-6 w-6 text-amber-500" />
            </div>
            <DialogTitle className="text-center">Convert to Canvas?</DialogTitle>
            <DialogDescription className="text-center">
              This will wrap your document content in a canvas container. You can then add more containers and freely arrange them. This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowConvertDialog(false)} disabled={isConverting}>
              Cancel
            </Button>
            <Button onClick={() => void confirmConvertToCanvas()} disabled={isConverting}>
              {isConverting && <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />}
              {isConverting ? 'Converting...' : 'Convert'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

export default EditorPanel
