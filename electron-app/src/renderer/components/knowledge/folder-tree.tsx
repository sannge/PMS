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
import { FilePlus, Folder, FileText, Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import {
  DndContext,
  DragEndEvent,
  DragOverlay,
  DragStartEvent,
  PointerSensor,
  useSensor,
  useSensors,
  closestCenter,
} from '@dnd-kit/core'
import {
  SortableContext,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/contexts/auth-context'
import { useKnowledgeBase } from '@/contexts/knowledge-base-context'
import {
  useFolderTree,
  useCreateFolder,
  useRenameFolder,
  useDeleteFolder,
  useReorderFolder,
  type FolderTreeNode,
} from '@/hooks/use-document-folders'
import {
  useDocuments,
  useCreateDocument,
  useRenameDocument,
  useDeleteDocument,
  useReorderDocument,
  type DocumentListItem,
} from '@/hooks/use-documents'
import { FolderTreeItem } from './folder-tree-item'
import { FolderContextMenu } from './folder-context-menu'
import { CreateDialog } from './create-dialog'
import { DeleteDialog } from './delete-dialog'

// ============================================================================
// Types
// ============================================================================

interface ContextMenuTarget {
  id: string
  type: 'folder' | 'document'
  name: string
  x: number
  y: number
}

interface ActiveDragItem {
  id: string
  type: 'folder' | 'document'
  name: string
}

// ============================================================================
// Skeleton
// ============================================================================

/**
 * Tree item skeleton - matches FolderTreeItem layout (icon + text)
 */
function TreeItemSkeleton({ depth = 0, widthPercent = 60 }: { depth?: number; widthPercent?: number }): JSX.Element {
  return (
    <div
      className="flex items-center gap-1.5 py-1 pr-2"
      style={{ paddingLeft: depth * 20 + 12 }}
    >
      <div className="h-4 w-4 rounded bg-muted animate-pulse shrink-0" />
      <div
        className="h-4 rounded bg-muted animate-pulse"
        style={{ width: `${widthPercent}%` }}
      />
    </div>
  )
}

function FolderTreeSkeleton(): JSX.Element {
  return (
    <div className="py-1 space-y-0.5">
      {/* Folder skeleton */}
      <TreeItemSkeleton depth={0} widthPercent={55} />
      {/* Nested document skeletons */}
      <TreeItemSkeleton depth={1} widthPercent={70} />
      <TreeItemSkeleton depth={1} widthPercent={50} />
      {/* Another folder */}
      <TreeItemSkeleton depth={0} widthPercent={45} />
      {/* Nested items */}
      <TreeItemSkeleton depth={1} widthPercent={65} />
      <TreeItemSkeleton depth={2} widthPercent={60} />
    </div>
  )
}

// ============================================================================
// Main Component
// ============================================================================

export function FolderTree(): JSX.Element {
  const {
    scope,
    scopeId,
    expandedFolderIds,
    selectedFolderId,
    selectedDocumentId,
    searchQuery,
    toggleFolder,
    expandFolder,
    selectDocument,
    selectFolder,
  } = useKnowledgeBase()

  // Auth state for personal scope resolution
  const userId = useAuthStore((s) => s.user?.id ?? null)

  // Data queries
  const {
    data: folderTree,
    isLoading: isFoldersLoading,
    isFetching: isFoldersFetching,
  } = useFolderTree(scope, scopeId)

  const {
    data: unfiledResponse,
    isLoading: isUnfiledLoading,
  } = useDocuments(scope, scopeId, { includeUnfiled: true })

  // Mutations
  const createFolder = useCreateFolder()
  const createDocument = useCreateDocument()
  const renameFolder = useRenameFolder(scope, scopeId ?? '')
  const renameDocument = useRenameDocument(scope, scopeId ?? '')
  const deleteFolder = useDeleteFolder(scope, scopeId ?? '')
  const deleteDocument = useDeleteDocument(scope, scopeId ?? '')
  const reorderFolder = useReorderFolder(scope, scopeId ?? '')
  const reorderDocument = useReorderDocument(scope, scopeId ?? '')

  // ========================================================================
  // Drag and drop state
  // ========================================================================

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 5 },
    })
  )

  const [activeItem, setActiveItem] = useState<ActiveDragItem | null>(null)

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

  const isLoading = isFoldersLoading && isUnfiledLoading

  const folders = folderTree ?? []
  const unfiledDocs = unfiledResponse?.items ?? []

  // ========================================================================
  // Search filtering
  // ========================================================================

  const matchesSearch = useCallback((text: string): boolean => {
    if (!searchQuery) return true
    return text.toLowerCase().includes(searchQuery.toLowerCase())
  }, [searchQuery])

  const filterFolderTree = useCallback((nodes: FolderTreeNode[]): FolderTreeNode[] => {
    if (!searchQuery) return nodes

    return nodes.reduce<FolderTreeNode[]>((acc, node) => {
      const filteredChildren = filterFolderTree(node.children)
      const hasMatchingChildren = filteredChildren.length > 0
      const nodeMatches = matchesSearch(node.name)

      if (nodeMatches || hasMatchingChildren) {
        acc.push({
          ...node,
          children: filteredChildren,
        })
      }
      return acc
    }, [])
  }, [searchQuery, matchesSearch])

  const filteredFolders = useMemo(
    () => filterFolderTree(folders),
    [filterFolderTree, folders]
  )

  const filteredDocs = useMemo(() => {
    if (!searchQuery) return unfiledDocs
    return unfiledDocs.filter(doc => matchesSearch(doc.title))
  }, [unfiledDocs, searchQuery, matchesSearch])

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

  // Create flat list of sortable IDs for DndContext
  const sortableItems = useMemo(() => {
    const items: string[] = []

    // Add all folders (flattened recursively)
    const addFolders = (nodes: FolderTreeNode[]) => {
      nodes.forEach(node => {
        items.push(`folder-${node.id}`)
        addFolders(node.children)
      })
    }
    addFolders(filteredFolders)

    // Add unfiled documents
    filteredDocs.forEach(doc => {
      items.push(`doc-${doc.id}`)
    })

    return items
  }, [filteredFolders, filteredDocs])

  // Helper to find folder by id from tree
  const findFolderById = useCallback((nodes: FolderTreeNode[], id: string): FolderTreeNode | null => {
    for (const node of nodes) {
      if (node.id === id) return node
      const found = findFolderById(node.children, id)
      if (found) return found
    }
    return null
  }, [])

  const handleDragStart = useCallback((event: DragStartEvent) => {
    const { active } = event
    const activeIdStr = String(active.id)
    const [type, id] = activeIdStr.split('-')

    if (type === 'folder') {
      const folder = findFolderById(filteredFolders, id)
      if (folder) {
        setActiveItem({ id, type: 'folder', name: folder.name })
      }
    } else if (type === 'doc') {
      const doc = filteredDocs.find(d => d.id === id)
      if (doc) {
        setActiveItem({ id, type: 'document', name: doc.title })
      }
    }
  }, [filteredFolders, filteredDocs, findFolderById])

  const handleDragEnd = useCallback(async (event: DragEndEvent) => {
    const { active, over } = event
    setActiveItem(null)

    if (!over || active.id === over.id) return

    const activeIdStr = String(active.id)
    const overIdStr = String(over.id)

    const [activeType, activeId] = activeIdStr.split('-')
    const [overType] = overIdStr.split('-')

    // Only allow reordering within same type (folder with folders, doc with docs)
    // This prevents cross-type moves which could cause confusion
    if (activeType !== overType) {
      return
    }

    // Find the new position index
    const overIndex = sortableItems.indexOf(overIdStr)
    if (overIndex === -1) return

    // Calculate new sort_order based on surrounding items
    // Using simple index-based ordering for now
    const newSortOrder = overIndex

    try {
      if (activeType === 'folder') {
        await reorderFolder.mutateAsync({
          folderId: activeId,
          sortOrder: newSortOrder,
        })
      } else if (activeType === 'doc') {
        // Documents need row_version, use 1 as default
        await reorderDocument.mutateAsync({
          documentId: activeId,
          sortOrder: newSortOrder,
          rowVersion: 1,
        })
      }
    } catch (error) {
      console.error('Failed to reorder:', error)
      toast.error('Failed to reorder item')
    }
  }, [sortableItems, reorderFolder, reorderDocument])

  // ========================================================================
  // Context menu handlers
  // ========================================================================

  const handleContextMenu = useCallback(
    (e: React.MouseEvent, id: string, type: 'folder' | 'document', name: string) => {
      e.preventDefault()
      e.stopPropagation()
      setContextMenuTarget({ id, type, name, x: e.clientX, y: e.clientY })
    },
    []
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
        selectFolder(null)
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
    [scope, scopeId, userId, createType, createParentId, createDocument, createFolder, selectDocument, selectFolder, expandFolder]
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
    (newName: string) => {
      if (!renamingItemId) return

      if (renamingItemType === 'folder') {
        renameFolder.mutate({ folderId: renamingItemId, name: newName })
      } else {
        // For documents we need row_version; use 1 as default since rename
        // via context menu is on newly visible items. The API will reject
        // conflicts with a 409 if stale.
        renameDocument.mutate({
          documentId: renamingItemId,
          title: newName,
          row_version: 1,
        })
      }

      setRenamingItemId(null)
    },
    [renamingItemId, renamingItemType, renameFolder, renameDocument]
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
          ? folders.find((f) => f.id === id)?.name || 'this folder'
          : unfiledDocs.find((d) => d.id === id)?.title || 'this document'
      setDeleteTarget({ id, type, name })
      setDeleteDialogOpen(true)
    },
    [folders, unfiledDocs, handleCloseContextMenu]
  )

  const handleDeleteConfirm = useCallback(async () => {
    if (!deleteTarget) return
    if (deleteTarget.type === 'folder') {
      await deleteFolder.mutateAsync(deleteTarget.id)
      if (selectedFolderId === deleteTarget.id) selectFolder(null)
    } else {
      await deleteDocument.mutateAsync(deleteTarget.id)
      if (selectedDocumentId === deleteTarget.id) selectDocument(null)
    }
  }, [deleteTarget, deleteFolder, deleteDocument, selectedFolderId, selectedDocumentId, selectFolder, selectDocument])

  // ========================================================================
  // Selection handlers
  // ========================================================================

  const handleSelectFolder = useCallback(
    (folderId: string) => {
      toggleFolder(folderId)
      selectFolder(folderId)
      selectDocument(null)
    },
    [toggleFolder, selectFolder, selectDocument]
  )

  const handleSelectDocument = useCallback(
    (documentId: string) => {
      selectDocument(documentId)
      selectFolder(null)
    },
    [selectDocument, selectFolder]
  )

  // ========================================================================
  // Create first document (empty state)
  // ========================================================================

  const handleCreateFirstDocument = useCallback(() => {
    const resolvedScopeId = scope === 'personal' ? (userId ?? '') : (scopeId ?? '')
    createDocument.mutate(
      {
        title: 'Untitled',
        scope,
        scope_id: resolvedScopeId,
      },
      {
        onSuccess: (data) => {
          selectDocument(data.id)
          setRenamingItemId(data.id)
          setRenamingItemType('document')
        },
        onError: (error) => {
          toast.error(error.message)
        },
      }
    )
  }, [scope, scopeId, userId, createDocument, selectDocument])

  // ========================================================================
  // Recursive folder renderer
  // ========================================================================

  const renderFolderNode = useCallback(
    (node: FolderTreeNode, depth: number): JSX.Element => {
      const isExpanded = expandedFolderIds.has(node.id)
      const isSelected = selectedFolderId === node.id

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
            sortableId={`folder-${node.id}`}
            onToggleExpand={() => toggleFolder(node.id)}
            onSelect={() => handleSelectFolder(node.id)}
            onContextMenu={(e) => handleContextMenu(e, node.id, 'folder', node.name)}
            onRenameSubmit={handleRenameSubmit}
            onRenameCancel={handleRenameCancel}
          />
          {isExpanded &&
            node.children.map((child) => renderFolderNode(child, depth + 1))}
        </div>
      )
    },
    [
      expandedFolderIds,
      selectedFolderId,
      renamingItemId,
      activeItem,
      toggleFolder,
      handleSelectFolder,
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
          sortableId={`doc-${doc.id}`}
          onSelect={() => handleSelectDocument(doc.id)}
          onContextMenu={(e) => handleContextMenu(e, doc.id, 'document', doc.title)}
          onRenameSubmit={handleRenameSubmit}
          onRenameCancel={handleRenameCancel}
        />
      )
    },
    [
      selectedDocumentId,
      renamingItemId,
      activeItem,
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
    return <FolderTreeSkeleton />
  }

  const hasNoData = folders.length === 0 && unfiledDocs.length === 0
  const hasNoResults = filteredFolders.length === 0 && filteredDocs.length === 0

  // Empty state - no data at all
  if (hasNoData) {
    return (
      <div className="flex flex-col items-center justify-center p-6 text-center">
        <p className="text-sm text-muted-foreground mb-3">No documents yet</p>
        <button
          onClick={handleCreateFirstDocument}
          disabled={createDocument.isPending}
          className={cn(
            'inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-md',
            'bg-primary text-primary-foreground hover:bg-primary/90',
            'transition-colors',
            'disabled:pointer-events-none disabled:opacity-50'
          )}
        >
          {createDocument.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <FilePlus className="h-4 w-4" />
          )}
          {createDocument.isPending ? 'Creating...' : 'Create your first document'}
        </button>
      </div>
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
      onDragEnd={handleDragEnd}
    >
      <SortableContext items={sortableItems} strategy={verticalListSortingStrategy}>
        <div className="py-1" role="tree">
          {/* Subtle background refresh indicator */}
          {isFoldersFetching && !isFoldersLoading && (
            <div className="flex items-center justify-end px-2 pb-0.5">
              <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
            </div>
          )}

          {/* Folder tree */}
          {filteredFolders.map((node) => renderFolderNode(node, 0))}

          {/* Root-level documents (no folder) */}
          {filteredDocs.length > 0 && (
            <>
              {filteredDocs.map((doc) => renderDocumentItem(doc, 0))}
            </>
          )}
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
