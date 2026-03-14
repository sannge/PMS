/**
 * Folder Context Menu
 *
 * Right-click context menu for folder and document tree items.
 * Uses a custom positioned div pattern (not Radix context menu).
 * Supports boundary checking to prevent viewport overflow.
 */

import { useMemo, useCallback, useEffect } from 'react'
import {
  FolderPlus,
  FilePlus,
  FileInput,
  Upload,
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
    type: 'folder' | 'document' | 'file'
    name: string
  }
  position: { x: number; y: number }
  /** Whether the user can edit items (when false, only shows view-related options) */
  canEdit?: boolean
  onClose: () => void
  onNewFolder: (parentId: string) => void
  onNewDocument: (folderId: string) => void
  onRename: (id: string) => void
  onDelete: (id: string, type: 'folder' | 'document' | 'file') => void
  /** When provided, shows "Import Document" menu item for folders */
  onImport?: (folderId: string) => void
  /** When provided, shows "Upload Files" menu item for folders */
  onUploadFiles?: (folderId: string) => void
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
  canEdit = true,
  onClose,
  onNewFolder,
  onNewDocument,
  onRename,
  onDelete,
  onImport,
  onUploadFiles,
}: FolderContextMenuProps): JSX.Element {
  // Build menu items based on target type and permissions
  const menuItems: MenuEntry[] = useMemo(() => {
    // When user can't edit, don't show any context menu items for CRUD
    if (!canEdit) return []

    if (target.type === 'folder') {
      const items: MenuEntry[] = [
        { label: 'New Folder', icon: FolderPlus, action: () => onNewFolder(target.id) },
        { label: 'New Document', icon: FilePlus, action: () => onNewDocument(target.id) },
      ]
      if (onImport) {
        items.push({ label: 'Import Document', icon: FileInput, action: () => onImport(target.id) })
      }
      if (onUploadFiles) {
        items.push({ label: 'Upload Files...', icon: Upload, action: () => onUploadFiles(target.id) })
      }
      items.push(
        { type: 'separator' as const },
        { label: 'Rename', icon: Pencil, action: () => onRename(target.id) },
        { type: 'separator' as const },
        { label: 'Delete', icon: Trash2, action: () => onDelete(target.id, 'folder'), destructive: true },
      )
      return items
    }

    if (target.type === 'file') {
      return [
        { label: 'Rename', icon: Pencil, action: () => onRename(target.id) },
        { type: 'separator' as const },
        { label: 'Delete', icon: Trash2, action: () => onDelete(target.id, 'file'), destructive: true },
      ]
    }

    return [
      { label: 'Rename', icon: Pencil, action: () => onRename(target.id) },
      { type: 'separator' as const },
      { label: 'Delete', icon: Trash2, action: () => onDelete(target.id, 'document'), destructive: true },
    ]
  }, [target, canEdit, onNewFolder, onNewDocument, onRename, onDelete, onImport, onUploadFiles])

  // Auto-close if menu has no items (read-only user)
  const isEmpty = menuItems.length === 0
  useEffect(() => {
    if (isEmpty) onClose()
  }, [isEmpty, onClose])

  if (isEmpty) return null as unknown as JSX.Element

  // Boundary checking -- adjust position so menu stays within viewport
  // MED-5: Calculate height from actual item count instead of static estimate
  const adjustedPosition = useMemo(() => {
    const menuWidth = 180
    const ITEM_HEIGHT = 32 // px per menu item (py-1.5 = 12px + text ~20px)
    const SEPARATOR_HEIGHT = 9 // py-1 = 8px + 1px border
    const PADDING = 8 // p-1 container padding
    const menuHeight = menuItems.reduce((h, entry) => {
      return h + (isSeparator(entry) ? SEPARATOR_HEIGHT : ITEM_HEIGHT)
    }, PADDING * 2)
    return {
      x: Math.min(position.x, window.innerWidth - menuWidth - 8),
      y: Math.min(position.y, window.innerHeight - menuHeight - 8),
    }
  }, [position, menuItems])

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
