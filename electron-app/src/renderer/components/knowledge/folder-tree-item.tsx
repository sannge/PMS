/**
 * Folder Tree Item
 *
 * Renders a single node in the folder tree -- either a folder or a document.
 * VSCode explorer-style: chevron arrows, indent guides, full-width selection.
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
  ChevronRight,
  Folder,
  FileText,
  FileSpreadsheet,
  FileImage,
  FileArchive,
  FileCode,
  File,
  Lock,
  Loader2,
  AlertCircle,
} from 'lucide-react'
import { DocumentStatusBadge } from './document-status-badge'
import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { cn } from '@/lib/utils'
import { useAuthUserId } from '@/contexts/auth-context'
import type { ActiveLockInfo } from '@/hooks/use-document-lock'
import type { FolderTreeNode } from '@/hooks/use-document-folders'
import type { DocumentListItem } from '@/hooks/use-documents'
import type { FolderFileListItem } from '@/hooks/use-folder-files'

// ============================================================================
// Lock Indicator Component (props-driven, no internal queries)
// ============================================================================

interface DocumentLockIndicatorProps {
  lockInfo: ActiveLockInfo | undefined
  hidden?: boolean
}

/**
 * Displays a lock icon when a document is being edited by another user.
 *
 * Lock info is passed as props from the parent tree component which
 * fetches all active locks in a single batch query (useActiveLocks).
 * This avoids N+1 per-document lock status queries.
 */
const DocumentLockIndicator = memo(function DocumentLockIndicator({
  lockInfo,
  hidden = false,
}: DocumentLockIndicatorProps): JSX.Element | null {
  const userId = useAuthUserId()

  // Hide if no lock, during rename, or if locked by the current user
  if (hidden || !lockInfo || lockInfo.userId === userId) return null

  return (
    <span
      className="shrink-0 flex items-center gap-1 text-red-500/80"
      title={lockInfo.userName ? `Editing: ${lockInfo.userName}` : 'Locked'}
    >
      <Lock className="h-3.5 w-3.5" />
      {lockInfo.userName && (
        <span className="text-[11px] truncate max-w-[80px]">{lockInfo.userName}</span>
      )}
    </span>
  )
})

// ============================================================================
// File Icon Helper
// ============================================================================

/**
 * Returns the appropriate icon component for a file based on its extension.
 */
function getFileIcon(extension: string): typeof File {
  const ext = extension.toLowerCase().replace('.', '')
  switch (ext) {
    case 'pdf':
    case 'docx':
    case 'doc':
    case 'txt':
    case 'rtf':
    case 'odt':
    case 'md':
      return FileText
    case 'xlsx':
    case 'xls':
    case 'csv':
    case 'ods':
      return FileSpreadsheet
    case 'png':
    case 'jpg':
    case 'jpeg':
    case 'gif':
    case 'svg':
    case 'webp':
    case 'bmp':
    case 'ico':
      return FileImage
    case 'zip':
    case 'rar':
    case '7z':
    case 'tar':
    case 'gz':
      return FileArchive
    case 'js':
    case 'ts':
    case 'jsx':
    case 'tsx':
    case 'py':
    case 'java':
    case 'cpp':
    case 'c':
    case 'rs':
    case 'go':
    case 'html':
    case 'css':
    case 'json':
    case 'xml':
    case 'yaml':
    case 'yml':
      return FileCode
    default:
      return File
  }
}

// ============================================================================
// Main Component
// ============================================================================

export interface FolderTreeItemProps {
  node: FolderTreeNode | DocumentListItem | FolderFileListItem
  type: 'folder' | 'document' | 'file'
  depth: number
  isExpanded?: boolean
  isSelected: boolean
  isRenaming: boolean
  /** Whether this item is currently being dragged */
  isDragging?: boolean
  /** Whether this folder is a drop target for nesting */
  isDropTarget?: boolean
  /** Sortable ID for @dnd-kit (e.g. "folder-{id}" or "doc-{id}") */
  sortableId?: string
  /** Lock info from useActiveLocks (passed down from tree component) */
  lockInfo?: ActiveLockInfo
  onToggleExpand?: () => void
  onSelect: () => void
  onContextMenu: (e: React.MouseEvent) => void
  onRenameSubmit: (newName: string) => void
  onRenameCancel: () => void
}

