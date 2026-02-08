/**
 * Knowledge Tree
 *
 * Unified tree component for the knowledge base. Handles both personal and
 * application scopes with a single codebase. Application scope optionally
 * shows project sections with lazy-loaded content.
 *
 * Features:
 * - Recursive folder/document tree rendering
 * - Context menu for CRUD operations
 * - Drag-and-drop reordering via @dnd-kit
 * - Search filtering with auto-expand
 * - Lazy-loaded project sections (application scope only)
 */

import { useState, useCallback, useMemo, useEffect } from 'react'
import { FilePlus, Folder, FileText, FolderKanban, ChevronRight } from 'lucide-react'
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

interface KnowledgeTreeProps {
  /** Application ID - when provided, shows project sections */
  applicationId?: string
}

interface ContextMenuTarget {
  id: string
  type: 'folder' | 'document'
  name: string
  x: number
  y: number
  scope: 'application' | 'project' | 'personal'
  scopeId: string
}

interface ActiveDragItem {
  id: string
  type: 'folder' | 'document'
  name: string
  scope: string
}

// ============================================================================
// Skeleton Components
// ============================================================================

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
      <TreeItemSkeleton depth={0} widthPercent={55} />
      <TreeItemSkeleton depth={1} widthPercent={70} />
      <TreeItemSkeleton depth={1} widthPercent={50} />
      <TreeItemSkeleton depth={0} widthPercent={45} />
      <TreeItemSkeleton depth={1} widthPercent={65} />
      <TreeItemSkeleton depth={2} widthPercent={60} />
    </div>
  )
}

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
// Project Section (lazy-loaded, only for application scope)
// ============================================================================

