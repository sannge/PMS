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
 *
 * Drag-and-drop: Uses @dnd-kit for reordering items within the same scope.
 * Cross-scope moves (app-level to project-level or between projects) are prevented.
 */

import { useState, useCallback, useMemo, useEffect } from 'react'
import { FilePlus, Folder, FileText, FolderKanban, ChevronRight, Loader2 } from 'lucide-react'
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
import { useKnowledgeBase } from '@/contexts/knowledge-base-context'
import { useProjects, type Project } from '@/hooks/query-index'
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
  useProjectsWithContent,
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

interface ActiveDragItem {
  id: string
  type: 'folder' | 'document'
  name: string
  /** Scope of the dragged item (app or project:{id}) */
  scope: string
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
  activeItem: ActiveDragItem | null
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
  activeItem,
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

  // Create sortable IDs for this project's items
  const projectSortableItems = useMemo(() => {
    const items: string[] = []
    const addFolders = (nodes: FolderTreeNode[]) => {
      nodes.forEach(node => {
        items.push(`project-${project.id}-folder-${node.id}`)
        addFolders(node.children)
      })
    }
    addFolders(folders)
    unfiledDocs.forEach(doc => {
      items.push(`project-${project.id}-doc-${doc.id}`)
    })
    return items
  }, [project.id, folders, unfiledDocs])

