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
import { FilePlus, Folder, FileText, FolderKanban, ChevronRight, Loader2 } from 'lucide-react'
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
import { useQueryClient } from '@tanstack/react-query'
import { cn } from '@/lib/utils'
import { queryKeys } from '@/lib/query-client'
import { useAuthStore } from '@/contexts/auth-context'
import { useKnowledgeBase } from '@/contexts/knowledge-base-context'
import { useProjects, type Project } from '@/hooks/query-index'
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
  useProjectsWithContent,
  type Document,
  type DocumentListItem,
  type DocumentListResponse,
} from '@/hooks/use-documents'
import { useActiveLocks } from '@/hooks/use-document-lock'
import { FolderTreeItem } from './folder-tree-item'
import { FolderDocuments } from './folder-documents'
import { TreeSkeleton, ProjectContentSkeleton } from './tree-skeletons'
import { RootDropZone, ROOT_DROP_ZONE_ID } from './root-drop-zone'
import { FolderContextMenu } from './folder-context-menu'
import { CreateDialog } from './create-dialog'
import { DeleteDialog } from './delete-dialog'
import { matchesSearch, filterFolderTree, findFolderById, isDescendantOf } from './tree-utils'
import { parseSortableId, parsePrefixToScope, type ScopeInfo } from './dnd-utils'

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
  /** For documents: the folder_id at drag start (cached to avoid repeated query scans) */
  folderId: string | null
}

// ============================================================================
// Project Section (lazy-loaded, only for application scope)
// ============================================================================

