/**
 * Knowledge Base Sidebar
 *
 * Main sidebar container that composes all sidebar sections:
 * - Tab bar (KnowledgeTabBar for My Notes + application tabs)
 * - Search bar
 * - Quick creation buttons (new doc / new folder)
 * - Folder tree (FolderTree component)
 * - Tag filter (TagFilterList with click-to-filter)
 *
 * Supports collapsed/expanded modes with smooth transitions.
 */

import { useState } from 'react'
import { PanelLeftClose, PanelLeftOpen, FilePlus, FolderPlus } from 'lucide-react'
import { cn } from '@/lib/utils'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useKnowledgeBase } from '@/contexts/knowledge-base-context'
import { useAuthStore } from '@/contexts/auth-context'
import { useApplicationsWithDocs, useCreateDocument } from '@/hooks/use-documents'
import { useCreateFolder } from '@/hooks/use-document-folders'
import { KnowledgeTabBar } from './knowledge-tab-bar'
import { SearchBar } from './search-bar'
import { FolderTree } from './folder-tree'
import { ApplicationTree } from './application-tree'
import { TagFilterList } from './tag-filter-list'
import { CreateDialog } from './create-dialog'

export function KnowledgeSidebar(): JSX.Element {
  const {
    isSidebarCollapsed,
    toggleSidebar,
    activeTab,
    setActiveTab,
    selectedFolderId,
  } = useKnowledgeBase()
  const userId = useAuthStore((s) => s.user?.id ?? null)
  const { data: scopesSummary } = useApplicationsWithDocs()
  const createDocument = useCreateDocument()
  const createFolder = useCreateFolder()

  // Dialog state
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [createType, setCreateType] = useState<'document' | 'folder'>('document')

  const resolveScope = () => {
    if (activeTab === 'personal') {
      return { scope: 'personal' as const, scopeId: userId ?? '' }
    }
    const appId = activeTab.slice(4)
    return { scope: 'application' as const, scopeId: appId }
  }

  const handleCreateDocClick = () => {
    setCreateType('document')
    setCreateDialogOpen(true)
  }

  const handleCreateFolderClick = () => {
    setCreateType('folder')
    setCreateDialogOpen(true)
  }

  const handleCreateSubmit = async (name: string) => {
    const { scope, scopeId } = resolveScope()
    if (!scopeId) return

    if (createType === 'document') {
      await createDocument.mutateAsync({
        title: name,
        scope,
        scope_id: scopeId,
        folder_id: selectedFolderId || null, // Use selected folder
      })
    } else {
      await createFolder.mutateAsync({
        name,
        scope,
        scope_id: scopeId,
        parent_id: selectedFolderId || null, // Create inside selected folder
      })
    }
  }

  return (
    <div
      className={cn(
        'flex flex-col border-r border-border bg-sidebar h-full transition-all duration-200',
        isSidebarCollapsed ? 'w-10' : 'w-64'
      )}
    >
      {/* Collapse toggle */}
      <div className={cn(
        'flex items-center border-b border-border',
        isSidebarCollapsed ? 'justify-center p-1.5' : 'justify-between px-2 py-1.5'
      )}>
        {!isSidebarCollapsed && (
          <span className="text-xs font-semibold text-foreground">Notes</span>
        )}
        <button
          onClick={toggleSidebar}
          className={cn(
            'flex items-center justify-center rounded-md p-1',
            'text-muted-foreground hover:text-foreground hover:bg-muted/50',
            'transition-colors'
          )}
          title={isSidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          aria-label={isSidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {isSidebarCollapsed ? (
            <PanelLeftOpen className="h-4 w-4" />
          ) : (
            <PanelLeftClose className="h-4 w-4" />
          )}
        </button>
      </div>

      {/* Sidebar content (hidden when collapsed) */}
      {!isSidebarCollapsed && (
        <>
          {/* Tab bar section */}
          <KnowledgeTabBar
            activeTab={activeTab}
            onTabChange={setActiveTab}
            applicationsWithDocs={scopesSummary?.applications ?? []}
          />

          {/* Search bar section */}
          <div className="p-2 border-b border-border">
            <SearchBar />
          </div>

          {/* Quick creation buttons */}
          <div className="flex items-center gap-0.5 px-1.5 py-0.5 border-b border-border">
            <button
              onClick={handleCreateDocClick}
              className="p-1 rounded hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
              title="New document"
            >
              <FilePlus className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={handleCreateFolderClick}
              className="p-1 rounded hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
              title="New folder"
            >
              <FolderPlus className="h-3.5 w-3.5" />
            </button>
          </div>

          {/* Create dialog */}
          <CreateDialog
            open={createDialogOpen}
            onOpenChange={setCreateDialogOpen}
            type={createType}
            onSubmit={handleCreateSubmit}
          />

          {/* Folder tree section */}
          <ScrollArea className="flex-1">
            {activeTab === 'personal' ? (
              <FolderTree />
            ) : activeTab.startsWith('app:') ? (
              <ApplicationTree applicationId={activeTab.slice(4)} />
            ) : (
              <FolderTree />
            )}
          </ScrollArea>

          {/* Tag filter section */}
          <div className="border-t border-border p-2">
            <TagFilterList />
          </div>
        </>
      )}
    </div>
  )
}

export default KnowledgeSidebar
