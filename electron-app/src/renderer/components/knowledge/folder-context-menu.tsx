/**
 * Folder Context Menu (stub)
 *
 * Placeholder for context menu component. Full implementation in Task 2.
 */

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

export function FolderContextMenu(_props: FolderContextMenuProps): JSX.Element {
  return <div />
}

export default FolderContextMenu
