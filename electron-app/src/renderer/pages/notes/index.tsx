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

import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { KnowledgeBaseProvider, useKnowledgeBase } from '@/contexts/knowledge-base-context'
import { useAuthStore } from '@/contexts/auth-context'
import { useApplicationsWithDocs, useDocument } from '@/hooks/use-documents'
import { useKnowledgePermissions } from '@/hooks/use-knowledge-permissions'
import { useWebSocket, WebSocketClient, MessageType } from '@/hooks/use-websocket'
import { queryKeys } from '@/lib/query-client'
import { KnowledgeSidebar } from '@/components/knowledge/knowledge-sidebar'
import { KnowledgeTabBar } from '@/components/knowledge/knowledge-tab-bar'
import { SearchBar } from '@/components/knowledge/search-bar'
import { EditorPanel } from '@/components/knowledge/editor-panel'

/**
 * NotesPageContent - Inner component that needs context access.
 */
function NotesPageContent(): JSX.Element {
  const { activeTab, setActiveTab, selectedDocumentId, selectDocument } = useKnowledgeBase()
  const { data: scopesSummary, isLoading: isAppsLoading } = useApplicationsWithDocs()
  const userId = useAuthStore((s) => s.user?.id ?? null)
  const { joinRoom, leaveRoom, status: wsStatus, subscribe } = useWebSocket()
  const queryClient = useQueryClient()

  // Read selected document metadata to determine its scope (shared cache with EditorPanel)
  const { data: selectedDoc } = useDocument(selectedDocumentId)

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
          <EditorPanel keyByDocumentId canEdit={canEdit} isOwner={isOwner} />
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
