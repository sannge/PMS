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

import { useState, useCallback, useMemo, useEffect, useRef } from 'react'
import { FilePlus, Folder, FileText, File as FileIcon, FolderKanban, ChevronRight, Archive } from 'lucide-react'
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
import { useAuthUserId } from '@/contexts/auth-context'
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
import { createEmptyCanvas } from './canvas-types'
import { matchesSearch, filterFolderTree, findFolderById, isDescendantOf, collectAncestorIds } from './tree-utils'
import { useProjectPermissionsMap } from '@/hooks/use-knowledge-permissions'
import { useUploadFile, useRenameFile, useDeleteFile, useMoveFile, useUnfiledFiles, fetchFileDownloadUrl, type FolderFileListItem, type UploadConflictError } from '@/hooks/use-folder-files'
import { FileConflictDialog } from './file-conflict-dialog'
import { parseSortableId, parsePrefixToScope, type ScopeInfo } from './dnd-utils'

// ============================================================================
// Types
// ============================================================================

interface KnowledgeTreeProps {
  /** Application ID - when provided, shows project sections */
  applicationId?: string
  /** Whether the current user has edit permission (defaults to true) */
  canEdit?: boolean
}

interface ContextMenuTarget {
  id: string
  type: 'folder' | 'document' | 'file'
  name: string
  x: number
  y: number
  scope: 'application' | 'project' | 'personal'
  scopeId: string
  /** For file targets: the folder containing the file */
  folderId?: string
}

interface ActiveDragItem {
  id: string
  type: 'folder' | 'document' | 'file'
  name: string
  scope: string
  /** For documents/files: the folder_id at drag start (cached to avoid repeated query scans) */
  folderId: string | null
}

// ============================================================================
// Project Section (lazy-loaded, only for application scope)
// ============================================================================

