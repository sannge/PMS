/**
 * Folder Documents
 *
 * Renders documents inside a specific folder. Lazy-loads via a per-folder
 * query so we only fetch data when the folder is expanded. Isolated as its
 * own component to avoid hook-count issues when folders expand/collapse.
 *
 * Shared by KnowledgeTree and its ProjectSection sub-component.
 */

import { useDocuments } from '@/hooks/use-documents'
import { type ActiveLockInfo } from '@/hooks/use-document-lock'
import { FolderTreeItem } from './folder-tree-item'
import { TreeItemSkeleton } from './tree-skeletons'

export interface FolderDocumentsProps {
  scope: string
  scopeId: string | null
  folderId: string
  depth: number
  selectedDocumentId: string | null
  renamingItemId: string | null
  /** Prefix for sortable IDs (e.g. "app", "personal", "project-{id}") */
  sortableIdPrefix: string
  /** Currently active drag item ID (for isDragging state) */
  activeItemId: string | null
  /** Active locks map for this scope (from useActiveLocks) */
  activeLocks: Map<string, ActiveLockInfo>
  onSelectDocument: (documentId: string) => void
  onContextMenu: (e: React.MouseEvent, id: string, type: 'folder' | 'document', name: string) => void
  onRenameSubmit: (newName: string) => void
  onRenameCancel: () => void
}

export function FolderDocuments({
  scope,
  scopeId,
  folderId,
  depth,
  selectedDocumentId,
  renamingItemId,
  sortableIdPrefix,
  activeItemId,
  activeLocks,
  onSelectDocument,
  onContextMenu,
  onRenameSubmit,
  onRenameCancel,
}: FolderDocumentsProps): JSX.Element | null {
  const { data, isLoading } = useDocuments(scope, scopeId, { folderId })
  const docs = data?.items ?? []

  if (isLoading) {
    return (
      <div className="space-y-0.5">
        <TreeItemSkeleton depth={depth} widthPercent={65} />
        <TreeItemSkeleton depth={depth} widthPercent={50} />
      </div>
    )
  }

  if (docs.length === 0) return null

  return (
    <>
      {docs.map((doc) => (
        <FolderTreeItem
          key={doc.id}
          node={doc}
          type="document"
          depth={depth}
          isSelected={selectedDocumentId === doc.id}
          isRenaming={renamingItemId === doc.id}
          isDragging={activeItemId === doc.id}
          sortableId={sortableIdPrefix ? `${sortableIdPrefix}-doc-${doc.id}` : undefined}
          lockInfo={activeLocks.get(doc.id)}
          onSelect={() => onSelectDocument(doc.id)}
          onContextMenu={(e) => onContextMenu(e, doc.id, 'document', doc.title)}
          onRenameSubmit={onRenameSubmit}
          onRenameCancel={onRenameCancel}
        />
      ))}
    </>
  )
}
