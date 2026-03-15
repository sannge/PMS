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
import { FilePlus, FolderPlus, Upload } from 'lucide-react'
import { cn } from '@/lib/utils'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  KnowledgeBaseProvider,
  useKnowledgeBase,
  type ScopeType,
} from '@/contexts/knowledge-base-context'
import { useCreateDocument } from '@/hooks/use-documents'
import { useCreateFolder } from '@/hooks/use-document-folders'
import { useUploadFile, type UploadConflictError } from '@/hooks/use-folder-files'
import { createEmptyCanvas } from './canvas-types'
import { useKnowledgePermissions } from '@/hooks/use-knowledge-permissions'
import { SearchBar } from './search-bar'
import { KnowledgeTree } from './knowledge-tree'
import { EditorPanel } from './editor-panel'
import { CreateDialog } from './create-dialog'
import { FileConflictDialog } from './file-conflict-dialog'
import { toast } from 'sonner'

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

interface ConflictEntry {
  file: File
  existingFileId: string | null
}

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
  const { selectDocument, selectedFolderId } = useKnowledgeBase()

  // Resizable tree panel state
  const [treeWidth, setTreeWidth] = useState(DEFAULT_TREE_WIDTH)
  const isResizingRef = useRef(false)
  const containerRef = useRef<HTMLDivElement>(null)

  // Permissions
  const { canEdit, isOwner } = useKnowledgePermissions(scope, scopeId)

  // Creation mutations
  const createDocument = useCreateDocument()
  const createFolder = useCreateFolder()

  // Dialog state for name prompt
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [createType, setCreateType] = useState<'document' | 'folder'>('document')

  // File upload
  const uploadFileInputRef = useRef<HTMLInputElement>(null)
  const uploadFileMutation = useUploadFile()

  // Conflict dialog state
  const [conflictDialogOpen, setConflictDialogOpen] = useState(false)
  const [conflictQueue, setConflictQueue] = useState<ConflictEntry[]>([])

  const conflictFile = conflictQueue.length > 0 ? conflictQueue[0].file : null
  const conflictExistingFileId = conflictQueue.length > 0 ? conflictQueue[0].existingFileId : null

  // When the conflict queue empties while the dialog is open, close the dialog.
  useEffect(() => {
    if (conflictDialogOpen && conflictQueue.length === 0) {
      setConflictDialogOpen(false)
    }
  }, [conflictDialogOpen, conflictQueue.length])

  const handleCreateDocClick = useCallback(() => {
    setCreateType('document')
    setCreateDialogOpen(true)
  }, [])

  const handleCreateFolderClick = useCallback(() => {
    setCreateType('folder')
    setCreateDialogOpen(true)
  }, [])

  const handleCreateSubmit = useCallback(async (name: string, format?: 'document' | 'canvas') => {
    if (!scopeId) return

    // Close dialog immediately before mutation to prevent re-open on cache invalidation
    setCreateDialogOpen(false)

    if (createType === 'document') {
      const doc = await createDocument.mutateAsync({
        title: name,
        scope,
        scope_id: scopeId,
        folder_id: null,
        content_json: format === 'canvas' ? JSON.stringify(createEmptyCanvas()) : undefined,
      })
      selectDocument(doc.id)
    } else {
      await createFolder.mutateAsync({
        name,
        scope,
        scope_id: scopeId,
        parent_id: null,
      })
    }
  }, [createType, scope, scopeId, createDocument, createFolder, selectDocument])

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
              onClick={handleCreateDocClick}
              className="p-1 rounded hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
              title="New document"
            >
              <FilePlus className="h-4 w-4" />
            </button>
            <button
              onClick={handleCreateFolderClick}
              className="p-1 rounded hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
              title="New folder"
            >
              <FolderPlus className="h-4 w-4" />
            </button>
            <button
              onClick={() => uploadFileInputRef.current?.click()}
              className="p-1 rounded hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
              title="Upload files"
              aria-label="Upload files"
            >
              <Upload className="h-4 w-4" />
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

      {/* Create dialog */}
      <CreateDialog open={createDialogOpen} onOpenChange={setCreateDialogOpen} type={createType} onSubmit={handleCreateSubmit} />

      {/* Hidden file input for upload */}
      <input
        ref={uploadFileInputRef}
        type="file"
        multiple
        onChange={async (e) => {
          const files = e.target.files
          if (!files || files.length === 0) return
          const conflicts: ConflictEntry[] = []
          const total = files.length
          let uploaded = 0

          const toastId = total > 1
            ? toast.loading(`Uploading 0/${total} files...`)
            : toast.loading(`Uploading ${files[0].name}...`)

          for (let i = 0; i < files.length; i++) {
            try {
              await uploadFileMutation.mutateAsync({
                file: files[i],
                folderId: selectedFolderId ?? undefined,
                scope,
                scopeId,
              })
              uploaded++
              if (total > 1) {
                toast.loading(`Uploading ${uploaded}/${total} files...`, { id: toastId })
              }
            } catch (err) {
              const error = err as UploadConflictError
              if (error.status === 409) {
                conflicts.push({ file: files[i], existingFileId: error.existingFileId ?? null })
              } else {
                toast.error(`Failed to upload ${files[i].name}: ${error.message}`)
              }
            }
          }

          if (uploaded > 0) {
            toast.success(
              total === 1 ? `${files[0].name} uploaded` : `${uploaded} file${uploaded > 1 ? 's' : ''} uploaded`,
              { id: toastId }
            )
          } else {
            toast.dismiss(toastId)
          }

          if (conflicts.length > 0) {
            setConflictQueue(conflicts)
            setConflictDialogOpen(true)
            if (conflicts.length > 1) {
              toast.info(`${conflicts.length} files had conflicts. Resolve them one at a time.`)
            }
          }

          e.target.value = ''
        }}
        className="hidden"
        aria-hidden="true"
      />

      {/* File conflict dialog */}
      <FileConflictDialog
        open={conflictDialogOpen}
        onOpenChange={setConflictDialogOpen}
        file={conflictFile}
        folderId={selectedFolderId ?? null}
        scope={scope}
        scopeId={scopeId}
        existingFileId={conflictExistingFileId}
        onResolved={() => {
          setConflictQueue((prev) => prev.slice(1))
        }}
      />
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
