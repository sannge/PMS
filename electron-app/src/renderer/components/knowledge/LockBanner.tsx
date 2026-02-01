/**
 * LockBanner Component
 *
 * Displays document lock status as a banner above the editor.
 * Shows different states:
 * - Locked by current user: blue banner with "Stop editing" button
 * - Locked by another user: amber banner with optional "Take over editing" for owners
 * - Unlocked: renders nothing
 */

import { Lock, Unlock } from 'lucide-react'
import type { LockHolder } from '@/hooks/use-document-lock'

// ============================================================================
// Types
// ============================================================================

interface LockBannerProps {
  lockHolder: LockHolder | null
  isLockedByMe: boolean
  canForceTake: boolean
  onStopEditing: () => void
  onForceTake: () => void
}

// ============================================================================
// Component
// ============================================================================

export function LockBanner({
  lockHolder,
  isLockedByMe,
  canForceTake,
  onStopEditing,
  onForceTake,
}: LockBannerProps) {
  if (!lockHolder) {
    return null
  }

  if (isLockedByMe) {
    return (
      <div className="flex items-center justify-between px-3 py-2 bg-primary/10 border-b text-sm">
        <div className="flex items-center gap-2 text-primary">
          <Lock className="h-4 w-4" />
          <span>You are editing this document</span>
        </div>
        <button
          onClick={onStopEditing}
          className="text-sm text-primary hover:underline"
        >
          Stop editing
        </button>
      </div>
    )
  }

  // Locked by another user
  return (
    <div className="flex items-center justify-between px-3 py-2 bg-amber-500/10 border-b text-sm">
      <div className="flex items-center gap-2 text-amber-700 dark:text-amber-400">
        <Unlock className="h-4 w-4" />
        <span>Being edited by {lockHolder.user_name}</span>
      </div>
      {canForceTake && (
        <button
          onClick={onForceTake}
          className="text-sm text-amber-700 dark:text-amber-400 hover:underline"
        >
          Take over editing
        </button>
      )}
    </div>
  )
}