interface ProjectSectionProps {
  project: Project
  expandedFolderIds: Set<string>
  selectedFolderId: string | null
  selectedDocumentId: string | null
  renamingItemId: string | null
  activeItem: ActiveDragItem | null
  onToggleFolder: (folderId: string) => void
  onSelectFolder: (folderId: string) => void
  onSelectDocument: (documentId: string) => void
  onContextMenu: (
    e: React.MouseEvent,
    id: string,
    type: 'folder' | 'document',
    name: string,
    scope: 'application' | 'project' | 'personal',
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
  onToggleFolder,
  onSelectFolder,
  onSelectDocument,
  onContextMenu,
  onRenameSubmit,
  onRenameCancel,
}: ProjectSectionProps): JSX.Element {
  const [isExpanded, setIsExpanded] = useState(false)

  // Lazy-load project content only when expanded
  const { data: projectFolders, isLoading: isFoldersLoading } = useFolderTree(
    'project',
    isExpanded ? project.id : null
  )

  const { data: projectUnfiled, isLoading: isUnfiledLoading } = useDocuments(
    'project',
    isExpanded ? project.id : null,
    { includeUnfiled: true }
  )

  const toggleExpanded = useCallback(() => setIsExpanded((prev) => !prev), [])

  const folders = projectFolders ?? []
  const unfiledDocs = projectUnfiled?.items ?? []
  const isLoading = isExpanded && isFoldersLoading && isUnfiledLoading

  // Sortable IDs for project items
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
          {nodeExpanded && node.children.map((child) => renderFolderNode(child, depth + 1))}
        </div>
      )
    },
    [expandedFolderIds, selectedFolderId, renamingItemId, activeItem, project.id, onToggleFolder, onSelectFolder, onContextMenu, onRenameSubmit, onRenameCancel]
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
    [selectedDocumentId, renamingItemId, activeItem, project.id, onSelectDocument, onContextMenu, onRenameSubmit, onRenameCancel]
  )

  return (
    <div className="border-l-2 border-primary/20 ml-2 mt-1">
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

export function KnowledgeTree({ applicationId }: KnowledgeTreeProps): JSX.Element {
  const {
    scope: contextScope,
    scopeId: contextScopeId,
    expandedFolderIds,
    selectedFolderId,
    selectedDocumentId,
    searchQuery,
    toggleFolder,
    expandFolder,
    selectDocument,
    selectFolder,
  } = useKnowledgeBase()

  const userId = useAuthStore((s) => s.user?.id ?? null)

  // Determine effective scope - applicationId prop overrides context
  const isApplicationScope = !!applicationId
  const scope = isApplicationScope ? 'application' : contextScope
  const scopeId = isApplicationScope ? applicationId : contextScopeId

  // Resolve scopeId for personal scope (use userId)
  const effectiveScopeId = scope === 'personal' ? userId : scopeId

  // Data queries
  const { data: folderTree, isLoading: isFoldersLoading } = useFolderTree(scope, effectiveScopeId)
  const { data: unfiledResponse, isLoading: isUnfiledLoading } = useDocuments(scope, effectiveScopeId, { includeUnfiled: true })

  // Project data (only for application scope)
  const { data: projects } = useProjects(isApplicationScope ? applicationId : undefined)
  const { data: projectsWithContent, isLoading: isProjectsContentLoading } = useProjectsWithContent(isApplicationScope ? applicationId! : null)

  // Mutations
  const createFolder = useCreateFolder()
  const createDocument = useCreateDocument()
  const renameFolder = useRenameFolder(scope, effectiveScopeId ?? '')
  const renameDocument = useRenameDocument(scope, effectiveScopeId ?? '')
  const deleteFolder = useDeleteFolder(scope, effectiveScopeId ?? '')
  const deleteDocument = useDeleteDocument(scope, effectiveScopeId ?? '')
  const reorderFolder = useReorderFolder(scope, effectiveScopeId ?? '')
  const reorderDocument = useReorderDocument(scope, effectiveScopeId ?? '')

  // Drag and drop
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } })
  )
  const [activeItem, setActiveItem] = useState<ActiveDragItem | null>(null)

  // UI state
  const [renamingItemId, setRenamingItemId] = useState<string | null>(null)
  const [renamingItemType, setRenamingItemType] = useState<'folder' | 'document'>('folder')
  const [contextMenuTarget, setContextMenuTarget] = useState<ContextMenuTarget | null>(null)

  // Dialog state
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [createType, setCreateType] = useState<'document' | 'folder'>('document')
  const [createParentId, setCreateParentId] = useState<string | null>(null)
  const [createScope, setCreateScope] = useState<'application' | 'project' | 'personal'>('personal')
  const [createScopeId, setCreateScopeId] = useState<string>('')
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; type: 'document' | 'folder'; name: string } | null>(null)

  const folders = folderTree ?? []
  const unfiledDocs = unfiledResponse?.items ?? []
  const projectList = projects ?? []

  // Only show loading skeleton on true first load (no data at all)
  // Don't show skeleton when switching tabs if we have any cached/placeholder data
  const hasAnyData = folders.length > 0 || unfiledDocs.length > 0
  const isInitialLoad = isFoldersLoading && isUnfiledLoading && !hasAnyData

  // Project filtering (application scope only)
  const projectIdsWithContent = useMemo(
    () => new Set(projectsWithContent?.project_ids ?? []),
    [projectsWithContent?.project_ids]
  )

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
        acc.push({ ...node, children: filteredChildren })
      }
      return acc
    }, [])
  }, [searchQuery, matchesSearch])

  const filteredFolders = useMemo(() => filterFolderTree(folders), [filterFolderTree, folders])
  const filteredDocs = useMemo(() => {
    if (!searchQuery) return unfiledDocs
    return unfiledDocs.filter(doc => matchesSearch(doc.title))
  }, [unfiledDocs, searchQuery, matchesSearch])

  const filteredProjects = useMemo(() => {
    if (!isApplicationScope) return []
    if (searchQuery) {
      return projectList.filter(project => matchesSearch(project.name))
    }
    return projectList.filter(project => projectIdsWithContent.has(project.id))
  }, [isApplicationScope, projectList, projectIdsWithContent, searchQuery, matchesSearch])

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
  // Drag and drop
  // ========================================================================

  const sortableItems = useMemo(() => {
    const items: string[] = []
    const prefix = isApplicationScope ? 'app' : 'personal'
    const addFolders = (nodes: FolderTreeNode[]) => {
      nodes.forEach(node => {
        items.push(`${prefix}-folder-${node.id}`)
        addFolders(node.children)
      })
    }
    addFolders(filteredFolders)
    filteredDocs.forEach(doc => {
      items.push(`${prefix}-doc-${doc.id}`)
    })
    return items
  }, [isApplicationScope, filteredFolders, filteredDocs])

  const findFolderById = useCallback((nodes: FolderTreeNode[], id: string): FolderTreeNode | null => {
    for (const node of nodes) {
      if (node.id === id) return node
      const found = findFolderById(node.children, id)
      if (found) return found
    }
    return null
  }, [])

  const parseSortableId = useCallback((sortableId: string): { scope: string; type: 'folder' | 'document'; itemId: string } | null => {
    const prefix = isApplicationScope ? 'app' : 'personal'
    if (sortableId.startsWith(`${prefix}-folder-`)) {
      return { scope: prefix, type: 'folder', itemId: sortableId.replace(`${prefix}-folder-`, '') }
    }
    if (sortableId.startsWith(`${prefix}-doc-`)) {
      return { scope: prefix, type: 'document', itemId: sortableId.replace(`${prefix}-doc-`, '') }
    }
    // Project items: project-{projId}-folder-{id} or project-{projId}-doc-{id}
    const projectMatch = sortableId.match(/^project-([^-]+)-(folder|doc)-(.+)$/)
    if (projectMatch) {
      const [, projectId, typeStr, itemId] = projectMatch
      return { scope: `project:${projectId}`, type: typeStr === 'folder' ? 'folder' : 'document', itemId }
    }
    return null
  }, [isApplicationScope])

  const handleDragStart = useCallback((event: DragStartEvent) => {
    const parsed = parseSortableId(String(event.active.id))
    if (!parsed) return

    let name = 'Item'
    const prefix = isApplicationScope ? 'app' : 'personal'
    if (parsed.scope === prefix) {
      if (parsed.type === 'folder') {
        const folder = findFolderById(filteredFolders, parsed.itemId)
        if (folder) name = folder.name
      } else {
        const doc = filteredDocs.find(d => d.id === parsed.itemId)
        if (doc) name = doc.title
      }
    }

    setActiveItem({ id: parsed.itemId, type: parsed.type, name, scope: parsed.scope })
  }, [isApplicationScope, filteredFolders, filteredDocs, findFolderById, parseSortableId])

  const handleDragEnd = useCallback(async (event: DragEndEvent) => {
    const { active, over } = event
    setActiveItem(null)

    if (!over || active.id === over.id) return

    const activeParsed = parseSortableId(String(active.id))
    const overParsed = parseSortableId(String(over.id))

    if (!activeParsed || !overParsed) return
    if (activeParsed.scope !== overParsed.scope) return // No cross-scope
    if (activeParsed.type !== overParsed.type) return // No cross-type

    const newSortOrder = sortableItems.indexOf(String(over.id))

    try {
      if (activeParsed.type === 'folder') {
        await reorderFolder.mutateAsync({ folderId: activeParsed.itemId, sortOrder: newSortOrder })
      } else {
        await reorderDocument.mutateAsync({ documentId: activeParsed.itemId, sortOrder: newSortOrder, rowVersion: 1 })
      }
    } catch (error) {
      console.error('Failed to reorder:', error)
      toast.error('Failed to reorder item')
    }
  }, [parseSortableId, sortableItems, reorderFolder, reorderDocument])

  // ========================================================================
  // Context menu handlers
  // ========================================================================

  const handleContextMenu = useCallback(
    (e: React.MouseEvent, id: string, type: 'folder' | 'document', name: string, menuScope: 'application' | 'project' | 'personal' = scope as 'application' | 'project' | 'personal', menuScopeId: string = effectiveScopeId ?? '') => {
      e.preventDefault()
      e.stopPropagation()
      setContextMenuTarget({ id, type, name, x: e.clientX, y: e.clientY, scope: menuScope, scopeId: menuScopeId })
    },
    [scope, effectiveScopeId]
  )

  const handleCloseContextMenu = useCallback(() => setContextMenuTarget(null), [])

  // ========================================================================
  // CRUD handlers
  // ========================================================================

  const handleNewFolder = useCallback((parentId: string) => {
    handleCloseContextMenu()
    const target = contextMenuTarget
    setCreateType('folder')
    setCreateParentId(parentId)
    setCreateScope(target?.scope ?? (scope as 'application' | 'project' | 'personal'))
    setCreateScopeId(target?.scopeId ?? effectiveScopeId ?? '')
    setCreateDialogOpen(true)
  }, [contextMenuTarget, scope, effectiveScopeId, handleCloseContextMenu])

  const handleNewDocument = useCallback((folderId: string) => {
    handleCloseContextMenu()
    const target = contextMenuTarget
    setCreateType('document')
    setCreateParentId(folderId)
    setCreateScope(target?.scope ?? (scope as 'application' | 'project' | 'personal'))
    setCreateScopeId(target?.scopeId ?? effectiveScopeId ?? '')
    setCreateDialogOpen(true)
  }, [contextMenuTarget, scope, effectiveScopeId, handleCloseContextMenu])

  const handleCreateSubmit = useCallback(async (name: string) => {
    const resolvedScopeId = createScope === 'personal' ? (userId ?? '') : createScopeId

    if (createType === 'document') {
      const doc = await createDocument.mutateAsync({
        title: name,
        scope: createScope,
        scope_id: resolvedScopeId,
        folder_id: createParentId,
      })
      selectDocument(doc.id)
      selectFolder(null)
      if (createParentId) expandFolder(createParentId)
    } else {
      await createFolder.mutateAsync({
        name,
        scope: createScope,
        scope_id: resolvedScopeId,
        parent_id: createParentId,
      })
      if (createParentId) expandFolder(createParentId)
    }
  }, [createType, createScope, createScopeId, createParentId, userId, createDocument, createFolder, selectDocument, selectFolder, expandFolder])

  const handleRename = useCallback((id: string, type: 'folder' | 'document') => {
    handleCloseContextMenu()
    setRenamingItemId(id)
    setRenamingItemType(type)
  }, [handleCloseContextMenu])

  const handleRenameSubmit = useCallback((newName: string) => {
    if (!renamingItemId) return
    if (renamingItemType === 'folder') {
      renameFolder.mutate({ folderId: renamingItemId, name: newName })
    } else {
      renameDocument.mutate({ documentId: renamingItemId, title: newName, row_version: 1 })
    }
    setRenamingItemId(null)
  }, [renamingItemId, renamingItemType, renameFolder, renameDocument])

  const handleRenameCancel = useCallback(() => setRenamingItemId(null), [])

  const handleDelete = useCallback((id: string, type: 'folder' | 'document') => {
    handleCloseContextMenu()
    const name = type === 'folder'
      ? folders.find((f) => f.id === id)?.name || 'this folder'
      : unfiledDocs.find((d) => d.id === id)?.title || 'this document'
    setDeleteTarget({ id, type, name })
    setDeleteDialogOpen(true)
  }, [folders, unfiledDocs, handleCloseContextMenu])

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

  const handleSelectFolder = useCallback((folderId: string) => {
    toggleFolder(folderId)
    selectFolder(folderId)
    selectDocument(null)
  }, [toggleFolder, selectFolder, selectDocument])

  const handleSelectDocument = useCallback((documentId: string) => {
    selectDocument(documentId)
    selectFolder(null)
  }, [selectDocument, selectFolder])

  // ========================================================================
  // Create first document (empty state)
  // ========================================================================

  const handleCreateFirstDocument = useCallback(() => {
    setCreateType('document')
    setCreateParentId(null)
    setCreateScope(scope as 'application' | 'project' | 'personal')
    setCreateScopeId(effectiveScopeId ?? '')
    setCreateDialogOpen(true)
  }, [scope, effectiveScopeId])

  // ========================================================================
  // Render helpers
  // ========================================================================

  const renderFolderNode = useCallback(
    (node: FolderTreeNode, depth: number): JSX.Element => {
      const isExpanded = expandedFolderIds.has(node.id)
      const isSelected = selectedFolderId === node.id
      const prefix = isApplicationScope ? 'app' : 'personal'
      const isDragging = activeItem?.id === node.id && activeItem?.type === 'folder' && activeItem?.scope === prefix

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
            sortableId={`${prefix}-folder-${node.id}`}
            onToggleExpand={() => toggleFolder(node.id)}
            onSelect={() => handleSelectFolder(node.id)}
            onContextMenu={(e) => handleContextMenu(e, node.id, 'folder', node.name)}
            onRenameSubmit={handleRenameSubmit}
            onRenameCancel={handleRenameCancel}
          />
          {isExpanded && node.children.map((child) => renderFolderNode(child, depth + 1))}
        </div>
      )
    },
    [isApplicationScope, expandedFolderIds, selectedFolderId, renamingItemId, activeItem, toggleFolder, handleSelectFolder, handleContextMenu, handleRenameSubmit, handleRenameCancel]
  )

  const renderDocumentItem = useCallback(
    (doc: DocumentListItem, depth: number): JSX.Element => {
      const isSelected = selectedDocumentId === doc.id
      const prefix = isApplicationScope ? 'app' : 'personal'
      const isDragging = activeItem?.id === doc.id && activeItem?.type === 'document' && activeItem?.scope === prefix

      return (
        <FolderTreeItem
          key={doc.id}
          node={doc}
          type="document"
          depth={depth}
          isSelected={isSelected}
          isRenaming={renamingItemId === doc.id}
          isDragging={isDragging}
          sortableId={`${prefix}-doc-${doc.id}`}
          onSelect={() => handleSelectDocument(doc.id)}
          onContextMenu={(e) => handleContextMenu(e, doc.id, 'document', doc.title)}
          onRenameSubmit={handleRenameSubmit}
          onRenameCancel={handleRenameCancel}
        />
      )
    },
    [isApplicationScope, selectedDocumentId, renamingItemId, activeItem, handleSelectDocument, handleContextMenu, handleRenameSubmit, handleRenameCancel]
  )

  // ========================================================================
  // Render
  // ========================================================================

  if (isInitialLoad) {
    return <TreeSkeleton />
  }

  const hasNoData = folders.length === 0 && unfiledDocs.length === 0 && (isApplicationScope ? projectIdsWithContent.size === 0 : true)
  const hasNoResults = filteredFolders.length === 0 && filteredDocs.length === 0 && filteredProjects.length === 0

  // Empty state
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
        <CreateDialog open={createDialogOpen} onOpenChange={setCreateDialogOpen} type={createType} onSubmit={handleCreateSubmit} />
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
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
      <div className="py-1" role="tree">
        {/* Main folder tree */}
        <SortableContext items={sortableItems} strategy={verticalListSortingStrategy}>
          {filteredFolders.map((node) => renderFolderNode(node, 0))}
          {filteredDocs.map((doc) => renderDocumentItem(doc, 0))}
        </SortableContext>

        {/* Project sections (application scope only) */}
        {isApplicationScope && filteredProjects.length > 0 && (
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
          target={{ id: contextMenuTarget.id, type: contextMenuTarget.type, name: contextMenuTarget.name }}
          position={{ x: contextMenuTarget.x, y: contextMenuTarget.y }}
          onClose={handleCloseContextMenu}
          onNewFolder={handleNewFolder}
          onNewDocument={handleNewDocument}
          onRename={(id) => handleRename(id, contextMenuTarget.type)}
          onDelete={handleDelete}
        />
      )}

      {/* Create dialog */}
      <CreateDialog open={createDialogOpen} onOpenChange={setCreateDialogOpen} type={createType} onSubmit={handleCreateSubmit} />

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

export default KnowledgeTree
