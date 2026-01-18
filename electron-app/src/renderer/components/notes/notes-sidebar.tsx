/**
 * Notes Sidebar Component
 *
 * Collapsible hierarchical tree view of notes for navigation.
 *
 * Features:
 * - Collapsible sidebar with toggle
 * - Tree structure with expand/collapse
 * - Create new note (root or child)
 * - Context menu for note actions
 * - Search filtering
 * - Active note highlighting
 */

import { useState, useCallback, useMemo } from 'react'
import { cn } from '@/lib/utils'
import type { NoteTree, Note } from '@/stores/notes-store'
import {
  ChevronRight,
  ChevronDown,
  ChevronLeft,
  StickyNote,
  FolderOpen,
  Folder,
  Plus,
  MoreHorizontal,
  Pencil,
  Trash2,
  FilePlus,
  Search,
  X,
} from 'lucide-react'
import { SkeletonNotesSidebar, ProgressBar } from '@/components/ui/skeleton'

// ============================================================================
// Types
// ============================================================================

export interface NotesSidebarProps {
  /**
   * Hierarchical note tree data
   */
  noteTree: NoteTree[]
  /**
   * Currently selected/active note ID
   */
  activeNoteId?: string | null
  /**
   * Whether the sidebar is loading
   */
  isLoading?: boolean
  /**
   * Whether the sidebar is collapsed
   */
  isCollapsed?: boolean
  /**
   * Callback when collapsed state changes
   */
  onCollapsedChange?: (collapsed: boolean) => void
  /**
   * Callback when a note is selected
   */
  onSelectNote?: (note: NoteTree) => void
  /**
   * Callback when creating a new note
   */
  onCreateNote?: (parentId?: string | null) => void
  /**
   * Callback when editing a note
   */
  onEditNote?: (note: NoteTree) => void
  /**
   * Callback when deleting a note
   */
  onDeleteNote?: (note: NoteTree) => void
  /**
   * Optional className for the container
   */
  className?: string
}

interface NoteTreeItemProps {
  note: NoteTree
  level: number
  activeNoteId?: string | null
  expandedIds: Set<string>
  onToggleExpand: (noteId: string) => void
  onSelectNote?: (note: NoteTree) => void
  onCreateChild?: (parentId: string) => void
  onEditNote?: (note: NoteTree) => void
  onDeleteNote?: (note: NoteTree) => void
}

interface ContextMenuProps {
  note: NoteTree
  position: { x: number; y: number }
  onClose: () => void
  onCreateChild: () => void
  onEdit: () => void
  onDelete: () => void
}

// ============================================================================
// Context Menu Component
// ============================================================================

function ContextMenu({
  note,
  position,
  onClose,
  onCreateChild,
  onEdit,
  onDelete,
}: ContextMenuProps): JSX.Element {
  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-50"
        onClick={onClose}
        onContextMenu={(e) => {
          e.preventDefault()
          onClose()
        }}
      />
      {/* Menu */}
      <div
        className={cn(
          'fixed z-50 min-w-[160px] rounded-md border border-border bg-popover p-1 shadow-md',
          'animate-in fade-in-0 zoom-in-95'
        )}
        style={{ top: position.y, left: position.x }}
      >
        <button
          onClick={() => {
            onCreateChild()
            onClose()
          }}
          className={cn(
            'flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm text-foreground',
            'hover:bg-accent hover:text-accent-foreground',
            'focus:outline-none'
          )}
        >
          <FilePlus className="h-4 w-4" />
          Add Child Note
        </button>
        <button
          onClick={() => {
            onEdit()
            onClose()
          }}
          className={cn(
            'flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm text-foreground',
            'hover:bg-accent hover:text-accent-foreground',
            'focus:outline-none'
          )}
        >
          <Pencil className="h-4 w-4" />
          Rename
        </button>
        <div className="my-1 h-px bg-border" />
        <button
          onClick={() => {
            onDelete()
            onClose()
          }}
          className={cn(
            'flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm text-destructive',
            'hover:bg-destructive/10',
            'focus:outline-none'
          )}
        >
          <Trash2 className="h-4 w-4" />
          Delete
        </button>
      </div>
    </>
  )
}

// ============================================================================
// Note Tree Item Component
// ============================================================================

