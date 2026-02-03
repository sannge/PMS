/**
 * Application Tree
 *
 * Mixed-scope tree component for application tabs. Renders:
 * 1. App-level folders and documents (scope: application)
 * 2. Auto-generated project folder sections with lazy-loaded contents
 *
 * Project sections are visually distinguished from app-level items
 * using FolderKanban icon, muted text color, and a subtle left border accent.
 * Project folder contents are only fetched when the section is expanded.
 */

import { useState, useCallback, useMemo, useEffect } from 'react'
import { FilePlus, FolderKanban, ChevronRight, Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { useKnowledgeBase } from '@/contexts/knowledge-base-context'
import { useProjects, type Project } from '@/hooks/query-index'
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
import { CreateDialog } from './create-dialog'
import { DeleteDialog } from './delete-dialog'

// ============================================================================
// Types
// ============================================================================

interface ApplicationTreeProps {
  applicationId: string
}

interface ContextMenuTarget {
  id: string
  type: 'folder' | 'document'
  name: string
  x: number
  y: number
  /** Scope override for context menu actions (e.g. project scope within app tree) */
  scope: 'application' | 'project'
  scopeId: string
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

function TreeSkeleton(): JSX.Element {
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

/**
 * Skeleton for project section content - shows 3 document rows at depth 1
 */
function ProjectContentSkeleton(): JSX.Element {
  return (
    <div className="space-y-0.5 py-1">
      <TreeItemSkeleton depth={1} widthPercent={65} />
      <TreeItemSkeleton depth={1} widthPercent={80} />
      <TreeItemSkeleton depth={1} widthPercent={50} />
    </div>
  )
}

// ============================================================================
// Project Section (lazy-loaded)
// ============================================================================

interface ProjectSectionProps {
  project: Project
  expandedFolderIds: Set<string>
  selectedFolderId: string | null
  selectedDocumentId: string | null
  renamingItemId: string | null
  /** Hide this project section if it has no documents after loading */
  hideIfEmpty?: boolean
  onToggleFolder: (folderId: string) => void
  onSelectFolder: (folderId: string) => void
  onSelectDocument: (documentId: string) => void
  onContextMenu: (
    e: React.MouseEvent,
    id: string,
    type: 'folder' | 'document',
    name: string,
    scope: 'application' | 'project',
    scopeId: string
  ) => void
  onRenameSubmit: (newName: string) => void
  onRenameCancel: () => void
}

function ProjectSection({
  project,
  expandedFolderIds,
  selectedFolderId,
  selectedDocumentId,
  renamingItemId,
  hideIfEmpty = false,
  onToggleFolder,
  onSelectFolder,
  onSelectDocument,
  onContextMenu,
  onRenameSubmit,
  onRenameCancel,
}: ProjectSectionProps): JSX.Element | null {
  const [isExpanded, setIsExpanded] = useState(false)

  // Lazy-load project tree only when expanded.
  // When not expanded, pass null scopeId so the query is disabled.
  const { data: projectFolders, isLoading: isFoldersLoading } = useFolderTree(
    'project',
    isExpanded ? project.id : null
  )

  const { data: projectUnfiled, isLoading: isUnfiledLoading } = useDocuments(
    'project',
    isExpanded ? project.id : null,
    { includeUnfiled: true }
  )

  const toggleExpanded = useCallback(() => {
    setIsExpanded((prev) => !prev)
  }, [])

  const folders = projectFolders ?? []
  const unfiledDocs = projectUnfiled?.items ?? []
  const isLoading = isExpanded && isFoldersLoading && isUnfiledLoading

  // Determine if project has content (only knowable after data loads)
  const isEmpty = useMemo(() => {
    // Can't determine if loading or not yet expanded
    if (!isExpanded || isLoading) return false
    return folders.length === 0 && unfiledDocs.length === 0
  }, [isExpanded, isLoading, folders.length, unfiledDocs.length])

  // Hide section if expanded, loaded, and empty (when hideIfEmpty is true)
  if (hideIfEmpty && isExpanded && isEmpty && !isLoading) {
    return null
  }

  const renderFolderNode = useCallback(
    (node: FolderTreeNode, depth: number): JSX.Element => {
      const nodeExpanded = expandedFolderIds.has(node.id)
      const isSelected = selectedFolderId === node.id

      return (
        <div key={node.id}>
          <FolderTreeItem
            node={node}
            type="folder"
            depth={depth}
            isExpanded={nodeExpanded}
            isSelected={isSelected}
            isRenaming={renamingItemId === node.id}
            onToggleExpand={() => onToggleFolder(node.id)}
            onSelect={() => onSelectFolder(node.id)}
            onContextMenu={(e) =>
              onContextMenu(e, node.id, 'folder', node.name, 'project', project.id)
            }
            onRenameSubmit={onRenameSubmit}
            onRenameCancel={onRenameCancel}
          />
          {nodeExpanded &&
            node.children.map((child) => renderFolderNode(child, depth + 1))}
        </div>
      )
    },
    [
      expandedFolderIds,
      selectedFolderId,
      renamingItemId,
      project.id,
      onToggleFolder,
      onSelectFolder,
      onContextMenu,
      onRenameSubmit,
      onRenameCancel,
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
          onSelect={() => onSelectDocument(doc.id)}
          onContextMenu={(e) =>
            onContextMenu(e, doc.id, 'document', doc.title, 'project', project.id)
          }
          onRenameSubmit={onRenameSubmit}
          onRenameCancel={onRenameCancel}
        />
      )
    },
    [
      selectedDocumentId,
      renamingItemId,
      project.id,
      onSelectDocument,
      onContextMenu,
      onRenameSubmit,
      onRenameCancel,
    ]
  )

  return (
    <div className="border-l-2 border-primary/20 ml-2 mt-1">
      {/* Project section header */}
      <button
        onClick={toggleExpanded}
        className={cn(
          'flex items-center gap-1.5 w-full py-1 px-2 rounded-sm',
          'text-primary/70 hover:bg-accent/50 transition-colors',
          'text-sm font-medium'
        )}
      >
        <ChevronRight
          className={cn(
            'h-3.5 w-3.5 shrink-0 transition-transform duration-150',
            isExpanded && 'rotate-90'
          )}
        />
        <FolderKanban className="h-4 w-4 shrink-0" />
        <span className="truncate">{project.name}</span>
      </button>

      {/* Expanded content */}
      {isExpanded && (
        <div className="pl-2">
          {isLoading ? (
            <ProjectContentSkeleton />
          ) : (
            <>
              {folders.map((node) => renderFolderNode(node, 1))}
              {unfiledDocs.map((doc) => renderDocumentItem(doc, 1))}
              {folders.length === 0 && unfiledDocs.length === 0 && (
                <div className="px-2 py-1.5 text-xs text-muted-foreground">
                  No documents yet
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Main Component
// ============================================================================

export function ApplicationTree({ applicationId }: ApplicationTreeProps): JSX.Element {
  const {
    expandedFolderIds,
    selectedFolderId,
    selectedDocumentId,
    searchQuery,
    toggleFolder,
    expandFolder,
    selectDocument,
    selectFolder,
  } = useKnowledgeBase()

  // App-level data queries
  const {
    data: folderTree,
    isLoading: isFoldersLoading,
    isFetching: isFoldersFetching,
  } = useFolderTree('application', applicationId)

  const {
    data: unfiledResponse,
    isLoading: isUnfiledLoading,
  } = useDocuments('application', applicationId, { includeUnfiled: true })

  // Projects for this application
  const { data: projects } = useProjects(applicationId)

  // Mutations -- app scope
  const createFolder = useCreateFolder()
  const createDocument = useCreateDocument()
  const renameFolderApp = useRenameFolder('application', applicationId)
  const renameDocumentApp = useRenameDocument('application', applicationId)
  const deleteFolderApp = useDeleteFolder('application', applicationId)
  const deleteDocumentApp = useDeleteDocument('application', applicationId)

  // Local UI state
  const [renamingItemId, setRenamingItemId] = useState<string | null>(null)
  const [renamingItemType, setRenamingItemType] = useState<'folder' | 'document'>('folder')
  const [contextMenuTarget, setContextMenuTarget] = useState<ContextMenuTarget | null>(null)

  // Dialog state
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [createType, setCreateType] = useState<'document' | 'folder'>('document')
  const [createParentId, setCreateParentId] = useState<string | null>(null)
  const [createScope, setCreateScope] = useState<'application' | 'project'>('application')
  const [createScopeId, setCreateScopeId] = useState<string>(applicationId)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<{
    id: string
    type: 'document' | 'folder'
    name: string
  } | null>(null)

  const isLoading = isFoldersLoading && isUnfiledLoading

  const folders = folderTree ?? []
  const unfiledDocs = unfiledResponse?.items ?? []
  const projectList = projects ?? []

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

  // Filter projects: keep project if its name matches search
  // (Project section content is lazy-loaded so we can't filter by document content)
  const filteredProjects = useMemo(() => {
    if (!searchQuery) return projectList
    return projectList.filter(project => matchesSearch(project.name))
  }, [projectList, searchQuery, matchesSearch])

  // Auto-expand folders with matching children when searching
  useEffect(() => {
    if (!searchQuery) return

    const expandMatchingFolders = (nodes: FolderTreeNode[]) => {
      nodes.forEach(node => {
        if (node.children.length > 0) {
          expandFolder(node.id)
          expandMatchingFolders(node.children)
        }
      })
    }

    expandMatchingFolders(filteredFolders)
  }, [searchQuery, filteredFolders, expandFolder])

  // ========================================================================
  // Context menu handlers (scope-aware)
  // ========================================================================

  const handleContextMenu = useCallback(
    (
      e: React.MouseEvent,
      id: string,
      type: 'folder' | 'document',
      name: string,
      scope: 'application' | 'project' = 'application',
      scopeId: string = ''
    ) => {
      e.preventDefault()
      e.stopPropagation()
      setContextMenuTarget({
        id,
        type,
        name,
        x: e.clientX,
        y: e.clientY,
        scope,
        scopeId: scopeId || applicationId,
      })
    },
    [applicationId]
  )

  const handleCloseContextMenu = useCallback(() => {
    setContextMenuTarget(null)
  }, [])

  // ========================================================================
  // CRUD callbacks (scope-aware)
  // ========================================================================

  const handleNewFolder = useCallback(
    (parentId: string) => {
      handleCloseContextMenu()
      const target = contextMenuTarget
      const scope = target?.scope ?? 'application'
      const scopeId = target?.scopeId ?? applicationId

      setCreateType('folder')
      setCreateParentId(parentId)
      setCreateScope(scope)
      setCreateScopeId(scopeId)
      setCreateDialogOpen(true)
    },
    [contextMenuTarget, applicationId, handleCloseContextMenu]
  )

  const handleNewDocument = useCallback(
    (folderId: string) => {
      handleCloseContextMenu()
      const target = contextMenuTarget
      const scope = target?.scope ?? 'application'
      const scopeId = target?.scopeId ?? applicationId

      setCreateType('document')
      setCreateParentId(folderId)
      setCreateScope(scope)
      setCreateScopeId(scopeId)
      setCreateDialogOpen(true)
    },
    [contextMenuTarget, applicationId, handleCloseContextMenu]
  )

  const handleCreateSubmit = useCallback(
    async (name: string) => {
      if (createType === 'document') {
        const doc = await createDocument.mutateAsync({
          title: name,
          scope: createScope,
          scope_id: createScopeId,
          folder_id: createParentId,
        })
        selectDocument(doc.id)
        selectFolder(null)
        if (createParentId) expandFolder(createParentId)
      } else {
        await createFolder.mutateAsync({
          name,
          scope: createScope,
          scope_id: createScopeId,
          parent_id: createParentId,
        })
        if (createParentId) expandFolder(createParentId)
      }
    },
    [createType, createScope, createScopeId, createParentId, createDocument, createFolder, selectDocument, selectFolder, expandFolder]
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

      // Determine which scope mutation to use based on context
      // For simplicity, use app-scope mutations (project items will
      // also work since rename/delete endpoints are ID-based, not scope-filtered)
      if (renamingItemType === 'folder') {
        renameFolderApp.mutate({ folderId: renamingItemId, name: newName })
      } else {
        renameDocumentApp.mutate({
          documentId: renamingItemId,
          title: newName,
          row_version: 1,
        })
      }

      setRenamingItemId(null)
    },
    [renamingItemId, renamingItemType, renameFolderApp, renameDocumentApp]
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
      await deleteFolderApp.mutateAsync(deleteTarget.id)
      if (selectedFolderId === deleteTarget.id) selectFolder(null)
    } else {
      await deleteDocumentApp.mutateAsync(deleteTarget.id)
      if (selectedDocumentId === deleteTarget.id) selectDocument(null)
    }
  }, [deleteTarget, deleteFolderApp, deleteDocumentApp, selectedFolderId, selectedDocumentId, selectFolder, selectDocument])

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
    createDocument.mutate(
      {
        title: 'Untitled',
        scope: 'application',
        scope_id: applicationId,
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
  }, [applicationId, createDocument, selectDocument])

  // ========================================================================
  // Recursive folder renderer (app-level)
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
            onContextMenu={(e) =>
              handleContextMenu(e, node.id, 'folder', node.name, 'application', applicationId)
            }
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
      applicationId,
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
          onContextMenu={(e) =>
            handleContextMenu(e, doc.id, 'document', doc.title, 'application', applicationId)
          }
          onRenameSubmit={handleRenameSubmit}
          onRenameCancel={handleRenameCancel}
        />
      )
    },
    [
      selectedDocumentId,
      renamingItemId,
      applicationId,
      handleSelectDocument,
      handleContextMenu,
      handleRenameSubmit,
      handleRenameCancel,
    ]
  )

  // ========================================================================
  // Render
  // ========================================================================

  if (isLoading) {
    return <TreeSkeleton />
  }

  const hasNoData = folders.length === 0 && unfiledDocs.length === 0 && projectList.length === 0
  const hasNoResults = filteredFolders.length === 0 && filteredDocs.length === 0 && filteredProjects.length === 0

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
    <div className="py-1" role="tree">
      {/* Subtle background refresh indicator */}
      {isFoldersFetching && !isFoldersLoading && (
        <div className="flex items-center justify-end px-2 pb-0.5">
          <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
        </div>
      )}

      {/* App-level folder tree */}
      {filteredFolders.length > 0 && (
        <>
          {filteredFolders.map((node) => renderFolderNode(node, 0))}
        </>
      )}

      {/* App-level root documents (no folder) - render without confusing "Unfiled" label */}
      {filteredDocs.length > 0 && (
        <>
          {filteredDocs.map((doc) => renderDocumentItem(doc, 0))}
        </>
      )}

      {/* Project sections */}
      {filteredProjects.length > 0 && (
        <>
          <div className="px-2 pt-3 pb-1">
            <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              Projects
            </span>
          </div>
          {filteredProjects.map((project) => (
            <ProjectSection
              key={project.id}
              project={project}
              expandedFolderIds={expandedFolderIds}
              selectedFolderId={selectedFolderId}
              selectedDocumentId={selectedDocumentId}
              renamingItemId={renamingItemId}
              hideIfEmpty={!searchQuery}
              onToggleFolder={toggleFolder}
              onSelectFolder={handleSelectFolder}
              onSelectDocument={handleSelectDocument}
              onContextMenu={handleContextMenu}
              onRenameSubmit={handleRenameSubmit}
              onRenameCancel={handleRenameCancel}
            />
          ))}
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
    </div>
  )
}

export default ApplicationTree
