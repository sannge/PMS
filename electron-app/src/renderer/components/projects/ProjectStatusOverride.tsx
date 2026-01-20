/**
 * ProjectStatusOverride Component
 *
 * Panel for project owners to manually override project status.
 * Features:
 * - View current status (derived vs override)
 * - Set status override with reason
 * - Optional expiration date
 * - Clear override to revert to derived status
 */

import { useState, useCallback, useEffect } from 'react'
import { cn } from '@/lib/utils'
import {
  AlertTriangle,
  Shield,
  Clock,
  X,
  Check,
  Loader2,
  ChevronDown,
  Calendar,
  Info,
} from 'lucide-react'
import { useAuthStore, getAuthHeaders } from '@/stores/auth-store'

// ============================================================================
// Types
// ============================================================================

export interface TaskStatus {
  id: string
  name: string
  color: string
  position: number
}

export interface Project {
  id: string
  name: string
  derived_status_id: string | null
  override_status_id: string | null
  override_reason: string | null
  override_by_user_id: string | null
  override_expires_at: string | null
}

export interface ProjectStatusOverrideProps {
  project: Project
  statuses: TaskStatus[]
  isOwner: boolean
  onOverrideSet?: () => void
  onOverrideCleared?: () => void
  className?: string
}

// ============================================================================
// Component
// ============================================================================

