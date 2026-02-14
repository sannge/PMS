/**
 * Document Search Hook
 *
 * TanStack Query hook for full-text document search via Meilisearch.
 * Debounces the search query by 300ms and uses keepPreviousData
 * for smooth UI transitions between result sets.
 *
 * Search results are NOT persisted to IndexedDB (the 'search' prefix
 * is in NON_PERSISTENT_KEYS in cache-config.ts).
 *
 * @see fastapi-backend/app/routers/document_search.py
 */

import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { useAuthStore } from '@/contexts/auth-context'
import { queryKeys } from '@/lib/query-client'
import { useState, useEffect, useCallback } from 'react'

const SEARCH_DEBOUNCE_MS = 300
const MIN_QUERY_LENGTH = 2
const PAGE_SIZE = 20
const MAX_LIMIT = 50 // Must match backend le=50 in document_search.py

export interface SearchResultHit {
  id: string
  title: string
  application_id: string | null
  project_id: string | null
  user_id: string | null
  folder_id: string | null
  updated_at: string | number
  created_by: string | null
  snippet?: string            // HTML snippet with <mark> around the match
  occurrenceIndex?: number    // 0-based index when a doc has multiple matches
  matchedTerms?: string[]     // Actual matched text (may differ from query due to fuzzy matching)
  _formatted?: {
    title?: string
    content_plain?: string
  }
}

export interface SearchResponse {
  hits: SearchResultHit[]
  estimatedTotalHits: number
  hitsBeforeExpansion?: number  // Document count before per-occurrence expansion
  processingTimeMs: number
  query: string
  fallback?: boolean // true when PostgreSQL FTS fallback was used
}

export function useDocumentSearch(query: string) {
  const token = useAuthStore((s) => s.token)
  const [limit, setLimit] = useState(PAGE_SIZE)

  // Debounce the search query
  const [debouncedQuery, setDebouncedQuery] = useState('')
  useEffect(() => {
    if (!query || query.length < MIN_QUERY_LENGTH) {
      setDebouncedQuery('')
      return
    }
    const timer = setTimeout(
      () => setDebouncedQuery(query),
      SEARCH_DEBOUNCE_MS,
    )
    return () => clearTimeout(timer)
  }, [query])

  // Reset limit when the query changes
  useEffect(() => {
    setLimit(PAGE_SIZE)
  }, [debouncedQuery])

  const result = useQuery({
    queryKey: [...queryKeys.documentSearch(debouncedQuery), limit],
    queryFn: async () => {
      const response = await window.electronAPI.get<SearchResponse>(
        `/api/documents/search?q=${encodeURIComponent(debouncedQuery)}&limit=${limit}`,
        { Authorization: `Bearer ${token}` },
      )
      if (response.status !== 200) {
        const detail = (response.data as unknown as { detail?: string })?.detail
        const err = new Error(detail || 'Search failed') as Error & { status?: number }
        err.status = response.status
        throw err
      }
      return response.data
    },
    enabled: !!token && debouncedQuery.length >= MIN_QUERY_LENGTH,
    placeholderData: keepPreviousData,
    staleTime: 10_000, // 10s -- search content changes frequently
    gcTime: 60_000, // 1 minute garbage collection
    refetchOnWindowFocus: false, // User controls search via input, not window focus
    refetchOnMount: false, // Cached results fine for brief tab switches
    retry: 1, // Only retry once (don't hammer a down service)
    retryDelay: 2000, // Wait 2s before retry
  })

  // Use pre-expansion document count for pagination comparison (hits may be expanded into multiple occurrences)
  const docCount = result.data?.hitsBeforeExpansion ?? result.data?.hits.length ?? 0
  const hasMore = (result.data?.estimatedTotalHits ?? 0) > docCount && limit < MAX_LIMIT

  const loadMore = useCallback(() => {
    setLimit((prev) => Math.min(prev + PAGE_SIZE, MAX_LIMIT))
  }, [])

  return {
    ...result,
    debouncedQuery,
    hasMore,
    loadMore,
  }
}
