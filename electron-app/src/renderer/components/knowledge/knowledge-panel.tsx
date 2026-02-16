/**
 * KnowledgePanel
 *
 * Reusable two-panel knowledge base component for embedding in detail pages.
 * Left panel: search, creation buttons, folder/document tree.
 * Right panel: shared EditorPanel (view/edit lifecycle).
 *
 * Wraps itself in a KnowledgeBaseProvider with a scoped storage prefix
 * so multiple mounted instances don't share localStorage state.
 */

import { useCallback, useRef, useEffect, useState } from 'react'
import { FilePlus, FolderPlus } from 'lucide-react'
import { cn } from '@/lib/utils'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  KnowledgeBaseProvider,
  useKnowledgeBase,
  type ScopeType,
} from '@/contexts/knowledge-base-context'
import { useCreateDocument } from '@/hooks/use-documents'
import { useCreateFolder } from '@/hooks/use-document-folders'
import { useKnowledgePermissions } from '@/hooks/use-knowledge-permissions'
import { SearchBar } from './search-bar'
import { KnowledgeTree } from './knowledge-tree'
import { EditorPanel } from './editor-panel'

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
  const { selectDocument } = useKnowledgeBase()

  // Resizable tree panel state
  const [treeWidth, setTreeWidth] = useState(DEFAULT_TREE_WIDTH)
  const isResizingRef = useRef(false)
  const containerRef = useRef<HTMLDivElement>(null)

  // Permissions
  const { canEdit, isOwner } = useKnowledgePermissions(scope, scopeId)

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
          <SearchBar scopeToContext />
        </div>

        {/* Quick creation buttons (hidden for read-only users) */}
        {canEdit && (
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
        )}

        {/* Tree */}
        <ScrollArea className="flex-1">
          <KnowledgeTree
            applicationId={scope === 'application' && showProjectFolders ? scopeId : undefined}
            canEdit={canEdit}
          />
        </ScrollArea>
      </div>

      {/* Resize handle */}
      <div
        className="w-1 cursor-col-resize bg-border hover:bg-primary/50 transition-colors flex-shrink-0"
        onMouseDown={handleResizeMouseDown}
      />

      {/* Right panel: editor */}
      <EditorPanel canEdit={canEdit} isOwner={isOwner} />
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
