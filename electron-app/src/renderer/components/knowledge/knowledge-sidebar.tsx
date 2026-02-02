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
import { TagFilterList } from './tag-filter-list'

export function KnowledgeSidebar(): JSX.Element {
  const { isSidebarCollapsed, toggleSidebar, activeTab, setActiveTab } = useKnowledgeBase()
  const userId = useAuthStore((s) => s.user?.id ?? null)
  const { data: scopesSummary } = useApplicationsWithDocs()
  const createDocument = useCreateDocument()
  const createFolder = useCreateFolder()

  const resolveScope = () => {
    if (activeTab === 'personal') {
      return { scope: 'personal' as const, scopeId: userId ?? '' }
    }
    const appId = activeTab.slice(4)
    return { scope: 'application' as const, scopeId: appId }
  }

  const handleCreateDoc = () => {
    const { scope, scopeId } = resolveScope()
    if (!scopeId) return
    createDocument.mutate({
      title: 'Untitled',
      scope,
      scope_id: scopeId,
      folder_id: null,
    })
  }

  const handleCreateFolder = () => {
    const { scope, scopeId } = resolveScope()
    if (!scopeId) return
    createFolder.mutate({
      name: 'New Folder',
      scope,
      scope_id: scopeId,
      parent_id: null,
    })
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

          {/* Folder tree section */}
          <ScrollArea className="flex-1">
            <FolderTree />
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
