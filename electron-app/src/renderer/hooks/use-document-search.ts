/**
 * Document Search Hook
 *
 * TanStack Query hook for full-text document search via Meilisearch.
 * Debounces the search query by 300ms and uses keepPreviousData
 * for smooth UI transitions between result sets.
 *
 * Uses useInfiniteQuery for efficient offset-based pagination
 * (avoids re-downloading already-fetched results on "load more").
 * Search results are NOT persisted to IndexedDB (the 'search' prefix
 * is in NON_PERSISTENT_KEYS in cache-config.ts).
 *
 * @see fastapi-backend/app/routers/document_search.py
 */

import { useInfiniteQuery, keepPreviousData } from '@tanstack/react-query'
import { useAuthStore } from '@/contexts/auth-context'
import { queryKeys } from '@/lib/query-client'
import { useState, useEffect, useMemo, useCallback } from 'react'

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

export interface DocumentSearchOptions {
  /** Narrow results to a specific application */
  applicationId?: string
  /** Narrow results to a specific project */
  projectId?: string
}

export function useDocumentSearch(query: string, options?: DocumentSearchOptions) {
  const token = useAuthStore((s) => s.token)
  const applicationId = options?.applicationId
  const projectId = options?.projectId

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

  const result = useInfiniteQuery({
    queryKey: queryKeys.documentSearch(debouncedQuery, applicationId, projectId),
    queryFn: async ({ pageParam }) => {
      const params = new URLSearchParams({
        q: debouncedQuery,
        limit: String(PAGE_SIZE),
        offset: String(pageParam),
      })
      if (applicationId) params.set('application_id', applicationId)
      if (projectId) params.set('project_id', projectId)

      const response = await window.electronAPI.get<SearchResponse>(
        `/api/documents/search?${params.toString()}`,
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
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      const totalDocsFetched = allPages.reduce(
        (sum, p) => sum + (p.hitsBeforeExpansion ?? p.hits.length), 0,
      )
      if (totalDocsFetched >= (lastPage.estimatedTotalHits ?? 0) || totalDocsFetched >= MAX_LIMIT) {
        return undefined
      }
      return totalDocsFetched
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

  // Flatten pages into a single SearchResponse for consumer compatibility
  const data = useMemo<SearchResponse | undefined>(() => {
    if (!result.data) return undefined
    const pages = result.data.pages
    const lastPage = pages[pages.length - 1]
    return {
      hits: pages.flatMap(p => p.hits),
      estimatedTotalHits: lastPage?.estimatedTotalHits ?? 0,
      hitsBeforeExpansion: pages.reduce((sum, p) => sum + (p.hitsBeforeExpansion ?? p.hits.length), 0),
      processingTimeMs: lastPage?.processingTimeMs ?? 0,
      query: lastPage?.query ?? debouncedQuery,
      fallback: pages.some(p => p.fallback),
    }
  }, [result.data, debouncedQuery])

  const loadMore = useCallback(() => {
    if (result.hasNextPage && !result.isFetchingNextPage) {
      result.fetchNextPage()
    }
  }, [result.fetchNextPage, result.hasNextPage, result.isFetchingNextPage])

  return {
    data,
    isLoading: result.isLoading,
    isFetching: result.isFetching,
    isFetchingNextPage: result.isFetchingNextPage,
    error: result.error,
    debouncedQuery,
    hasMore: result.hasNextPage ?? false,
    loadMore,
  }
}