  const renderFolderNode = useCallback(
    (node: FolderTreeNode, depth: number): JSX.Element => {
      const nodeExpanded = expandedFolderIds.has(node.id)
      const isSelected = selectedFolderId === node.id
      const isDragging = activeItem?.id === node.id && activeItem?.type === 'folder' && activeItem?.scope === `project:${project.id}`

      return (
        <div key={node.id}>
          <FolderTreeItem
            node={node}
            type="folder"
            depth={depth}
            isExpanded={nodeExpanded}
            isSelected={isSelected}
            isRenaming={renamingItemId === node.id}
            isDragging={isDragging}
            sortableId={`project-${project.id}-folder-${node.id}`}
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
      activeItem,
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
      const isDragging = activeItem?.id === doc.id && activeItem?.type === 'document' && activeItem?.scope === `project:${project.id}`

      return (
        <FolderTreeItem
          key={doc.id}
          node={doc}
          type="document"
          depth={depth}
          isSelected={isSelected}
          isRenaming={renamingItemId === doc.id}
          isDragging={isDragging}
          sortableId={`project-${project.id}-doc-${doc.id}`}
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
      activeItem,
      project.id,
      onSelectDocument,
      onContextMenu,
      onRenameSubmit,
      onRenameCancel,
    ]
  )

  // Hide section if expanded, loaded, and empty (when hideIfEmpty is true)
  // This must be AFTER all hooks to avoid React "fewer hooks" error
  if (hideIfEmpty && isExpanded && isEmpty && !isLoading) {
    return null
  }

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
            <SortableContext items={projectSortableItems} strategy={verticalListSortingStrategy}>
              {folders.map((node) => renderFolderNode(node, 1))}
              {unfiledDocs.map((doc) => renderDocumentItem(doc, 1))}
              {folders.length === 0 && unfiledDocs.length === 0 && (
                <div className="px-2 py-1.5 text-xs text-muted-foreground">
                  No documents yet
                </div>
              )}
            </SortableContext>
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
  const { data: projectsWithContent, isLoading: isProjectsContentLoading } = useProjectsWithContent(applicationId)

  // Mutations -- app scope
  const createFolder = useCreateFolder()
  const createDocument = useCreateDocument()
  const renameFolderApp = useRenameFolder('application', applicationId)
  const renameDocumentApp = useRenameDocument('application', applicationId)
  const deleteFolderApp = useDeleteFolder('application', applicationId)
  const deleteDocumentApp = useDeleteDocument('application', applicationId)
  const reorderFolderApp = useReorderFolder('application', applicationId)
  const reorderDocumentApp = useReorderDocument('application', applicationId)

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
  const [createScope, setCreateScope] = useState<'application' | 'project'>('application')
  const [createScopeId, setCreateScopeId] = useState<string>(applicationId)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<{
    id: string
    type: 'document' | 'folder'
    name: string
  } | null>(null)

  const isLoading = (isFoldersLoading && isUnfiledLoading) || isProjectsContentLoading

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
  // Set of project IDs that have documents/folders
  const projectIdsWithContent = useMemo(
    () => new Set(projectsWithContent?.project_ids ?? []),
    [projectsWithContent?.project_ids]
  )

  const filteredProjects = useMemo(() => {
    // When searching, show all projects that match the search
    if (searchQuery) {
      return projectList.filter(project => matchesSearch(project.name))
    }
    // When not searching, only show projects with content
    return projectList.filter(project => projectIdsWithContent.has(project.id))
  }, [projectList, projectIdsWithContent, searchQuery, matchesSearch])

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
  // Drag and drop handlers
  // ========================================================================

  // Create flat list of sortable IDs for app-level items
  const appLevelSortableItems = useMemo(() => {
    const items: string[] = []
    const addFolders = (nodes: FolderTreeNode[]) => {
      nodes.forEach(node => {
        items.push(`app-folder-${node.id}`)
        addFolders(node.children)
      })
    }
    addFolders(filteredFolders)
    filteredDocs.forEach(doc => {
      items.push(`app-doc-${doc.id}`)
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

  // Parse sortable ID to extract scope and item info
  // Format: "app-folder-{id}" | "app-doc-{id}" | "project-{projId}-folder-{id}" | "project-{projId}-doc-{id}"
  const parseSortableId = useCallback((sortableId: string): { scope: string; type: 'folder' | 'document'; itemId: string } | null => {
    if (sortableId.startsWith('app-folder-')) {
      return { scope: 'app', type: 'folder', itemId: sortableId.replace('app-folder-', '') }
    }
    if (sortableId.startsWith('app-doc-')) {
      return { scope: 'app', type: 'document', itemId: sortableId.replace('app-doc-', '') }
    }
    // project-{projId}-folder-{id} or project-{projId}-doc-{id}
    const projectMatch = sortableId.match(/^project-([^-]+)-(folder|doc)-(.+)$/)
    if (projectMatch) {
      const [, projectId, typeStr, itemId] = projectMatch
      return {
        scope: `project:${projectId}`,
        type: typeStr === 'folder' ? 'folder' : 'document',
        itemId,
      }
    }
    return null
  }, [])

  const handleDragStart = useCallback((event: DragStartEvent) => {
    const { active } = event
    const activeIdStr = String(active.id)
    const parsed = parseSortableId(activeIdStr)

    if (!parsed) return

    let name = 'Item'
    if (parsed.scope === 'app') {
      if (parsed.type === 'folder') {
        const folder = findFolderById(filteredFolders, parsed.itemId)
        if (folder) name = folder.name
      } else {
        const doc = filteredDocs.find(d => d.id === parsed.itemId)
        if (doc) name = doc.title
      }
    }
    // For project items, name resolution would require project folder data
    // which may not be loaded. Use a generic fallback.

    setActiveItem({
      id: parsed.itemId,
      type: parsed.type,
      name,
      scope: parsed.scope,
    })
  }, [filteredFolders, filteredDocs, findFolderById, parseSortableId])

  const handleDragEnd = useCallback(async (event: DragEndEvent) => {
    const { active, over } = event
    setActiveItem(null)

    if (!over || active.id === over.id) return

    const activeIdStr = String(active.id)
    const overIdStr = String(over.id)

    const activeParsed = parseSortableId(activeIdStr)
    const overParsed = parseSortableId(overIdStr)

    if (!activeParsed || !overParsed) return

    // Prevent cross-scope drags
    if (activeParsed.scope !== overParsed.scope) {
      console.log('Cannot drag between scopes:', activeParsed.scope, '->', overParsed.scope)
      return
    }

    // Prevent cross-type drags (folder to doc position)
    if (activeParsed.type !== overParsed.type) {
      return
    }

    // Determine the new sort order based on position
    let newSortOrder: number
    if (activeParsed.scope === 'app') {
      newSortOrder = appLevelSortableItems.indexOf(overIdStr)
    } else {
      // For project items, calculate based on over position
      // Since project sections have their own SortableContext, this is simpler
      newSortOrder = 0 // Will be refined by the mutation
    }

    try {
      if (activeParsed.scope === 'app') {
        // App-level reorder
        if (activeParsed.type === 'folder') {
          await reorderFolderApp.mutateAsync({
            folderId: activeParsed.itemId,
            sortOrder: newSortOrder,
          })
        } else {
          await reorderDocumentApp.mutateAsync({
            documentId: activeParsed.itemId,
            sortOrder: newSortOrder,
            rowVersion: 1,
          })
        }
      } else {
        // Project-level reorder
        // Note: For project items, we'd need project-scoped mutations
        // For now, the app-level mutations work since they're ID-based
        if (activeParsed.type === 'folder') {
          await reorderFolderApp.mutateAsync({
            folderId: activeParsed.itemId,
            sortOrder: newSortOrder,
          })
        } else {
          await reorderDocumentApp.mutateAsync({
            documentId: activeParsed.itemId,
            sortOrder: newSortOrder,
            rowVersion: 1,
          })
        }
      }
    } catch (error) {
      console.error('Failed to reorder:', error)
      toast.error('Failed to reorder item')
    }
  }, [parseSortableId, appLevelSortableItems, reorderFolderApp, reorderDocumentApp])

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
    setCreateType('document')
    setCreateParentId(null)
    setCreateScope('application')
    setCreateScopeId(applicationId)
    setCreateDialogOpen(true)
  }, [applicationId])

  // ========================================================================
  // Recursive folder renderer (app-level)
  // ========================================================================

  const renderFolderNode = useCallback(
    (node: FolderTreeNode, depth: number): JSX.Element => {
      const isExpanded = expandedFolderIds.has(node.id)
      const isSelected = selectedFolderId === node.id
      const isDragging = activeItem?.id === node.id && activeItem?.type === 'folder' && activeItem?.scope === 'app'

      return (
        <div key={node.id}>
          <FolderTreeItem
            node={node}
            type="folder"
            depth={depth}
            isExpanded={isExpanded}
            isSelected={isSelected}
            isRenaming={renamingItemId === node.id}
            isDragging={isDragging}
            sortableId={`app-folder-${node.id}`}
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
      activeItem,
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
      const isDragging = activeItem?.id === doc.id && activeItem?.type === 'document' && activeItem?.scope === 'app'

      return (
        <FolderTreeItem
          key={doc.id}
          node={doc}
          type="document"
          depth={depth}
          isSelected={isSelected}
          isRenaming={renamingItemId === doc.id}
          isDragging={isDragging}
          sortableId={`app-doc-${doc.id}`}
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
      activeItem,
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

  const hasNoData = folders.length === 0 && unfiledDocs.length === 0 && projectIdsWithContent.size === 0
  const hasNoResults = filteredFolders.length === 0 && filteredDocs.length === 0 && filteredProjects.length === 0

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
      onDragEnd={handleDragEnd}
    >
      <div className="py-1" role="tree">
        {/* Subtle background refresh indicator */}
        {isFoldersFetching && !isFoldersLoading && (
          <div className="flex items-center justify-end px-2 pb-0.5">
            <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
          </div>
        )}

        {/* App-level folder tree */}
        <SortableContext items={appLevelSortableItems} strategy={verticalListSortingStrategy}>
          {filteredFolders.length > 0 && (
            <>
              {filteredFolders.map((node) => renderFolderNode(node, 0))}
            </>
          )}

          {/* App-level root documents (no folder) */}
          {filteredDocs.length > 0 && (
            <>
              {filteredDocs.map((doc) => renderDocumentItem(doc, 0))}
            </>
          )}
        </SortableContext>

        {/* Project sections - each has its own SortableContext */}
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
                activeItem={activeItem}
                hideIfEmpty={false}
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
      </div>

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

export default ApplicationTree
