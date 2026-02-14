/**
 * Delete Dialog
 *
 * Confirmation dialog for deleting documents or folders.
 * Shows loading state during deletion and warns about folder contents.
 */

import { useState } from 'react'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
} from '@/components/ui/confirm-dialog'
import { Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface DeleteDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  itemName: string
  itemType: 'document' | 'folder'
  onConfirm: () => Promise<void>
}

export function DeleteDialog({
  open,
  onOpenChange,
  itemName,
  itemType,
  onConfirm,
}: DeleteDialogProps): JSX.Element {
  const [isDeleting, setIsDeleting] = useState(false)

  const handleConfirm = async () => {
    setIsDeleting(true)
    try {
      await onConfirm()
      // With optimistic updates, the item disappears instantly from the tree
      // so we can close the dialog immediately
      onOpenChange(false)
    } finally {
      setIsDeleting(false)
    }
  }

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <div className="p-6">
          <div className="text-center mb-6">
            <AlertDialogTitle className="mb-2">
              Delete {itemType}?
            </AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete &quot;{itemName}&quot;?
              {itemType === 'folder' && ' This will also delete all documents inside.'}
              {' '}This action cannot be undone.
            </AlertDialogDescription>
          </div>
          <div className="flex items-center justify-center gap-3">
            <AlertDialogCancel disabled={isDeleting}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirm}
              disabled={isDeleting}
              className={cn(
                'bg-destructive text-destructive-foreground hover:bg-destructive/90'
              )}
            >
              {isDeleting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {isDeleting ? 'Deleting...' : 'Delete'}
            </AlertDialogAction>
          </div>
        </div>
      </AlertDialogContent>
    </AlertDialog>
  )
}

export default DeleteDialog
