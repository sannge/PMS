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

import { Pencil, Lock, Save, X, Loader2, LayoutGrid } from 'lucide-react'
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
  /** Whether the current user has edit permission */
  canEdit: boolean
  isDirty: boolean
  isSaving: boolean
  /** True while entering edit mode (refetch + lock acquire) */
  isEntering: boolean
  /** True while exiting edit mode (save + lock release) */
  isExiting: boolean
  /** Whether the document is in canvas format */
  isCanvas?: boolean
  onEdit: () => void
  onSave: () => void
  onCancel: () => void
  onForceTake: () => void
  /** Callback to convert this document to canvas format */
  onConvertToCanvas?: () => void
}

// ============================================================================
// Component
// ============================================================================

export function DocumentActionBar({
  mode,
  lockHolder,
  isLockedByOther,
  canForceTake,
  canEdit,
  isDirty,
  isSaving,
  isEntering,
  isExiting,
  isCanvas,
  onEdit,
  onSave,
  onCancel,
  onForceTake,
  onConvertToCanvas,
}: DocumentActionBarProps) {
  // View mode
  if (mode === 'view') {
    // Locked by another user
    if (isLockedByOther && lockHolder) {
      return (
        <div className="flex items-center justify-between px-4 py-1.5 border-b bg-amber-500/10">
          <div className="flex items-center gap-2 text-sm text-amber-700 dark:text-amber-400">
            <Lock className="h-3.5 w-3.5" aria-hidden="true" />
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
                <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
              ) : null}
              {isEntering ? 'Taking over...' : 'Take over'}
            </Button>
          )}
        </div>
      )
    }

    // Unlocked — show Edit button or "View only" indicator
    return (
      <div className="flex items-center justify-end gap-2 px-4 py-1.5 border-b bg-muted/30 shrink-0 min-w-0 overflow-hidden">
        {canEdit ? (
          <>
            {!isCanvas && onConvertToCanvas && (
              <Button
                variant="ghost"
                size="sm"
                onClick={onConvertToCanvas}
                disabled={isEntering}
                className="h-7 text-xs gap-1.5 text-muted-foreground"
                aria-label="Convert document to canvas format"
              >
                <LayoutGrid className="h-3.5 w-3.5" aria-hidden="true" />
                Canvas
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={onEdit}
              disabled={isEntering}
              className="h-7 text-xs gap-1.5"
            >
              {isEntering ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
              ) : (
                <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
              )}
              {isEntering ? 'Opening editor...' : 'Edit'}
            </Button>
          </>
        ) : (
          <span className="text-xs text-muted-foreground">View only</span>
        )}
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
            <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
            <span>Saving...</span>
          </>
        ) : isExiting ? (
          <>
            <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
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
          <X className="h-3.5 w-3.5" aria-hidden="true" />
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
            <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
          ) : (
            <Save className="h-3.5 w-3.5" aria-hidden="true" />
          )}
          {isSaving ? 'Saving...' : 'Save'}
        </Button>
      </div>
    </div>
  )
}
