/**
 * useFileSearchHighlight
 *
 * DOM-based text highlighting for file previews (PDF, Excel, CSV, DOCX).
 * Uses MutationObserver + retry polling to detect when content appears,
 * then scans text nodes, wraps matches in <mark> elements, and scrolls
 * the first match into view.
 *
 * Retry polling covers cases where MutationObserver misses content
 * (e.g., docx-preview renders asynchronously in a single batch).
 */

import { useEffect, useRef, type RefObject } from 'react'

const HIGHLIGHT_CLASS = 'file-search-highlight'
const ACTIVE_CLASS = 'file-search-highlight-active'

/** Retry intervals (ms) — covers async renders up to ~4s */
const RETRY_DELAYS = [300, 600, 1200, 2500, 4000]

/**
 * Walk all text nodes inside a container and wrap substrings matching any
 * of the given terms in <mark> elements. Returns the list of created marks.
 */
function highlightTextNodes(container: HTMLElement, terms: string[]): HTMLElement[] {
  // Filter out very short terms (< 2 chars) that cause excessive false positives
  const filtered = terms.filter((t) => t.length >= 2)
  if (!filtered.length) return []

  const sorted = [...filtered].sort((a, b) => b.length - a.length)
  const escaped = sorted.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  const regex = new RegExp(`(${escaped.join('|')})`, 'gi')

  const marks: HTMLElement[] = []
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const parent = node.parentElement
      if (!parent) return NodeFilter.FILTER_REJECT
      const tag = parent.tagName
      if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'MARK') return NodeFilter.FILTER_REJECT
      return NodeFilter.FILTER_ACCEPT
    },
  })

  const textNodes: Text[] = []
  let node: Text | null
  while ((node = walker.nextNode() as Text | null)) {
    if (node.textContent && regex.test(node.textContent)) {
      textNodes.push(node)
    }
    regex.lastIndex = 0
  }

  for (const textNode of textNodes) {
    const text = textNode.textContent ?? ''
    const fragment = document.createDocumentFragment()
    let lastIndex = 0
    regex.lastIndex = 0

    let match: RegExpExecArray | null
    while ((match = regex.exec(text)) !== null) {
      if (match.index > lastIndex) {
        fragment.appendChild(document.createTextNode(text.slice(lastIndex, match.index)))
      }
      const mark = document.createElement('mark')
      mark.className = HIGHLIGHT_CLASS
      mark.textContent = match[0]
      fragment.appendChild(mark)
      marks.push(mark)
      lastIndex = regex.lastIndex
    }

    if (lastIndex < text.length) {
      fragment.appendChild(document.createTextNode(text.slice(lastIndex)))
    }

    textNode.parentNode?.replaceChild(fragment, textNode)
  }

  return marks
}

function clearHighlights(container: HTMLElement): void {
  const marks = container.querySelectorAll(`mark.${HIGHLIGHT_CLASS}`)
  marks.forEach((mark) => {
    const parent = mark.parentNode
    if (!parent) return
    parent.replaceChild(document.createTextNode(mark.textContent ?? ''), mark)
    parent.normalize()
  })
}

/**
 * Apply highlights and scroll to first match.
 * Returns true if at least one match was highlighted.
 */
function applyHighlights(container: HTMLElement, terms: string[], scrollToFirst: boolean): boolean {
  clearHighlights(container)
  if (!terms.length) return false

  const marks = highlightTextNodes(container, terms)

  if (marks.length > 0 && scrollToFirst) {
    marks[0].classList.add(ACTIVE_CLASS)
    marks[0].scrollIntoView({ behavior: 'smooth', block: 'center' })
    setTimeout(() => marks[0]?.classList.remove(ACTIVE_CLASS), 2000)
  }

  return marks.length > 0
}

/**
 * Highlight search terms in a container's text content and scroll to the first match.
 *
 * Strategy:
 * 1. MutationObserver watches for new DOM content (handles PDF page-by-page rendering)
 * 2. Retry polling at increasing intervals (handles docx-preview and other async renders)
 * 3. Stops retrying once highlights are successfully applied
 */
export function useFileSearchHighlight(
  containerRef: RefObject<HTMLElement | null>,
  terms: string[],
): void {
  const hasHighlightedRef = useRef(false)
  const retriesRef = useRef<ReturnType<typeof setTimeout>[]>([])
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Reset when terms change
  useEffect(() => {
    hasHighlightedRef.current = false
  }, [terms])

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    // Cleanup helper
    const clearTimers = () => {
      retriesRef.current.forEach(clearTimeout)
      retriesRef.current = []
      if (debounceRef.current) {
        clearTimeout(debounceRef.current)
        debounceRef.current = null
      }
    }

    if (!terms.length) {
      clearHighlights(container)
      return
    }

    const tryApply = () => {
      if (!containerRef.current || hasHighlightedRef.current) return
      const found = applyHighlights(containerRef.current, terms, true)
      if (found) {
        hasHighlightedRef.current = true
        clearTimers()
      }
    }

    // Debounced apply triggered by MutationObserver
    const scheduleApply = () => {
      if (hasHighlightedRef.current) return
      if (debounceRef.current) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(tryApply, 150)
    }

    // Strategy 1: MutationObserver for incremental content (PDF pages, etc.)
    const observer = new MutationObserver((mutations) => {
      if (hasHighlightedRef.current) return
      const hasNewContent = mutations.some((m) =>
        m.type === 'childList' &&
        Array.from(m.addedNodes).some((n) => {
          if (n.nodeType === Node.ELEMENT_NODE) {
            return !(n as HTMLElement).classList?.contains(HIGHLIGHT_CLASS)
          }
          return n.nodeType === Node.TEXT_NODE
        }),
      )
      if (hasNewContent) scheduleApply()
    })

    observer.observe(container, { childList: true, subtree: true })

    // Strategy 2: Retry polling for async renders (docx-preview, etc.)
    // Try immediately, then at increasing intervals
    tryApply()
    for (const delay of RETRY_DELAYS) {
      retriesRef.current.push(setTimeout(tryApply, delay))
    }

    return () => {
      observer.disconnect()
      clearTimers()
      if (container) clearHighlights(container)
    }
  }, [containerRef, terms])
}