interface ProjectSectionProps {
  project: Project
  expandedFolderIds: Set<string>
  selectedDocumentId: string | null
  renamingItemId: string | null
  activeItem: ActiveDragItem | null
  dropTargetFolderId: string | null
  /** Folder ID currently targeted by context menu (for transient highlight) */
  contextMenuFolderId: string | null
  /** Hide this project section if it has no documents after loading */
  hideIfEmpty?: boolean
  onToggleFolder: (folderId: string) => void
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
  selectedDocumentId,
  renamingItemId,
  activeItem,
  dropTargetFolderId,
  contextMenuFolderId,
  hideIfEmpty = false,
  onToggleFolder,
  onSelectDocument,
  onContextMenu,
  onRenameSubmit,
  onRenameCancel,
}: ProjectSectionProps): JSX.Element | null {
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

  // Active locks for this project scope (lazy: only fetches when expanded)
  const projectActiveLocks = useActiveLocks('project', isExpanded ? project.id : null)

  const toggleExpanded = useCallback(() => setIsExpanded((prev) => !prev), [])

  const folders = projectFolders ?? []
  const unfiledDocs = projectUnfiled?.items ?? []
  const isLoading = isExpanded && (isFoldersLoading || isUnfiledLoading) && folders.length === 0 && unfiledDocs.length === 0

  const isEmpty = useMemo(() => {
    if (!isExpanded || isLoading) return false
    return folders.length === 0 && unfiledDocs.length === 0
  }, [isExpanded, isLoading, folders.length, unfiledDocs.length])

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

  // No-op sorting strategy: items are alphabetically ordered, DnD is only for nesting
  const noReorderStrategy = useCallback(() => null, [])

  const renderFolderNode = useCallback(
    (node: FolderTreeNode, depth: number): JSX.Element => {
      const nodeExpanded = expandedFolderIds.has(node.id)
      const isSelected = contextMenuFolderId === node.id
      const isDragging = activeItem?.id === node.id && activeItem?.type === 'folder' && activeItem?.scope === `project:${project.id}`
      const isDropTarget = dropTargetFolderId === node.id

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
            isDropTarget={isDropTarget}
            sortableId={`project-${project.id}-folder-${node.id}`}
            onToggleExpand={() => onToggleFolder(node.id)}
            onSelect={() => onToggleFolder(node.id)}
            onContextMenu={(e) =>
              onContextMenu(e, node.id, 'folder', node.name, 'project', project.id)
            }
            onRenameSubmit={onRenameSubmit}
            onRenameCancel={onRenameCancel}
          />
          {nodeExpanded && (
            <>
              {node.children.map((child) => renderFolderNode(child, depth + 1))}
              <FolderDocuments
                scope="project"
                scopeId={project.id}
                folderId={node.id}
                depth={depth + 1}
                selectedDocumentId={selectedDocumentId}
                renamingItemId={renamingItemId}
                sortableIdPrefix={`project-${project.id}`}
                activeItemId={activeItem?.type === 'document' ? activeItem.id : null}
                activeLocks={projectActiveLocks}
                onSelectDocument={onSelectDocument}
                onContextMenu={(e, id, type, name) =>
                  onContextMenu(e, id, type, name, 'project', project.id)
                }
                onRenameSubmit={onRenameSubmit}
                onRenameCancel={onRenameCancel}
              />
            </>
          )}
        </div>
      )
    },
    [expandedFolderIds, contextMenuFolderId, selectedDocumentId, renamingItemId, activeItem, dropTargetFolderId, project.id, projectActiveLocks, onToggleFolder, onSelectDocument, onContextMenu, onRenameSubmit, onRenameCancel]
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
          lockInfo={projectActiveLocks.get(doc.id)}
          onSelect={() => onSelectDocument(doc.id)}
          onContextMenu={(e) =>
            onContextMenu(e, doc.id, 'document', doc.title, 'project', project.id)
          }
          onRenameSubmit={onRenameSubmit}
          onRenameCancel={onRenameCancel}
        />
      )
    },
    [selectedDocumentId, renamingItemId, activeItem, project.id, projectActiveLocks, onSelectDocument, onContextMenu, onRenameSubmit, onRenameCancel]
  )

  // Hide section if expanded, loaded, and empty (when hideIfEmpty is true)
  // This must be AFTER all hooks to avoid React "fewer hooks" error
  if (hideIfEmpty && isExpanded && isEmpty && !isLoading) {
    return null
  }

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
            <SortableContext items={projectSortableItems} strategy={noReorderStrategy}>
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
    selectedDocumentId,
    searchQuery,
    toggleFolder,
    expandFolder,
    selectDocument,
  } = useKnowledgeBase()

  const userId = useAuthStore((s) => s.user?.id ?? null)

  // Determine effective scope - applicationId prop overrides context
  const isApplicationScope = !!applicationId
  const scope = isApplicationScope ? 'application' : contextScope
  const scopeId = isApplicationScope ? applicationId : contextScopeId

  // Resolve scopeId for personal scope (use userId)
  const effectiveScopeId = scope === 'personal' ? userId : scopeId

  // Data queries
  const { data: folderTree, isLoading: isFoldersLoading, isFetching: isFoldersFetching } = useFolderTree(scope, effectiveScopeId)
  const { data: unfiledResponse, isLoading: isUnfiledLoading } = useDocuments(scope, effectiveScopeId, { includeUnfiled: true })

  // Active locks for the current scope (single batch request replaces N per-document queries)
  const activeLocks = useActiveLocks(scope, effectiveScopeId)

  // Project data (only for application scope)
  const { data: projects } = useProjects(isApplicationScope ? applicationId : undefined)
  const { data: projectsWithContent, isLoading: isProjectsContentLoading } = useProjectsWithContent(isApplicationScope ? applicationId! : null)

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

  /** Find a document's list item data from TanStack Query cache (searches all scopes). */
  const findDocInCache = useCallback((documentId: string): DocumentListItem | null => {
    const lists = queryClient.getQueriesData<DocumentListResponse>({
      queryKey: ['documents'],
      exact: false,
    })
    for (const [, data] of lists) {
      const item = data?.items?.find(i => i.id === documentId)
      if (item) return item
    }
    return null
  }, [queryClient])

  /** Look up a document's current row_version from TanStack Query cache. */
  const getDocRowVersion = useCallback((documentId: string): number | null => {
    const doc = queryClient.getQueryData<Document>(queryKeys.document(documentId))
    if (doc?.row_version) return doc.row_version
    return findDocInCache(documentId)?.row_version ?? null
  }, [queryClient, findDocInCache])

  /** Resolve DnD prefix to scope/scopeId for mutation params. */
  const getScopeFromPrefix = useCallback((prefix: string): ScopeInfo => {
    const parsed = parsePrefixToScope(prefix)
    if (!parsed) return { scope, scopeId: effectiveScopeId ?? '' }
    return { scope: parsed.scope, scopeId: parsed.scopeId || (effectiveScopeId ?? '') }
  }, [scope, effectiveScopeId])

  // Drag and drop
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } })
  )
  const [activeItem, setActiveItem] = useState<ActiveDragItem | null>(null)
  const [dropTargetFolderId, setDropTargetFolderId] = useState<string | null>(null)

  // UI state
  const [renamingItemId, setRenamingItemId] = useState<string | null>(null)
  const [renamingItemType, setRenamingItemType] = useState<'folder' | 'document'>('folder')
  const [renamingItemScope, setRenamingItemScope] = useState<string | null>(null)
  const [renamingItemScopeId, setRenamingItemScopeId] = useState<string | null>(null)
  const [contextMenuTarget, setContextMenuTarget] = useState<ContextMenuTarget | null>(null)

  // Dialog state
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [createType, setCreateType] = useState<'document' | 'folder'>('document')
  const [createParentId, setCreateParentId] = useState<string | null>(null)
  const [createScope, setCreateScope] = useState<'application' | 'project' | 'personal'>('personal')
  const [createScopeId, setCreateScopeId] = useState<string>('')
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; type: 'document' | 'folder'; name: string; scope: string | null; scopeId: string | null } | null>(null)

  const folders = folderTree ?? []
  const unfiledDocs = unfiledResponse?.items ?? []
  const projectList = projects ?? []

  // Only show loading skeleton on true first load (no data at all)
  // Don't show skeleton when switching tabs if we have any cached/placeholder data
  const hasAnyData = folders.length > 0 || unfiledDocs.length > 0
  const isInitialLoad = (isFoldersLoading || isUnfiledLoading || (isApplicationScope && isProjectsContentLoading)) && !hasAnyData

  // Project filtering (application scope only)
  const projectIdsWithContent = useMemo(
    () => new Set(projectsWithContent?.project_ids ?? []),
    [projectsWithContent?.project_ids]
  )

  // ========================================================================
  // Search filtering
  // ========================================================================

  const filteredFolders = useMemo(() => filterFolderTree(folders, searchQuery), [folders, searchQuery])
  const filteredDocs = useMemo(() => {
    if (!searchQuery) return unfiledDocs
    return unfiledDocs.filter(doc => matchesSearch(doc.title, searchQuery))
  }, [unfiledDocs, searchQuery])

  const filteredProjects = useMemo(() => {
    if (!isApplicationScope) return []
    if (searchQuery) {
      return projectList.filter(project => matchesSearch(project.name, searchQuery))
    }
    return projectList.filter(project => projectIdsWithContent.has(project.id))
  }, [isApplicationScope, projectList, projectIdsWithContent, searchQuery])

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

  /** Get the correct folder tree for a DnD prefix scope (app-level or project from cache). */
  const getFolderTree = useCallback((prefix: string): FolderTreeNode[] => {
    const colonIdx = prefix.indexOf(':')
    if (colonIdx === -1) return folders
    const scopeType = prefix.slice(0, colonIdx)
    const scopeId = prefix.slice(colonIdx + 1)
    if (scopeType === 'project' && scopeId) {
      return queryClient.getQueryData<FolderTreeNode[]>(queryKeys.documentFolders('project', scopeId)) ?? []
    }
    return folders
  }, [folders, queryClient])

  // DnD prefix: 'app' for application scope, otherwise the raw scope string (e.g. 'personal', 'project')
  const dndPrefix = isApplicationScope ? 'app' : scope

  // Sortable IDs for DnD (no reordering - only used for drag identification)
  const sortableItems = useMemo(() => {
    const items: string[] = []
    const addFolders = (nodes: FolderTreeNode[]) => {
      nodes.forEach(node => {
        items.push(`${dndPrefix}-folder-${node.id}`)
        addFolders(node.children)
      })
    }
    addFolders(filteredFolders)
    filteredDocs.forEach(doc => {
      items.push(`${dndPrefix}-doc-${doc.id}`)
    })
    return items
  }, [dndPrefix, filteredFolders, filteredDocs])

  // No-op sorting strategy: items are alphabetically ordered by the backend,
  // so we disable visual shifting during drag. DnD is only for nesting.
  const noReorderStrategy = useCallback(() => null, [])

  const validPrefixes = useMemo(() => [dndPrefix], [dndPrefix])

  const parse = useCallback((sortableId: string) => {
    return parseSortableId(sortableId, validPrefixes)
  }, [validPrefixes])

  const handleDragStart = useCallback((event: DragStartEvent) => {
    const parsed = parse(String(event.active.id))
    if (!parsed) return

    let name = 'Item'
    if (parsed.prefix === dndPrefix) {
      if (parsed.type === 'folder') {
        const folder = findFolderById(filteredFolders, parsed.itemId)
        if (folder) name = folder.name
      } else {
        const doc = filteredDocs.find(d => d.id === parsed.itemId)
        if (doc) name = doc.title
      }
    }

    const folderId = parsed.type === 'document' ? (findDocInCache(parsed.itemId)?.folder_id ?? null) : null
    setActiveItem({ id: parsed.itemId, type: parsed.type, name, scope: parsed.prefix, folderId })
  }, [dndPrefix, filteredFolders, filteredDocs, parse, findDocInCache])

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

    // Show drop target highlight when hovering over a folder with a different item
    if (overParsed.type === 'folder' && activeParsed.itemId !== overParsed.itemId) {
      setDropTargetFolderId(overParsed.itemId)
    } else if (overParsed.type === 'document') {
      // Resolve the document's parent folder so hovering over a child doc highlights the folder
      const parentFolderId = findDocInCache(overParsed.itemId)?.folder_id ?? null
      if (
        parentFolderId &&
        activeParsed.itemId !== parentFolderId &&
        // Don't highlight if dragging a doc already in that folder (use cached folderId from drag start)
        !(activeParsed.type === 'document' && activeItem?.folderId === parentFolderId) &&
        !(activeParsed.type === 'folder' && isDescendantOf(getFolderTree(activeParsed.prefix), activeParsed.itemId, parentFolderId))
      ) {
        setDropTargetFolderId(parentFolderId)
      } else {
        setDropTargetFolderId(null)
      }
    } else {
      setDropTargetFolderId(null)
    }
  }, [parse, findDocInCache, getFolderTree, activeItem])

  /** Check if a folder is at root level (no parent) in any cached tree */
  const isRootFolder = useCallback((folderId: string): boolean => {
    if (folders.some(f => f.id === folderId)) return true
    // Also check project folder trees in cache
    const allTrees = queryClient.getQueriesData<FolderTreeNode[]>({
      queryKey: ['documentFolders'],
      exact: false,
    })
    for (const [, rootNodes] of allTrees) {
      if (Array.isArray(rootNodes) && rootNodes.some(f => f.id === folderId)) return true
    }
    return false
  }, [folders, queryClient])

  /** Check if a document is at root level (unfiled) in any cached list */
  const isRootDocument = useCallback((documentId: string): boolean => {
    if (unfiledDocs.some(d => d.id === documentId)) return true
    const doc = findDocInCache(documentId)
    return doc !== null && !doc.folder_id
  }, [unfiledDocs, findDocInCache])

  /** Move an item to root (folder_id=null for docs, parent_id=null for folders) */
  const moveItemToRoot = useCallback(async (parsed: { prefix: string; type: 'folder' | 'document'; itemId: string }) => {
    const itemScope = getScopeFromPrefix(parsed.prefix)
    if (parsed.type === 'document') {
      const docFolderId = findDocInCache(parsed.itemId)?.folder_id
      if (docFolderId) {
        const rowVersion = getDocRowVersion(parsed.itemId)
        if (!rowVersion) {
          toast.error('Could not determine document version. Please try again.')
          return
        }
        await moveDocument.mutateAsync({ documentId: parsed.itemId, folder_id: null, row_version: rowVersion, ...itemScope })
        toast.success('Moved to root')
      }
    } else {
      const activeIsRoot = isRootFolder(parsed.itemId)
      if (!activeIsRoot) {
        await moveFolder.mutateAsync({ folderId: parsed.itemId, parent_id: null, ...itemScope })
        toast.success('Moved to root')
      }
    }
  }, [findDocInCache, getDocRowVersion, moveDocument, moveFolder, isRootFolder, getScopeFromPrefix])

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
    if (activeParsed.prefix !== overParsed.prefix) return // No cross-scope

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

    const scopeFolders = getFolderTree(activeParsed.prefix)
    const itemScope = getScopeFromPrefix(activeParsed.prefix)

    try {
      // Case 1: Dropping onto a folder → move item inside
      if (effectiveTargetType === 'folder' && activeParsed.itemId !== effectiveTargetId) {
        if (activeParsed.type === 'folder') {
          if (activeParsed.itemId === effectiveTargetId || isDescendantOf(scopeFolders, activeParsed.itemId, effectiveTargetId)) {
            toast.error('Cannot move a folder into its own subfolder')
            return
          }
          await moveFolder.mutateAsync({ folderId: activeParsed.itemId, parent_id: effectiveTargetId, ...itemScope })
          const targetFolder = findFolderById(scopeFolders, effectiveTargetId)
          toast.success(`Moved to ${targetFolder?.name ?? 'folder'}`)
        } else {
          // Skip if doc is already in this folder
          if (findDocInCache(activeParsed.itemId)?.folder_id === effectiveTargetId) return
          const rowVersion = getDocRowVersion(activeParsed.itemId)
          if (!rowVersion) {
            toast.error('Could not determine document version. Please try again.')
            return
          }
          await moveDocument.mutateAsync({ documentId: activeParsed.itemId, folder_id: effectiveTargetId, row_version: rowVersion, ...itemScope })
          const targetFolder = findFolderById(scopeFolders, effectiveTargetId)
          toast.success(`Moved to ${targetFolder?.name ?? 'folder'}`)
        }
        expandFolder(effectiveTargetId)
        return
      }

      // Case 2: Dropping onto a root-level item → move to root (unfiled) if currently nested
      if (overParsed.type === 'document' || overParsed.type === 'folder') {
        const overIsRoot = overParsed.type === 'folder'
          ? isRootFolder(overParsed.itemId)
          : isRootDocument(overParsed.itemId)

        if (!overIsRoot) return // Don't do anything if dropping on a nested sibling

        await moveItemToRoot(activeParsed)
      }
    } catch (error) {
      console.error('Failed to move:', error)
      toast.error(error instanceof Error ? error.message : 'Failed to move item')
    }
  }, [parse, moveFolder, moveDocument, expandFolder, getDocRowVersion, findDocInCache, isRootFolder, isRootDocument, moveItemToRoot, getFolderTree, getScopeFromPrefix])

  // ========================================================================
  // Context menu handlers
  // ========================================================================

  const handleContextMenu = useCallback(
    (e: React.MouseEvent, id: string, type: 'folder' | 'document', name: string, menuScope: 'application' | 'project' | 'personal' = scope as 'application' | 'project' | 'personal', menuScopeId: string = effectiveScopeId ?? '') => {
      e.preventDefault()
      e.stopPropagation()
      // For documents, select to open in editor. Folders only highlight via contextMenuTarget.
      if (type === 'document') {
        selectDocument(id)
      }
      setContextMenuTarget({ id, type, name, x: e.clientX, y: e.clientY, scope: menuScope, scopeId: menuScopeId })
    },
    [scope, effectiveScopeId, selectDocument]
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
  }, [createType, createScope, createScopeId, createParentId, userId, createDocument, createFolder, selectDocument, expandFolder])

  const handleRename = useCallback((id: string, type: 'folder' | 'document') => {
    const targetScope = contextMenuTarget?.scope ?? null
    const targetScopeId = contextMenuTarget?.scopeId ?? null
    handleCloseContextMenu()
    setRenamingItemId(id)
    setRenamingItemType(type)
    setRenamingItemScope(targetScope)
    setRenamingItemScopeId(targetScopeId)
  }, [handleCloseContextMenu, contextMenuTarget])

  const handleRenameSubmit = useCallback(async (newName: string) => {
    if (!renamingItemId) return
    const itemScope = renamingItemScope ?? scope
    const itemScopeId = renamingItemScopeId ?? effectiveScopeId ?? ''
    try {
      if (renamingItemType === 'folder') {
        await renameFolder.mutateAsync({ folderId: renamingItemId, name: newName, scope: itemScope, scopeId: itemScopeId })
      } else {
        const rowVersion = getDocRowVersion(renamingItemId)
        if (!rowVersion) {
          toast.error('Could not determine document version. Please try again.')
          setRenamingItemId(null)
          setRenamingItemScope(null)
          setRenamingItemScopeId(null)
          return
        }
        await renameDocument.mutateAsync({ documentId: renamingItemId, title: newName, row_version: rowVersion, scope: itemScope, scopeId: itemScopeId })
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to rename')
    }
    setRenamingItemId(null)
    setRenamingItemScope(null)
    setRenamingItemScopeId(null)
  }, [renamingItemId, renamingItemType, renamingItemScope, renamingItemScopeId, renameFolder, renameDocument, getDocRowVersion, scope, effectiveScopeId])

  const handleRenameCancel = useCallback(() => {
    setRenamingItemId(null)
    setRenamingItemScope(null)
    setRenamingItemScopeId(null)
  }, [])

  const handleDelete = useCallback((id: string, type: 'folder' | 'document') => {
    const targetScope = contextMenuTarget?.scope ?? null
    const targetScopeId = contextMenuTarget?.scopeId ?? null
    handleCloseContextMenu()
    const name = type === 'folder'
      ? findFolderById(folders, id)?.name || 'this folder'
      : findDocInCache(id)?.title || unfiledDocs.find((d) => d.id === id)?.title || 'this document'
    setDeleteTarget({ id, type, name, scope: targetScope, scopeId: targetScopeId })
    setDeleteDialogOpen(true)
  }, [folders, unfiledDocs, findDocInCache, contextMenuTarget, handleCloseContextMenu])

  const handleDeleteConfirm = useCallback(async () => {
    if (!deleteTarget) return
    const itemScope = deleteTarget.scope ?? scope
    const itemScopeId = deleteTarget.scopeId ?? effectiveScopeId ?? ''
    if (deleteTarget.type === 'folder') {
      await deleteFolder.mutateAsync({ folderId: deleteTarget.id, scope: itemScope, scopeId: itemScopeId })
    } else {
      await deleteDocument.mutateAsync({ documentId: deleteTarget.id, scope: itemScope, scopeId: itemScopeId })
      if (selectedDocumentId === deleteTarget.id) selectDocument(null)
    }
  }, [deleteTarget, deleteFolder, deleteDocument, selectedDocumentId, selectDocument, scope, effectiveScopeId])

  // ========================================================================
  // Selection handlers
  // ========================================================================

  const handleSelectDocument = useCallback((documentId: string) => {
    selectDocument(documentId)
  }, [selectDocument])

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
          lockInfo={activeLocks.get(doc.id)}
          onSelect={() => handleSelectDocument(doc.id)}
          onContextMenu={(e) => handleContextMenu(e, doc.id, 'document', doc.title)}
          onRenameSubmit={handleRenameSubmit}
          onRenameCancel={handleRenameCancel}
        />
      )
    },
    [isApplicationScope, selectedDocumentId, renamingItemId, activeItem, activeLocks, handleSelectDocument, handleContextMenu, handleRenameSubmit, handleRenameCancel]
  )

  // Stable primitive for context-menu folder highlight (avoids object ref in deps)
  const contextMenuFolderId = contextMenuTarget?.type === 'folder' ? contextMenuTarget.id : null

  const renderFolderNode = useCallback(
    (node: FolderTreeNode, depth: number): JSX.Element => {
      const isExpanded = expandedFolderIds.has(node.id)
      const isSelected = contextMenuFolderId === node.id
      const prefix = isApplicationScope ? 'app' : 'personal'
      const isDragging = activeItem?.id === node.id && activeItem?.type === 'folder' && activeItem?.scope === prefix
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
            isDragging={isDragging}
            isDropTarget={isDropTarget}
            sortableId={`${prefix}-folder-${node.id}`}
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
                scopeId={effectiveScopeId}
                folderId={node.id}
                depth={depth + 1}
                selectedDocumentId={selectedDocumentId}
                renamingItemId={renamingItemId}
                sortableIdPrefix={prefix}
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
    [isApplicationScope, scope, effectiveScopeId, expandedFolderIds, contextMenuFolderId, selectedDocumentId, renamingItemId, activeItem, dropTargetFolderId, activeLocks, toggleFolder, handleSelectDocument, handleContextMenu, handleRenameSubmit, handleRenameCancel]
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
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragStart={handleDragStart} onDragOver={handleDragOver} onDragEnd={handleDragEnd}>
      <div className="py-1" role="tree">
        {/* Main folder tree */}
        <SortableContext items={sortableItems} strategy={noReorderStrategy}>
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
                selectedDocumentId={selectedDocumentId}
                renamingItemId={renamingItemId}
                activeItem={activeItem}
                dropTargetFolderId={dropTargetFolderId}
                contextMenuFolderId={contextMenuFolderId}
                onToggleFolder={toggleFolder}
                onSelectDocument={handleSelectDocument}
                onContextMenu={handleContextMenu}
                onRenameSubmit={handleRenameSubmit}
                onRenameCancel={handleRenameCancel}
              />
            ))}
          </>
        )}

        {/* Root drop zone - visible during drag for moving items to root */}
        {activeItem && <RootDropZone />}
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
