/**
 * SaveStatus Component
 *
 * Displays real-time save state in the editor status bar.
 * Shows "Saving..." with pulse animation, "Saved Xs ago" with
 * live-updating timer, or "Save failed" in red on error.
 */

import { useEffect, useState } from 'react'
import type { SaveStatus as SaveStatusType } from '@/hooks/use-auto-save'
import { cn } from '@/lib/utils'

// ============================================================================
// Helpers
// ============================================================================

/** Format seconds into a human-readable relative time string */
function formatRelativeTime(seconds: number): string {
  if (seconds < 5) return 'Saved just now'
  if (seconds < 60) return `Saved ${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  return `Saved ${minutes}m ago`
}

// ============================================================================
// Component
// ============================================================================

export interface SaveStatusProps {
  status: SaveStatusType
  className?: string
}

export function SaveStatus({ status, className }: SaveStatusProps) {
  const [, setTick] = useState(0)

  // Live-update the "Saved Xs ago" text every second
  useEffect(() => {
    if (status.state !== 'saved') return

    const interval = setInterval(() => {
      setTick((t) => t + 1)
    }, 1000)

    return () => clearInterval(interval)
  }, [status])

  if (status.state === 'idle') {
    return null
  }

  if (status.state === 'saving') {
    return (
      <span className={cn('text-xs text-muted-foreground animate-pulse', className)}>
        Saving...
      </span>
    )
  }

  if (status.state === 'saved') {
    const seconds = Math.floor((Date.now() - status.at) / 1000)
    return (
      <span className={cn('text-xs text-muted-foreground', className)}>
        {formatRelativeTime(seconds)}
      </span>
    )
  }

  // state === 'error'
  return (
    <span className={cn('text-xs text-destructive', className)} title={status.message}>
      Save failed
    </span>
  )
}
