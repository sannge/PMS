/**
 * File Conflict Dialog
 *
 * Shown when a file upload returns HTTP 409 (conflict) because a file
 * with the same name already exists in the folder.
 *
 * Options:
 * - Replace: overwrite the existing file
 * - Keep Both: re-upload with an incremented name (e.g., "report (1).xlsx")
 * - Cancel: skip the file
 *
 * Uses Radix AlertDialog from the confirm-dialog component.
 */

import { useState, useCallback } from 'react'
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogTitle,
  AlertDialogDescription,
} from '@/components/ui/confirm-dialog'
import { AlertTriangle, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useReplaceFile, useUploadFile, type UploadConflictError } from '@/hooks/use-folder-files'
import { toast } from 'sonner'

// ============================================================================
// Types
// ============================================================================

export interface FileConflictDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** The file that caused the conflict */
  file: File | null
  /** The folder the file was being uploaded to (null for unfiled uploads) */
  folderId: string | null
  /** Scope type for unfiled uploads (used when folderId is null) */
  scope?: string
  /** Scope entity ID for unfiled uploads (used when folderId is null) */
  scopeId?: string
  /** The ID of the existing file to replace (if known) */
  existingFileId?: string | null
  /** Called after the conflict is resolved */
  onResolved?: () => void
}

// ============================================================================
// Helpers
// ============================================================================

/**
 * Increment a filename: "report.xlsx" -> "report (1).xlsx"
 * "report (1).xlsx" -> "report (2).xlsx"
 */
function incrementFilename(filename: string): string {
  const lastDot = filename.lastIndexOf('.')
  const name = lastDot > 0 ? filename.slice(0, lastDot) : filename
  const ext = lastDot > 0 ? filename.slice(lastDot) : ''

  const match = name.match(/^(.+?)\s*\((\d+)\)$/)
  if (match) {
    const baseName = match[1]
    const num = parseInt(match[2], 10) + 1
    return `${baseName} (${num})${ext}`
  }

  return `${name} (1)${ext}`
}

/** Maximum retry attempts for "Keep Both" to avoid infinite loops. */
const MAX_KEEP_BOTH_ATTEMPTS = 10

// ============================================================================
// Component
// ============================================================================

export function FileConflictDialog({
  open,
  onOpenChange,
  file,
  folderId,
  scope,
  scopeId,
  existingFileId,
  onResolved,
}: FileConflictDialogProps): JSX.Element {
  // Track which action is in progress to show spinner on correct button
  const [activeAction, setActiveAction] = useState<'idle' | 'replacing' | 'keepingBoth'>('idle')
  const replaceFile = useReplaceFile()
  const uploadFile = useUploadFile()

  const handleReplace = useCallback(async () => {
    if (!file || !existingFileId || (!folderId && !scopeId)) return
    setActiveAction('replacing')
    try {
      await replaceFile.mutateAsync({
        fileId: existingFileId,
        file,
        folderId: folderId ?? '',
        scope,
        scopeId,
      })
      onOpenChange(false)
      onResolved?.()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to replace file')
    } finally {
      setActiveAction('idle')
    }
  }, [file, folderId, scope, scopeId, existingFileId, replaceFile, onOpenChange, onResolved])

  const handleKeepBoth = useCallback(async () => {
    if (!file || (!folderId && !scopeId)) return
    setActiveAction('keepingBoth')
    try {
      // Retry with incremented names if we keep getting 409
      let candidateName = incrementFilename(file.name)
      for (let attempt = 0; attempt < MAX_KEEP_BOTH_ATTEMPTS; attempt++) {
        try {
          await uploadFile.mutateAsync({
            file,
            folderId: folderId ?? undefined,
            scope: !folderId ? scope : undefined,
            scopeId: !folderId ? scopeId : undefined,
            displayName: candidateName,
          })
          // Success -- break out
          onOpenChange(false)
          onResolved?.()
          return
        } catch (err) {
          const uploadErr = err as UploadConflictError
          if (uploadErr.status === 409 && attempt < MAX_KEEP_BOTH_ATTEMPTS - 1) {
            // Name still conflicts, try next increment
            candidateName = incrementFilename(candidateName)
            continue
          }
          // Non-conflict error or max attempts exceeded
          throw err
        }
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to upload file')
    } finally {
      setActiveAction('idle')
    }
  }, [file, folderId, scope, scopeId, uploadFile, onOpenChange, onResolved])

  const handleCancel = useCallback(() => {
    onOpenChange(false)
    onResolved?.()
  }, [onOpenChange, onResolved])

  const isProcessing = activeAction !== 'idle'

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <div className="p-6">
          {/* Icon */}
          <div className="mb-4 flex justify-center">
            <div className={cn(
              'flex items-center justify-center',
              'h-12 w-12 rounded-full',
              'bg-amber-500/10 border border-amber-500/20'
            )}>
              <AlertTriangle className="h-6 w-6 text-amber-500" />
            </div>
          </div>

          {/* Title & Description */}
          <div className="text-center mb-6">
            <AlertDialogTitle className="mb-2">
              File already exists
            </AlertDialogTitle>
            <AlertDialogDescription>
              A file named &quot;{file?.name}&quot; already exists in this folder.
              What would you like to do?
            </AlertDialogDescription>
          </div>

          {/* Actions */}
          <div className="flex flex-col gap-2">
            {existingFileId && (
              <button
                onClick={handleReplace}
                disabled={isProcessing}
                className={cn(
                  'w-full inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2.5',
                  'text-sm font-semibold transition-all duration-200',
                  'bg-primary text-primary-foreground hover:bg-primary/90',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                  'disabled:pointer-events-none disabled:opacity-50'
                )}
              >
                {activeAction === 'replacing' && <Loader2 className="h-4 w-4 animate-spin" />}
                Replace
              </button>
            )}
            <button
              onClick={handleKeepBoth}
              disabled={isProcessing}
              className={cn(
                'w-full inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2.5',
                'text-sm font-medium transition-all duration-200',
                'bg-secondary text-foreground hover:bg-secondary/80',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                'disabled:pointer-events-none disabled:opacity-50'
              )}
            >
              {activeAction === 'keepingBoth' && <Loader2 className="h-4 w-4 animate-spin" />}
              Keep Both
            </button>
            <button
              onClick={handleCancel}
              disabled={isProcessing}
              className={cn(
                'w-full inline-flex items-center justify-center rounded-lg px-4 py-2.5',
                'text-sm font-medium text-muted-foreground',
                'hover:text-foreground hover:bg-muted/50',
                'transition-all duration-200',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                'disabled:pointer-events-none disabled:opacity-50'
              )}
            >
              Cancel
            </button>
          </div>
        </div>
      </AlertDialogContent>
    </AlertDialog>
  )
}

export default FileConflictDialog
