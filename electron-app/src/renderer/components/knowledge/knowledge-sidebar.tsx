/**
 * Knowledge Base Sidebar
 *
 * Main sidebar container that composes all sidebar sections:
 * - Search bar
 * - Scope filter (placeholder for Plan 03)
 * - Folder tree (FolderTree component)
 * - Tag filter (placeholder for Plan 03)
 *
 * Supports collapsed/expanded modes with smooth transitions.
 */

import { PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { cn } from '@/lib/utils'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useKnowledgeBase } from '@/contexts/knowledge-base-context'
import { SearchBar } from './search-bar'
import { FolderTree } from './folder-tree'

export function KnowledgeSidebar(): JSX.Element {
  const { isSidebarCollapsed, toggleSidebar } = useKnowledgeBase()

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
          {/* Search bar section */}
          <div className="p-2 border-b border-border">
            <SearchBar />
          </div>

          {/* Scope filter section -- PLACEHOLDER for Plan 03 */}
          <div className="px-2 py-1.5 border-b border-border">
            <div className="text-xs text-muted-foreground">All Documents</div>
          </div>

          {/* Folder tree section */}
          <ScrollArea className="flex-1">
            <FolderTree />
          </ScrollArea>

          {/* Tag filter section -- PLACEHOLDER for Plan 03 */}
          <div className="border-t border-border p-2">
            <div className="text-xs text-muted-foreground">Tags</div>
          </div>
        </>
      )}
    </div>
  )
}

export default KnowledgeSidebar
