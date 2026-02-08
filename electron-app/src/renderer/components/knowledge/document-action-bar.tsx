/**
 * DocumentActionBar
 *
 * Combined action bar above the editor that replaces LockBanner and SaveStatus bar.
 * Shows contextual controls based on view/edit mode and lock state.
 *
 * | Mode                | Left                   | Right                          |
 * |---------------------|------------------------|--------------------------------|
 * | View, unlocked      | (empty)                | "Edit" button                  |
 * | View, locked other  | "Being edited by X"    | "Take over" (if owner)         |
 * | Edit, clean         | (empty)                | "Cancel" + "Save" (disabled)   |
 * | Edit, dirty         | "Unsaved changes"      | "Cancel" + "Save" (enabled)    |
 * | Edit, saving        | "Saving..."            | "Cancel" + "Save" (disabled)   |
 */

import { Pencil, Lock, Save, X, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import type { LockHolder } from '@/hooks/use-document-lock'

// ============================================================================
// Types
// ============================================================================

export interface DocumentActionBarProps {
  mode: 'view' | 'edit'
  lockHolder: LockHolder | null
  isLockedByOther: boolean
  canForceTake: boolean
  isDirty: boolean
  isSaving: boolean
  /** True while entering edit mode (refetch + lock acquire) */
  isEntering: boolean
  /** True while exiting edit mode (save + lock release) */
  isExiting: boolean
  onEdit: () => void
  onSave: () => void
  onCancel: () => void
  onForceTake: () => void
}

// ============================================================================
// Component
// ============================================================================

export function DocumentActionBar({
  mode,
  lockHolder,
  isLockedByOther,
  canForceTake,
  isDirty,
  isSaving,
  isEntering,
  isExiting,
  onEdit,
  onSave,
  onCancel,
  onForceTake,
}: DocumentActionBarProps) {
  // View mode
  if (mode === 'view') {
    // Locked by another user
    if (isLockedByOther && lockHolder) {
      return (
        <div className="flex items-center justify-between px-4 py-1.5 border-b bg-amber-500/10">
          <div className="flex items-center gap-2 text-sm text-amber-700 dark:text-amber-400">
            <Lock className="h-3.5 w-3.5" />
            <span>Being edited by {lockHolder.user_name}</span>
          </div>
          {canForceTake && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onForceTake}
              disabled={isEntering}
              className="h-7 text-xs gap-1.5"
            >
              {isEntering ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : null}
              {isEntering ? 'Taking over...' : 'Take over'}
            </Button>
          )}
        </div>
      )
    }

    // Unlocked — show Edit button
    return (
      <div className="flex items-center justify-end px-4 py-1.5 border-b bg-muted/30">
        <Button
          variant="ghost"
          size="sm"
          onClick={onEdit}
          disabled={isEntering}
          className="h-7 text-xs gap-1.5"
        >
          {isEntering ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Pencil className="h-3.5 w-3.5" />
          )}
          {isEntering ? 'Opening editor...' : 'Edit'}
        </Button>
      </div>
    )
  }

  // Edit mode
  const busy = isSaving || isExiting

  return (
    <div className="flex items-center justify-between px-4 py-1.5 border-b bg-primary/5">
      {/* Left side: status */}
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        {isSaving ? (
          <>
            <Loader2 className="h-3 w-3 animate-spin" />
            <span>Saving...</span>
          </>
        ) : isExiting ? (
          <>
            <Loader2 className="h-3 w-3 animate-spin" />
            <span>Closing editor...</span>
          </>
        ) : isDirty ? (
          <span>Unsaved changes</span>
        ) : null}
      </div>

      {/* Right side: action buttons */}
      <div className="flex items-center gap-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={onCancel}
          disabled={busy}
          className="h-7 text-xs gap-1.5"
        >
          <X className="h-3.5 w-3.5" />
          Cancel
        </Button>
        <Button
          variant="default"
          size="sm"
          onClick={onSave}
          disabled={!isDirty || busy}
          className="h-7 text-xs gap-1.5"
        >
          {isSaving ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Save className="h-3.5 w-3.5" />
          )}
          {isSaving ? 'Saving...' : 'Save'}
        </Button>
      </div>
    </div>
  )
}
