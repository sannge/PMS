/**
 * Create Dialog
 *
 * Reusable dialog for creating documents or folders with name input.
 * Shows loading state during submission and validates non-empty name.
 */

import { useState, useEffect } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Loader2 } from 'lucide-react'

export interface CreateDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  type: 'document' | 'folder'
  onSubmit: (name: string) => Promise<void>
}

export function CreateDialog({
  open,
  onOpenChange,
  type,
  onSubmit,
}: CreateDialogProps): JSX.Element {
  const defaultName = type === 'document' ? 'Untitled' : 'New Folder'
  const [name, setName] = useState(defaultName)
  const [isSubmitting, setIsSubmitting] = useState(false)

  // Reset name when dialog opens or type changes
  useEffect(() => {
    if (open) {
      setName(type === 'document' ? 'Untitled' : 'New Folder')
    }
  }, [open, type])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return

    setIsSubmitting(true)
    try {
      await onSubmit(name.trim())
      onOpenChange(false)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[400px]">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>
              Create {type === 'document' ? 'Document' : 'Folder'}
            </DialogTitle>
            <DialogDescription>
              Enter a name for your new {type}.
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <Label htmlFor="name">Name</Label>
            <Input
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={type === 'document' ? 'Document name' : 'Folder name'}
              autoFocus
              disabled={isSubmitting}
              className="mt-1.5"
            />
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting || !name.trim()}>
              {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {isSubmitting ? 'Creating...' : 'Create'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export default CreateDialog