export function ProjectStatusOverride({
  project,
  statuses,
  isOwner,
  onOverrideSet,
  onOverrideCleared,
  className,
}: ProjectStatusOverrideProps): JSX.Element {
  const token = useAuthStore((state) => state.token)

  const [isEditing, setIsEditing] = useState(false)
  const [selectedStatusId, setSelectedStatusId] = useState<string | null>(null)
  const [reason, setReason] = useState('')
  const [expiresAt, setExpiresAt] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showStatusDropdown, setShowStatusDropdown] = useState(false)

  // Get current and override status objects
  const derivedStatus = statuses.find((s) => s.id === project.derived_status_id)
  const overrideStatus = statuses.find((s) => s.id === project.override_status_id)
  const hasOverride = !!project.override_status_id
  const isExpired = project.override_expires_at
    ? new Date(project.override_expires_at) < new Date()
    : false

  // Reset form when editing state changes
  useEffect(() => {
    if (isEditing) {
      setSelectedStatusId(null)
      setReason('')
      setExpiresAt('')
      setError(null)
    }
  }, [isEditing])

  // Set override
  const handleSetOverride = useCallback(async () => {
    if (!selectedStatusId || !reason.trim()) return

    setIsSubmitting(true)
    setError(null)

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const payload: Record<string, unknown> = {
        override_status_id: selectedStatusId,
        override_reason: reason.trim(),
      }

      if (expiresAt) {
        payload.override_expires_at = new Date(expiresAt).toISOString()
      }

      const response = await window.electronAPI.put<Project>(
        `/api/projects/${project.id}/override-status`,
        payload,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        const errorData = response.data as { detail?: string }
        throw new Error(errorData?.detail || 'Failed to set override')
      }

      setIsEditing(false)
      onOverrideSet?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to set override')
    } finally {
      setIsSubmitting(false)
    }
  }, [project.id, selectedStatusId, reason, expiresAt, token, onOverrideSet])

  // Clear override
  const handleClearOverride = useCallback(async () => {
    setIsSubmitting(true)
    setError(null)

    try {
      if (!window.electronAPI) {
        throw new Error('Electron API not available')
      }

      const response = await window.electronAPI.delete<Project>(
        `/api/projects/${project.id}/override-status`,
        getAuthHeaders(token)
      )

      if (response.status !== 200) {
        const errorData = response.data as { detail?: string }
        throw new Error(errorData?.detail || 'Failed to clear override')
      }

      onOverrideCleared?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to clear override')
    } finally {
      setIsSubmitting(false)
    }
  }, [project.id, token, onOverrideCleared])

  // Selected status for the dropdown
  const selectedStatus = statuses.find((s) => s.id === selectedStatusId)

  return (
    <div
      className={cn(
        'rounded-lg border border-border bg-card p-4',
        className
      )}
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        <Shield className="h-4 w-4 text-muted-foreground" />
        <h3 className="text-sm font-semibold text-foreground">Project Status</h3>
      </div>

      {/* Current status display */}
      <div className="space-y-3">
        {/* Derived status */}
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">Calculated Status:</span>
          <StatusBadge status={derivedStatus} label={derivedStatus?.name || 'Not set'} />
        </div>

        {/* Override status */}
        {hasOverride && (
          <>
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground flex items-center gap-1">
                <AlertTriangle className="h-3 w-3 text-amber-500" />
                Override:
              </span>
              <StatusBadge
                status={overrideStatus}
                label={overrideStatus?.name || 'Unknown'}
                isOverride
                isExpired={isExpired}
              />
            </div>

            {/* Override details */}
            <div className="bg-muted/30 rounded-md p-2 text-xs space-y-1">
              <div className="flex items-start gap-1">
                <Info className="h-3 w-3 mt-0.5 text-muted-foreground flex-shrink-0" />
                <span className="text-muted-foreground">{project.override_reason}</span>
              </div>
              {project.override_expires_at && (
                <div className="flex items-center gap-1 text-muted-foreground">
                  <Clock className="h-3 w-3" />
                  <span>
                    {isExpired ? 'Expired' : 'Expires'}:{' '}
                    {new Date(project.override_expires_at).toLocaleDateString()}
                  </span>
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {/* Error display */}
      {error && (
        <div className="mt-3 flex items-center gap-2 px-2 py-1.5 bg-destructive/10 rounded-md">
          <AlertTriangle className="h-3 w-3 text-destructive flex-shrink-0" />
          <span className="text-xs text-destructive">{error}</span>
        </div>
      )}

      {/* Owner actions */}
      {isOwner && (
        <div className="mt-4 pt-3 border-t border-border">
          {isEditing ? (
            <div className="space-y-3">
              {/* Status selector */}
              <div className="relative">
                <label className="text-xs text-muted-foreground mb-1 block">
                  Override to Status
                </label>
                <button
                  onClick={() => setShowStatusDropdown(!showStatusDropdown)}
                  className={cn(
                    'w-full flex items-center justify-between px-3 py-2 rounded-md',
                    'border border-border bg-background',
                    'text-sm text-foreground',
                    'hover:border-primary/50',
                    'transition-colors'
                  )}
                >
                  {selectedStatus ? (
                    <StatusBadge status={selectedStatus} label={selectedStatus.name} />
                  ) : (
                    <span className="text-muted-foreground">Select status...</span>
                  )}
                  <ChevronDown className="h-4 w-4 text-muted-foreground" />
                </button>

                {showStatusDropdown && (
                  <div
                    className={cn(
                      'absolute top-full left-0 right-0 mt-1 z-50',
                      'border border-border rounded-md bg-popover shadow-lg',
                      'max-h-48 overflow-y-auto'
                    )}
                  >
                    {statuses.map((status) => (
                      <button
                        key={status.id}
                        onClick={() => {
                          setSelectedStatusId(status.id)
                          setShowStatusDropdown(false)
                        }}
                        className={cn(
                          'w-full flex items-center gap-2 px-3 py-2',
                          'text-sm hover:bg-muted',
                          'transition-colors',
                          selectedStatusId === status.id && 'bg-muted'
                        )}
                      >
                        <div
                          className="w-3 h-3 rounded-full"
                          style={{ backgroundColor: status.color }}
                        />
                        <span>{status.name}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Reason input */}
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">
                  Reason (required)
                </label>
                <textarea
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="Why are you overriding the status?"
                  rows={2}
                  maxLength={500}
                  className={cn(
                    'w-full px-3 py-2 rounded-md resize-none',
                    'border border-border bg-background',
                    'text-sm text-foreground',
                    'placeholder:text-muted-foreground',
                    'focus:outline-none focus:ring-1 focus:ring-ring'
                  )}
                />
                <div className="text-[10px] text-muted-foreground text-right mt-0.5">
                  {reason.length}/500
                </div>
              </div>

              {/* Expiration date */}
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">
                  Expires (optional)
                </label>
                <div className="relative">
                  <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <input
                    type="datetime-local"
                    value={expiresAt}
                    onChange={(e) => setExpiresAt(e.target.value)}
                    min={new Date().toISOString().slice(0, 16)}
                    className={cn(
                      'w-full pl-9 pr-3 py-2 rounded-md',
                      'border border-border bg-background',
                      'text-sm text-foreground',
                      'focus:outline-none focus:ring-1 focus:ring-ring'
                    )}
                  />
                </div>
              </div>

              {/* Actions */}
              <div className="flex items-center gap-2">
                <button
                  onClick={handleSetOverride}
                  disabled={!selectedStatusId || !reason.trim() || isSubmitting}
                  className={cn(
                    'flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-md',
                    'bg-primary text-primary-foreground text-sm font-medium',
                    'hover:bg-primary/90',
                    'disabled:opacity-50 disabled:cursor-not-allowed',
                    'transition-colors'
                  )}
                >
                  {isSubmitting ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Check className="h-4 w-4" />
                  )}
                  Set Override
                </button>
                <button
                  onClick={() => setIsEditing(false)}
                  disabled={isSubmitting}
                  className={cn(
                    'px-3 py-2 rounded-md',
                    'text-sm text-muted-foreground',
                    'hover:bg-muted',
                    'transition-colors'
                  )}
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <button
                onClick={() => setIsEditing(true)}
                className={cn(
                  'flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-md',
                  'border border-border',
                  'text-sm font-medium text-foreground',
                  'hover:bg-muted',
                  'transition-colors'
                )}
              >
                <AlertTriangle className="h-4 w-4" />
                {hasOverride ? 'Change Override' : 'Set Override'}
              </button>
              {hasOverride && (
                <button
                  onClick={handleClearOverride}
                  disabled={isSubmitting}
                  className={cn(
                    'inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-md',
                    'text-sm font-medium text-destructive',
                    'hover:bg-destructive/10',
                    'disabled:opacity-50',
                    'transition-colors'
                  )}
                >
                  {isSubmitting ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <X className="h-4 w-4" />
                  )}
                  Clear
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Sub-components
// ============================================================================

interface StatusBadgeProps {
  status: TaskStatus | undefined
  label: string
  isOverride?: boolean
  isExpired?: boolean
}

function StatusBadge({ status, label, isOverride, isExpired }: StatusBadgeProps): JSX.Element {
  return (
    <div
      className={cn(
        'inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full',
        'text-xs font-medium',
        isExpired && 'opacity-50'
      )}
      style={{
        backgroundColor: status ? `${status.color}20` : undefined,
        color: status?.color || 'inherit',
      }}
    >
      <div
        className="w-2 h-2 rounded-full"
        style={{ backgroundColor: status?.color || '#888' }}
      />
      {label}
      {isOverride && !isExpired && (
        <AlertTriangle className="h-2.5 w-2.5 text-amber-500" />
      )}
      {isExpired && (
        <span className="text-muted-foreground">(expired)</span>
      )}
    </div>
  )
}

// ============================================================================
// Exports
// ============================================================================

export default ProjectStatusOverride