export const FolderTreeItem = memo(function FolderTreeItem({
  node,
  type,
  depth,
  isExpanded,
  isSelected,
  isRenaming,
  isDragging: isDraggingProp,
  isDropTarget,
  sortableId,
  lockInfo,
  onToggleExpand,
  onSelect,
  onContextMenu,
  onRenameSubmit,
  onRenameCancel,
}: FolderTreeItemProps): JSX.Element {
  const displayName = type === 'folder'
    ? (node as FolderTreeNode).name
    : type === 'file'
      ? (node as FolderFileListItem).display_name
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
    opacity: isDragging ? 0.4 : 1,
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

  const handleChevronClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    if (onToggleExpand) onToggleExpand()
  }, [onToggleExpand])

  const handleClick = useCallback(() => {
    if (type === 'folder') {
      if (onToggleExpand) onToggleExpand()
    } else {
      onSelect()
    }
  }, [type, onToggleExpand, onSelect])

  // File-specific data
  const fileNode = type === 'file' ? (node as FolderFileListItem) : null
  const FileIcon = fileNode ? getFileIcon(fileNode.file_extension) : null

  // Indent guide width per level (px)
  const INDENT_SIZE = 16
  const INDENT_OFFSET = 8

  return (
    <div
      ref={setNodeRef}
      {...attributes}
      {...listeners}
      className={cn(
        'group relative flex items-center h-[22px] pr-2 cursor-pointer select-none',
        'hover:bg-[hsl(var(--accent)/0.5)] transition-colors duration-75',
        isSelected && !isDropTarget && 'bg-accent text-accent-foreground',
        isDragging && 'opacity-40',
        isDropTarget && 'bg-primary/20 outline outline-1 outline-primary/60 -outline-offset-1'
      )}
      style={{
        ...style,
        paddingLeft: depth * INDENT_SIZE + INDENT_OFFSET,
      }}
      onClick={handleClick}
      onContextMenu={onContextMenu}
      role="treeitem"
      aria-expanded={type === 'folder' ? isExpanded : undefined}
      aria-selected={isSelected}
      {...(type === 'document' ? { 'data-tree-document-id': node.id } : {})}
    >
      {/* Indent guides */}
      {depth > 0 && Array.from({ length: depth }, (_, i) => (
        <span
          key={i}
          className="absolute top-0 bottom-0 w-px bg-border/40"
          style={{ left: i * INDENT_SIZE + INDENT_OFFSET + INDENT_SIZE / 2 }}
        />
      ))}

      {/* Chevron (folders only) */}
      {type === 'folder' ? (
        <span
          className="shrink-0 flex items-center justify-center w-4 h-4"
          onClick={handleChevronClick}
        >
          <ChevronRight
            className={cn(
              'h-3.5 w-3.5 text-muted-foreground/70 transition-transform duration-100',
              isExpanded && 'rotate-90'
            )}
          />
        </span>
      ) : (
        <span className="shrink-0 w-4" />
      )}

      {/* Icon */}
      {type === 'folder' ? (
        <Folder className="h-4 w-4 shrink-0 mr-1 text-muted-foreground" />
      ) : type === 'file' && FileIcon ? (
        <FileIcon className="h-4 w-4 shrink-0 mr-1 text-muted-foreground" />
      ) : (
        <FileText className="h-4 w-4 shrink-0 mr-1 text-muted-foreground" />
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
            'flex-1 min-w-0 text-[13px] leading-[22px] bg-background text-foreground border border-border px-1 rounded-sm',
            'outline-none'
          )}
          onClick={(e) => e.stopPropagation()}
        />
      ) : (
        <span className="flex-1 min-w-0 text-[13px] leading-[22px] truncate">{displayName}</span>
      )}

      {/* Extraction status indicator for files */}
      {type === 'file' && !isRenaming && fileNode && (
        <>
          {(fileNode.extraction_status === 'pending' || fileNode.extraction_status === 'processing') && (
            <span className="shrink-0" title="Processing...">
              <Loader2 className="h-3 w-3 text-primary animate-spin" />
            </span>
          )}
          {fileNode.extraction_status === 'failed' && (
            <span className="shrink-0" title="Extraction failed">
              <AlertCircle className="h-3 w-3 text-destructive" />
            </span>
          )}
        </>
      )}

      {/* Embedding status indicator for documents */}
      {type === 'document' && !isRenaming && ((node as DocumentListItem).embedding_status === 'stale' || (node as DocumentListItem).embedding_status === 'syncing') && (
        <DocumentStatusBadge
          documentId={node.id}
          embeddingStatus={(node as DocumentListItem).embedding_status}
          variant="dot"
        />
      )}

      {/* Lock indicator for documents being edited */}
      {type === 'document' && (
        <DocumentLockIndicator lockInfo={lockInfo} hidden={isRenaming} />
      )}
    </div>
  )
})

export default FolderTreeItem
