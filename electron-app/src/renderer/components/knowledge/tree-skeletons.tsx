/**
 * Tree Skeletons
 *
 * Shared loading skeleton components for knowledge tree views.
 * Used by KnowledgeTree, FolderTree, ApplicationTree, and FolderDocuments.
 */

/**
 * Single tree item skeleton - matches FolderTreeItem layout (icon + text)
 */
export function TreeItemSkeleton({ depth = 0, widthPercent = 60 }: { depth?: number; widthPercent?: number }): JSX.Element {
  return (
    <div
      className="flex items-center gap-1.5 py-1 pr-2"
      style={{ paddingLeft: depth * 20 + 12 }}
    >
      <div className="h-4 w-4 rounded bg-muted animate-pulse shrink-0" />
      <div
        className="h-4 rounded bg-muted animate-pulse"
        style={{ width: `${widthPercent}%` }}
      />
    </div>
  )
}

/**
 * Full tree loading skeleton - 6 rows with mixed depths
 */
export function TreeSkeleton(): JSX.Element {
  return (
    <div className="py-1 space-y-0.5">
      <TreeItemSkeleton depth={0} widthPercent={55} />
      <TreeItemSkeleton depth={1} widthPercent={70} />
      <TreeItemSkeleton depth={1} widthPercent={50} />
      <TreeItemSkeleton depth={0} widthPercent={45} />
      <TreeItemSkeleton depth={1} widthPercent={65} />
      <TreeItemSkeleton depth={2} widthPercent={60} />
    </div>
  )
}

/**
 * Project section content skeleton - 3 document rows at depth 1
 */
export function ProjectContentSkeleton(): JSX.Element {
  return (
    <div className="space-y-0.5 py-1">
      <TreeItemSkeleton depth={1} widthPercent={65} />
      <TreeItemSkeleton depth={1} widthPercent={80} />
      <TreeItemSkeleton depth={1} widthPercent={50} />
    </div>
  )
}
