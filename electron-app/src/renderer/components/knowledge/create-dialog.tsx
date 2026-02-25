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
import { Loader2, FileText, LayoutGrid } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface CreateDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  type: 'document' | 'folder'
  onSubmit: (name: string, format?: 'document' | 'canvas') => Promise<void>
}

export function CreateDialog({
  open,
  onOpenChange,
  type,
  onSubmit,
}: CreateDialogProps): JSX.Element {
  const defaultName = type === 'document' ? 'Untitled' : 'New Folder'
  const [name, setName] = useState(defaultName)
  const [format, setFormat] = useState<'document' | 'canvas'>('document')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Reset name, format, and error when dialog opens or type changes
  useEffect(() => {
    if (open) {
      setName(type === 'document' ? 'Untitled' : 'New Folder')
      setFormat('document')
      setError(null)
    }
  }, [open, type])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return

    setIsSubmitting(true)
    setError(null)
    try {
      await onSubmit(name.trim(), type === 'document' ? format : undefined)
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create')
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
          <div className="py-4 space-y-3">
            <div>
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                value={name}
                onChange={(e) => { setName(e.target.value); setError(null) }}
                placeholder={type === 'document' ? 'Document name' : 'Folder name'}
                autoFocus
                disabled={isSubmitting}
                className="mt-1.5"
              />
            </div>
            {type === 'document' && (
              <div>
                <Label id="format-label">Format</Label>
                <div
                  role="radiogroup"
                  aria-labelledby="format-label"
                  className="flex gap-1 mt-1.5"
                  onKeyDown={(e) => {
                    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
                      e.preventDefault()
                      const next = format === 'document' ? 'canvas' : 'document'
                      setFormat(next)
                      // Move focus to the newly selected button
                      const container = e.currentTarget
                      const buttons = container.querySelectorAll<HTMLButtonElement>('[role="radio"]')
                      const idx = next === 'document' ? 0 : 1
                      buttons[idx]?.focus()
                    }
                  }}
                >
                  <Button
                    type="button"
                    role="radio"
                    aria-checked={format === 'document'}
                    tabIndex={format === 'document' ? 0 : -1}
                    variant={format === 'document' ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => setFormat('document')}
                    disabled={isSubmitting}
                    className={cn('flex-1 gap-1.5', format !== 'document' && 'text-muted-foreground')}
                  >
                    <FileText className="h-3.5 w-3.5" aria-hidden="true" />
                    Document
                  </Button>
                  <Button
                    type="button"
                    role="radio"
                    aria-checked={format === 'canvas'}
                    tabIndex={format === 'canvas' ? 0 : -1}
                    variant={format === 'canvas' ? 'default' : 'outline'}
                    size="sm"
                    onClick={() => setFormat('canvas')}
                    disabled={isSubmitting}
                    className={cn('flex-1 gap-1.5', format !== 'canvas' && 'text-muted-foreground')}
                  >
                    <LayoutGrid className="h-3.5 w-3.5" aria-hidden="true" />
                    Canvas
                  </Button>
                </div>
                <span className="sr-only" aria-live="polite">
                  {format === 'canvas' ? 'Canvas format selected' : 'Document format selected'}
                </span>
              </div>
            )}
            {error && (
              <p className="text-sm text-destructive">{error}</p>
            )}
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
              {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />}
              {isSubmitting ? 'Creating...' : 'Create'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export default CreateDialog
