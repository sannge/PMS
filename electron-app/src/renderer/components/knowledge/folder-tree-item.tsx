/**
 * Folder Tree Item
 *
 * Renders a single node in the folder tree -- either a folder or a document.
 * OneNote page-list style: no chevron arrows, clean indentation only.
 * Handles expand/collapse, selection, right-click context menu, and inline rename.
 * Shows lock indicator when a document is being edited by another user.
 *
 * Lock status is queried per-document using useDocumentLockStatus hook
 * with real-time WebSocket updates for instant feedback.
 */

import { useRef, useEffect, useState, useCallback } from 'react'
import {
  Folder,
  FolderOpen,
  FileText,
  Lock,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useDocumentLockStatus } from '@/hooks/use-document-lock'
import type { FolderTreeNode } from '@/hooks/use-document-folders'
import type { DocumentListItem } from '@/hooks/use-documents'

export interface FolderTreeItemProps {
  node: FolderTreeNode | DocumentListItem
  type: 'folder' | 'document'
  depth: number
  isExpanded?: boolean
  isSelected: boolean
  isRenaming: boolean
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

  // Query lock status for documents (hook is disabled for folders via null id)
  const { isLocked, lockHolder } = useDocumentLockStatus(
    type === 'document' ? node.id : null
  )

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
      className={cn(
        'flex items-center gap-1.5 py-1 pr-2 cursor-pointer rounded-sm',
        'hover:bg-accent/50 transition-colors',
        isSelected && 'bg-accent text-accent-foreground'
      )}
      style={{ paddingLeft: depth * 20 + 12 }}
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
      {type === 'document' && isLocked && !isRenaming && (
        <span
          className="shrink-0 text-amber-500"
          title={lockHolder?.userName ? `Editing: ${lockHolder.userName}` : 'Locked'}
        >
          <Lock className="h-3.5 w-3.5" />
        </span>
      )}
    </div>
  )
}

export default FolderTreeItem
