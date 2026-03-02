/**
 * TanStack Query Hooks for Document Import
 *
 * Provides React Query hooks for importing PDF/DOCX/PPTX documents
 * into the knowledge base via the AI import pipeline.
 *
 * - useImportDocument: Mutation to upload a file for import
 * - useImportJobStatus: Polling query for import job progress
 * - useImportJobs: Query for listing recent import jobs
 *
 * @see fastapi-backend/app/routers/ai_import.py
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query'
import { useAuthToken, getAuthHeaders } from '@/contexts/auth-context'
import { queryKeys } from '@/lib/query-client'

// ============================================================================
// Types
// ============================================================================

export interface ImportJobResponse {
  id: string
  user_id: string
  file_name: string
  file_type: string
  file_size: number
  status: 'pending' | 'processing' | 'completed' | 'failed'
  progress_pct: number
  document_id: string | null
  scope: string
  scope_id: string
  folder_id: string | null
  title: string | null
  error_message: string | null
  created_at: string
  completed_at: string | null
}

export interface ImportJobListResponse {
  items: ImportJobResponse[]
  total: number
  limit: number
  offset: number
}

export interface ImportJobCreateResponse {
  job_id: string
  status: string
  file_name: string
}

interface ImportDocumentPayload {
  file: File
  title: string
  scope: string
  scope_id: string
  folder_id?: string | null
}

// ============================================================================
// Constants
// ============================================================================

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8001'

// getAuthHeaders imported from @/contexts/auth-context

// ============================================================================
// Mutations
// ============================================================================

/**
 * Upload a document file for import into the knowledge base.
 *
 * Sends the file as multipart/form-data to POST /api/ai/import.
 * Returns the initial job status with a job_id for progress tracking.
 */
export function useImportDocument(): UseMutationResult<
  ImportJobCreateResponse,
  Error,
  ImportDocumentPayload
> {
  const token = useAuthToken()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ file, title, scope, scope_id, folder_id }: ImportDocumentPayload) => {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('title', title)
      formData.append('scope', scope)
      formData.append('scope_id', scope_id)
      if (folder_id) {
        formData.append('folder_id', folder_id)
      }

      // Use fetch directly for multipart/form-data
      // Do NOT set Content-Type header — browser sets it with boundary
      const response = await fetch(`${API_BASE}/api/ai/import/`, {
        method: 'POST',
        headers: {
          ...getAuthHeaders(token),
        },
        body: formData,
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(
          (errorData as Record<string, unknown>).detail as string || 'Upload failed'
        )
      }

      return (await response.json()) as ImportJobCreateResponse
    },
    onSuccess: () => {
      // Invalidate the import jobs list so it picks up the new job
      queryClient.invalidateQueries({ queryKey: queryKeys.importJobs })
    },
  })
}

// ============================================================================
// Queries
// ============================================================================

/**
 * Poll the status of an import job.
 *
 * Fetches GET /api/ai/import/{jobId} and polls every 2 seconds
 * while the job is in "pending" or "processing" state.
 * Stops polling once the job reaches "completed" or "failed".
 */
export function useImportJobStatus(
  jobId: string | null
): UseQueryResult<ImportJobResponse, Error> {
  const token = useAuthToken()

  return useQuery({
    queryKey: queryKeys.importJob(jobId ?? ''),
    queryFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.get<ImportJobResponse>(
        `/api/ai/import/${jobId}`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        const errorData = response.data as unknown as Record<string, unknown> | undefined
        throw new Error(
          (typeof errorData?.detail === 'string' ? errorData.detail : null) ||
            'Failed to fetch import status'
        )
      }

      return response.data as ImportJobResponse
    },
    enabled: !!token && !!jobId,
    refetchInterval: (query) => {
      const data = query.state.data as ImportJobResponse | undefined
      if (data?.status === 'pending' || data?.status === 'processing') {
        return 2000
      }
      return false
    },
    // Don't refetch on window focus — polling handles freshness
    refetchOnWindowFocus: false,
    staleTime: 0,
  })
}

/**
 * List the current user's recent import jobs.
 *
 * Fetches GET /api/ai/import/jobs with an optional status filter.
 */
export function useImportJobs(
  status?: string
): UseQueryResult<ImportJobListResponse, Error> {
  const token = useAuthToken()

  return useQuery({
    queryKey: status
      ? [...queryKeys.importJobs, status]
      : queryKeys.importJobs,
    queryFn: async () => {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const params = new URLSearchParams()
      if (status) {
        params.set('status', status)
      }
      const queryString = params.toString() ? `?${params.toString()}` : ''

      const response = await window.electronAPI.get<ImportJobListResponse>(
        `/api/ai/import/jobs${queryString}`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        const errorData = response.data as unknown as Record<string, unknown> | undefined
        throw new Error(
          (typeof errorData?.detail === 'string' ? errorData.detail : null) ||
            'Failed to fetch import jobs'
        )
      }

      return (response.data as ImportJobListResponse)
    },
    enabled: !!token,
    staleTime: 30 * 1000,
  })
}
