/**
 * TanStack Query Hooks for Chat Sessions
 *
 * Provides React Query hooks for chat session CRUD and message persistence.
 * Uses in-memory cache only (no IndexedDB persistence).
 */

import {
  useQuery,
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query'
import { useAuthToken } from '@/contexts/auth-context'
import { authGet, authPost, authPatch, authDelete } from '@/lib/api-client'
import { queryKeys } from '@/lib/query-client'
import type { ChatSessionSummary } from '@/components/ai/types'

// ============================================================================
// Types
// ============================================================================

// Raw API response uses snake_case
interface RawSessionSummary {
  id: string
  title: string
  created_at: string
  updated_at: string
  message_count: number
  last_message_preview: string
  application_id: string | null
  thread_id: string | null
  total_input_tokens: number
  total_output_tokens: number
  context_summary: string | null
  summary_up_to_msg_seq: number | null
}

interface RawSessionListResponse {
  sessions: RawSessionSummary[]
  total: number
}

interface SessionListResponse {
  sessions: ChatSessionSummary[]
  total: number
}

function mapSession(raw: RawSessionSummary): ChatSessionSummary {
  return {
    id: raw.id,
    title: raw.title,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
    messageCount: raw.message_count,
    lastMessagePreview: raw.last_message_preview,
    applicationId: raw.application_id,
    threadId: raw.thread_id,
    totalInputTokens: raw.total_input_tokens,
    totalOutputTokens: raw.total_output_tokens,
    contextSummary: raw.context_summary ?? null,
    summarizedAtSequence: raw.summary_up_to_msg_seq ?? null,
  }
}

interface ChatMessageOut {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources: unknown | null
  checkpoint_id: string | null
  is_error: boolean
  created_at: string
  sequence: number
}

interface ChatMessagePage {
  messages: ChatMessageOut[]
  has_more: boolean
}

// ============================================================================
// Session Queries
// ============================================================================

/**
 * Fetch all chat sessions for the current user.
 */
export function useChatSessions() {
  const token = useAuthToken()

  return useQuery({
    queryKey: queryKeys.chatSessions,
    queryFn: async (): Promise<SessionListResponse> => {
      const res = await authGet<RawSessionListResponse>('/api/ai/sessions/?limit=100')
      if (res.status >= 400) throw new Error(`Failed to load sessions: ${res.status}`)
      const data = res.data!
      return {
        sessions: data.sessions.map(mapSession),
        total: data.total,
      }
    },
    enabled: !!token,
    staleTime: 5 * 60 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
    refetchOnWindowFocus: false,
  })
}

/**
 * Fetch messages for a session with cursor-based pagination.
 */
export function useChatMessages(sessionId: string | null) {
  const token = useAuthToken()

  return useInfiniteQuery({
    queryKey: queryKeys.chatMessages(sessionId || ''),
    queryFn: async ({ pageParam }) => {
      let url = `/api/ai/sessions/${sessionId}/messages?limit=20`
      if (pageParam != null) url += `&before=${pageParam}`
      const response = await authGet<ChatMessagePage>(url)
      if (response.status !== 200) {
        throw new Error(`Failed to fetch messages: ${response.status}`)
      }
      return response.data!
    },
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (lastPage) =>
      lastPage.has_more ? lastPage.messages[0]?.sequence : undefined,
    enabled: !!token && !!sessionId,
    staleTime: Infinity,
    gcTime: 10 * 60 * 1000,
    refetchOnWindowFocus: false,
  })
}

/**
 * Helper to get flat list of messages from infinite query.
 */
export function useChatMessagesList(sessionId: string | null) {
  const query = useChatMessages(sessionId)

  const messages = query.data?.pages.slice().reverse().flatMap((page) => page.messages) ?? []

  return {
    messages,
    isLoading: query.isLoading,
    isFetchingNextPage: query.isFetchingNextPage,
    hasNextPage: query.hasNextPage ?? false,
    fetchNextPage: () => query.fetchNextPage(),
    error: query.error,
  }
}

// ============================================================================
// Session Mutations
// ============================================================================

/**
 * Create a new chat session.
 */
export function useCreateSession() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: { application_id?: string }) =>
      authPost<ChatSessionSummary>('/api/ai/sessions', data),
    onSuccess: (response) => {
      if (response.data) {
        queryClient.setQueryData(
          queryKeys.chatSessions,
          (old: SessionListResponse | undefined) => {
            if (!old) return old
            return {
              sessions: [response.data!, ...old.sessions],
              total: old.total + 1,
            }
          }
        )
      }
    },
  })
}

/**
 * Update a chat session (title, archive status).
 */
export function useUpdateSession() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: { title?: string; is_archived?: boolean } }) =>
      authPatch<ChatSessionSummary>(`/api/ai/sessions/${id}`, data),
    onSuccess: (response, { id, data }) => {
      queryClient.setQueryData(
        queryKeys.chatSessions,
        (old: SessionListResponse | undefined) => {
          if (!old) return old
          return {
            sessions: data.is_archived
              ? old.sessions.filter((s) => s.id !== id)
              : old.sessions.map((s) =>
                  s.id === id && response.data ? { ...s, ...mapSession(response.data as unknown as RawSessionSummary) } : s
                ),
            total: data.is_archived ? old.total - 1 : old.total,
          }
        }
      )
    },
  })
}

/**
 * Delete a chat session.
 */
export function useDeleteSession() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (id: string) => authDelete(`/api/ai/sessions/${id}`),
    onSuccess: (_response, id) => {
      queryClient.setQueryData(
        queryKeys.chatSessions,
        (old: SessionListResponse | undefined) => {
          if (!old) return old
          return {
            sessions: old.sessions.filter((s) => s.id !== id),
            total: old.total - 1,
          }
        }
      )
      queryClient.removeQueries({ queryKey: queryKeys.chatMessages(id) })
    },
  })
}

/**
 * Persist messages to a session.
 */
export function usePersistMessages() {
  return useMutation({
    mutationFn: ({
      sessionId,
      messages,
    }: {
      sessionId: string
      messages: Array<{
        role: string
        content: string
        sources?: unknown
        checkpoint_id?: string
        is_error?: boolean
      }>
    }) => authPost(`/api/ai/sessions/${sessionId}/messages`, { messages }),
  })
}
