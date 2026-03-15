/**
 * Knowledge Base Sidebar
 *
 * Main sidebar container that composes all sidebar sections:
 * - Quick creation buttons (new doc / new folder)
 * - Folder tree (KnowledgeTree component)
 * - Tag filter (TagFilterList with click-to-filter)
 *
 * Note: Search bar and tab bar are now at page level.
 * Supports collapsed/expanded modes and resizable width.
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { PanelLeftClose, PanelLeftOpen, FilePlus, FolderPlus, Upload, GripVertical } from 'lucide-react'
import { cn } from '@/lib/utils'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useKnowledgeBase } from '@/contexts/knowledge-base-context'
import { useAuthUserId } from '@/contexts/auth-context'
import { useCreateDocument } from '@/hooks/use-documents'
import { useCreateFolder } from '@/hooks/use-document-folders'
import { useUploadFile, type UploadConflictError } from '@/hooks/use-folder-files'
import { useKnowledgePermissions } from '@/hooks/use-knowledge-permissions'
import { KnowledgeTree } from './knowledge-tree'
import { TagFilterList } from './tag-filter-list'
import { CreateDialog } from './create-dialog'
import { FileConflictDialog } from './file-conflict-dialog'
import { createEmptyCanvas } from './canvas-types'
import { toast } from 'sonner'

const SIDEBAR_WIDTH_KEY = 'knowledge-sidebar-width'
const DEFAULT_WIDTH = 256
const MIN_WIDTH = 200
const MAX_WIDTH = 500

interface ConflictEntry {
  file: File
  existingFileId: string | null
}

export function KnowledgeSidebar(): JSX.Element {
  const {
    isSidebarCollapsed,
    toggleSidebar,
    activeTab,
    selectedFolderId,
  } = useKnowledgeBase()
  const userId = useAuthUserId()
  const createDocument = useCreateDocument()
  const createFolder = useCreateFolder()

  // Permissions
  const permScope = activeTab === 'personal' ? 'personal' as const : 'application' as const
  const permScopeId = activeTab === 'personal' ? null : activeTab.slice(4)
  const { canEdit } = useKnowledgePermissions(permScope, permScopeId)

  // Dialog state
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [createType, setCreateType] = useState<'document' | 'folder'>('document')

  // File upload
  const uploadFileInputRef = useRef<HTMLInputElement>(null)
  const uploadFileMutation = useUploadFile()

  // Conflict dialog state — supports sequential resolution of multiple conflicts
  const [conflictDialogOpen, setConflictDialogOpen] = useState(false)
  const [conflictQueue, setConflictQueue] = useState<ConflictEntry[]>([])
  const [conflictFolderId, setConflictFolderId] = useState<string | null>(null)
  const [conflictScope, setConflictScope] = useState<string | undefined>()
  const [conflictScopeId, setConflictScopeId] = useState<string | undefined>()

  // Derive current conflict from the front of the queue
  const conflictFile = conflictQueue.length > 0 ? conflictQueue[0].file : null
  const conflictExistingFileId = conflictQueue.length > 0 ? conflictQueue[0].existingFileId : null

  // When the conflict queue empties while the dialog is open, close the dialog.
  // This is done via useEffect instead of inside the setConflictQueue updater to
  // avoid clearing file/scope state while the dialog close animation is still
  // rendering (which would cause null props during the animation).
  useEffect(() => {
    if (conflictDialogOpen && conflictQueue.length === 0) {
      setConflictDialogOpen(false)
      setConflictFolderId(null)
      setConflictScope(undefined)
      setConflictScopeId(undefined)
    }
  }, [conflictDialogOpen, conflictQueue.length])

  // Resizable width state
  const [sidebarWidth, setSidebarWidth] = useState(() => {
    try {
      const stored = localStorage.getItem(SIDEBAR_WIDTH_KEY)
      const parsed = stored ? parseInt(stored, 10) : NaN
      return isNaN(parsed) ? DEFAULT_WIDTH : Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, parsed))
    } catch {
      return DEFAULT_WIDTH
    }
  })
  const [isResizing, setIsResizing] = useState(false)
  const sidebarRef = useRef<HTMLDivElement>(null)

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
      // Persist width to localStorage only on mouseup (not during drag)
      localStorage.setItem(SIDEBAR_WIDTH_KEY, String(
        Math.min(MAX_WIDTH, Math.max(MIN_WIDTH,
          sidebarRef.current
            ? sidebarRef.current.getBoundingClientRect().width
            : sidebarWidth
        ))
      ))
    }

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)

    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
  }, [isResizing, sidebarWidth])

  const resolveScope = useCallback(() => {
    if (activeTab === 'personal') {
      return { scope: 'personal' as const, scopeId: userId ?? '' }
    }
    const appId = activeTab.slice(4)
    return { scope: 'application' as const, scopeId: appId }
  }, [activeTab, userId])

  const handleCreateDocClick = () => {
    setCreateType('document')
    setCreateDialogOpen(true)
  }

  const handleCreateFolderClick = () => {
    setCreateType('folder')
    setCreateDialogOpen(true)
  }

  const handleCreateSubmit = async (name: string, format?: 'document' | 'canvas') => {
    const { scope, scopeId } = resolveScope()
    if (!scopeId) return

    // Close dialog immediately before mutation to prevent re-open on cache invalidation
    setCreateDialogOpen(false)

    try {
      if (createType === 'document') {
        await createDocument.mutateAsync({
          title: name,
          scope,
          scope_id: scopeId,
          folder_id: selectedFolderId || null, // Use selected folder
          content_json: format === 'canvas' ? JSON.stringify(createEmptyCanvas()) : undefined,
        })
        toast.success(format === 'canvas' ? 'Canvas created' : 'Document created')
      } else {
        await createFolder.mutateAsync({
          name,
          scope,
          scope_id: scopeId,
          parent_id: selectedFolderId || null, // Create inside selected folder
        })
        toast.success('Folder created')
      }
    } catch (err) {
      toast.error(
        createType === 'document'
          ? 'Failed to create document'
          : 'Failed to create folder'
      )
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
          {/* Quick creation buttons (hidden for read-only users) */}
          {canEdit && (
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
              <button
                onClick={() => uploadFileInputRef.current?.click()}
                className="p-1 rounded hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
                title="Upload files"
                aria-label="Upload files"
              >
                <Upload className="h-3.5 w-3.5" />
              </button>
            </div>
          )}

          {/* Create dialog */}
          <CreateDialog
            open={createDialogOpen}
            onOpenChange={setCreateDialogOpen}
            type={createType}
            onSubmit={handleCreateSubmit}
          />

          {/* Hidden file input for sidebar upload button */}
          <input
            ref={uploadFileInputRef}
            type="file"
            multiple
            onChange={async (e) => {
              const files = e.target.files
              if (!files || files.length === 0) return
              const { scope: resolvedScope, scopeId: resolvedScopeId } = resolveScope()
              const folderId = selectedFolderId ?? undefined
              const conflicts: { file: File; existingFileId: string | null }[] = []
              const total = files.length
              let uploaded = 0

              // Show progress toast for multi-file uploads
              const toastId = total > 1
                ? toast.loading(`Uploading 0/${total} files...`)
                : toast.loading(`Uploading ${files[0].name}...`)

              for (let i = 0; i < files.length; i++) {
                try {
                  await uploadFileMutation.mutateAsync({
                    file: files[i],
                    folderId,
                    scope: resolvedScope,
                    scopeId: resolvedScopeId,
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

              // Dismiss progress toast and show result
              if (uploaded > 0) {
                toast.success(
                  total === 1 ? `${files[0].name} uploaded` : `${uploaded} file${uploaded > 1 ? 's' : ''} uploaded`,
                  { id: toastId }
                )
              } else {
                toast.dismiss(toastId)
              }

              // Queue all conflicts for sequential resolution
              if (conflicts.length > 0) {
                setConflictQueue(conflicts)
                setConflictFolderId(folderId ?? null)
                setConflictScope(resolvedScope)
                setConflictScopeId(resolvedScopeId)
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
            folderId={conflictFolderId}
            scope={conflictScope}
            scopeId={conflictScopeId}
            existingFileId={conflictExistingFileId}
            onResolved={() => {
              // Remove the resolved conflict from the queue.
              // When the queue becomes empty, the useEffect above will
              // close the dialog and clear state on the next render,
              // avoiding null props during the close animation.
              setConflictQueue((prev) => prev.slice(1))
            }}
          />

          {/* Folder tree section */}
          <ScrollArea className="flex-1">
            <KnowledgeTree
              applicationId={activeTab.startsWith('app:') ? activeTab.slice(4) : undefined}
              canEdit={canEdit}
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