function NoteTreeItem({
  note,
  level,
  activeNoteId,
  expandedIds,
  onToggleExpand,
  onSelectNote,
  onCreateChild,
  onEditNote,
  onDeleteNote,
}: NoteTreeItemProps): JSX.Element {
  const [showContextMenu, setShowContextMenu] = useState(false)
  const [contextMenuPosition, setContextMenuPosition] = useState({ x: 0, y: 0 })
  const [showActions, setShowActions] = useState(false)

  const hasChildren = note.children && note.children.length > 0
  const isExpanded = expandedIds.has(note.id)
  const isActive = activeNoteId === note.id

  const handleContextMenu = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setContextMenuPosition({ x: e.clientX, y: e.clientY })
    setShowContextMenu(true)
  }, [])

  const handleClick = useCallback(() => {
    onSelectNote?.(note)
  }, [note, onSelectNote])

  const handleToggleExpand = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation()
      onToggleExpand(note.id)
    },
    [note.id, onToggleExpand]
  )

  const handleMoreClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    const rect = e.currentTarget.getBoundingClientRect()
    setContextMenuPosition({ x: rect.right, y: rect.top })
    setShowContextMenu(true)
  }, [])

  return (
    <>
      <div
        className={cn(
          'group flex items-center gap-1 rounded-md px-2 py-1.5 text-sm cursor-pointer',
          'hover:bg-accent/50',
          'focus:outline-none focus:ring-1 focus:ring-ring',
          isActive && 'bg-primary/10 text-primary font-medium'
        )}
        style={{ paddingLeft: `${8 + level * 16}px` }}
        onClick={handleClick}
        onContextMenu={handleContextMenu}
        onMouseEnter={() => setShowActions(true)}
        onMouseLeave={() => setShowActions(false)}
        tabIndex={0}
        role="treeitem"
        aria-selected={isActive}
        aria-expanded={hasChildren ? isExpanded : undefined}
      >
        {/* Expand/Collapse Toggle */}
        <button
          onClick={handleToggleExpand}
          className={cn(
            'flex h-5 w-5 flex-shrink-0 items-center justify-center rounded hover:bg-accent',
            !hasChildren && 'invisible'
          )}
          tabIndex={-1}
        >
          {hasChildren &&
            (isExpanded ? (
              <ChevronDown className="h-4 w-4 text-muted-foreground" />
            ) : (
              <ChevronRight className="h-4 w-4 text-muted-foreground" />
            ))}
        </button>

        {/* Icon */}
        <span className="flex-shrink-0">
          {hasChildren ? (
            isExpanded ? (
              <FolderOpen className="h-4 w-4 text-muted-foreground" />
            ) : (
              <Folder className="h-4 w-4 text-muted-foreground" />
            )
          ) : (
            <StickyNote className="h-4 w-4 text-muted-foreground" />
          )}
        </span>

        {/* Title */}
        <span className="flex-1 truncate">{note.title}</span>

        {/* Actions */}
        {showActions && (
          <button
            onClick={handleMoreClick}
            className={cn(
              'flex h-5 w-5 items-center justify-center rounded opacity-0 group-hover:opacity-100',
              'hover:bg-accent text-muted-foreground hover:text-foreground',
              'focus:outline-none focus:opacity-100'
            )}
            tabIndex={-1}
          >
            <MoreHorizontal className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Children */}
      {hasChildren && isExpanded && (
        <div role="group">
          {note.children.map((child) => (
            <NoteTreeItem
              key={child.id}
              note={child}
              level={level + 1}
              activeNoteId={activeNoteId}
              expandedIds={expandedIds}
              onToggleExpand={onToggleExpand}
              onSelectNote={onSelectNote}
              onCreateChild={onCreateChild}
              onEditNote={onEditNote}
              onDeleteNote={onDeleteNote}
            />
          ))}
        </div>
      )}

      {/* Context Menu */}
      {showContextMenu && (
        <ContextMenu
          note={note}
          position={contextMenuPosition}
          onClose={() => setShowContextMenu(false)}
          onCreateChild={() => onCreateChild?.(note.id)}
          onEdit={() => onEditNote?.(note)}
          onDelete={() => onDeleteNote?.(note)}
        />
      )}
    </>
  )
}

// ============================================================================
// Notes Sidebar Component
// ============================================================================

