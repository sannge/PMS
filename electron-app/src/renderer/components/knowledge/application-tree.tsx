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
  /** For documents: the folder_id at drag start (cached to avoid repeated query scans) */
  folderId: string | null
}

// ============================================================================
// Project Section (lazy-loaded)
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
    scope: 'application' | 'project',
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

  // Active locks for this project scope (lazy: only fetches when expanded)
  const projectActiveLocks = useActiveLocks('project', isExpanded ? project.id : null)

  const toggleExpanded = useCallback(() => {
    setIsExpanded((prev) => !prev)
  }, [])

  const folders = projectFolders ?? []
  const unfiledDocs = projectUnfiled?.items ?? []
  const isLoading = isExpanded && (isFoldersLoading || isUnfiledLoading) && folders.length === 0 && unfiledDocs.length === 0

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
    [
      expandedFolderIds,
      contextMenuFolderId,
      selectedDocumentId,
      renamingItemId,
      activeItem,
      dropTargetFolderId,
      project.id,
      projectActiveLocks,
      onToggleFolder,
      onSelectDocument,
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
    [
      selectedDocumentId,
      renamingItemId,
      activeItem,
      project.id,
      projectActiveLocks,
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

export function ApplicationTree({ applicationId }: ApplicationTreeProps): JSX.Element {
  const {
    expandedFolderIds,
    selectedDocumentId,
    searchQuery,
    toggleFolder,
    expandFolder,
    selectDocument,
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

  // Active locks for application scope (single batch request replaces N per-document queries)
  const activeLocks = useActiveLocks('application', applicationId)

  // Projects for this application
  const { data: projects } = useProjects(applicationId)
  const { data: projectsWithContent, isLoading: isProjectsContentLoading } = useProjectsWithContent(applicationId)

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

  /** Find a document's list item data from TanStack Query cache.
   *  Searches the provided scope first, then application scope as fallback. */
  const findDocInCache = useCallback((documentId: string, docScope?: string, docScopeId?: string): DocumentListItem | null => {
    const scopesToSearch = docScope && docScopeId
      ? [[docScope, docScopeId], ['application', applicationId]]
      : [['application', applicationId]]

    for (const [s, sid] of scopesToSearch) {
      const lists = queryClient.getQueriesData<DocumentListResponse>({
        queryKey: queryKeys.documents(s, sid),
        exact: false,
      })
      for (const [, data] of lists) {
        const item = data?.items.find(i => i.id === documentId)
        if (item) return item
      }
    }
    return null
  }, [queryClient, applicationId])

  /** Look up a document's current row_version from TanStack Query cache. */
  const getDocRowVersion = useCallback((documentId: string, docScope?: string, docScopeId?: string): number | null => {
    const doc = queryClient.getQueryData<Document>(queryKeys.document(documentId))
    if (doc?.row_version) return doc.row_version
    return findDocInCache(documentId, docScope, docScopeId)?.row_version ?? null
  }, [queryClient, findDocInCache])

  /** Resolve DnD prefix to scope/scopeId for mutation params. */
  const getScopeFromPrefix = useCallback((prefix: string): ScopeInfo => {
    const parsed = parsePrefixToScope(prefix)
    if (!parsed) return { scope: 'application', scopeId: applicationId }
    return { scope: parsed.scope, scopeId: parsed.scopeId || applicationId }
  }, [applicationId])

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
  const [renamingItemScope, setRenamingItemScope] = useState<string | null>(null)
  const [renamingItemScopeId, setRenamingItemScopeId] = useState<string | null>(null)
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
    scope: 'application' | 'project'
    scopeId: string
  } | null>(null)

  const folders = folderTree ?? []
  const unfiledDocs = unfiledResponse?.items ?? []
  const projectList = projects ?? []

  // Show skeleton when at least one query is loading and we have no data yet
  const isLoading = (isFoldersLoading || isUnfiledLoading || isProjectsContentLoading) && folders.length === 0 && unfiledDocs.length === 0

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
      return projectList.filter(project => matchesSearch(project.name, searchQuery))
    }
    // When not searching, only show projects with content
    return projectList.filter(project => projectIdsWithContent.has(project.id))
  }, [projectList, projectIdsWithContent, searchQuery])

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

  // No-op sorting strategy: items are alphabetically ordered by the backend,
  // so we disable visual shifting during drag. DnD is only for nesting.
  const noReorderStrategy = useCallback(() => null, [])

  const validPrefixes = useMemo(() => ['app'], [])

  const parse = useCallback((sortableId: string) => {
    return parseSortableId(sortableId, validPrefixes)
  }, [validPrefixes])

  const handleDragStart = useCallback((event: DragStartEvent) => {
    const { active } = event
    const activeIdStr = String(active.id)
    const parsed = parse(activeIdStr)

    if (!parsed) return

    let name = 'Item'
    if (parsed.prefix === 'app') {
      if (parsed.type === 'folder') {
        const folder = findFolderById(filteredFolders, parsed.itemId)
        if (folder) name = folder.name
      } else {
        const doc = filteredDocs.find(d => d.id === parsed.itemId)
        if (doc) name = doc.title
      }
    }

    let folderId: string | null = null
    if (parsed.type === 'document') {
      const isProjectScope = parsed.prefix.startsWith('project:')
      const docScope = isProjectScope ? 'project' : 'application'
      const docScopeId = isProjectScope ? parsed.prefix.replace('project:', '') : applicationId
      folderId = findDocInCache(parsed.itemId, docScope, docScopeId)?.folder_id ?? null
    }
    setActiveItem({
      id: parsed.itemId,
      type: parsed.type,
      name,
      scope: parsed.prefix,
      folderId,
    })
  }, [filteredFolders, filteredDocs, parse, findDocInCache, applicationId])

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
      const isOverProjectScope = overParsed.prefix.startsWith('project:')
      const overProjectId = isOverProjectScope ? overParsed.prefix.replace('project:', '') : null
      const docScope = isOverProjectScope ? 'project' : 'application'
      const docScopeId = isOverProjectScope ? overProjectId! : applicationId
      const parentFolderId = findDocInCache(overParsed.itemId, docScope, docScopeId)?.folder_id ?? null

      if (parentFolderId && activeParsed.itemId !== parentFolderId) {
        // Resolve the relevant folder tree for descendant checks
        const relevantFolders = isOverProjectScope
          ? (queryClient.getQueryData<FolderTreeNode[]>(queryKeys.documentFolders('project', overProjectId!)) ?? [])
          : folders

        if (
          // Don't highlight if dragging a doc already in that folder (use cached folderId from drag start)
          !(activeParsed.type === 'document' && activeItem?.folderId === parentFolderId) &&
          // Don't highlight if dragging a folder into its own descendant
          !(activeParsed.type === 'folder' && isDescendantOf(relevantFolders, activeParsed.itemId, parentFolderId))
        ) {
          setDropTargetFolderId(parentFolderId)
        } else {
          setDropTargetFolderId(null)
        }
      } else {
        setDropTargetFolderId(null)
      }
    } else {
      setDropTargetFolderId(null)
    }
  }, [parse, findDocInCache, folders, applicationId, queryClient, activeItem])

  /** Check if a folder is at root level (no parent) in any cached tree */
  const isRootFolder = useCallback((folderId: string): boolean => {
    if (folders.some(f => f.id === folderId)) return true
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
    // Search all document list caches (including project scopes)
    const allLists = queryClient.getQueriesData<DocumentListResponse>({
      queryKey: ['documents'],
      exact: false,
    })
    for (const [, data] of allLists) {
      const item = data?.items?.find((i: DocumentListItem) => i.id === documentId)
      if (item) return !item.folder_id
    }
    return false
  }, [unfiledDocs, queryClient])

  /** Move an item to root (folder_id=null for docs, parent_id=null for folders) */
  const moveItemToRoot = useCallback(async (parsed: { prefix: string; type: 'folder' | 'document'; itemId: string }) => {
    const itemScope = getScopeFromPrefix(parsed.prefix)
    if (parsed.type === 'document') {
      const docFolderId = findDocInCache(parsed.itemId, itemScope.scope, itemScope.scopeId)?.folder_id
      if (docFolderId) {
        const rowVersion = getDocRowVersion(parsed.itemId, itemScope.scope, itemScope.scopeId)
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

    // Prevent cross-scope drags
    if (activeParsed.prefix !== overParsed.prefix) return

    // Determine which folder tree to search for project vs app scope
    const isProjectScope = activeParsed.prefix.startsWith('project:')
    const projectId = isProjectScope ? activeParsed.prefix.replace('project:', '') : null
    const relevantFolders = isProjectScope
      ? (queryClient.getQueryData<FolderTreeNode[]>(queryKeys.documentFolders('project', projectId!)) ?? [])
      : folders

    // Resolve effective drop target: if dropping on a document inside a folder,
    // treat it as dropping onto that parent folder
    let effectiveTargetType = overParsed.type
    let effectiveTargetId = overParsed.itemId
    if (overParsed.type === 'document') {
      const docScope = isProjectScope ? 'project' : 'application'
      const docScopeId = isProjectScope ? projectId! : applicationId
      const parentFolderId = findDocInCache(overParsed.itemId, docScope, docScopeId)?.folder_id
      if (parentFolderId) {
        effectiveTargetType = 'folder'
        effectiveTargetId = parentFolderId
      }
    }

    const itemScope = getScopeFromPrefix(activeParsed.prefix)

    try {
      // Case 1: Dropping onto a folder → move item inside
      if (effectiveTargetType === 'folder' && activeParsed.itemId !== effectiveTargetId) {
        if (activeParsed.type === 'folder') {
          // Prevent circular: can't move folder into itself or its own descendant
          if (activeParsed.itemId === effectiveTargetId || isDescendantOf(relevantFolders, activeParsed.itemId, effectiveTargetId)) {
            toast.error('Cannot move a folder into its own subfolder')
            return
          }
          await moveFolder.mutateAsync({ folderId: activeParsed.itemId, parent_id: effectiveTargetId, ...itemScope })
          const targetFolder = findFolderById(relevantFolders, effectiveTargetId)
          toast.success(`Moved to ${targetFolder?.name ?? 'folder'}`)
        } else {
          const docScope = isProjectScope ? 'project' : 'application'
          const docScopeId = isProjectScope ? projectId! : applicationId
          // Skip if doc is already in this folder
          if (findDocInCache(activeParsed.itemId, docScope, docScopeId)?.folder_id === effectiveTargetId) return
          const rowVersion = getDocRowVersion(activeParsed.itemId, docScope, docScopeId)
          if (!rowVersion) {
            toast.error('Could not determine document version. Please try again.')
            return
          }
          await moveDocument.mutateAsync({ documentId: activeParsed.itemId, folder_id: effectiveTargetId, row_version: rowVersion, ...itemScope })
          const targetFolder = findFolderById(relevantFolders, effectiveTargetId)
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

        if (!overIsRoot) return // Don't do anything if dropping on a nested sibling

        await moveItemToRoot(activeParsed)
      }
    } catch (error) {
      console.error('Failed to move:', error)
      toast.error(error instanceof Error ? error.message : 'Failed to move item')
    }
  }, [parse, folders, queryClient, applicationId, moveFolder, moveDocument, expandFolder, getDocRowVersion, findDocInCache, isRootFolder, isRootDocument, moveItemToRoot, getScopeFromPrefix])

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
      // For documents, select to open in editor. Folders only highlight via contextMenuTarget.
      if (type === 'document') {
        selectDocument(id)
      }
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
    [applicationId, selectDocument]
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
    [createType, createScope, createScopeId, createParentId, createDocument, createFolder, selectDocument, expandFolder]
  )

  const handleRename = useCallback(
    (id: string, type: 'folder' | 'document') => {
      const targetScope = contextMenuTarget?.scope ?? null
      const targetScopeId = contextMenuTarget?.scopeId ?? null
      handleCloseContextMenu()
      setRenamingItemId(id)
      setRenamingItemType(type)
      setRenamingItemScope(targetScope)
      setRenamingItemScopeId(targetScopeId)
    },
    [handleCloseContextMenu, contextMenuTarget]
  )

  const handleRenameSubmit = useCallback(
    async (newName: string) => {
      if (!renamingItemId) return
      const itemScope = renamingItemScope ?? 'application'
      const itemScopeId = renamingItemScopeId ?? applicationId

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
          await renameDocument.mutateAsync({
            documentId: renamingItemId,
            title: newName,
            row_version: rowVersion,
            scope: itemScope,
            scopeId: itemScopeId,
          })
        }
      } catch (err) {
        toast.error(err instanceof Error ? err.message : 'Failed to rename')
      }

      setRenamingItemId(null)
      setRenamingItemScope(null)
      setRenamingItemScopeId(null)
    },
    [renamingItemId, renamingItemType, renamingItemScope, renamingItemScopeId, renameFolder, renameDocument, getDocRowVersion, applicationId]
  )

  const handleRenameCancel = useCallback(() => {
    setRenamingItemId(null)
    setRenamingItemScope(null)
    setRenamingItemScopeId(null)
  }, [])

  const handleDelete = useCallback(
    (id: string, type: 'folder' | 'document') => {
      // Capture scope before closing context menu (contextMenuTarget is cleared on close)
      const scope = contextMenuTarget?.scope ?? 'application'
      const scopeId = contextMenuTarget?.scopeId ?? applicationId
      handleCloseContextMenu()
      // Find the name from the tree data
      const name =
        type === 'folder'
          ? findFolderById(folders, id)?.name || 'this folder'
          : findDocInCache(id)?.title || unfiledDocs.find((d) => d.id === id)?.title || 'this document'
      setDeleteTarget({ id, type, name, scope, scopeId })
      setDeleteDialogOpen(true)
    },
    [folders, unfiledDocs, handleCloseContextMenu, contextMenuTarget, applicationId, findDocInCache]
  )

  const handleDeleteConfirm = useCallback(async () => {
    if (!deleteTarget) return
    const itemScope = deleteTarget.scope ?? 'application'
    const itemScopeId = deleteTarget.scopeId ?? applicationId
    if (deleteTarget.type === 'folder') {
      await deleteFolder.mutateAsync({ folderId: deleteTarget.id, scope: itemScope, scopeId: itemScopeId })
    } else {
      await deleteDocument.mutateAsync({ documentId: deleteTarget.id, scope: itemScope, scopeId: itemScopeId })
      if (selectedDocumentId === deleteTarget.id) selectDocument(null)
    }
  }, [deleteTarget, deleteFolder, deleteDocument, selectedDocumentId, selectDocument, applicationId])

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
    setCreateScope('application')
    setCreateScopeId(applicationId)
    setCreateDialogOpen(true)
  }, [applicationId])

  // ========================================================================
  // Recursive folder renderer (app-level)
  // ========================================================================

  // Stable primitive for context-menu folder highlight (avoids object ref in deps)
  const contextMenuFolderId = contextMenuTarget?.type === 'folder' ? contextMenuTarget.id : null

  const renderFolderNode = useCallback(
    (node: FolderTreeNode, depth: number): JSX.Element => {
      const isExpanded = expandedFolderIds.has(node.id)
      const isSelected = contextMenuFolderId === node.id
      const isDragging = activeItem?.id === node.id && activeItem?.type === 'folder' && activeItem?.scope === 'app'
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
            sortableId={`app-folder-${node.id}`}
            onToggleExpand={() => toggleFolder(node.id)}
            onSelect={() => toggleFolder(node.id)}
            onContextMenu={(e) =>
              handleContextMenu(e, node.id, 'folder', node.name, 'application', applicationId)
            }
            onRenameSubmit={handleRenameSubmit}
            onRenameCancel={handleRenameCancel}
          />
          {isExpanded && (
            <>
              {node.children.map((child) => renderFolderNode(child, depth + 1))}
              <FolderDocuments
                scope="application"
                scopeId={applicationId}
                folderId={node.id}
                depth={depth + 1}
                selectedDocumentId={selectedDocumentId}
                renamingItemId={renamingItemId}
                sortableIdPrefix="app"
                activeItemId={activeItem?.type === 'document' ? activeItem.id : null}
                activeLocks={activeLocks}
                onSelectDocument={handleSelectDocument}
                onContextMenu={(e, id, type, name) =>
                  handleContextMenu(e, id, type, name, 'application', applicationId)
                }
                onRenameSubmit={handleRenameSubmit}
                onRenameCancel={handleRenameCancel}
              />
            </>
          )}
        </div>
      )
    },
    [
      expandedFolderIds,
      contextMenuFolderId,
      selectedDocumentId,
      renamingItemId,
      activeItem,
      dropTargetFolderId,
      applicationId,
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
          lockInfo={activeLocks.get(doc.id)}
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
      onDragOver={handleDragOver}
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
        <SortableContext items={appLevelSortableItems} strategy={noReorderStrategy}>
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
                selectedDocumentId={selectedDocumentId}
                renamingItemId={renamingItemId}
                activeItem={activeItem}
                dropTargetFolderId={dropTargetFolderId}
                contextMenuFolderId={contextMenuFolderId}
                hideIfEmpty={false}
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