interface ProjectSectionProps {
  project: Project
  expandedFolderIds: Set<string>
  selectedDocumentId: string | null
  selectedFileId?: string | null
  renamingItemId: string | null
  activeItem: ActiveDragItem | null
  dropTargetFolderId: string | null
  /** Folder ID currently targeted by context menu (for transient highlight) */
  contextMenuFolderId: string | null
  /** Hide this project section if it has no documents after loading */
  hideIfEmpty?: boolean
  /** Whether the user can edit items in this project section */
  canEdit?: boolean
  /** When this matches project.id, auto-expand the project section */
  revealProjectId?: string | null
  /** Folder ID to reveal (expand ancestors) once project content loads */
  revealFolderId?: string | null
  expandFolders?: (ids: string[]) => void
  clearReveal?: () => void
  onToggleFolder: (folderId: string) => void
  onSelectDocument: (documentId: string) => void
  onSelectFile?: (file: FolderFileListItem) => void
  onFileContextMenu?: (e: React.MouseEvent, file: FolderFileListItem, menuScope?: 'application' | 'project' | 'personal', menuScopeId?: string) => void
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
  selectedFileId,
  renamingItemId,
  activeItem,
  dropTargetFolderId,
  contextMenuFolderId,
  hideIfEmpty = false,
  canEdit = true,
  revealProjectId,
  revealFolderId,
  expandFolders: expandFoldersFn,
  clearReveal: clearRevealFn,
  onToggleFolder,
  onSelectDocument,
  onSelectFile,
  onFileContextMenu,
  onContextMenu,
  onRenameSubmit,
  onRenameCancel,
}: ProjectSectionProps): JSX.Element | null {
  const [isExpanded, setIsExpanded] = useState(false)
  const revealProcessedRef = useRef<string | null>(null)

  // Reset reveal guard when revealFolderId is cleared
  useEffect(() => {
    if (!revealFolderId) revealProcessedRef.current = null
  }, [revealFolderId])

  // Auto-expand when this project is the reveal target
  useEffect(() => {
    if (revealProjectId === project.id && !isExpanded) {
      setIsExpanded(true)
    }
  }, [revealProjectId, project.id, isExpanded])

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

  // Unfiled files at project scope root
  const { data: projectUnfiledFiles } = useUnfiledFiles(
    'project',
    isExpanded ? project.id : null
  )

  // Active locks for this project scope (lazy: only fetches when expanded)
  const projectActiveLocks = useActiveLocks('project', isExpanded ? project.id : null)

  const toggleExpanded = useCallback(() => setIsExpanded((prev) => !prev), [])

  const folders = projectFolders ?? []
  const unfiledDocs = projectUnfiled?.items ?? []
  const unfiledFiles = projectUnfiledFiles?.items ?? []
  const isLoading = isExpanded && (isFoldersLoading || isUnfiledLoading) && folders.length === 0 && unfiledDocs.length === 0

  // Expand ancestors when this project is the reveal target and data has loaded
  useEffect(() => {
    if (
      revealProjectId !== project.id ||
      !revealFolderId ||
      !expandFoldersFn ||
      !clearRevealFn ||
      folders.length === 0 ||
      revealProcessedRef.current === revealFolderId
    ) return
    revealProcessedRef.current = revealFolderId
    const ancestorIds = collectAncestorIds(folders, revealFolderId)
    expandFoldersFn(ancestorIds)
    clearRevealFn()
  }, [revealProjectId, revealFolderId, project.id, folders, expandFoldersFn, clearRevealFn])

  const isEmpty = useMemo(() => {
    if (!isExpanded || isLoading) return false
    return folders.length === 0 && unfiledDocs.length === 0 && unfiledFiles.length === 0
  }, [isExpanded, isLoading, folders.length, unfiledDocs.length, unfiledFiles.length])

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
    unfiledFiles.forEach(file => {
      items.push(`project-${project.id}-file-${file.id}`)
    })
    return items
  }, [project.id, folders, unfiledDocs, unfiledFiles])

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
            sortableId={canEdit ? `project-${project.id}-folder-${node.id}` : undefined}
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
                selectedFileId={selectedFileId}
                renamingItemId={renamingItemId}
                sortableIdPrefix={canEdit ? `project-${project.id}` : ''}
                activeItemId={activeItem?.type === 'document' ? activeItem.id : null}
                activeLocks={projectActiveLocks}
                onSelectDocument={onSelectDocument}
                onContextMenu={(e, id, type, name) =>
                  onContextMenu(e, id, type, name, 'project', project.id)
                }
                onRenameSubmit={onRenameSubmit}
                onRenameCancel={onRenameCancel}
                onSelectFile={onSelectFile}
                onFileContextMenu={(e, file) => onFileContextMenu?.(e, file, 'project', project.id)}
              />
            </>
          )}
        </div>
      )
    },
    [expandedFolderIds, contextMenuFolderId, selectedDocumentId, selectedFileId, renamingItemId, activeItem, dropTargetFolderId, project.id, canEdit, projectActiveLocks, onToggleFolder, onSelectDocument, onContextMenu, onRenameSubmit, onRenameCancel, onFileContextMenu]
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
          sortableId={canEdit ? `project-${project.id}-doc-${doc.id}` : undefined}
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
    [selectedDocumentId, renamingItemId, activeItem, project.id, canEdit, projectActiveLocks, onSelectDocument, onContextMenu, onRenameSubmit, onRenameCancel]
  )

  // Hide section if expanded, loaded, and empty (when hideIfEmpty is true)
  // This must be AFTER all hooks to avoid React "fewer hooks" error
  if (hideIfEmpty && isExpanded && isEmpty && !isLoading) {
    return null
  }

  const isArchived = project.archived_at !== null

  return (
    <div className={cn('border-l-2 border-primary/20 ml-2 mt-1', isArchived && 'opacity-70')}>
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
        {isArchived && (
          <span className="inline-flex items-center gap-0.5 text-[10px] text-muted-foreground/70 shrink-0">
            <Archive className="h-3 w-3" />
            Archived
          </span>
        )}
      </button>

      {isExpanded && (
        <div className="pl-2">
          {isLoading ? (
            <ProjectContentSkeleton />
          ) : (
            <SortableContext items={projectSortableItems} strategy={noReorderStrategy}>
              {folders.map((node) => renderFolderNode(node, 1))}
              {unfiledDocs.map((doc) => renderDocumentItem(doc, 1))}
              {unfiledFiles.map((file) => (
                <FolderTreeItem
                  key={`file-${file.id}`}
                  node={file}
                  type="file"
                  depth={1}
                  isSelected={selectedFileId === file.id}
                  isRenaming={renamingItemId === file.id}
                  sortableId={canEdit ? `project-${project.id}-file-${file.id}` : undefined}
                  onSelect={() => onSelectFile?.(file)}
                  onContextMenu={(e) => onFileContextMenu?.(e, file, 'project', project.id)}
                  onRenameSubmit={onRenameSubmit}
                  onRenameCancel={onRenameCancel}
                />
              ))}
              {folders.length === 0 && unfiledDocs.length === 0 && unfiledFiles.length === 0 && (
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

export function KnowledgeTree({ applicationId, canEdit = true }: KnowledgeTreeProps): JSX.Element {
  const {
    scope: contextScope,
    scopeId: contextScopeId,
    expandedFolderIds,
    selectedDocumentId,
    selectedFileId,
    searchQuery,
    revealFolderId,
    revealProjectId,
    toggleFolder,
    expandFolder,
    selectDocument,
    selectFile,
    expandFolders,
    clearReveal,
  } = useKnowledgeBase()

  const userId = useAuthUserId()

  // Determine effective scope - applicationId prop overrides context
  const isApplicationScope = !!applicationId
  const scope = isApplicationScope ? 'application' : contextScope
  const scopeId = isApplicationScope ? applicationId : contextScopeId

  // Resolve scopeId for personal scope (use userId)
  const effectiveScopeId = scope === 'personal' ? userId : scopeId

  // Data queries
  const { data: folderTree, isLoading: isFoldersLoading, isFetching: isFoldersFetching } = useFolderTree(scope, effectiveScopeId)
  const { data: unfiledResponse, isLoading: isUnfiledLoading } = useDocuments(scope, effectiveScopeId, { includeUnfiled: true })
  const { data: unfiledFilesResponse } = useUnfiledFiles(scope, effectiveScopeId)

  // Active locks for the current scope (single batch request replaces N per-document queries)
  const activeLocks = useActiveLocks(scope, effectiveScopeId)

  // Project data (only for application scope)
  const { data: projects } = useProjects(isApplicationScope ? applicationId : undefined, { includeArchived: true })
  const { data: projectsWithContent, isLoading: isProjectsContentLoading } = useProjectsWithContent(isApplicationScope ? applicationId! : null)

  // Per-project permissions (application scope only)
  const { permissionsMap: projectPermissionsMap } = useProjectPermissionsMap(
    isApplicationScope ? applicationId : undefined
  )

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

  /** Find a file's list item data from TanStack Query cache (searches all folder file caches). */
  const findFileInCache = useCallback((fileId: string): FolderFileListItem | null => {
    const lists = queryClient.getQueriesData<{ items: FolderFileListItem[] }>({
      queryKey: ['folderFiles'],
      exact: false,
    })
    for (const [, data] of lists) {
      const item = data?.items?.find(i => i.id === fileId)
      if (item) return item
    }
    return null
  }, [queryClient])

  // --- Drag lookup Maps (FIX-3) ---
  // Pre-built Maps for O(1) lookups during drag operations (handleDragOver fires at 60fps).
  // Built once at drag start, cleared on drag end. Falls back to linear scan for non-drag usage.
  const dragDocMapRef = useRef<Map<string, DocumentListItem> | null>(null)
  const dragFileMapRef = useRef<Map<string, FolderFileListItem> | null>(null)

  /** Build lookup Maps from the current query cache. Called once at drag start. */
  const buildDragLookupMaps = useCallback(() => {
    const docMap = new Map<string, DocumentListItem>()
    const allDocs = queryClient.getQueriesData<DocumentListResponse>({
      queryKey: ['documents'],
      exact: false,
    })
    for (const [, data] of allDocs) {
      if (data?.items) {
        for (const doc of data.items) {
          docMap.set(doc.id, doc)
        }
      }
    }
    dragDocMapRef.current = docMap

    const fileMap = new Map<string, FolderFileListItem>()
    const allFiles = queryClient.getQueriesData<{ items: FolderFileListItem[] }>({
      queryKey: ['folderFiles'],
      exact: false,
    })
    for (const [, data] of allFiles) {
      if (data?.items) {
        for (const file of data.items) {
          fileMap.set(file.id, file)
        }
      }
    }
    dragFileMapRef.current = fileMap
  }, [queryClient])

  const clearDragLookupMaps = useCallback(() => {
    dragDocMapRef.current = null
    dragFileMapRef.current = null
  }, [])

  /** O(1) doc lookup during drag, falls back to linear scan if maps not built. */
  const findDocDuringDrag = useCallback((documentId: string): DocumentListItem | null => {
    if (dragDocMapRef.current) return dragDocMapRef.current.get(documentId) ?? null
    return findDocInCache(documentId)
  }, [findDocInCache])

  /** O(1) file lookup during drag, falls back to linear scan if maps not built. */
  const findFileDuringDrag = useCallback((fileId: string): FolderFileListItem | null => {
    if (dragFileMapRef.current) return dragFileMapRef.current.get(fileId) ?? null
    return findFileInCache(fileId)
  }, [findFileInCache])

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
  const [renamingItemType, setRenamingItemType] = useState<'folder' | 'document' | 'file'>('folder')
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

  // File upload state
  const uploadFileInputRef = useRef<HTMLInputElement>(null)
  const uploadFolderIdRef = useRef<string | null>(null)
  const uploadFileMutation = useUploadFile()
  const renameFileMutation = useRenameFile()
  const deleteFileMutation = useDeleteFile()
  const moveFileMutation = useMoveFile()
  const [conflictDialogOpen, setConflictDialogOpen] = useState(false)
  const [conflictQueue, setConflictQueue] = useState<{ file: File; existingFileId: string | null }[]>([])
  const [conflictFolderId, setConflictFolderId] = useState<string | null>(null)

  // Derive current conflict from the front of the queue
  const conflictFile = conflictQueue.length > 0 ? conflictQueue[0].file : null
  const conflictExistingFileId = conflictQueue.length > 0 ? conflictQueue[0].existingFileId : null

  // When the conflict queue empties while the dialog is open, close the dialog.
  // Done via useEffect (not inside setConflictQueue updater) to avoid clearing
  // file props while the dialog close animation is still rendering.
  useEffect(() => {
    if (conflictDialogOpen && conflictQueue.length === 0) {
      setConflictDialogOpen(false)
      setConflictFolderId(null)
    }
  }, [conflictDialogOpen, conflictQueue.length])

  const folders = folderTree ?? []
  const unfiledDocs = unfiledResponse?.items ?? []
  const unfiledFiles = unfiledFilesResponse?.items ?? []
  const projectList = projects ?? []

  // Only show loading skeleton on true first load (no data at all)
  // Don't show skeleton when switching tabs if we have any cached/placeholder data
  const hasAnyData = folders.length > 0 || unfiledDocs.length > 0 || unfiledFiles.length > 0
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
  const filteredUnfiledFiles = useMemo(() => {
    if (!searchQuery) return unfiledFiles
    return unfiledFiles.filter(file => matchesSearch(file.display_name, searchQuery))
  }, [unfiledFiles, searchQuery])

  const filteredProjects = useMemo(() => {
    if (!isApplicationScope) return []
    let filtered: Project[]
    if (searchQuery) {
      filtered = projectList.filter(project => matchesSearch(project.name, searchQuery))
    } else {
      filtered = projectList.filter(project => projectIdsWithContent.has(project.id))
    }
    // Sort archived projects to the end, preserving backend order within each group
    return filtered.sort((a, b) => {
      const aArchived = a.archived_at !== null ? 1 : 0
      const bArchived = b.archived_at !== null ? 1 : 0
      return aArchived - bArchived
    })
  }, [isApplicationScope, projectList, projectIdsWithContent, searchQuery])

  // Auto-expand folders with matching children when searching (batch dispatch)
  useEffect(() => {
    if (!searchQuery) return
    const idsToExpand: string[] = []
    const collect = (nodes: FolderTreeNode[]) => {
      nodes.forEach(node => {
        if (node.children.length > 0) {
          idsToExpand.push(node.id)
          collect(node.children)
        }
      })
    }
    collect(filteredFolders)
    if (idsToExpand.length > 0) expandFolders(idsToExpand)
  }, [searchQuery, filteredFolders, expandFolders])

  // Auto-expand ancestors when navigating to a document via search
  const revealProcessedRef = useRef<string | null>(null)
  const pendingScrollRef = useRef(false)

  // Reset reveal guard when revealFolderId is cleared so re-navigation to
  // the same folder works correctly.
  useEffect(() => {
    if (!revealFolderId) {
      revealProcessedRef.current = null
      pendingScrollRef.current = false
    }
  }, [revealFolderId])

  useEffect(() => {
    if (!revealFolderId) return
    if (revealProjectId) {
      // Project reveal: folder expansion handled by ProjectSection, but we
      // still need scroll-into-view once the folders expand in the DOM.
      pendingScrollRef.current = true
      return
    }
    if (!folders.length) return
    if (revealProcessedRef.current === revealFolderId) return
    revealProcessedRef.current = revealFolderId
    pendingScrollRef.current = true
    const ancestorIds = collectAncestorIds(folders, revealFolderId)
    expandFolders(ancestorIds)
    clearReveal()
  }, [revealFolderId, revealProjectId, folders, expandFolders, clearReveal])

  // Fallback: clear stale reveal state if project data never loads (e.g. filtered out, query error)
  useEffect(() => {
    if (!revealProjectId || !revealFolderId) return
    const fallback = setTimeout(() => clearReveal(), 3000)
    return () => clearTimeout(fallback)
  }, [revealProjectId, revealFolderId, clearReveal])

  // Scroll the selected document into view in the tree after reveal expansion.
  // Only fires once per reveal (pendingScrollRef is set in the reveal effect above).
  // The 150ms delay accounts for DOM updates after folder expansion in a non-virtualized tree.
  useEffect(() => {
    if (!selectedDocumentId || !pendingScrollRef.current) return
    pendingScrollRef.current = false
    const timer = setTimeout(() => {
      document.querySelector(`[data-tree-document-id="${CSS.escape(selectedDocumentId)}"]`)
        ?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    }, 150)
    return () => clearTimeout(timer)
  }, [selectedDocumentId, expandedFolderIds]) // re-run when folders expand

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
    filteredUnfiledFiles.forEach(file => {
      items.push(`${dndPrefix}-file-${file.id}`)
    })
    return items
  }, [dndPrefix, filteredFolders, filteredDocs, filteredUnfiledFiles])

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

    // Build O(1) lookup maps once at drag start (used by handleDragOver at 60fps)
    buildDragLookupMaps()

    let name = 'Item'
    let folderId: string | null = null
    if (parsed.prefix === dndPrefix) {
      if (parsed.type === 'folder') {
        const folder = findFolderById(filteredFolders, parsed.itemId)
        if (folder) name = folder.name
      } else if (parsed.type === 'file') {
        const fileItem = findFileDuringDrag(parsed.itemId)
        if (fileItem) {
          name = fileItem.display_name
          folderId = fileItem.folder_id
        }
      } else {
        const doc = filteredDocs.find(d => d.id === parsed.itemId)
        if (doc) name = doc.title
        folderId = findDocDuringDrag(parsed.itemId)?.folder_id ?? null
      }
    } else {
      // Project scope
      if (parsed.type === 'file') {
        const fileItem = findFileDuringDrag(parsed.itemId)
        if (fileItem) {
          name = fileItem.display_name
          folderId = fileItem.folder_id
        }
      } else if (parsed.type === 'document') {
        folderId = findDocDuringDrag(parsed.itemId)?.folder_id ?? null
      }
    }

    if (parsed.type === 'document' && folderId === null) {
      folderId = findDocDuringDrag(parsed.itemId)?.folder_id ?? null
    }
    setActiveItem({ id: parsed.itemId, type: parsed.type, name, scope: parsed.prefix, folderId })
  }, [dndPrefix, filteredFolders, filteredDocs, parse, findDocDuringDrag, findFileDuringDrag, buildDragLookupMaps])

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
    } else if (overParsed.type === 'document' || overParsed.type === 'file') {
      // Resolve the item's parent folder so hovering over a child doc/file highlights the folder
      // Uses O(1) Map lookup instead of linear cache scan (this handler fires at 60fps)
      const parentFolderId = overParsed.type === 'document'
        ? (findDocDuringDrag(overParsed.itemId)?.folder_id ?? null)
        : (findFileDuringDrag(overParsed.itemId)?.folder_id ?? null)
      if (
        parentFolderId &&
        activeParsed.itemId !== parentFolderId &&
        // Don't highlight if dragging an item already in that folder
        !((activeParsed.type === 'document' || activeParsed.type === 'file') && activeItem?.folderId === parentFolderId) &&
        !(activeParsed.type === 'folder' && isDescendantOf(getFolderTree(activeParsed.prefix), activeParsed.itemId, parentFolderId))
      ) {
        setDropTargetFolderId(parentFolderId)
      } else {
        setDropTargetFolderId(null)
      }
    } else {
      setDropTargetFolderId(null)
    }
  }, [parse, findDocDuringDrag, findFileDuringDrag, getFolderTree, activeItem])

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

  /** Move an item to root (folder_id=null for docs/files, parent_id=null for folders) */
  const moveItemToRoot = useCallback(async (parsed: { prefix: string; type: 'folder' | 'document' | 'file'; itemId: string }) => {
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
    } else if (parsed.type === 'file') {
      const fileItem = findFileInCache(parsed.itemId)
      if (fileItem?.folder_id) {
        await moveFileMutation.mutateAsync({
          fileId: parsed.itemId,
          targetFolderId: null,
          rowVersion: fileItem.row_version,
          sourceFolderId: fileItem.folder_id,
          scope: itemScope.scope,
          scopeId: itemScope.scopeId,
        })
        toast.success('Moved to root')
      }
    } else {
      const activeIsRoot = isRootFolder(parsed.itemId)
      if (!activeIsRoot) {
        await moveFolder.mutateAsync({ folderId: parsed.itemId, parent_id: null, ...itemScope })
        toast.success('Moved to root')
      }
    }
  }, [findDocInCache, findFileInCache, getDocRowVersion, moveDocument, moveFolder, moveFileMutation, isRootFolder, getScopeFromPrefix])

  const handleDragEnd = useCallback(async (event: DragEndEvent) => {
    const { active, over } = event
    setActiveItem(null)
    setDropTargetFolderId(null)

    if (!over || active.id === over.id) {
      clearDragLookupMaps()
      return
    }

    const activeParsed = parse(String(active.id))

    // Case 0: Dropping onto root drop zone → move to root
    if (String(over.id) === ROOT_DROP_ZONE_ID) {
      if (!activeParsed) {
        clearDragLookupMaps()
        return
      }
      try {
        await moveItemToRoot(activeParsed)
      } catch (error) {
        console.error('Failed to move:', error)
        toast.error(error instanceof Error ? error.message : 'Failed to move item')
      }
      clearDragLookupMaps()
      return
    }

    const overParsed = parse(String(over.id))

    if (!activeParsed || !overParsed) {
      clearDragLookupMaps()
      return
    }
    if (activeParsed.prefix !== overParsed.prefix) {
      clearDragLookupMaps()
      return // No cross-scope
    }

    // Resolve effective drop target: if dropping on a document/file inside a folder,
    // treat it as dropping onto that parent folder
    let effectiveTargetType = overParsed.type
    let effectiveTargetId = overParsed.itemId
    if (overParsed.type === 'document') {
      const parentFolderId = findDocDuringDrag(overParsed.itemId)?.folder_id
      if (parentFolderId) {
        effectiveTargetType = 'folder'
        effectiveTargetId = parentFolderId
      }
    } else if (overParsed.type === 'file') {
      const parentFolderId = findFileDuringDrag(overParsed.itemId)?.folder_id
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
        } else if (activeParsed.type === 'file') {
          // Skip if file is already in this folder
          const fileItem = findFileDuringDrag(activeParsed.itemId)
          if (!fileItem) {
            toast.error('Could not determine file version. Please try again.')
            return
          }
          if (fileItem.folder_id === effectiveTargetId) return
          await moveFileMutation.mutateAsync({
            fileId: activeParsed.itemId,
            targetFolderId: effectiveTargetId,
            rowVersion: fileItem.row_version,
            sourceFolderId: fileItem.folder_id ?? null,
            scope: itemScope.scope,
            scopeId: itemScope.scopeId,
          })
          const targetFolder = findFolderById(scopeFolders, effectiveTargetId)
          toast.success(`Moved to ${targetFolder?.name ?? 'folder'}`)
        } else {
          // Skip if doc is already in this folder
          if (findDocDuringDrag(activeParsed.itemId)?.folder_id === effectiveTargetId) return
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
      if (overParsed.type === 'document' || overParsed.type === 'folder' || overParsed.type === 'file') {
        const overIsRoot = overParsed.type === 'folder'
          ? isRootFolder(overParsed.itemId)
          : overParsed.type === 'file'
            ? !(findFileDuringDrag(overParsed.itemId)?.folder_id)
            : isRootDocument(overParsed.itemId)

        if (!overIsRoot) return // Don't do anything if dropping on a nested sibling

        await moveItemToRoot(activeParsed)
      }
    } catch (error) {
      console.error('Failed to move:', error)
      toast.error(error instanceof Error ? error.message : 'Failed to move item')
    } finally {
      clearDragLookupMaps()
    }
  }, [parse, moveFolder, moveDocument, moveFileMutation, expandFolder, getDocRowVersion, findDocDuringDrag, findFileDuringDrag, isRootFolder, isRootDocument, moveItemToRoot, getFolderTree, getScopeFromPrefix, clearDragLookupMaps])

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

  const handleUploadFiles = useCallback((folderId: string) => {
    handleCloseContextMenu()
    uploadFolderIdRef.current = folderId
    uploadFileInputRef.current?.click()
  }, [handleCloseContextMenu])

  const handleFileInputChange = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    const folderId = uploadFolderIdRef.current
    if (!files || files.length === 0 || !folderId) return

    // Collect conflicts to show after all uploads complete
    const conflicts: { file: File; existingFileId: string | null }[] = []

    // Sequential upload - continue processing remaining files on conflict
    for (let i = 0; i < files.length; i++) {
      const file = files[i]
      try {
        await uploadFileMutation.mutateAsync({ file, folderId })
      } catch (err) {
        const error = err as UploadConflictError
        if (error.status === 409) {
          conflicts.push({ file, existingFileId: error.existingFileId ?? null })
        } else {
          toast.error(`Failed to upload ${file.name}: ${error.message}`)
        }
      }
    }

    // Queue all conflicts for sequential resolution
    if (conflicts.length > 0) {
      setConflictQueue(conflicts)
      setConflictFolderId(folderId)
      setConflictDialogOpen(true)
      if (conflicts.length > 1) {
        toast.info(`${conflicts.length} files had conflicts. Resolve them one at a time.`)
      }
    }

    // Reset input
    e.target.value = ''
  }, [uploadFileMutation])

  const handleFileSelect = useCallback((file: FolderFileListItem) => {
    // Seed the detail cache so useFileDetail returns instantly (no redundant fetch)
    queryClient.setQueryData(queryKeys.folderFile(file.id), file)
    // Prefetch download URL so FileViewerPanel has it ready on mount
    queryClient.prefetchQuery({
      queryKey: queryKeys.folderFileDownloadUrl(file.id),
      queryFn: () => fetchFileDownloadUrl(file.id),
      staleTime: 4 * 60 * 1000,
    })
    selectFile(file.id)
  }, [selectFile, queryClient])

  const handleFileContextMenu = useCallback(
    (e: React.MouseEvent, file: FolderFileListItem, menuScope?: 'application' | 'project' | 'personal', menuScopeId?: string) => {
      e.preventDefault()
      e.stopPropagation()
      setContextMenuTarget({
        id: file.id,
        type: 'file',
        name: file.display_name,
        x: e.clientX,
        y: e.clientY,
        scope: menuScope ?? scope as 'application' | 'project' | 'personal',
        scopeId: menuScopeId ?? effectiveScopeId ?? '',
        folderId: file.folder_id ?? undefined,
      })
    },
    [scope, effectiveScopeId]
  )

  const handleCreateSubmit = useCallback(async (name: string, format?: 'document' | 'canvas') => {
    const resolvedScopeId = createScope === 'personal' ? (userId ?? '') : createScopeId

    // Close dialog immediately before mutation to prevent re-open on cache invalidation
    setCreateDialogOpen(false)

    if (createType === 'document') {
      const doc = await createDocument.mutateAsync({
        title: name,
        scope: createScope,
        scope_id: resolvedScopeId,
        folder_id: createParentId,
        content_json: format === 'canvas' ? JSON.stringify(createEmptyCanvas()) : undefined,
      })
      selectDocument(doc.id)
      if (createParentId) expandFolder(createParentId)
      toast.success(format === 'canvas' ? 'Canvas created' : 'Document created')
    } else {
      await createFolder.mutateAsync({
        name,
        scope: createScope,
        scope_id: resolvedScopeId,
        parent_id: createParentId,
      })
      if (createParentId) expandFolder(createParentId)
      toast.success('Folder created')
    }
  }, [createType, createScope, createScopeId, createParentId, userId, createDocument, createFolder, selectDocument, expandFolder])

  const handleRename = useCallback((id: string, type: 'folder' | 'document' | 'file') => {
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
      } else if (renamingItemType === 'file') {
        const fileItem = findFileInCache(renamingItemId)
        if (!fileItem) {
          toast.error('Could not find file data. Please try again.')
          setRenamingItemId(null)
          setRenamingItemScope(null)
          setRenamingItemScopeId(null)
          return
        }
        await renameFileMutation.mutateAsync({
          fileId: renamingItemId,
          displayName: newName,
          folderId: fileItem.folder_id ?? '',
          rowVersion: fileItem.row_version,
          scope: itemScope,
          scopeId: itemScopeId,
        })
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
  }, [renamingItemId, renamingItemType, renamingItemScope, renamingItemScopeId, renameFolder, renameDocument, renameFileMutation, findFileInCache, getDocRowVersion, scope, effectiveScopeId])

  const handleRenameCancel = useCallback(() => {
    setRenamingItemId(null)
    setRenamingItemScope(null)
    setRenamingItemScopeId(null)
  }, [])

  const handleDelete = useCallback((id: string, type: 'folder' | 'document' | 'file') => {
    const targetScope = contextMenuTarget?.scope ?? null
    const targetScopeId = contextMenuTarget?.scopeId ?? null
    const targetFolderId = contextMenuTarget?.folderId ?? null
    handleCloseContextMenu()

    if (type === 'file') {
      const fileItem = findFileInCache(id)
      const fileFolderId = targetFolderId ?? fileItem?.folder_id ?? ''
      // Clear content viewer if the deleted file is currently selected
      if (selectedFileId === id) {
        selectFile(null)
      }
      deleteFileMutation.mutate(
        {
          fileId: id,
          folderId: fileFolderId,
          scope: targetScope ?? scope,
          scopeId: targetScopeId ?? effectiveScopeId ?? '',
        },
        {
          onError: (err) => toast.error(err instanceof Error ? err.message : 'Failed to delete file'),
        }
      )
      return
    }

    const name = type === 'folder'
      ? findFolderById(folders, id)?.name || 'this folder'
      : findDocInCache(id)?.title || unfiledDocs.find((d) => d.id === id)?.title || 'this document'
    setDeleteTarget({ id, type, name, scope: targetScope, scopeId: targetScopeId })
    setDeleteDialogOpen(true)
  }, [folders, unfiledDocs, findDocInCache, findFileInCache, deleteFileMutation, contextMenuTarget, handleCloseContextMenu, selectedFileId, selectFile])

  const handleDeleteConfirm = useCallback(async () => {
    if (!deleteTarget) return
    const itemScope = deleteTarget.scope ?? scope
    const itemScopeId = deleteTarget.scopeId ?? effectiveScopeId ?? ''
    if (deleteTarget.type === 'folder') {
      // Capture selected doc's folder_id BEFORE mutation invalidates cache
      const selectedDocFolderId = selectedDocumentId ? findDocInCache(selectedDocumentId)?.folder_id : null
      await deleteFolder.mutateAsync({ folderId: deleteTarget.id, scope: itemScope, scopeId: itemScopeId })
      toast.success('Folder deleted')
      // Cascade: folder deletion removes all documents inside it.
      // Clear selection if the selected document was directly in the deleted folder,
      // or in any subfolder (descendant), or if the cache was already invalidated.
      if (selectedDocumentId) {
        const wasInDeletedFolder = selectedDocFolderId === deleteTarget.id
        const treeFolders = deleteTarget.scope === 'project' && deleteTarget.scopeId
          ? (queryClient.getQueryData<FolderTreeNode[]>(queryKeys.documentFolders('project', deleteTarget.scopeId)) ?? [])
          : folders
        const wasInSubfolder = selectedDocFolderId != null && isDescendantOf(treeFolders, deleteTarget.id, selectedDocFolderId)
        const cacheAlreadyCleared = !findDocInCache(selectedDocumentId)
        if (wasInDeletedFolder || wasInSubfolder || cacheAlreadyCleared) {
          selectDocument(null)
        }
      }
    } else {
      await deleteDocument.mutateAsync({ documentId: deleteTarget.id, scope: itemScope, scopeId: itemScopeId })
      toast.success('Document deleted')
      if (selectedDocumentId === deleteTarget.id) selectDocument(null)
    }
  }, [deleteTarget, deleteFolder, deleteDocument, selectedDocumentId, selectDocument, findDocInCache, queryClient, folders, scope, effectiveScopeId])

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
      const prefix = dndPrefix
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
          sortableId={canEdit ? `${prefix}-doc-${doc.id}` : undefined}
          lockInfo={activeLocks.get(doc.id)}
          onSelect={() => handleSelectDocument(doc.id)}
          onContextMenu={(e) => handleContextMenu(e, doc.id, 'document', doc.title)}
          onRenameSubmit={handleRenameSubmit}
          onRenameCancel={handleRenameCancel}
        />
      )
    },
    [dndPrefix, canEdit, selectedDocumentId, renamingItemId, activeItem, activeLocks, handleSelectDocument, handleContextMenu, handleRenameSubmit, handleRenameCancel]
  )

  // Stable primitive for context-menu folder highlight (avoids object ref in deps)
  const contextMenuFolderId = contextMenuTarget?.type === 'folder' ? contextMenuTarget.id : null

  const renderFolderNode = useCallback(
    (node: FolderTreeNode, depth: number): JSX.Element => {
      const isExpanded = expandedFolderIds.has(node.id)
      const isSelected = contextMenuFolderId === node.id
      const prefix = dndPrefix
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
            sortableId={canEdit ? `${prefix}-folder-${node.id}` : undefined}
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
                selectedFileId={selectedFileId}
                renamingItemId={renamingItemId}
                sortableIdPrefix={canEdit ? prefix : ''}
                activeItemId={activeItem?.type === 'document' ? activeItem.id : null}
                activeLocks={activeLocks}
                onSelectDocument={handleSelectDocument}
                onContextMenu={handleContextMenu}
                onRenameSubmit={handleRenameSubmit}
                onRenameCancel={handleRenameCancel}
                onSelectFile={handleFileSelect}
                onFileContextMenu={handleFileContextMenu}
              />
            </>
          )}
        </div>
      )
    },
    [dndPrefix, canEdit, scope, effectiveScopeId, expandedFolderIds, contextMenuFolderId, selectedDocumentId, selectedFileId, renamingItemId, activeItem, dropTargetFolderId, activeLocks, toggleFolder, handleSelectDocument, handleContextMenu, handleRenameSubmit, handleRenameCancel, handleFileSelect, handleFileContextMenu]
  )

  // ========================================================================
  // Render
  // ========================================================================

  if (isInitialLoad) {
    return <TreeSkeleton />
  }

  const hasNoData = folders.length === 0 && unfiledDocs.length === 0 && unfiledFiles.length === 0 && (isApplicationScope ? projectIdsWithContent.size === 0 : true)
  const hasNoResults = filteredFolders.length === 0 && filteredDocs.length === 0 && filteredUnfiledFiles.length === 0 && filteredProjects.length === 0

  // Empty state
  if (hasNoData) {
    return (
      <>
        <div className="flex flex-col items-center justify-center p-6 text-center">
          <p className="text-sm text-muted-foreground mb-3">No documents yet</p>
          {canEdit && (
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
          )}
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
        {/* Subtle background refresh indicator - thin indeterminate progress bar */}
        {isFoldersFetching && !isFoldersLoading && (
          <div className="h-0.5 w-full overflow-hidden bg-primary/10">
            <div
              className="h-full w-2/5 rounded-full bg-primary/40 animate-kt-progress"
            />
          </div>
        )}

        {/* Main folder tree */}
        <SortableContext items={sortableItems} strategy={noReorderStrategy}>
          {filteredFolders.map((node) => renderFolderNode(node, 0))}
          {filteredDocs.map((doc) => renderDocumentItem(doc, 0))}
          {filteredUnfiledFiles.map((file) => (
            <FolderTreeItem
              key={`file-${file.id}`}
              node={file}
              type="file"
              depth={0}
              isSelected={selectedFileId === file.id}
              isRenaming={renamingItemId === file.id}
              sortableId={canEdit ? `${dndPrefix}-file-${file.id}` : undefined}
              onSelect={() => handleFileSelect(file)}
              onContextMenu={(e) => handleFileContextMenu(e, file)}
              onRenameSubmit={handleRenameSubmit}
              onRenameCancel={handleRenameCancel}
            />
          ))}
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
                selectedFileId={selectedFileId}
                renamingItemId={renamingItemId}
                activeItem={activeItem}
                dropTargetFolderId={dropTargetFolderId}
                contextMenuFolderId={contextMenuFolderId}
                canEdit={projectPermissionsMap.get(project.id) ?? canEdit}
                revealProjectId={revealProjectId}
                revealFolderId={revealFolderId}
                expandFolders={expandFolders}
                clearReveal={clearReveal}
                onToggleFolder={toggleFolder}
                onSelectDocument={handleSelectDocument}
                onSelectFile={handleFileSelect}
                onFileContextMenu={handleFileContextMenu}
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
            ) : activeItem.type === 'file' ? (
              <FileIcon className="h-4 w-4 text-muted-foreground" />
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
          canEdit={
            contextMenuTarget.scope === 'project'
              ? (projectPermissionsMap.get(contextMenuTarget.scopeId) ?? canEdit)
              : canEdit
          }
          onClose={handleCloseContextMenu}
          onNewFolder={handleNewFolder}
          onNewDocument={handleNewDocument}
          onRename={(id) => handleRename(id, contextMenuTarget.type)}
          onDelete={handleDelete}
          onUploadFiles={handleUploadFiles}
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

      {/* Hidden file input for folder upload */}
      <input
        ref={uploadFileInputRef}
        type="file"
        multiple
        onChange={handleFileInputChange}
        className="hidden"
        aria-hidden="true"
      />

      {/* File conflict dialog */}
      <FileConflictDialog
        open={conflictDialogOpen}
        onOpenChange={(open) => {
          setConflictDialogOpen(open)
          if (!open) {
            setConflictQueue([])
            setConflictFolderId(null)
          }
        }}
        file={conflictFile}
        folderId={conflictFolderId}
        existingFileId={conflictExistingFileId}
        onResolved={() => {
          // Remove the resolved conflict from the queue.
          // When the queue becomes empty, the useEffect above will
          // close the dialog and clear state on the next render.
          setConflictQueue((prev) => prev.slice(1))
        }}
      />
    </DndContext>
  )
}

export default KnowledgeTree
