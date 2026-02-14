import { useState, useEffect, useRef } from 'react'
import { X } from 'lucide-react'
import DOMPurify from 'dompurify'
import type { SearchResultHit, SearchResponse } from '@/hooks/use-document-search'

/** Sanitize Meilisearch _formatted HTML to only allow <mark> tags */
function sanitizeHighlightHtml(html: string): string {
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ['mark'],
    ALLOWED_ATTR: [],
  })
}

function SearchResultSnippet({ html }: { html: string }) {
  const sanitized = sanitizeHighlightHtml(html)
  return (
    <span dangerouslySetInnerHTML={{ __html: sanitized }} />
  )
}

function formatRelativeTime(isoOrTimestamp: string | number): string {
  const date = new Date(
    typeof isoOrTimestamp === 'number'
      ? isoOrTimestamp * 1000
      : /^\d+$/.test(isoOrTimestamp)
        ? Number(isoOrTimestamp) * 1000
        : isoOrTimestamp
  )
  if (isNaN(date.getTime())) return ''
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMin = Math.floor(Math.abs(diffMs) / 60000)
  if (diffMin < 1) return 'just now'
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${diffHr}h ago`
  const diffDay = Math.floor(diffHr / 24)
  if (diffDay < 30) return `${diffDay}d ago`
  return date.toLocaleDateString()
}

interface SearchResultsPanelProps {
  query: string
  results: SearchResponse | undefined
  isLoading: boolean
  isFetching: boolean
  error?: Error & { status?: number }
  containerRef?: React.RefObject<HTMLElement>
  onResultClick: (hit: SearchResultHit) => void
  onClose: () => void
  onSelectedIndexChange?: (index: number) => void
  onLoadMore?: () => void
  hasMore?: boolean
}

export function SearchResultsPanel({
  query,
  results,
  isLoading,
  isFetching,
  error,
  containerRef,
  onResultClick,
  onClose,
  onSelectedIndexChange,
  onLoadMore,
  hasMore,
}: SearchResultsPanelProps) {
  const [selectedIndex, setSelectedIndex] = useState(-1)
  const listRef = useRef<HTMLDivElement>(null)

  // Reset selection when results change
  useEffect(() => {
    setSelectedIndex(-1)
  }, [results])

  // Notify parent of selected index changes for aria-activedescendant
  useEffect(() => {
    onSelectedIndexChange?.(selectedIndex)
  }, [selectedIndex, onSelectedIndexChange])

  // Keyboard navigation scoped to the search container
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Only handle events when focus is within the search container
      const scope = containerRef?.current ?? listRef.current
      if (scope && !scope.contains(document.activeElement)) return

      if (!results?.hits.length && e.key !== 'Escape') return
      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault()
          setSelectedIndex((i) => Math.min(i + 1, (results?.hits.length ?? 1) - 1))
          break
        case 'ArrowUp':
          e.preventDefault()
          setSelectedIndex((i) => Math.max(i - 1, 0))
          break
        case 'Enter':
          if (selectedIndex >= 0 && results?.hits[selectedIndex]) {
            e.preventDefault()
            onResultClick(results.hits[selectedIndex])
          }
          break
        case 'Escape':
          e.preventDefault()
          onClose()
          break
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [results, selectedIndex, onResultClick, onClose, containerRef])

  // Scroll selected item into view
  useEffect(() => {
    if (selectedIndex >= 0 && listRef.current) {
      const items = listRef.current.querySelectorAll('[data-search-result]')
      items[selectedIndex]?.scrollIntoView({ block: 'nearest' })
    }
  }, [selectedIndex])

  if (!query || query.length < 2) return null

  function renderErrorMessage() {
    if (!error) return null
    let message = error.message
    if (error.status === 429) {
      message = 'Search rate limit reached. Please wait a moment.'
    } else if (error.status === 503) {
      message = 'Search temporarily unavailable.'
    }
    return (
      <div className="p-4 text-center text-sm text-destructive">
        {message}
      </div>
    )
  }

  return (
    <div
      ref={listRef}
      role="listbox"
      aria-label="Search results"
      id="search-results-listbox"
      className="absolute top-full left-0 right-0 z-50 mt-1
                 bg-popover border rounded-md shadow-lg max-h-[400px] overflow-y-auto"
    >
      {/* Header with result count */}
      <div className="flex items-center justify-between px-3 py-2 border-b">
        <div aria-live="polite" role="status" className="text-xs text-muted-foreground">
          {`${results?.hits.length ?? 0} results`}
          {isFetching && ' (updating...)'}
          {results?.fallback && ' (basic search)'}
        </div>
        <button
          onClick={onClose}
          aria-label="Close search results"
          className="text-muted-foreground hover:text-foreground"
        >
          <X className="h-3 w-3" />
        </button>
      </div>

      {/* Error state */}
      {renderErrorMessage()}

      {/* Loading state */}
      {isLoading && !results && !error && (
        <div className="p-4 text-center text-sm text-muted-foreground">
          Searching...
        </div>
      )}

      {/* Empty state */}
      {results && results.hits.length === 0 && (
        <div className="p-4 text-center text-sm text-muted-foreground">
          No results found for &quot;{query}&quot;
        </div>
      )}

      {/* Results */}
      {results?.hits.map((hit, index) => {
        const snippetHtml = hit.snippet || hit._formatted?.content_plain || ''
        const isFollowUp = hit.occurrenceIndex != null && hit.occurrenceIndex > 0
        const resultKey = `${hit.id}-${hit.occurrenceIndex ?? 0}`
        return (
          <button
            key={resultKey}
            data-search-result
            role="option"
            aria-selected={index === selectedIndex}
            id={`search-result-${resultKey}`}
            onClick={() => onResultClick(hit)}
            className={`w-full text-left px-3 py-2 hover:bg-accent
                       focus:bg-accent focus:outline-none border-b last:border-b-0
                       ${index === selectedIndex ? 'bg-accent' : ''}
                       ${isFollowUp ? 'pl-6' : ''}`}
          >
            {!isFollowUp && (
              <div className="font-medium text-sm truncate">
                <SearchResultSnippet html={hit._formatted?.title ?? hit.title} />
              </div>
            )}
            {snippetHtml && (
              <div className={`text-xs text-muted-foreground line-clamp-2 ${isFollowUp ? '' : 'mt-0.5'}`}>
                <SearchResultSnippet html={snippetHtml} />
              </div>
            )}
            {!isFollowUp && (
              <div className="text-xs text-muted-foreground/60 mt-0.5">
                Updated {formatRelativeTime(hit.updated_at)}
              </div>
            )}
          </button>
        )
      })}

      {/* Load more button */}
      {hasMore && onLoadMore && (
        <button
          onClick={onLoadMore}
          disabled={isFetching}
          className="w-full px-3 py-2 text-xs text-center text-muted-foreground
                     hover:text-foreground hover:bg-accent transition-colors border-t"
        >
          {isFetching ? 'Loading...' : 'Load more results'}
        </button>
      )}
    </div>
  )
}
