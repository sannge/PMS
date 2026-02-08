/**
 * Knowledge Base Search Bar
 *
 * Debounced search input for filtering documents in the sidebar.
 * Uses a local state for immediate input feedback, then updates
 * the KnowledgeBaseContext after 300ms of inactivity.
 */

import { useState, useEffect, useRef } from 'react'
import { Search, X } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import { useKnowledgeBase } from '@/contexts/knowledge-base-context'

const DEBOUNCE_MS = 300

export interface SearchBarProps {
  className?: string
}

export function SearchBar({ className }: SearchBarProps = {}): JSX.Element {
  const { searchQuery, setSearch } = useKnowledgeBase()
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

  return (
    <div className={cn('relative', className)}>
      <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
      <Input
        value={localValue}
        onChange={(e) => setLocalValue(e.target.value)}
        placeholder="Search documents..."
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
  )
}

export default SearchBar
