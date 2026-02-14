/**
 * Shared tree utility functions for knowledge base tree components.
 *
 * Pure functions with no React dependencies. Used by KnowledgeTree
 * for search filtering and tree traversal.
 */

import type { FolderTreeNode } from '@/hooks/use-document-folders'

/** Case-insensitive substring match. Returns true if searchQuery is empty. */
export function matchesSearch(text: string, searchQuery: string): boolean {
  if (!searchQuery) return true
  return text.toLowerCase().includes(searchQuery.toLowerCase())
}

/**
 * Recursively filter a folder tree, keeping nodes whose name matches
 * or that have descendants whose names match.
 */
export function filterFolderTree(nodes: FolderTreeNode[], searchQuery: string): FolderTreeNode[] {
  if (!searchQuery) return nodes

  return nodes.reduce<FolderTreeNode[]>((acc, node) => {
    const filteredChildren = filterFolderTree(node.children, searchQuery)
    const hasMatchingChildren = filteredChildren.length > 0
    const nodeMatches = matchesSearch(node.name, searchQuery)

    if (nodeMatches || hasMatchingChildren) {
      acc.push({ ...node, children: filteredChildren })
    }
    return acc
  }, [])
}

/** Recursively find a folder by ID in a tree of FolderTreeNodes. */
export function findFolderById(nodes: FolderTreeNode[], id: string): FolderTreeNode | null {
  for (const node of nodes) {
    if (node.id === id) return node
    const found = findFolderById(node.children, id)
    if (found) return found
  }
  return null
}

/** Check if `candidateChildId` is a descendant of `parentId` in the tree. */
export function isDescendantOf(nodes: FolderTreeNode[], parentId: string, candidateChildId: string): boolean {
  const parent = findFolderById(nodes, parentId)
  if (!parent) return false
  const check = (children: FolderTreeNode[]): boolean => {
    for (const child of children) {
      if (child.id === candidateChildId) return true
      if (check(child.children)) return true
    }
    return false
  }
  return check(parent.children)
}
