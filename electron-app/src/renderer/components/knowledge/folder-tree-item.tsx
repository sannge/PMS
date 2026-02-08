/**
 * Folder Tree Item
 *
 * Renders a single node in the folder tree -- either a folder or a document.
 * OneNote page-list style: no chevron arrows, clean indentation only.
 * Handles expand/collapse, selection, right-click context menu, and inline rename.
 * Shows lock indicator when a document is being edited by another user.
 *
 * Lock status is queried per-document using a separate DocumentLockIndicator
 * component to avoid hook count issues when tree items are added/removed.
 *
 * Drag-and-drop: Uses @dnd-kit useSortable hook for drag feedback.
 */

import { useRef, useEffect, useState, useCallback, memo } from 'react'
import {
  Folder,
  FolderOpen,
  FileText,
  Lock,
} from 'lucide-react'
import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/contexts/auth-context'
import { useDocumentLockStatus } from '@/hooks/use-document-lock'
import type { FolderTreeNode } from '@/hooks/use-document-folders'
import type { DocumentListItem } from '@/hooks/use-documents'

// ============================================================================
// Lock Indicator Component (isolated hooks to avoid hook count issues)
// ============================================================================

interface DocumentLockIndicatorProps {
  documentId: string
  hidden?: boolean
}

/**
 * Separate component for document lock indicator to isolate the hook.
 * This prevents "Rendered fewer hooks than expected" errors when
 * tree items are dynamically added/removed during folder expansion.
 *
 * Uses React.memo to prevent unnecessary re-renders when parent re-renders
 * but documentId hasn't changed.
 */
const DocumentLockIndicator = memo(function DocumentLockIndicator({
  documentId,
  hidden = false,
}: DocumentLockIndicatorProps): JSX.Element | null {
  const userId = useAuthStore((s) => s.user?.id)
  const { isLocked, lockHolder } = useDocumentLockStatus(documentId)

  // Hide if not locked, during rename, or if locked by the current user
  if (hidden || !isLocked || lockHolder?.userId === userId) return null

  return (
    <span
      className="shrink-0 flex items-center gap-1 text-red-500/80"
      title={lockHolder?.userName ? `Editing: ${lockHolder.userName}` : 'Locked'}
    >
      <Lock className="h-3.5 w-3.5" />
      {lockHolder?.userName && (
        <span className="text-[11px] truncate max-w-[80px]">{lockHolder.userName}</span>
      )}
    </span>
  )
})

// ============================================================================
// Main Component
// ============================================================================

export interface FolderTreeItemProps {
  node: FolderTreeNode | DocumentListItem
  type: 'folder' | 'document'
  depth: number
  isExpanded?: boolean
  isSelected: boolean
  isRenaming: boolean
  /** Whether this item is currently being dragged */
  isDragging?: boolean
  /** Sortable ID for @dnd-kit (e.g. "folder-{id}" or "doc-{id}") */
  sortableId?: string
  /** @deprecated Lock status is now queried internally for documents */
  isLocked?: boolean
  /** @deprecated Lock status is now queried internally for documents */
  lockHolderName?: string
  onToggleExpand?: () => void
  onSelect: () => void
  onContextMenu: (e: React.MouseEvent) => void
  onRenameSubmit: (newName: string) => void
  onRenameCancel: () => void
}

export function FolderTreeItem({
  node,
  type,
  depth,
  isExpanded,
  isSelected,
  isRenaming,
  isDragging: isDraggingProp,
  sortableId,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  isLocked: _isLockedProp,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  lockHolderName: _lockHolderNameProp,
  onToggleExpand,
  onSelect,
  onContextMenu,
  onRenameSubmit,
  onRenameCancel,
}: FolderTreeItemProps): JSX.Element {
  const displayName = type === 'folder'
    ? (node as FolderTreeNode).name
    : (node as DocumentListItem).title

  // Sortable hook for drag-and-drop
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging: isDraggingSortable,
  } = useSortable({
    id: sortableId || node.id,
    disabled: !sortableId || isRenaming,
  })

  const isDragging = isDraggingProp || isDraggingSortable

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  }

  const [renameValue, setRenameValue] = useState(displayName)
  const inputRef = useRef<HTMLInputElement>(null)

  // Auto-focus and select all on rename mode
  useEffect(() => {
    if (isRenaming && inputRef.current) {
      setRenameValue(displayName)
      inputRef.current.focus()
      inputRef.current.select()
    }
  }, [isRenaming, displayName])

  const handleRenameKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter') {
        e.preventDefault()
        const trimmed = renameValue.trim()
        if (trimmed && trimmed !== displayName) {
          onRenameSubmit(trimmed)
        } else {
          onRenameCancel()
        }
      } else if (e.key === 'Escape') {
        e.preventDefault()
        onRenameCancel()
      }
    },
    [renameValue, displayName, onRenameSubmit, onRenameCancel]
  )

  const handleRenameBlur = useCallback(() => {
    const trimmed = renameValue.trim()
    if (trimmed && trimmed !== displayName) {
      onRenameSubmit(trimmed)
    } else {
      onRenameCancel()
    }
  }, [renameValue, displayName, onRenameSubmit, onRenameCancel])

  const handleClick = useCallback(() => {
    if (type === 'folder' && onToggleExpand) {
      onToggleExpand()
    }
    onSelect()
  }, [type, onToggleExpand, onSelect])

  return (
    <div
      ref={setNodeRef}
      {...attributes}
      {...listeners}
      className={cn(
        'flex items-center gap-1.5 py-1 pr-2 cursor-pointer rounded-sm',
        'hover:bg-accent/50 transition-colors',
        isSelected && 'bg-accent text-accent-foreground',
        isDragging && 'cursor-grabbing bg-accent/30',
        sortableId && !isDragging && 'cursor-grab'
      )}
      style={{
        ...style,
        paddingLeft: depth * 20 + 12,
      }}
      onClick={handleClick}
      onContextMenu={onContextMenu}
      role="treeitem"
      aria-expanded={type === 'folder' ? isExpanded : undefined}
      aria-selected={isSelected}
    >
      {/* Icon */}
      {type === 'folder' ? (
        isExpanded ? (
          <FolderOpen className="h-4 w-4 shrink-0 text-muted-foreground" />
        ) : (
          <Folder className="h-4 w-4 shrink-0 text-muted-foreground" />
        )
      ) : (
        <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
      )}

      {/* Name or rename input */}
      {isRenaming ? (
        <input
          ref={inputRef}
          type="text"
          value={renameValue}
          onChange={(e) => setRenameValue(e.target.value)}
          onKeyDown={handleRenameKeyDown}
          onBlur={handleRenameBlur}
          className={cn(
            'flex-1 min-w-0 text-sm bg-background border border-border rounded px-1 py-0',
            'outline-none focus:ring-1 focus:ring-ring'
          )}
          onClick={(e) => e.stopPropagation()}
        />
      ) : (
        <span className="flex-1 min-w-0 text-sm truncate">{displayName}</span>
      )}

      {/* Lock indicator for documents being edited */}
      {type === 'document' && (
        <DocumentLockIndicator documentId={node.id} hidden={isRenaming} />
      )}
    </div>
  )
}

export default FolderTreeItem
