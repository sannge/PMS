/**
 * Folder Context Menu
 *
 * Right-click context menu for folder and document tree items.
 * Uses a custom positioned div pattern (not Radix context menu).
 * Supports boundary checking to prevent viewport overflow.
 */

import { useMemo, useCallback } from 'react'
import {
  FolderPlus,
  FilePlus,
  Pencil,
  Trash2,
  type LucideIcon,
} from 'lucide-react'
import { cn } from '@/lib/utils'

// ============================================================================
// Types
// ============================================================================

export interface FolderContextMenuProps {
  target: {
    id: string
    type: 'folder' | 'document'
    name: string
  }
  position: { x: number; y: number }
  onClose: () => void
  onNewFolder: (parentId: string) => void
  onNewDocument: (folderId: string) => void
  onRename: (id: string) => void
  onDelete: (id: string, type: 'folder' | 'document') => void
}

interface MenuItem {
  label: string
  icon: LucideIcon
  action: () => void
  destructive?: boolean
}

interface MenuSeparator {
  type: 'separator'
}

type MenuEntry = MenuItem | MenuSeparator

function isSeparator(entry: MenuEntry): entry is MenuSeparator {
  return 'type' in entry && entry.type === 'separator'
}

// ============================================================================
// Component
// ============================================================================

export function FolderContextMenu({
  target,
  position,
  onClose,
  onNewFolder,
  onNewDocument,
  onRename,
  onDelete,
}: FolderContextMenuProps): JSX.Element {
  // Build menu items based on target type
  const menuItems: MenuEntry[] = useMemo(() => {
    if (target.type === 'folder') {
      return [
        { label: 'New Folder', icon: FolderPlus, action: () => onNewFolder(target.id) },
        { label: 'New Document', icon: FilePlus, action: () => onNewDocument(target.id) },
        { type: 'separator' as const },
        { label: 'Rename', icon: Pencil, action: () => onRename(target.id) },
        { type: 'separator' as const },
        { label: 'Delete', icon: Trash2, action: () => onDelete(target.id, 'folder'), destructive: true },
      ]
    }

    return [
      { label: 'Rename', icon: Pencil, action: () => onRename(target.id) },
      { type: 'separator' as const },
      { label: 'Delete', icon: Trash2, action: () => onDelete(target.id, 'document'), destructive: true },
    ]
  }, [target, onNewFolder, onNewDocument, onRename, onDelete])

  // Boundary checking -- adjust position so menu stays within viewport
  const adjustedPosition = useMemo(() => {
    const menuWidth = 180
    const menuHeight = target.type === 'folder' ? 200 : 140
    return {
      x: Math.min(position.x, window.innerWidth - menuWidth - 8),
      y: Math.min(position.y, window.innerHeight - menuHeight - 8),
    }
  }, [position, target.type])

  const handleItemClick = useCallback(
    (action: () => void) => {
      action()
      onClose()
    },
    [onClose]
  )

  return (
    <>
      {/* Transparent backdrop to close menu on outside click */}
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
        className="fixed z-50 min-w-[180px] rounded-md border border-border bg-popover p-1 shadow-md"
        style={{
          left: adjustedPosition.x,
          top: adjustedPosition.y,
        }}
      >
        {menuItems.map((entry, index) => {
          if (isSeparator(entry)) {
            return (
              <div
                key={`sep-${index}`}
                className="my-1 h-px bg-border"
              />
            )
          }

          const Icon = entry.icon
          return (
            <div
              key={entry.label}
              className={cn(
                'flex items-center gap-2 px-2 py-1.5 text-sm rounded-sm cursor-pointer',
                'hover:bg-accent hover:text-accent-foreground',
                entry.destructive && 'text-destructive hover:text-destructive'
              )}
              onClick={() => handleItemClick(entry.action)}
            >
              <Icon className="h-4 w-4" />
              <span>{entry.label}</span>
            </div>
          )
        })}
      </div>
    </>
  )
}

export default FolderContextMenu
