/**
 * Shared drag-and-drop utility functions for knowledge base tree components.
 *
 * Pure functions with no React dependencies. Used by KnowledgeTree,
 * ApplicationTree, and FolderTree for sortable ID creation and parsing.
 */

/** Build a sortable ID string: `${prefix}-folder-${id}` or `${prefix}-doc-${id}`. */
export function makeSortableId(prefix: string, type: 'folder' | 'document', id: string): string {
  return `${prefix}-${type === 'folder' ? 'folder' : 'doc'}-${id}`
}

interface ParsedSortableId {
  prefix: string
  type: 'folder' | 'document'
  itemId: string
}

export interface ScopeInfo {
  scope: string
  scopeId: string
}

/**
 * Parse a DnD prefix to scope/scopeId.
 * 'app' → application, 'personal' → personal, 'project:{id}' → project with id.
 * Returns null for unrecognized prefixes.
 */
export function parsePrefixToScope(prefix: string): ScopeInfo | null {
  if (prefix === 'app') return { scope: 'application', scopeId: '' }
  if (prefix === 'personal') return { scope: 'personal', scopeId: '' }
  const colonIdx = prefix.indexOf(':')
  if (colonIdx !== -1) return { scope: prefix.slice(0, colonIdx), scopeId: prefix.slice(colonIdx + 1) }
  return null
}

/**
 * Parse a sortable ID string back into its parts.
 *
 * Tries each valid prefix to match `${prefix}-folder-{id}` or `${prefix}-doc-{id}`.
 * Also handles project IDs: `project-{projId}-folder-{id}` is parsed as
 * `{ prefix: 'project:{projId}', type: 'folder', itemId }`.
 */
export function parseSortableId(sortableId: string, validPrefixes: string[]): ParsedSortableId | null {
  for (const prefix of validPrefixes) {
    const folderPrefix = `${prefix}-folder-`
    if (sortableId.startsWith(folderPrefix)) {
      return { prefix, type: 'folder', itemId: sortableId.slice(folderPrefix.length) }
    }
    const docPrefix = `${prefix}-doc-`
    if (sortableId.startsWith(docPrefix)) {
      return { prefix, type: 'document', itemId: sortableId.slice(docPrefix.length) }
    }
  }

  // Project items: project-{projId}-folder-{id} or project-{projId}-doc-{id}
  // UUID-aware regex: project IDs contain hyphens (e.g. a1b2c3d4-e5f6-7890-abcd-ef1234567890)
  const projectMatch = sortableId.match(
    /^project-([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})-(folder|doc)-(.+)$/i
  )
  if (projectMatch) {
    const [, projectId, typeStr, itemId] = projectMatch
    return {
      prefix: `project:${projectId}`,
      type: typeStr === 'folder' ? 'folder' : 'document',
      itemId,
    }
  }

  return null
}
