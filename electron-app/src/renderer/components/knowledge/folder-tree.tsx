/**
 * Folder Tree
 *
 * Recursive folder tree component with expand/collapse, unfiled documents section,
 * loading skeleton, context menu integration, and drag-and-drop reordering.
 *
 * Loading behavior (CACHE-03): The tree renders immediately from IndexedDB cache.
 * A loading skeleton is only shown when there is no data at all (including no cache).
 * Background refetches do not trigger spinners or skeletons.
 *
 * Drag-and-drop: Uses @dnd-kit for reordering items within the same scope.
 * Cross-scope moves are prevented per CONTEXT.md constraints.
 */

import { useState, useCallback, useMemo, useEffect } from 'react'
import { FilePlus, Folder, FileText } from 'lucide-react'
import { toast } from 'sonner'
import {
  DndContext,
  DragEndEvent,
  DragOverEvent,
  DragOverlay,
  DragStartEvent,
  PointerSensor,
  useSensor,
  useSensors,
  closestCenter,
} from '@dnd-kit/core'
import {
  SortableContext,
} from '@dnd-kit/sortable'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/contexts/auth-context'
import { useKnowledgeBase } from '@/contexts/knowledge-base-context'
import { useQueryClient } from '@tanstack/react-query'
import { queryKeys } from '@/lib/query-client'
import {
  useFolderTree,
  useCreateFolder,
  useRenameFolder,
  useDeleteFolder,
  useMoveFolder,
  type FolderTreeNode,
} from '@/hooks/use-document-folders'
import {
  useDocuments,
  useCreateDocument,
  useRenameDocument,
  useDeleteDocument,
  useMoveDocument,
  type Document,
  type DocumentListItem,
  type DocumentListResponse,
} from '@/hooks/use-documents'
import { useActiveLocks } from '@/hooks/use-document-lock'
import { FolderTreeItem } from './folder-tree-item'
import { FolderDocuments } from './folder-documents'
import { TreeSkeleton } from './tree-skeletons'
import { RootDropZone, ROOT_DROP_ZONE_ID } from './root-drop-zone'
import { FolderContextMenu } from './folder-context-menu'
import { CreateDialog } from './create-dialog'
import { DeleteDialog } from './delete-dialog'
import { matchesSearch, filterFolderTree, findFolderById, isDescendantOf } from './tree-utils'
import { parseSortableId } from './dnd-utils'

// ============================================================================
// Types
// ============================================================================

interface ContextMenuTarget {
  id: string
  type: 'folder' | 'document'
  name: string
  x: number
  y: number
  scope: string
  scopeId: string
}

interface ActiveDragItem {
  id: string
  type: 'folder' | 'document'
  name: string
  /** For documents: the folder_id at drag start (cached to avoid repeated query scans) */
  folderId: string | null
}

// ============================================================================
// Main Component
// ============================================================================

