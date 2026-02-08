/**
 * Notes Page
 *
 * Main entry point for the Knowledge Base / Notes screen.
 * Wraps content in KnowledgeBaseProvider for shared UI state.
 *
 * Layout:
 * - Search bar at top (full width, outside sidebar)
 * - Sidebar on the left (tab bar, create buttons, folder tree, tag filter)
 * - Editor panel on the right
 *
 * The editor panel shows documents in view mode by default.
 * Users click "Edit" to acquire a lock and enter edit mode,
 * then "Save" to persist or "Cancel" to discard.
 */

import { useEffect, useMemo } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { FileText, Save, Trash2, AlertTriangle } from 'lucide-react'
import { KnowledgeBaseProvider, useKnowledgeBase } from '@/contexts/knowledge-base-context'
import { useAuthStore } from '@/contexts/auth-context'
import { useApplicationsWithDocs } from '@/hooks/use-documents'
import { useEditMode } from '@/hooks/use-edit-mode'
import { useWebSocket, WebSocketClient, MessageType } from '@/hooks/use-websocket'
import { queryKeys } from '@/lib/query-client'
import { KnowledgeSidebar } from '@/components/knowledge/knowledge-sidebar'
import { KnowledgeTabBar } from '@/components/knowledge/knowledge-tab-bar'
import { SearchBar } from '@/components/knowledge/search-bar'
import { DocumentEditor } from '@/components/knowledge/document-editor'
import { DocumentActionBar } from '@/components/knowledge/document-action-bar'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'

/**
 * EditorPanel - Inner component for the document editor area.
 * Must be inside KnowledgeBaseProvider to access selectedDocumentId.
 */
function EditorPanel() {
  const { selectedDocumentId } = useKnowledgeBase()

  // Edit mode state machine — owns the document query
  const editMode = useEditMode({
    documentId: selectedDocumentId,
    userRole: null, // Notes page doesn't have role-based access
  })

  const currentDoc = editMode.document

  // Memoize parsed content to avoid new object reference on every render
  const parsedContent = useMemo(
    () => currentDoc?.content_json ? JSON.parse(currentDoc.content_json) as object : undefined,
    [currentDoc?.content_json]
  )

  // Empty state when no document selected
  if (!selectedDocumentId || !currentDoc) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground gap-3">
        <FileText className="h-12 w-12 text-muted-foreground/30" />
        <p className="text-sm">Select a document to start editing</p>
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col min-w-0 min-h-0">
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

      {/* Document editor - keyed by documentId to force remount on switch */}
      <DocumentEditor
        key={selectedDocumentId}
        content={parsedContent}
        onChange={editMode.handleContentChange}
        editable={editMode.mode === 'edit'}
        placeholder="Start writing..."
        className="flex-1"
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
      <Dialog open={editMode.showQuitDialog} onOpenChange={() => { /* prevent close via overlay */ }}>
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

/**
 * NotesPageContent - Inner component that needs context access.
 */
function NotesPageContent(): JSX.Element {
  const { activeTab, setActiveTab, selectedDocumentId, selectDocument } = useKnowledgeBase()
  const { data: scopesSummary, isLoading: isAppsLoading } = useApplicationsWithDocs()
  const userId = useAuthStore((s) => s.user?.id ?? null)
  const { joinRoom, leaveRoom, status: wsStatus, subscribe } = useWebSocket()
  const queryClient = useQueryClient()

  // Join the appropriate WebSocket room based on active tab
  useEffect(() => {
    if (!wsStatus.isConnected) return

    let roomId: string | null = null

    if (activeTab === 'personal' && userId) {
      roomId = WebSocketClient.getUserRoom(userId)
    } else if (activeTab.startsWith('app:')) {
      const appId = activeTab.slice(4)
      roomId = WebSocketClient.getApplicationRoom(appId)
    }

    if (roomId) {
      joinRoom(roomId)
      return () => leaveRoom(roomId!)
    }
  }, [activeTab, userId, wsStatus.isConnected, joinRoom, leaveRoom])

  // Clear selection when the currently viewed document is deleted by another user
  useEffect(() => {
    if (!wsStatus.isConnected) return

    const unsubDocDeleted = subscribe<{ document_id: string }>(
      MessageType.DOCUMENT_DELETED,
      (data) => {
        if (data.document_id === selectedDocumentId) {
          selectDocument(null)
        }
      }
    )

    const unsubFolderDeleted = subscribe<{ folder_id: string }>(
      MessageType.FOLDER_DELETED,
      () => {
        // When a folder is deleted, documents inside it are also deleted.
        // The tree will refresh and if the selected doc no longer exists,
        // the EditorPanel will show the empty state.
      }
    )

    return () => {
      unsubDocDeleted()
      unsubFolderDeleted()
    }
  }, [wsStatus.isConnected, subscribe, selectedDocumentId, selectDocument])

  // Invalidate document cache when another user saves content
  useEffect(() => {
    if (!wsStatus.isConnected) return

    const unsubDocUpdated = subscribe<{ document_id: string; actor_id?: string }>(
      MessageType.DOCUMENT_UPDATED,
      (data) => {
        // Skip own actions
        if (data.actor_id && data.actor_id === userId) return
        queryClient.invalidateQueries({ queryKey: queryKeys.document(data.document_id) })
      }
    )

    return () => {
      unsubDocUpdated()
    }
  }, [wsStatus.isConnected, subscribe, userId, queryClient])

  return (
    <div className="flex flex-col h-full">
      {/* Search bar at very top */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border bg-background">
        <SearchBar className="flex-1 max-w-sm" />
      </div>

      {/* Full-width tab bar - like OneNote */}
      <KnowledgeTabBar
        activeTab={activeTab}
        onTabChange={setActiveTab}
        applicationsWithDocs={scopesSummary?.applications ?? []}
        isLoading={isAppsLoading}
      />

      {/* Main content area */}
      <div className="flex flex-1 min-h-0">
        <KnowledgeSidebar />
        <main className="flex-1 flex flex-col min-h-0">
          <EditorPanel />
        </main>
      </div>
    </div>
  )
}

/**
 * NotesPage - Main component wrapped in provider.
 */
export function NotesPage(): JSX.Element {
  return (
    <KnowledgeBaseProvider>
      <NotesPageContent />
    </KnowledgeBaseProvider>
  )
}

export default NotesPage
