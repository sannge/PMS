/**
 * Folder Tree
 *
 * Recursive folder tree component with expand/collapse, unfiled documents section,
 * loading skeleton, and context menu integration.
 *
 * Loading behavior (CACHE-03): The tree renders immediately from IndexedDB cache.
 * A loading skeleton is only shown when there is no data at all (including no cache).
 * Background refetches do not trigger spinners or skeletons.
 */

import { useState, useCallback } from 'react'
import { FilePlus, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useKnowledgeBase } from '@/contexts/knowledge-base-context'
import {
  useFolderTree,
  useCreateFolder,
  useRenameFolder,
  useDeleteFolder,
  type FolderTreeNode,
} from '@/hooks/use-document-folders'
import {
  useDocuments,
  useCreateDocument,
  useRenameDocument,
  useDeleteDocument,
  type DocumentListItem,
} from '@/hooks/use-documents'
import { FolderTreeItem } from './folder-tree-item'
import { FolderContextMenu } from './folder-context-menu'

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

// ============================================================================
// Skeleton
// ============================================================================

function FolderTreeSkeleton(): JSX.Element {
  const rows = [
    { width: '60%', paddingLeft: 8 },
    { width: '80%', paddingLeft: 24 },
    { width: '50%', paddingLeft: 24 },
    { width: '70%', paddingLeft: 40 },
  ]

  return (
    <div className="p-2 space-y-1.5">
      {rows.map((row, i) => (
        <div
          key={i}
          className="h-6 rounded animate-pulse bg-muted"
          style={{ width: row.width, marginLeft: row.paddingLeft }}
        />
      ))}
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
    toggleFolder,
    expandFolder,
    selectDocument,
    selectFolder,
  } = useKnowledgeBase()

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

  // Local UI state
  const [renamingItemId, setRenamingItemId] = useState<string | null>(null)
  const [renamingItemType, setRenamingItemType] = useState<'folder' | 'document'>('folder')
  const [contextMenuTarget, setContextMenuTarget] = useState<ContextMenuTarget | null>(null)

  const isLoading = isFoldersLoading && isUnfiledLoading

  const folders = folderTree ?? []
  const unfiledDocs = unfiledResponse?.items ?? []

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
      const resolvedScopeId = scopeId ?? ''
      createFolder.mutate(
        {
          name: 'New Folder',
          parent_id: parentId,
          scope,
          scope_id: resolvedScopeId,
        },
        {
          onSuccess: (data) => {
            expandFolder(parentId)
            setRenamingItemId(data.id)
            setRenamingItemType('folder')
          },
        }
      )
    },
    [scope, scopeId, createFolder, expandFolder, handleCloseContextMenu]
  )

  const handleNewDocument = useCallback(
    (folderId: string) => {
      handleCloseContextMenu()
      const resolvedScopeId = scopeId ?? ''
      createDocument.mutate(
        {
          title: 'Untitled',
          scope,
          scope_id: resolvedScopeId,
          folder_id: folderId,
        },
        {
          onSuccess: (data) => {
            expandFolder(folderId)
            selectDocument(data.id)
            selectFolder(null)
            setRenamingItemId(data.id)
            setRenamingItemType('document')
          },
        }
      )
    },
    [scope, scopeId, createDocument, expandFolder, selectDocument, selectFolder, handleCloseContextMenu]
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
      if (type === 'folder') {
        deleteFolder.mutate(id)
        if (selectedFolderId === id) {
          selectFolder(null)
        }
      } else {
        deleteDocument.mutate(id)
        if (selectedDocumentId === id) {
          selectDocument(null)
        }
      }
    },
    [deleteFolder, deleteDocument, selectedFolderId, selectedDocumentId, selectFolder, selectDocument, handleCloseContextMenu]
  )

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
    const resolvedScopeId = scopeId ?? ''
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
      }
    )
  }, [scope, scopeId, createDocument, selectDocument])

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

  const isEmpty = folders.length === 0 && unfiledDocs.length === 0

  // Empty state
  if (isEmpty) {
    return (
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
    )
  }

  return (
    <div className="py-1" role="tree">
      {/* Subtle background refresh indicator */}
      {isFoldersFetching && !isFoldersLoading && (
        <div className="flex items-center justify-end px-2 pb-0.5">
          <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
        </div>
      )}

      {/* Folder tree */}
      {folders.map((node) => renderFolderNode(node, 0))}

      {/* Unfiled documents section */}
      {unfiledDocs.length > 0 && (
        <>
          {folders.length > 0 && (
            <div className="px-2 pt-2 pb-0.5">
              <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                Unfiled
              </span>
            </div>
          )}
          {unfiledDocs.map((doc) => renderDocumentItem(doc, 0))}
        </>
      )}

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
    </div>
  )
}

export default FolderTree
