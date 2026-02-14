/**
 * Tag Filter List
 *
 * Displays tags for the current scope with click-to-toggle filtering.
 * Active tags are visually highlighted and filter the document list.
 * Supports multiple active tags (AND-filtered).
 *
 * Uses useDocumentTags hook for data and KnowledgeBaseContext for filter state.
 */

import { cn } from '@/lib/utils'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { useKnowledgeBase } from '@/contexts/knowledge-base-context'
import { useDocumentTags } from '@/hooks/use-document-tags'

// ============================================================================
// Constants
// ============================================================================

const DEFAULT_TAG_COLOR = '#6b7280' // gray-500

// ============================================================================
// Component
// ============================================================================

export function TagFilterList(): JSX.Element {
  const { scope, scopeId, activeTagIds, toggleTag, clearTags } = useKnowledgeBase()
  const { data: tags, isLoading } = useDocumentTags(scope, scopeId)

  const hasActiveTags = activeTagIds.length > 0

  // Loading state
  if (isLoading) {
    return (
      <div className="space-y-1">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Tags
          </span>
        </div>
        <div className="space-y-1 py-1">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="flex items-center gap-2 px-2 py-1">
              <Skeleton className="h-2 w-2 rounded-full" />
              <Skeleton className="h-3 flex-1 max-w-[80px]" />
            </div>
          ))}
        </div>
      </div>
    )
  }

  // Empty state
  if (!tags || tags.length === 0) {
    return (
      <div className="space-y-1">
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Tags
        </span>
        <p className="text-xs text-muted-foreground py-1">No tags yet</p>
      </div>
    )
  }

  return (
    <div className="space-y-1">
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Tags
        </span>
        {hasActiveTags && (
          <button
            onClick={clearTags}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            Clear
          </button>
        )}
      </div>

      {/* Tag list */}
      <ScrollArea className="max-h-40">
        <div className="space-y-0.5 py-0.5">
          {tags.map((tag) => {
            const isActive = activeTagIds.includes(tag.id)
            return (
              <button
                key={tag.id}
                onClick={() => toggleTag(tag.id)}
                className={cn(
                  'flex w-full items-center gap-2 px-2 py-1 rounded-sm cursor-pointer transition-colors text-left',
                  'hover:bg-accent',
                  isActive && 'bg-accent text-accent-foreground font-medium'
                )}
              >
                <span
                  className="h-2 w-2 rounded-full shrink-0"
                  style={{ backgroundColor: tag.color ?? DEFAULT_TAG_COLOR }}
                />
                <span className="text-sm truncate">{tag.name}</span>
              </button>
            )
          })}
        </div>
      </ScrollArea>
    </div>
  )
}

export default TagFilterList
