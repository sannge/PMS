/**
 * KnowledgePanel
 *
 * Reusable two-panel knowledge base component for embedding in detail pages.
 * Left panel: search, creation buttons, folder/document tree.
 * Right panel: document editor or empty state.
 *
 * Wraps itself in a KnowledgeBaseProvider with a scoped storage prefix
 * so multiple mounted instances don't share localStorage state.
 */

import { useCallback, useRef, useEffect, useState } from 'react'
import { FileText, FilePlus, FolderPlus } from 'lucide-react'
import { cn } from '@/lib/utils'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  KnowledgeBaseProvider,
  useKnowledgeBase,
  type ScopeType,
} from '@/contexts/knowledge-base-context'
import { useAuthStore } from '@/contexts/auth-context'
import { useDocument, useCreateDocument } from '@/hooks/use-documents'
import { useCreateFolder } from '@/hooks/use-document-folders'
import { useSaveDocumentContent } from '@/hooks/use-queries'
import { SearchBar } from './search-bar'
import { FolderTree } from './folder-tree'
import { ApplicationTree } from './application-tree'
import { DocumentEditor } from './document-editor'
import { SaveStatus } from './SaveStatus'
import type { SaveStatus as SaveStatusType } from '@/hooks/use-auto-save'

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

/** Debounce delay for saving content changes (ms) */
const SAVE_DEBOUNCE_MS = 2000

/** Resize constraints for tree panel */
const MIN_TREE_WIDTH = 200
const MAX_TREE_WIDTH = 500
const DEFAULT_TREE_WIDTH = 280

function InnerPanel({ scope, scopeId, showProjectFolders, className }: InnerPanelProps) {
  const userId = useAuthStore((s) => s.user?.id ?? '')
  const userName = useAuthStore((s) => s.user?.display_name ?? s.user?.email ?? '')
  const { selectedDocumentId, selectDocument, selectFolder } = useKnowledgeBase()

  // Resizable tree panel state
  const [treeWidth, setTreeWidth] = useState(DEFAULT_TREE_WIDTH)
  const isResizingRef = useRef(false)
  const containerRef = useRef<HTMLDivElement>(null)

  // Document data for the editor (renamed to avoid shadowing global document)
  const { data: currentDoc } = useDocument(selectedDocumentId)

  // Save mutation for content changes
  const saveMutation = useSaveDocumentContent()
  const saveTimerRef = useRef<ReturnType<typeof setTimeout>>()
  const rowVersionRef = useRef(1)

  // Save status state
  const [saveStatus, setSaveStatus] = useState<SaveStatusType>({ state: 'idle' })

  // Keep row version in sync
  useEffect(() => {
    if (currentDoc?.row_version) {
      rowVersionRef.current = currentDoc.row_version
    }
  }, [currentDoc?.row_version])

  // Reset save status when document changes
  useEffect(() => {
    setSaveStatus({ state: 'idle' })
  }, [selectedDocumentId])

  // Cleanup timer on unmount
  useEffect(() => {
    return () => {
      if (saveTimerRef.current) {
        clearTimeout(saveTimerRef.current)
      }
    }
  }, [])

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
          selectFolder(null)
        },
      }
    )
  }, [scope, scopeId, createDocument, selectDocument, selectFolder])

  const handleCreateFolder = useCallback(() => {
    if (!scopeId) return
    createFolder.mutate({
      name: 'New Folder',
      scope,
      scope_id: scopeId,
      parent_id: null,
    })
  }, [scope, scopeId, createFolder])

  const handleEditorChange = useCallback(
    (json: object) => {
      if (!selectedDocumentId) return

      // Debounced save
      if (saveTimerRef.current) {
        clearTimeout(saveTimerRef.current)
      }

      saveTimerRef.current = setTimeout(() => {
        setSaveStatus({ state: 'saving' })

        saveMutation.mutate(
          {
            documentId: selectedDocumentId,
            content_json: JSON.stringify(json),
            row_version: rowVersionRef.current,
          },
          {
            onSuccess: (data) => {
              if (data.row_version) {
                rowVersionRef.current = data.row_version
              }
              setSaveStatus({ state: 'saved', at: Date.now() })
            },
            onError: (error) => {
              setSaveStatus({ state: 'error', message: error.message })
            },
          }
        )
      }, SAVE_DEBOUNCE_MS)
    },
    [selectedDocumentId, saveMutation]
  )

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

        {/* Tree */}
        <ScrollArea className="flex-1">
          {scope === 'application' && showProjectFolders ? (
            <ApplicationTree applicationId={scopeId} />
          ) : (
            <FolderTree />
          )}
        </ScrollArea>
      </div>

      {/* Resize handle */}
      <div
        className="w-1 cursor-col-resize bg-border hover:bg-primary/50 transition-colors flex-shrink-0"
        onMouseDown={handleResizeMouseDown}
      />

      {/* Right panel: editor or empty state */}
      <div className="flex-1 flex flex-col min-w-0">
        {selectedDocumentId && currentDoc ? (
          <>
            {/* Save status indicator */}
            <div className="flex items-center justify-end px-4 py-1 border-b bg-muted/30">
              <SaveStatus status={saveStatus} />
            </div>

            {/* Document editor */}
            <DocumentEditor
              content={currentDoc.content_json ? JSON.parse(currentDoc.content_json) : undefined}
              onChange={handleEditorChange}
              editable={true}
              placeholder="Start writing..."
              documentId={selectedDocumentId}
              userId={userId}
              userName={userName}
              className="flex-1 border-0 rounded-none"
            />
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground gap-3">
            <FileText className="h-12 w-12 text-muted-foreground/30" />
            <p className="text-sm">Select a document to start editing</p>
          </div>
        )}
      </div>
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
