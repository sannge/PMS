/**
 * Knowledge Base Search Bar
 *
 * Debounced search input for filtering documents in the sidebar.
 * Uses a local state for immediate input feedback, then updates
 * the KnowledgeBaseContext after 300ms of inactivity.
 *
 * Includes a global search toggle (Globe icon) that switches between
 * searching within the current tab scope and searching across all tabs.
 *
 * NOTE: For Phase 02.1, both local and global modes use the same client-side
 * filtering within the current tab. The global toggle tracks user intent
 * in context state for future backend integration.
 *
 * TODO (Phase 9): When isGlobalSearch is true, call backend full-text search
 * API instead of client-side filtering. For now, local filtering works for
 * both modes.
 */

import { useState, useEffect, useRef } from 'react'
import { Search, X, Globe } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import { useKnowledgeBase } from '@/contexts/knowledge-base-context'

const DEBOUNCE_MS = 300

export interface SearchBarProps {
  onGlobalToggle?: (isGlobal: boolean) => void
}

export function SearchBar({ onGlobalToggle }: SearchBarProps = {}): JSX.Element {
  const { searchQuery, setSearch, isGlobalSearch, setGlobalSearch } = useKnowledgeBase()
  const [localValue, setLocalValue] = useState(searchQuery)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Sync local value when context query changes externally
  useEffect(() => {
    setLocalValue(searchQuery)
  }, [searchQuery])

  // Debounce context update
  useEffect(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
    }

    timerRef.current = setTimeout(() => {
      setSearch(localValue)
      timerRef.current = null
    }, DEBOUNCE_MS)

    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current)
      }
    }
  }, [localValue, setSearch])

  const handleClear = () => {
    setLocalValue('')
    setSearch('')
  }

  const handleToggleGlobal = () => {
    const next = !isGlobalSearch
    setGlobalSearch(next)
    onGlobalToggle?.(next)
  }

  return (
    <div className="relative flex items-center gap-1">
      <div className="relative flex-1">
        <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={localValue}
          onChange={(e) => setLocalValue(e.target.value)}
          placeholder={isGlobalSearch ? 'Search all documents...' : 'Search in this tab...'}
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
      </div>

      {/* Global search toggle */}
      <button
        onClick={handleToggleGlobal}
        className={cn(
          'flex items-center justify-center shrink-0 h-8 w-8 rounded-md transition-colors',
          isGlobalSearch
            ? 'bg-primary/10 text-primary hover:bg-primary/20'
            : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
        )}
        title={isGlobalSearch ? 'Searching all tabs (click for current tab only)' : 'Search current tab (click for all tabs)'}
        aria-label={isGlobalSearch ? 'Disable global search' : 'Enable global search'}
        aria-pressed={isGlobalSearch}
      >
        <Globe className="h-3.5 w-3.5" />
      </button>
    </div>
  )
}

export default SearchBar
