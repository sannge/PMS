/**
 * Knowledge Base Search Bar
 *
 * Debounced search input for filtering documents in the sidebar (tree filter)
 * AND full-text search via Meilisearch (useDocumentSearch hook).
 *
 * When the user types >= 2 characters, the SearchResultsPanel dropdown
 * appears with full-text search results. Clicking a result navigates to
 * that document and sets search highlight terms for in-editor highlighting.
 *
 * The existing tree-filter behavior (via KnowledgeBaseContext.setSearch)
 * continues to work alongside full-text search.
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { Search, X } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import { useKnowledgeBase } from '@/contexts/knowledge-base-context'
import { useDocumentSearch, type SearchResultHit } from '@/hooks/use-document-search'
import { SearchResultsPanel } from './search-results-panel'

export interface SearchBarProps {
  className?: string
}

/**
 * Determine the target tab string from a search result hit's scope fields.
 * - user_id set => 'personal'
 * - application_id set => 'app:{application_id}'
 * - project_id set => we need the application_id too (should be on the hit)
 */
function getTargetTab(hit: SearchResultHit): string {
  if (hit.user_id) return 'personal'
  if (hit.application_id) return `app:${hit.application_id}`
  if (hit.project_id) {
    console.warn('[SearchBar] Project-scoped document missing application_id:', hit.id)
  }
  return 'personal'
}

/**
 * Extract plain search terms from the query string for editor highlighting.
 * Splits on whitespace and filters out short tokens.
 */
function extractSearchTerms(query: string): string[] {
  return query
    .trim()
    .split(/\s+/)
    .filter((term) => term.length >= 2)
}

export function SearchBar({ className }: SearchBarProps = {}): JSX.Element {
  const { searchQuery, setSearch, navigateToDocument } = useKnowledgeBase()
  const [localValue, setLocalValue] = useState(searchQuery)
  const [showResults, setShowResults] = useState(false)
  const [selectedResultIndex, setSelectedResultIndex] = useState(-1)
  const containerRef = useRef<HTMLDivElement>(null)

  // Full-text search hook
  const { data: searchResults, isLoading, isFetching, error: searchError, debouncedQuery, hasMore, loadMore } = useDocumentSearch(localValue)

  // Show results panel when we have a debounced query
  useEffect(() => {
    if (debouncedQuery.length >= 2) {
      setShowResults(true)
    } else {
      setShowResults(false)
    }
  }, [debouncedQuery])

  // Sync local value when context query changes externally
  useEffect(() => {
    setLocalValue(searchQuery)
  }, [searchQuery])

  // Full-text search handles document finding -- no need to filter the tree.
  // Clear the tree filter whenever the search input changes.
  useEffect(() => {
    if (searchQuery) {
      setSearch('')
    }
  }, [localValue]) // eslint-disable-line react-hooks/exhaustive-deps

  // Close results panel when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setShowResults(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleClear = useCallback(() => {
    setLocalValue('')
    setSearch('')
    setShowResults(false)
  }, [setSearch])

  const handleResultClick = useCallback((hit: SearchResultHit) => {
    const targetTab = getTargetTab(hit)
    // Prefer actual matched terms from backend (handles fuzzy/typo matches correctly)
    const terms = hit.matchedTerms?.length ? hit.matchedTerms : extractSearchTerms(debouncedQuery)
    navigateToDocument(targetTab, hit.id, terms, hit.folder_id ?? undefined, hit.occurrenceIndex ?? 0)
    setShowResults(false)
  }, [debouncedQuery, navigateToDocument])

  const handleCloseResults = useCallback(() => {
    setShowResults(false)
  }, [])

  return (
    <div ref={containerRef} role="search" className={cn('relative', className)}>
      <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
      <Input
        value={localValue}
        onChange={(e) => setLocalValue(e.target.value)}
        onFocus={() => {
          if (debouncedQuery.length >= 2) {
            setShowResults(true)
          }
        }}
        placeholder="Search documents..."
        role="combobox"
        aria-expanded={showResults}
        aria-controls="search-results-listbox"
        aria-autocomplete="list"
        aria-activedescendant={selectedResultIndex >= 0 && searchResults?.hits[selectedResultIndex] ? `search-result-${searchResults.hits[selectedResultIndex].id}-${searchResults.hits[selectedResultIndex].occurrenceIndex ?? 0}` : undefined}
        className={cn(
          'h-8 pl-7 text-xs',
          'bg-muted/50 border-transparent',
          'focus-visible:bg-background focus-visible:border-input',
          localValue ? 'pr-7' : 'pr-2'
        )}
      />
      {localValue && (
        <button
          onClick={handleClear}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
          aria-label="Clear search"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
      {showResults && (
        <SearchResultsPanel
          query={debouncedQuery}
          results={searchResults}
          isLoading={isLoading}
          isFetching={isFetching}
          error={searchError as (Error & { status?: number }) | undefined}
          containerRef={containerRef}
          onResultClick={handleResultClick}
          onClose={handleCloseResults}
          onSelectedIndexChange={setSelectedResultIndex}
          onLoadMore={loadMore}
          hasMore={hasMore}
        />
      )}
    </div>
  )
}

export default SearchBar