export function FolderTree(): JSX.Element {
  const {
    scope,
    scopeId,
    expandedFolderIds,
    selectedDocumentId,
    searchQuery,
    toggleFolder,
    expandFolder,
    selectDocument,
  } = useKnowledgeBase()

  // Auth state for personal scope resolution
  const userId = useAuthStore((s) => s.user?.id ?? null)

  // Data queries
  const {
    data: folderTree,
    isLoading: isFoldersLoading,
  } = useFolderTree(scope, scopeId)

  const {
    data: unfiledResponse,
    isLoading: isUnfiledLoading,
  } = useDocuments(scope, scopeId, { includeUnfiled: true })

  // Active locks for the current scope (single batch request replaces N per-document queries)
  const activeLocks = useActiveLocks(scope, scopeId)

  // Mutations
  const queryClient = useQueryClient()
  const createFolder = useCreateFolder()
  const createDocument = useCreateDocument()
  const renameFolder = useRenameFolder()
  const renameDocument = useRenameDocument()
  const deleteFolder = useDeleteFolder()
  const deleteDocument = useDeleteDocument()
  const moveFolder = useMoveFolder()
  const moveDocument = useMoveDocument()

  /** Find a document's list item data from TanStack Query cache. */
  const findDocInCache = useCallback((documentId: string): DocumentListItem | null => {
    const lists = queryClient.getQueriesData<DocumentListResponse>({
      queryKey: queryKeys.documents(scope, scopeId ?? ''),
      exact: false,
    })
    for (const [, data] of lists) {
      const item = data?.items.find(i => i.id === documentId)
      if (item) return item
    }
    return null
  }, [queryClient, scope, scopeId])

  /** Look up a document's current row_version from TanStack Query cache. */
  const getDocRowVersion = useCallback((documentId: string): number | null => {
    const doc = queryClient.getQueryData<Document>(queryKeys.document(documentId))
    if (doc?.row_version) return doc.row_version
    return findDocInCache(documentId)?.row_version ?? null
  }, [queryClient, findDocInCache])

  // ========================================================================
  // Drag and drop state
  // ========================================================================

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 5 },
    })
  )

  const [activeItem, setActiveItem] = useState<ActiveDragItem | null>(null)
  const [dropTargetFolderId, setDropTargetFolderId] = useState<string | null>(null)

  // Local UI state
  const [renamingItemId, setRenamingItemId] = useState<string | null>(null)
  const [renamingItemType, setRenamingItemType] = useState<'folder' | 'document'>('folder')
  const [contextMenuTarget, setContextMenuTarget] = useState<ContextMenuTarget | null>(null)

  // Dialog state
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [createType, setCreateType] = useState<'document' | 'folder'>('document')
  const [createParentId, setCreateParentId] = useState<string | null>(null)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<{
    id: string
    type: 'document' | 'folder'
    name: string
  } | null>(null)

  const folders = folderTree ?? []
  const unfiledDocs = unfiledResponse?.items ?? []

  // Show skeleton when at least one query is loading and we have no data yet
  const isLoading = (isFoldersLoading || isUnfiledLoading) && folders.length === 0 && unfiledDocs.length === 0

  // ========================================================================
  // Search filtering
  // ========================================================================

  const filteredFolders = useMemo(
    () => filterFolderTree(folders, searchQuery),
    [folders, searchQuery]
  )

  const filteredDocs = useMemo(() => {
    if (!searchQuery) return unfiledDocs
    return unfiledDocs.filter(doc => matchesSearch(doc.title, searchQuery))
  }, [unfiledDocs, searchQuery])

  // Auto-expand folders with matching children when searching
  useEffect(() => {
    if (!searchQuery) return

    const expandMatchingFolders = (nodes: FolderTreeNode[]) => {
      nodes.forEach(node => {
        if (node.children.length > 0) {
          // Expand folder if it has children that match or contain matches
          expandFolder(node.id)
          expandMatchingFolders(node.children)
        }
      })
    }

    expandMatchingFolders(filteredFolders)
  }, [searchQuery, filteredFolders, expandFolder])

  // ========================================================================
  // Drag and drop handlers
  // ========================================================================

  // Sortable IDs for DnD (no reordering - only used for drag identification)
  const sortableItems = useMemo(() => {
    const items: string[] = []
    const addFolders = (nodes: FolderTreeNode[]) => {
      nodes.forEach(node => {
        items.push(`${scope}-folder-${node.id}`)
        addFolders(node.children)
      })
    }
    addFolders(filteredFolders)
    filteredDocs.forEach(doc => {
      items.push(`${scope}-doc-${doc.id}`)
    })
    return items
  }, [scope, filteredFolders, filteredDocs])

  // No-op sorting strategy: items are alphabetically ordered by the backend
  const noReorderStrategy = useCallback(() => null, [])

  const validPrefixes = useMemo(() => [scope], [scope])

  const parse = useCallback((sortableId: string) => {
    return parseSortableId(sortableId, validPrefixes)
  }, [validPrefixes])

  const handleDragStart = useCallback((event: DragStartEvent) => {
    const parsed = parse(String(event.active.id))
    if (!parsed) return

    let name = 'Item'
    if (parsed.type === 'folder') {
      const folder = findFolderById(filteredFolders, parsed.itemId)
      if (folder) name = folder.name
    } else {
      const doc = filteredDocs.find(d => d.id === parsed.itemId)
      if (doc) name = doc.title
    }

    const folderId = parsed.type === 'document' ? (findDocInCache(parsed.itemId)?.folder_id ?? null) : null
    setActiveItem({ id: parsed.itemId, type: parsed.type, name, folderId })
  }, [filteredFolders, filteredDocs, parse, findDocInCache])

  const handleDragOver = useCallback((event: DragOverEvent) => {
    const { over, active } = event
    if (!over || !active) {
      setDropTargetFolderId(null)
      return
    }
    const activeParsed = parse(String(active.id))
    const overParsed = parse(String(over.id))
    if (!activeParsed || !overParsed) {
      setDropTargetFolderId(null)
      return
    }
    if (overParsed.type === 'folder' && activeParsed.itemId !== overParsed.itemId) {
      setDropTargetFolderId(overParsed.itemId)
    } else if (overParsed.type === 'document') {
      // Resolve the document's parent folder so hovering over a child doc highlights the folder
      const parentFolderId = findDocInCache(overParsed.itemId)?.folder_id ?? null
      if (
        parentFolderId &&
        // Don't highlight if dragging the parent folder itself
        activeParsed.itemId !== parentFolderId &&
        // Don't highlight if dragging a doc already in that folder (use cached folderId from drag start)
        !(activeParsed.type === 'document' && activeItem?.folderId === parentFolderId) &&
        // Don't highlight if dragging a folder into its own descendant
        !(activeParsed.type === 'folder' && isDescendantOf(folders, activeParsed.itemId, parentFolderId))
      ) {
        setDropTargetFolderId(parentFolderId)
      } else {
        setDropTargetFolderId(null)
      }
    } else {
      setDropTargetFolderId(null)
    }
  }, [parse, findDocInCache, folders, activeItem])

  /** Check if a folder is at root level (no parent) */
  const isRootFolder = useCallback((folderId: string): boolean => {
    return folders.some(f => f.id === folderId)
  }, [folders])

  /** Check if a document is at root level (unfiled) */
  const isRootDocument = useCallback((documentId: string): boolean => {
    return unfiledDocs.some(d => d.id === documentId)
  }, [unfiledDocs])

  /** Move an item to root */
  const moveItemToRoot = useCallback(async (parsed: { type: 'folder' | 'document'; itemId: string }) => {
    if (parsed.type === 'document') {
      const docFolderId = findDocInCache(parsed.itemId)?.folder_id
      if (docFolderId) {
        const rowVersion = getDocRowVersion(parsed.itemId)
        if (!rowVersion) {
          toast.error('Could not determine document version. Please try again.')
          return
        }
        await moveDocument.mutateAsync({ documentId: parsed.itemId, folder_id: null, row_version: rowVersion, scope, scopeId: scopeId ?? '' })
        toast.success('Moved to root')
      }
    } else {
      const activeIsRoot = isRootFolder(parsed.itemId)
      if (!activeIsRoot) {
        await moveFolder.mutateAsync({ folderId: parsed.itemId, parent_id: null, scope, scopeId: scopeId ?? '' })
        toast.success('Moved to root')
      }
    }
  }, [findDocInCache, getDocRowVersion, moveDocument, moveFolder, isRootFolder])

  const handleDragEnd = useCallback(async (event: DragEndEvent) => {
    const { active, over } = event
    setActiveItem(null)
    setDropTargetFolderId(null)

    if (!over || active.id === over.id) return

    const activeParsed = parse(String(active.id))

    // Case 0: Dropping onto root drop zone → move to root
    if (String(over.id) === ROOT_DROP_ZONE_ID) {
      if (!activeParsed) return
      try {
        await moveItemToRoot(activeParsed)
      } catch (error) {
        console.error('Failed to move:', error)
        toast.error(error instanceof Error ? error.message : 'Failed to move item')
      }
      return
    }

    const overParsed = parse(String(over.id))
    if (!activeParsed || !overParsed) return

    // Resolve effective drop target: if dropping on a document inside a folder,
    // treat it as dropping onto that parent folder
    let effectiveTargetType = overParsed.type
    let effectiveTargetId = overParsed.itemId
    if (overParsed.type === 'document') {
      const parentFolderId = findDocInCache(overParsed.itemId)?.folder_id
      if (parentFolderId) {
        effectiveTargetType = 'folder'
        effectiveTargetId = parentFolderId
      }
    }

    try {
      // Case 1: Dropping onto a folder → move item inside
      if (effectiveTargetType === 'folder' && activeParsed.itemId !== effectiveTargetId) {
        if (activeParsed.type === 'folder') {
          if (activeParsed.itemId === effectiveTargetId || isDescendantOf(folders, activeParsed.itemId, effectiveTargetId)) {
            toast.error('Cannot move a folder into its own subfolder')
            return
          }
          await moveFolder.mutateAsync({ folderId: activeParsed.itemId, parent_id: effectiveTargetId, scope, scopeId: scopeId ?? '' })
          const targetFolder = findFolderById(folders, effectiveTargetId)
          toast.success(`Moved to ${targetFolder?.name ?? 'folder'}`)
        } else {
          // Skip if doc is already in this folder
          if (findDocInCache(activeParsed.itemId)?.folder_id === effectiveTargetId) return
          const rowVersion = getDocRowVersion(activeParsed.itemId)
          if (!rowVersion) {
            toast.error('Could not determine document version. Please try again.')
            return
          }
          await moveDocument.mutateAsync({ documentId: activeParsed.itemId, folder_id: effectiveTargetId, row_version: rowVersion, scope, scopeId: scopeId ?? '' })
          const targetFolder = findFolderById(folders, effectiveTargetId)
          toast.success(`Moved to ${targetFolder?.name ?? 'folder'}`)
        }
        expandFolder(effectiveTargetId)
        return
      }

      // Case 2: Dropping onto a root-level item → move to root if currently nested
      if (overParsed.type === 'document' || overParsed.type === 'folder') {
        const overIsRoot = overParsed.type === 'folder'
          ? isRootFolder(overParsed.itemId)
          : isRootDocument(overParsed.itemId)

        if (!overIsRoot) return

        await moveItemToRoot(activeParsed)
      }
    } catch (error) {
      console.error('Failed to move:', error)
      toast.error(error instanceof Error ? error.message : 'Failed to move item')
    }
  }, [parse, folders, moveFolder, moveDocument, expandFolder, getDocRowVersion, findDocInCache, isRootFolder, isRootDocument, moveItemToRoot])

  // ========================================================================
  // Context menu handlers
  // ========================================================================

  const handleContextMenu = useCallback(
    (e: React.MouseEvent, id: string, type: 'folder' | 'document', name: string) => {
      e.preventDefault()
      e.stopPropagation()
      // For documents, select to open in editor. Folders only highlight via contextMenuTarget.
      if (type === 'document') {
        selectDocument(id)
      }
      setContextMenuTarget({ id, type, name, x: e.clientX, y: e.clientY, scope, scopeId: scopeId ?? '' })
    },
    [scope, scopeId, selectDocument]
  )

  const handleCloseContextMenu = useCallback(() => {
    setContextMenuTarget(null)
  }, [])

  // ========================================================================
  // CRUD callbacks
  // ========================================================================

  const handleNewFolder = useCallback(
    (parentId: string) => {
      handleCloseContextMenu()
      setCreateType('folder')
      setCreateParentId(parentId)
      setCreateDialogOpen(true)
    },
    [handleCloseContextMenu]
  )

  const handleNewDocument = useCallback(
    (folderId: string) => {
      handleCloseContextMenu()
      setCreateType('document')
      setCreateParentId(folderId)
      setCreateDialogOpen(true)
    },
    [handleCloseContextMenu]
  )

  const handleCreateSubmit = useCallback(
    async (name: string) => {
      const resolvedScopeId = scope === 'personal' ? (userId ?? '') : (scopeId ?? '')

      if (createType === 'document') {
        const doc = await createDocument.mutateAsync({
          title: name,
          scope,
          scope_id: resolvedScopeId,
          folder_id: createParentId,
        })
        selectDocument(doc.id)
        if (createParentId) expandFolder(createParentId)
      } else {
        await createFolder.mutateAsync({
          name,
          scope,
          scope_id: resolvedScopeId,
          parent_id: createParentId,
        })
        if (createParentId) expandFolder(createParentId)
      }
    },
    [scope, scopeId, userId, createType, createParentId, createDocument, createFolder, selectDocument, expandFolder]
  )

  const handleRename = useCallback(
    (id: string, type: 'folder' | 'document') => {
      handleCloseContextMenu()
      setRenamingItemId(id)
      setRenamingItemType(type)
    },
    [handleCloseContextMenu]
  )

  const handleRenameSubmit = useCallback(
    async (newName: string) => {
      if (!renamingItemId) return

      try {
        if (renamingItemType === 'folder') {
          await renameFolder.mutateAsync({ folderId: renamingItemId, name: newName, scope, scopeId: scopeId ?? '' })
        } else {
          const rowVersion = getDocRowVersion(renamingItemId)
          if (!rowVersion) {
            toast.error('Could not determine document version. Please try again.')
            setRenamingItemId(null)
            return
          }
          await renameDocument.mutateAsync({
            documentId: renamingItemId,
            title: newName,
            row_version: rowVersion,
            scope,
            scopeId: scopeId ?? '',
          })
        }
      } catch (err) {
        toast.error(err instanceof Error ? err.message : 'Failed to rename')
      }

      setRenamingItemId(null)
    },
    [renamingItemId, renamingItemType, renameFolder, renameDocument, getDocRowVersion]
  )

  const handleRenameCancel = useCallback(() => {
    setRenamingItemId(null)
  }, [])

  const handleDelete = useCallback(
    (id: string, type: 'folder' | 'document') => {
      handleCloseContextMenu()
      // Find the name from the tree data
      const name =
        type === 'folder'
          ? findFolderById(folders, id)?.name || 'this folder'
          : findDocInCache(id)?.title || unfiledDocs.find((d) => d.id === id)?.title || 'this document'
      setDeleteTarget({ id, type, name })
      setDeleteDialogOpen(true)
    },
    [folders, unfiledDocs, handleCloseContextMenu, findDocInCache]
  )

  const handleDeleteConfirm = useCallback(async () => {
    if (!deleteTarget) return
    if (deleteTarget.type === 'folder') {
      await deleteFolder.mutateAsync({ folderId: deleteTarget.id, scope, scopeId: scopeId ?? '' })
    } else {
      await deleteDocument.mutateAsync({ documentId: deleteTarget.id, scope, scopeId: scopeId ?? '' })
      if (selectedDocumentId === deleteTarget.id) selectDocument(null)
    }
  }, [deleteTarget, deleteFolder, deleteDocument, selectedDocumentId, selectDocument])

  // ========================================================================
  // Selection handlers
  // ========================================================================

  const handleSelectDocument = useCallback(
    (documentId: string) => {
      selectDocument(documentId)
    },
    [selectDocument]
  )

  // ========================================================================
  // Create first document (empty state)
  // ========================================================================

  const handleCreateFirstDocument = useCallback(() => {
    setCreateType('document')
    setCreateParentId(null)
    setCreateDialogOpen(true)
  }, [])

  // ========================================================================
  // Recursive folder renderer
  // ========================================================================

  // Stable primitive for context-menu folder highlight (avoids object ref in deps)
  const contextMenuFolderId = contextMenuTarget?.type === 'folder' ? contextMenuTarget.id : null

  const renderFolderNode = useCallback(
    (node: FolderTreeNode, depth: number): JSX.Element => {
      const isExpanded = expandedFolderIds.has(node.id)
      const isSelected = contextMenuFolderId === node.id
      const isDropTarget = dropTargetFolderId === node.id

      return (
        <div key={node.id}>
          <FolderTreeItem
            node={node}
            type="folder"
            depth={depth}
            isExpanded={isExpanded}
            isSelected={isSelected}
            isRenaming={renamingItemId === node.id}
            isDragging={activeItem?.id === node.id && activeItem?.type === 'folder'}
            isDropTarget={isDropTarget}
            sortableId={`${scope}-folder-${node.id}`}
            onToggleExpand={() => toggleFolder(node.id)}
            onSelect={() => toggleFolder(node.id)}
            onContextMenu={(e) => handleContextMenu(e, node.id, 'folder', node.name)}
            onRenameSubmit={handleRenameSubmit}
            onRenameCancel={handleRenameCancel}
          />
          {isExpanded && (
            <>
              {node.children.map((child) => renderFolderNode(child, depth + 1))}
              <FolderDocuments
                scope={scope}
                scopeId={scopeId}
                folderId={node.id}
                depth={depth + 1}
                selectedDocumentId={selectedDocumentId}
                renamingItemId={renamingItemId}
                sortableIdPrefix={scope}
                activeItemId={activeItem?.type === 'document' ? activeItem.id : null}
                activeLocks={activeLocks}
                onSelectDocument={handleSelectDocument}
                onContextMenu={handleContextMenu}
                onRenameSubmit={handleRenameSubmit}
                onRenameCancel={handleRenameCancel}
              />
            </>
          )}
        </div>
      )
    },
    [
      scope,
      scopeId,
      expandedFolderIds,
      contextMenuFolderId,
      selectedDocumentId,
      renamingItemId,
      activeItem,
      dropTargetFolderId,
      activeLocks,
      toggleFolder,
      handleSelectDocument,
      handleContextMenu,
      handleRenameSubmit,
      handleRenameCancel,
    ]
  )

  const renderDocumentItem = useCallback(
    (doc: DocumentListItem, depth: number): JSX.Element => {
      const isSelected = selectedDocumentId === doc.id

      return (
        <FolderTreeItem
          key={doc.id}
          node={doc}
          type="document"
          depth={depth}
          isSelected={isSelected}
          isRenaming={renamingItemId === doc.id}
          isDragging={activeItem?.id === doc.id && activeItem?.type === 'document'}
          sortableId={`${scope}-doc-${doc.id}`}
          lockInfo={activeLocks.get(doc.id)}
          onSelect={() => handleSelectDocument(doc.id)}
          onContextMenu={(e) => handleContextMenu(e, doc.id, 'document', doc.title)}
          onRenameSubmit={handleRenameSubmit}
          onRenameCancel={handleRenameCancel}
        />
      )
    },
    [
      scope,
      selectedDocumentId,
      renamingItemId,
      activeItem,
      activeLocks,
      handleSelectDocument,
      handleContextMenu,
      handleRenameSubmit,
      handleRenameCancel,
    ]
  )

  // ========================================================================
  // Render
  // ========================================================================

  // Loading skeleton -- only when no data at all (CACHE-03)
  if (isLoading) {
    return <TreeSkeleton />
  }

  const hasNoData = folders.length === 0 && unfiledDocs.length === 0
  const hasNoResults = filteredFolders.length === 0 && filteredDocs.length === 0

  // Empty state - no data at all
  if (hasNoData) {
    return (
      <>
        <div className="flex flex-col items-center justify-center p-6 text-center">
          <p className="text-sm text-muted-foreground mb-3">No documents yet</p>
          <button
            onClick={handleCreateFirstDocument}
            className={cn(
              'inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md',
              'bg-primary text-primary-foreground hover:bg-primary/90',
              'transition-colors'
            )}
          >
            <FilePlus className="h-4 w-4" />
            Create your first document
          </button>
        </div>

        {/* Create dialog - must be rendered even in empty state */}
        <CreateDialog
          open={createDialogOpen}
          onOpenChange={setCreateDialogOpen}
          type={createType}
          onSubmit={handleCreateSubmit}
        />
      </>
    )
  }

  // No search results
  if (searchQuery && hasNoResults) {
    return (
      <div className="flex flex-col items-center justify-center p-6 text-center">
        <p className="text-sm text-muted-foreground">No results found</p>
      </div>
    )
  }

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragStart={handleDragStart}
      onDragOver={handleDragOver}
      onDragEnd={handleDragEnd}
    >
      <SortableContext items={sortableItems} strategy={noReorderStrategy}>
        <div className="py-1" role="tree">
          {/* Folder tree */}
          {filteredFolders.map((node) => renderFolderNode(node, 0))}

          {/* Root-level documents (no folder) */}
          {filteredDocs.length > 0 && (
            <>
              {filteredDocs.map((doc) => renderDocumentItem(doc, 0))}
            </>
          )}

          {/* Root drop zone - visible during drag for moving items to root */}
          {activeItem && <RootDropZone />}
        </div>
      </SortableContext>

      {/* Drag overlay */}
      <DragOverlay>
        {activeItem && (
          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-background border rounded-md shadow-lg opacity-90">
            {activeItem.type === 'folder' ? (
              <Folder className="h-4 w-4 text-muted-foreground" />
            ) : (
              <FileText className="h-4 w-4 text-muted-foreground" />
            )}
            <span className="text-sm truncate max-w-[200px]">{activeItem.name}</span>
          </div>
        )}
      </DragOverlay>

      {/* Context menu */}
      {contextMenuTarget && (
        <FolderContextMenu
          target={{
            id: contextMenuTarget.id,
            type: contextMenuTarget.type,
            name: contextMenuTarget.name,
          }}
          position={{ x: contextMenuTarget.x, y: contextMenuTarget.y }}
          onClose={handleCloseContextMenu}
          onNewFolder={handleNewFolder}
          onNewDocument={handleNewDocument}
          onRename={(id) =>
            handleRename(id, contextMenuTarget.type)
          }
          onDelete={handleDelete}
        />
      )}

      {/* Create dialog */}
      <CreateDialog
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
        type={createType}
        onSubmit={handleCreateSubmit}
      />

      {/* Delete dialog */}
      <DeleteDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        itemName={deleteTarget?.name || ''}
        itemType={deleteTarget?.type || 'document'}
        onConfirm={handleDeleteConfirm}
      />
    </DndContext>
  )
}

export default FolderTree
