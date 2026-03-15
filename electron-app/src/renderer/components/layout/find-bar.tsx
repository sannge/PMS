/**
 * Find Bar Component
 *
 * Browser-style Ctrl+F search. Pure renderer — no IPC, no findInPage.
 * Uses CSS Highlight API for highlighting (no DOM mutation).
 * Search-as-you-type with debounce, Enter/Shift+Enter to cycle.
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { X, ChevronUp, ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'

const MAX_MATCHES = 500
const MIN_QUERY_LENGTH = 2

/** Walk the DOM and return Ranges for every case-insensitive match of `query`. */
function findTextRanges(root: HTMLElement, query: string, skipEl?: HTMLElement | null): Range[] {
  const ranges: Range[] = []
  if (!query || query.length < MIN_QUERY_LENGTH) return ranges
  const lower = query.toLowerCase()
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      if (skipEl?.contains(node)) return NodeFilter.FILTER_REJECT
      const el = node.parentElement
      if (!el || el.closest('script, style, [hidden]')) return NodeFilter.FILTER_REJECT
      if (!el.offsetParent && el.tagName !== 'BODY') return NodeFilter.FILTER_REJECT
      return NodeFilter.FILTER_ACCEPT
    },
  })
  let node: Text | null
  while ((node = walker.nextNode() as Text | null)) {
    const text = (node.textContent ?? '').toLowerCase()
    let start = 0
    while (true) {
      const idx = text.indexOf(lower, start)
      if (idx === -1) break
      const range = document.createRange()
      range.setStart(node, idx)
      range.setEnd(node, idx + query.length)
      ranges.push(range)
      if (ranges.length >= MAX_MATCHES) return ranges
      start = idx + 1
    }
  }
  return ranges
}

export function FindBar(): JSX.Element | null {
  const [visible, setVisible] = useState(false)
  const [query, setQuery] = useState('')
  const [currentIdx, setCurrentIdx] = useState(-1)
  const [total, setTotal] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const barRef = useRef<HTMLDivElement>(null)
  const rangesRef = useRef<Range[]>([])

  const clearHighlights = useCallback(() => {
    CSS.highlights.delete('find-matches')
    CSS.highlights.delete('find-active')
    rangesRef.current = []
    setTotal(0)
    setCurrentIdx(-1)
  }, [])

  const runSearch = useCallback((text: string) => {
    clearHighlights()
    if (!text || text.length < MIN_QUERY_LENGTH) return
    const ranges = findTextRanges(document.body, text, barRef.current)
    rangesRef.current = ranges
    setTotal(ranges.length)
    if (ranges.length === 0) return
    CSS.highlights.set('find-matches', new Highlight(...ranges))
    setCurrentIdx(0)
    CSS.highlights.set('find-active', new Highlight(ranges[0]))
    ranges[0].startContainer.parentElement?.scrollIntoView({ block: 'center' })
  }, [clearHighlights])

  const goToMatch = useCallback((idx: number) => {
    const ranges = rangesRef.current
    if (ranges.length === 0) return
    const wrapped = ((idx % ranges.length) + ranges.length) % ranges.length
    setCurrentIdx(wrapped)
    CSS.highlights.set('find-active', new Highlight(ranges[wrapped]))
    ranges[wrapped].startContainer.parentElement?.scrollIntoView({ block: 'center' })
  }, [])

  const closeFindBar = useCallback(() => {
    setVisible(false)
    setQuery('')
    clearHighlights()
  }, [clearHighlights])

  // Debounced search-as-you-type
  useEffect(() => {
    if (!visible) return
    const id = setTimeout(() => runSearch(query), 200)
    return () => clearTimeout(id)
  }, [query, visible, runSearch])

  useEffect(() => {
    if (!visible) clearHighlights()
  }, [visible, clearHighlights])

  // Global keyboard handler
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
        e.preventDefault()
        setVisible(true)
        setTimeout(() => inputRef.current?.select(), 0)
        return
      }
      if (!visible) return
      if (e.key === 'Escape') {
        e.preventDefault()
        closeFindBar()
        return
      }
      if (e.key === 'Enter') {
        e.preventDefault()
        goToMatch(currentIdx + (e.shiftKey ? -1 : 1))
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [visible, closeFindBar, goToMatch, currentIdx])

  if (!visible) return null

  const capped = total >= MAX_MATCHES

  return (
    <div
      ref={barRef}
      className={cn(
        'fixed top-10 right-16 z-[9999] flex items-center gap-1 app-no-drag',
        'rounded-lg border border-border bg-card px-3 py-1.5',
        'shadow-lg animate-in slide-in-from-top-2 duration-150'
      )}
    >
      <input
        ref={inputRef}
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Find in page..."
        className={cn(
          'w-52 rounded border border-input bg-background px-2 py-1 text-xs',
          'text-foreground placeholder:text-muted-foreground',
          'focus:outline-none focus:ring-1 focus:ring-ring'
        )}
        autoFocus
      />

      <span className="min-w-[3.5rem] text-center text-[11px] text-muted-foreground tabular-nums whitespace-nowrap">
        {query.length >= MIN_QUERY_LENGTH
          ? total > 0
            ? `${currentIdx + 1} / ${total}${capped ? '+' : ''}`
            : 'No matches'
          : ''}
      </span>

      <button
        onClick={() => goToMatch(currentIdx - 1)}
        disabled={!query || total === 0}
        className={cn(
          'flex h-6 w-6 items-center justify-center rounded',
          'text-muted-foreground hover:bg-muted hover:text-foreground',
          'disabled:opacity-30 disabled:pointer-events-none',
          'transition-colors'
        )}
        title="Previous (Shift+Enter)"
      >
        <ChevronUp className="h-3.5 w-3.5" />
      </button>

      <button
        onClick={() => goToMatch(currentIdx + 1)}
        disabled={!query || total === 0}
        className={cn(
          'flex h-6 w-6 items-center justify-center rounded',
          'text-muted-foreground hover:bg-muted hover:text-foreground',
          'disabled:opacity-30 disabled:pointer-events-none',
          'transition-colors'
        )}
        title="Next (Enter)"
      >
        <ChevronDown className="h-3.5 w-3.5" />
      </button>

      <button
        onClick={closeFindBar}
        className={cn(
          'flex h-6 w-6 items-center justify-center rounded',
          'text-muted-foreground hover:bg-muted hover:text-foreground',
          'transition-colors'
        )}
        title="Close (Escape)"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  )
}
