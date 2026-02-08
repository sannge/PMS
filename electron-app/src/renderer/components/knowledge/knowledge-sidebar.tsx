/**
 * Knowledge Base Sidebar
 *
 * Main sidebar container that composes all sidebar sections:
 * - Quick creation buttons (new doc / new folder)
 * - Folder tree (FolderTree component)
 * - Tag filter (TagFilterList with click-to-filter)
 *
 * Note: Search bar and tab bar are now at page level.
 * Supports collapsed/expanded modes and resizable width.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { PanelLeftClose, PanelLeftOpen, FilePlus, FolderPlus, GripVertical } from 'lucide-react'
import { cn } from '@/lib/utils'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useKnowledgeBase } from '@/contexts/knowledge-base-context'
import { useAuthStore } from '@/contexts/auth-context'
import { useCreateDocument } from '@/hooks/use-documents'
import { useCreateFolder } from '@/hooks/use-document-folders'
import { KnowledgeTree } from './knowledge-tree'
import { TagFilterList } from './tag-filter-list'
import { CreateDialog } from './create-dialog'

const SIDEBAR_WIDTH_KEY = 'knowledge-sidebar-width'
const DEFAULT_WIDTH = 256
const MIN_WIDTH = 200
const MAX_WIDTH = 500

export function KnowledgeSidebar(): JSX.Element {
  const {
    isSidebarCollapsed,
    toggleSidebar,
    activeTab,
    selectedFolderId,
  } = useKnowledgeBase()
  const userId = useAuthStore((s) => s.user?.id ?? null)
  const createDocument = useCreateDocument()
  const createFolder = useCreateFolder()

  // Dialog state
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [createType, setCreateType] = useState<'document' | 'folder'>('document')

  // Resizable width state
  const [sidebarWidth, setSidebarWidth] = useState(() => {
    const stored = localStorage.getItem(SIDEBAR_WIDTH_KEY)
    return stored ? parseInt(stored, 10) : DEFAULT_WIDTH
  })
  const [isResizing, setIsResizing] = useState(false)
  const sidebarRef = useRef<HTMLDivElement>(null)

  // Persist width to localStorage
  useEffect(() => {
    localStorage.setItem(SIDEBAR_WIDTH_KEY, String(sidebarWidth))
  }, [sidebarWidth])

  // Handle resize drag
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    setIsResizing(true)
  }, [])

  useEffect(() => {
    if (!isResizing) return

    // Show resize cursor globally during drag
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'

    const handleMouseMove = (e: MouseEvent) => {
      if (!sidebarRef.current) return
      const newWidth = e.clientX - sidebarRef.current.getBoundingClientRect().left
      setSidebarWidth(Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, newWidth)))
    }

    const handleMouseUp = () => {
      setIsResizing(false)
    }

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)

    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
  }, [isResizing])

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
      ref={sidebarRef}
      className={cn(
        'relative flex flex-col border-r border-border bg-sidebar h-full',
        isSidebarCollapsed && 'w-10 transition-all duration-200'
      )}
      style={isSidebarCollapsed ? undefined : { width: sidebarWidth }}
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
            <KnowledgeTree
              applicationId={activeTab.startsWith('app:') ? activeTab.slice(4) : undefined}
            />
          </ScrollArea>

          {/* Tag filter section */}
          <div className="border-t border-border p-2">
            <TagFilterList />
          </div>

          {/* Resize handle */}
          <div
            onMouseDown={handleMouseDown}
            className={cn(
              'absolute top-0 right-0 w-1 h-full cursor-col-resize group hover:bg-primary/20',
              isResizing && 'bg-primary/30'
            )}
          >
            <div className="absolute top-1/2 right-0 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity">
              <GripVertical className="h-4 w-4 text-muted-foreground" />
            </div>
          </div>
        </>
      )}
    </div>
  )
}

export default KnowledgeSidebar
