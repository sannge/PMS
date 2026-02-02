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

import { useCallback, useRef, useEffect } from 'react'
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

function InnerPanel({ scope, scopeId, showProjectFolders, className }: InnerPanelProps) {
  const userId = useAuthStore((s) => s.user?.id ?? '')
  const { selectedDocumentId, selectDocument, selectFolder } = useKnowledgeBase()

  // Document data for the editor
  const { data: document } = useDocument(selectedDocumentId)

  // Save mutation for content changes
  const saveMutation = useSaveDocumentContent()
  const saveTimerRef = useRef<ReturnType<typeof setTimeout>>()
  const rowVersionRef = useRef(1)

  // Keep row version in sync
  useEffect(() => {
    if (document?.row_version) {
      rowVersionRef.current = document.row_version
    }
  }, [document?.row_version])

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
            },
          }
        )
      }, SAVE_DEBOUNCE_MS)
    },
    [selectedDocumentId, saveMutation]
  )

  return (
    <div className={cn('flex h-full border rounded-lg border-border overflow-hidden', className)}>
      {/* Left panel: tree */}
      <div className="w-64 flex-shrink-0 flex flex-col border-r border-border bg-sidebar">
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

      {/* Right panel: editor or empty state */}
      <div className="flex-1 flex flex-col min-w-0">
        {selectedDocumentId && document ? (
          <DocumentEditor
            content={document.content_json ? JSON.parse(document.content_json) : undefined}
            onChange={handleEditorChange}
            editable={true}
            placeholder="Start writing..."
            documentId={selectedDocumentId}
            userId={userId}
            className="flex-1"
          />
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