export function NotesSidebar({
  noteTree,
  activeNoteId,
  isLoading,
  isCollapsed = false,
  onCollapsedChange,
  onSelectNote,
  onCreateNote,
  onEditNote,
  onDeleteNote,
  className,
}: NotesSidebarProps): JSX.Element {
  // Track expanded nodes
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())

  // Search filter
  const [searchQuery, setSearchQuery] = useState('')

  // Toggle expand/collapse
  const handleToggleExpand = useCallback((noteId: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (next.has(noteId)) {
        next.delete(noteId)
      } else {
        next.add(noteId)
      }
      return next
    })
  }, [])

  // Handle create child note
  const handleCreateChild = useCallback(
    (parentId: string) => {
      onCreateNote?.(parentId)
    },
    [onCreateNote]
  )

  // Filter notes by search query
  const filterNotes = useCallback(
    (notes: NoteTree[], query: string): NoteTree[] => {
      if (!query.trim()) return notes

      const lowerQuery = query.toLowerCase()

      const filterRecursive = (items: NoteTree[]): NoteTree[] => {
        return items.reduce<NoteTree[]>((acc, note) => {
          const matchesTitle = note.title.toLowerCase().includes(lowerQuery)
          const filteredChildren = filterRecursive(note.children || [])

          if (matchesTitle || filteredChildren.length > 0) {
            acc.push({
              ...note,
              children: filteredChildren,
            })
          }

          return acc
        }, [])
      }

      return filterRecursive(notes)
    },
    []
  )

  // Filtered note tree
  const filteredNoteTree = useMemo(
    () => filterNotes(noteTree, searchQuery),
    [noteTree, searchQuery, filterNotes]
  )

  // Expand all when searching
  const displayExpandedIds = useMemo(() => {
    if (!searchQuery.trim()) return expandedIds

    // Expand all when searching
    const allIds = new Set<string>()
    const collectIds = (notes: NoteTree[]) => {
      notes.forEach((note) => {
        if (note.children && note.children.length > 0) {
          allIds.add(note.id)
          collectIds(note.children)
        }
      })
    }
    collectIds(filteredNoteTree)
    return allIds
  }, [expandedIds, searchQuery, filteredNoteTree])

  // Toggle sidebar collapse
  const handleToggleCollapse = useCallback(() => {
    onCollapsedChange?.(!isCollapsed)
  }, [isCollapsed, onCollapsedChange])

  // Collapsed view
  if (isCollapsed) {
    return (
      <div className={cn(
        'flex h-full w-10 flex-col bg-card border-r border-border',
        'transition-all duration-200',
        className
      )}>
        {/* Expand button */}
        <button
          onClick={handleToggleCollapse}
          className={cn(
            'flex h-8 w-full items-center justify-center',
            'text-muted-foreground hover:text-foreground hover:bg-muted',
            'border-b border-border transition-colors'
          )}
          title="Expand notes"
        >
          <ChevronRight className="h-4 w-4" />
        </button>

        {/* Create note button */}
        <button
          onClick={() => onCreateNote?.(null)}
          className={cn(
            'flex h-8 w-full items-center justify-center',
            'text-muted-foreground hover:text-foreground hover:bg-muted',
            'transition-colors'
          )}
          title="Create new note"
        >
          <Plus className="h-4 w-4" />
        </button>

        {/* Notes icon */}
        <div className="flex-1 flex items-start justify-center pt-4">
          <StickyNote className="h-4 w-4 text-muted-foreground/50" />
        </div>
      </div>
    )
  }

  return (
    <div className={cn(
      'flex h-full flex-col bg-card transition-all duration-200',
      className
    )}>
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-2 py-1.5">
        <h3 className="text-xs font-semibold text-foreground">Notes</h3>
        <div className="flex items-center gap-0.5">
          <button
            onClick={() => onCreateNote?.(null)}
            className={cn(
              'flex h-6 w-6 items-center justify-center rounded hover:bg-muted',
              'text-muted-foreground hover:text-foreground'
            )}
            title="Create New Note"
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={handleToggleCollapse}
            className={cn(
              'flex h-6 w-6 items-center justify-center rounded hover:bg-muted',
              'text-muted-foreground hover:text-foreground'
            )}
            title="Collapse sidebar"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Search */}
      <div className="border-b border-border px-2 py-1.5">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search..."
            className={cn(
              'w-full rounded-md border border-input bg-background py-1 pl-7 pr-6 text-xs',
              'placeholder:text-muted-foreground',
              'focus:outline-none focus:ring-1 focus:ring-ring'
            )}
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-1.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              <X className="h-3 w-3" />
            </button>
          )}
        </div>
      </div>

      {/* Subtle loading progress bar */}
      <ProgressBar isActive={isLoading && filteredNoteTree.length > 0} />

      {/* Note Tree */}
      <div className="flex-1 overflow-auto p-1.5" role="tree" aria-label="Notes">
        {isLoading && filteredNoteTree.length === 0 ? (
          <SkeletonNotesSidebar />
        ) : filteredNoteTree.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-6 text-center">
            <StickyNote className="h-6 w-6 text-muted-foreground opacity-50" />
            <p className="mt-2 text-xs text-muted-foreground">
              {searchQuery ? 'No matches' : 'No notes yet'}
            </p>
            {!searchQuery && (
              <button
                onClick={() => onCreateNote?.(null)}
                className={cn(
                  'mt-2 inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs',
                  'bg-primary text-primary-foreground',
                  'hover:bg-primary/90'
                )}
              >
                <Plus className="h-3 w-3" />
                Create Note
              </button>
            )}
          </div>
        ) : (
          filteredNoteTree.map((note) => (
            <NoteTreeItem
              key={note.id}
              note={note}
              level={0}
              activeNoteId={activeNoteId}
              expandedIds={displayExpandedIds}
              onToggleExpand={handleToggleExpand}
              onSelectNote={onSelectNote}
              onCreateChild={handleCreateChild}
              onEditNote={onEditNote}
              onDeleteNote={onDeleteNote}
            />
          ))
        )}
      </div>
    </div>
  )
}

export default NotesSidebar
