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

import { useEffect, useRef, useCallback } from 'react'
import { Skeleton } from '@/components/ui/skeleton'
import { KnowledgeBaseProvider, useKnowledgeBase } from '@/contexts/knowledge-base-context'
import { useAuthUserId } from '@/contexts/auth-context'
import { useApplicationsWithDocs, useDocument } from '@/hooks/use-documents'
import { useKnowledgePermissions } from '@/hooks/use-knowledge-permissions'
import { useWebSocket, WebSocketClient, MessageType } from '@/hooks/use-websocket'
import {
  consumePendingAiNavigation,
  subscribePendingAiNavigation,
} from '@/lib/ai-navigation'
import type { NavigationTarget } from '@/components/ai/types'
import { KnowledgeSidebar } from '@/components/knowledge/knowledge-sidebar'
import { KnowledgeTabBar } from '@/components/knowledge/knowledge-tab-bar'
import { SearchBar } from '@/components/knowledge/search-bar'
import { EditorPanel } from '@/components/knowledge/editor-panel'
import { FileViewerPanel } from '@/components/knowledge/file-viewer-panel'
import { useFileDetail } from '@/hooks/use-folder-files'

/**
 * NotesPageContent - Inner component that needs context access.
 */
function NotesPageContent(): JSX.Element {
  const { activeTab, setActiveTab, selectedDocumentId, selectedFileId, selectDocument, selectFile, navigateToDocument } = useKnowledgeBase()
  const { data: scopesSummary, isLoading: isAppsLoading } = useApplicationsWithDocs()
  const userId = useAuthUserId()
  const { joinRoom, leaveRoom, status: wsStatus, subscribe } = useWebSocket()

  // Read selected document metadata to determine its scope (shared cache with EditorPanel)
  const { data: selectedDoc } = useDocument(selectedDocumentId)

  // Read selected file metadata for file viewer panel
  const { data: selectedFile, isLoading: isFileLoading } = useFileDetail(selectedFileId)

  // Permissions — scope to the document's actual scope (project-scoped docs need project permissions)
  const permScope = selectedDoc?.project_id
    ? 'project' as const
    : activeTab === 'personal'
      ? 'personal' as const
      : 'application' as const
  const permScopeId = selectedDoc?.project_id
    ? selectedDoc.project_id
    : activeTab === 'personal'
      ? null
      : activeTab.slice(4)
  const { canEdit: rawCanEdit, isOwner: rawIsOwner, isLoading: isPermLoading } =
    useKnowledgePermissions(permScope, permScopeId)

  // Hold previous stable permissions while loading to prevent Edit button flicker
  // when switching from app-scope → project-scope on first project-doc selection.
  const stablePermsRef = useRef({ canEdit: false, isOwner: false })
  if (!isPermLoading) {
    stablePermsRef.current = { canEdit: rawCanEdit, isOwner: rawIsOwner }
  }
  const canEdit = isPermLoading ? stablePermsRef.current.canEdit : rawCanEdit
  const isOwner = isPermLoading ? stablePermsRef.current.isOwner : rawIsOwner

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

  // Clear selection when the currently viewed document/file is deleted by another user
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
      (data) => {
        // When a folder is deleted, documents inside it are cascade-deleted.
        // Only clear document selection if the selected document is in the deleted folder.
        if (selectedDocumentId && selectedDoc?.folder_id === data.folder_id) {
          selectDocument(null)
        }
        // Files in the folder are also cascade soft-deleted.
        // Only clear file selection if the file belongs to the deleted folder.
        if (selectedFileId && selectedFile?.folder_id === data.folder_id) {
          selectFile(null)
        }
      }
    )

    const unsubFileDeleted = subscribe<{ file_id: string }>(
      MessageType.FILE_DELETED,
      (data) => {
        if (data.file_id === selectedFileId) {
          selectFile(null)
        }
      }
    )

    return () => {
      unsubDocDeleted()
      unsubFolderDeleted()
      unsubFileDeleted()
    }
  }, [wsStatus.isConnected, subscribe, selectedDocumentId, selectDocument, selectedDoc, selectedFileId, selectFile, selectedFile])

  // Handle AI navigation: navigate to a document with highlight when Blair source is clicked
  const handleAiNavigation = useCallback(
    (target: NavigationTarget) => {
      if (target.type !== 'document') return

      const { documentId, applicationId, highlight } = target
      // Determine the correct tab from applicationId.
      // Guard against empty strings (truthy in JS but invalid as UUID).
      const hasValidAppId = applicationId && applicationId.length > 8
      const targetTab = hasValidAppId ? `app:${applicationId}` : 'personal'

      // Build search terms from highlight params for the search-highlight extension
      const searchTerms: string[] = []
      if (highlight?.headingContext) {
        searchTerms.push(highlight.headingContext)
      } else if (highlight?.chunkText) {
        // Use first 50 chars of chunk text as search term
        searchTerms.push(highlight.chunkText.slice(0, 50))
      }

      navigateToDocument(targetTab, documentId, searchTerms.length > 0 ? searchTerms : undefined)
    },
    [navigateToDocument],
  )

  // Consume pending AI navigation on mount + subscribe for live navigations
  useEffect(() => {
    const pending = consumePendingAiNavigation()
    if (pending) {
      // Use double-rAF to ensure knowledge tree is mounted and rendered
      let cancelled = false
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          if (!cancelled) handleAiNavigation(pending)
        })
      })
      return () => { cancelled = true }
    }
  }, [handleAiNavigation])

  useEffect(() => {
    return subscribePendingAiNavigation(handleAiNavigation)
  }, [handleAiNavigation])

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
        <main className="flex-1 flex flex-col min-h-0 min-w-0 overflow-hidden">
          {selectedFileId && isFileLoading ? (
            <div className="flex-1 flex flex-col min-h-0">
              {/* Header skeleton */}
              <div className="flex items-center justify-between px-4 py-2 border-b border-border">
                <div className="flex items-center gap-2">
                  <Skeleton className="h-4 w-40" />
                  <Skeleton className="h-4 w-16" />
                </div>
                <div className="flex items-center gap-1">
                  <Skeleton className="h-7 w-7 rounded" />
                  <Skeleton className="h-7 w-7 rounded" />
                </div>
              </div>
              {/* Content skeleton */}
              <div className="flex-1 p-6 space-y-4">
                <Skeleton className="h-5 w-48" />
                <div className="space-y-2.5">
                  <Skeleton className="h-3.5 w-full" />
                  <Skeleton className="h-3.5 w-[90%]" />
                  <Skeleton className="h-3.5 w-[75%]" />
                </div>
                <Skeleton className="h-40 w-full rounded-lg" />
                <div className="space-y-2.5">
                  <Skeleton className="h-3.5 w-[85%]" />
                  <Skeleton className="h-3.5 w-[60%]" />
                </div>
              </div>
            </div>
          ) : selectedFileId && selectedFile ? (
            <FileViewerPanel file={selectedFile} />
          ) : selectedFileId && !isFileLoading && !selectedFile ? (
            <div className="flex-1 flex items-center justify-center text-muted-foreground">
              <p>File not found or has been deleted.</p>
            </div>
          ) : (
            <EditorPanel keyByDocumentId canEdit={canEdit} isOwner={isOwner} />
          )}
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
