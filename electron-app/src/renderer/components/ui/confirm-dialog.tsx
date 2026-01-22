/**
 * Confirm Dialog Component
 *
 * A refined confirmation dialog for destructive actions.
 * Built on Radix AlertDialog with the Nordic design system.
 *
 * Features:
 * - Smooth animations
 * - File-specific delete variant with icon
 * - Keyboard accessible (Esc to cancel)
 * - Dark mode support
 * - Optional draggable/resizable mode
 */

import { forwardRef, type ReactNode } from 'react'
import * as AlertDialogPrimitive from '@radix-ui/react-alert-dialog'
import { cn } from '@/lib/utils'
import { AlertTriangle, Trash2, X } from 'lucide-react'
import { DraggableModal } from './draggable-modal'

// ============================================================================
// Base Components
// ============================================================================

const AlertDialog = AlertDialogPrimitive.Root
const AlertDialogTrigger = AlertDialogPrimitive.Trigger
const AlertDialogPortal = AlertDialogPrimitive.Portal

const AlertDialogOverlay = forwardRef<
  React.ElementRef<typeof AlertDialogPrimitive.Overlay>,
  React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Overlay>
>(({ className, ...props }, ref) => (
  <AlertDialogPrimitive.Overlay
    ref={ref}
    className={cn(
      'fixed inset-0 z-50 bg-black/40 backdrop-blur-sm',
      'data-[state=open]:animate-in data-[state=closed]:animate-out',
      'data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
      className
    )}
    {...props}
  />
))
AlertDialogOverlay.displayName = AlertDialogPrimitive.Overlay.displayName

const AlertDialogContent = forwardRef<
  React.ElementRef<typeof AlertDialogPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Content>
>(({ className, ...props }, ref) => (
  <AlertDialogPortal>
    <AlertDialogOverlay />
    <AlertDialogPrimitive.Content
      ref={ref}
      className={cn(
        'fixed left-[50%] top-[50%] z-50 w-full max-w-md',
        'translate-x-[-50%] translate-y-[-50%]',
        'bg-card border border-border rounded-xl shadow-xl',
        'data-[state=open]:animate-in data-[state=closed]:animate-out',
        'data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
        'data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95',
        'data-[state=closed]:slide-out-to-left-1/2 data-[state=closed]:slide-out-to-top-[48%]',
        'data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-[48%]',
        'duration-200',
        className
      )}
      {...props}
    />
  </AlertDialogPortal>
))
AlertDialogContent.displayName = AlertDialogPrimitive.Content.displayName

const AlertDialogTitle = forwardRef<
  React.ElementRef<typeof AlertDialogPrimitive.Title>,
  React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Title>
>(({ className, ...props }, ref) => (
  <AlertDialogPrimitive.Title
    ref={ref}
    className={cn('text-lg font-semibold text-foreground', className)}
    {...props}
  />
))
AlertDialogTitle.displayName = AlertDialogPrimitive.Title.displayName

const AlertDialogDescription = forwardRef<
  React.ElementRef<typeof AlertDialogPrimitive.Description>,
  React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Description>
>(({ className, ...props }, ref) => (
  <AlertDialogPrimitive.Description
    ref={ref}
    className={cn('text-sm text-muted-foreground', className)}
    {...props}
  />
))
AlertDialogDescription.displayName = AlertDialogPrimitive.Description.displayName

const AlertDialogAction = forwardRef<
  React.ElementRef<typeof AlertDialogPrimitive.Action>,
  React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Action>
>(({ className, ...props }, ref) => (
  <AlertDialogPrimitive.Action
    ref={ref}
    className={cn(
      'inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2.5',
      'text-sm font-semibold transition-all duration-200',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
      'disabled:pointer-events-none disabled:opacity-50',
      className
    )}
    {...props}
  />
))
AlertDialogAction.displayName = AlertDialogPrimitive.Action.displayName

const AlertDialogCancel = forwardRef<
  React.ElementRef<typeof AlertDialogPrimitive.Cancel>,
  React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Cancel>
>(({ className, ...props }, ref) => (
  <AlertDialogPrimitive.Cancel
    ref={ref}
    className={cn(
      'inline-flex items-center justify-center rounded-lg px-4 py-2.5',
      'text-sm font-medium text-muted-foreground',
      'bg-secondary hover:bg-secondary/80 hover:text-foreground',
      'transition-all duration-200',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
      'disabled:pointer-events-none disabled:opacity-50',
      className
    )}
    {...props}
  />
))
AlertDialogCancel.displayName = AlertDialogPrimitive.Cancel.displayName

// ============================================================================
// Compound Components
// ============================================================================

export interface ConfirmDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: string
  confirmLabel?: string
  cancelLabel?: string
  onConfirm: () => void
  onCancel?: () => void
  variant?: 'default' | 'destructive'
  icon?: ReactNode
  isLoading?: boolean
  /** Use draggable modal instead of fixed position */
  draggable?: boolean
}

/**
 * Generic confirmation dialog
 */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  onConfirm,
  onCancel,
  variant = 'default',
  icon,
  isLoading = false,
  draggable = false,
}: ConfirmDialogProps): JSX.Element {
  const handleCancel = () => {
    onCancel?.()
    onOpenChange(false)
  }

  const handleConfirm = () => {
    onConfirm()
  }

  // Draggable version
  if (draggable) {
    return (
      <DraggableModal
        open={open}
        onClose={handleCancel}
        initialWidth={400}
        minWidth={300}
        maxWidth={500}
        resizable={false}
        showDragHandle={true}
      >
        <div className="p-6">
          {/* Icon */}
          {icon && (
            <div className="mb-4 flex justify-center">
              {icon}
            </div>
          )}

          {/* Title & Description */}
          <div className="text-center mb-6">
            <h2 className="text-lg font-semibold text-foreground mb-2">{title}</h2>
            {description && (
              <p className="text-sm text-muted-foreground">{description}</p>
            )}
          </div>

          {/* Actions */}
          <div className="flex items-center justify-center gap-3">
            <button
              onClick={handleCancel}
              disabled={isLoading}
              className={cn(
                'inline-flex items-center justify-center rounded-lg px-4 py-2.5',
                'text-sm font-medium text-muted-foreground',
                'bg-secondary hover:bg-secondary/80 hover:text-foreground',
                'transition-all duration-200',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
                'disabled:pointer-events-none disabled:opacity-50'
              )}
            >
              {cancelLabel}
            </button>
            <button
              onClick={handleConfirm}
              disabled={isLoading}
              className={cn(
                'inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2.5',
                'text-sm font-semibold transition-all duration-200',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
                'disabled:pointer-events-none disabled:opacity-50',
                variant === 'destructive'
                  ? 'bg-destructive text-destructive-foreground hover:bg-destructive/90'
                  : 'bg-primary text-primary-foreground hover:bg-primary/90'
              )}
            >
              {isLoading ? (
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
              ) : null}
              {confirmLabel}
            </button>
          </div>
        </div>
      </DraggableModal>
    )
  }

  // Standard Radix version
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <div className="p-6">
          {/* Icon */}
          {icon && (
            <div className="mb-4 flex justify-center">
              {icon}
            </div>
          )}

          {/* Title & Description */}
          <div className="text-center mb-6">
            <AlertDialogTitle className="mb-2">{title}</AlertDialogTitle>
            {description && (
              <AlertDialogDescription>{description}</AlertDialogDescription>
            )}
          </div>

          {/* Actions */}
          <div className="flex items-center justify-center gap-3">
            <AlertDialogCancel onClick={handleCancel} disabled={isLoading}>
              {cancelLabel}
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirm}
              disabled={isLoading}
              className={cn(
                variant === 'destructive'
                  ? 'bg-destructive text-destructive-foreground hover:bg-destructive/90'
                  : 'bg-primary text-primary-foreground hover:bg-primary/90'
              )}
            >
              {isLoading ? (
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
              ) : null}
              {confirmLabel}
            </AlertDialogAction>
          </div>
        </div>
      </AlertDialogContent>
    </AlertDialog>
  )
}

// ============================================================================
// Delete File Confirmation Dialog
// ============================================================================

export interface DeleteFileDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  fileName: string
  fileIcon?: ReactNode
  onConfirm: () => void
  onCancel?: () => void
  isDeleting?: boolean
  /** Use draggable modal instead of fixed position */
  draggable?: boolean
}

/**
 * Specialized delete confirmation dialog for files/attachments
 */
export function DeleteFileDialog({
  open,
  onOpenChange,
  fileName,
  fileIcon,
  onConfirm,
  onCancel,
  isDeleting = false,
  draggable = false,
}: DeleteFileDialogProps): JSX.Element {
  const handleCancel = () => {
    onCancel?.()
    onOpenChange(false)
  }

  const handleConfirm = () => {
    onConfirm()
  }

  const content = (
    <div className="relative">
      {/* Decorative gradient background */}
      <div className="absolute inset-0 bg-gradient-to-b from-destructive/5 to-transparent rounded-t-xl pointer-events-none" />

      {/* Close button */}
      <button
        onClick={handleCancel}
        disabled={isDeleting}
        className={cn(
          'absolute right-4 top-4 p-1.5 rounded-lg',
          'text-muted-foreground hover:text-foreground hover:bg-muted',
          'transition-colors duration-150',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
          'disabled:opacity-50 disabled:pointer-events-none'
        )}
      >
        <X className="h-4 w-4" />
      </button>

      <div className="p-6 pt-8">
        {/* Icon Container */}
        <div className="mb-5 flex justify-center">
          <div className="relative">
            {/* Warning ring animation */}
            <div className="absolute inset-0 rounded-full bg-destructive/20 animate-ping" />
            {/* Icon background */}
            <div className={cn(
              'relative flex items-center justify-center',
              'h-16 w-16 rounded-full',
              'bg-destructive/10 border-2 border-destructive/20'
            )}>
              {fileIcon || <Trash2 className="h-7 w-7 text-destructive" />}
            </div>
          </div>
        </div>

        {/* Title */}
        <h2 className="text-lg font-semibold text-foreground text-center mb-2">
          Delete file?
        </h2>

        {/* File name with truncation */}
        <div className="mb-4 mx-auto max-w-[280px]">
          <div className={cn(
            'px-3 py-2 rounded-lg',
            'bg-muted/50 border border-border',
            'text-center'
          )}>
            <p className="text-sm font-medium text-foreground truncate" title={fileName}>
              {fileName}
            </p>
          </div>
        </div>

        {/* Warning message */}
        <p className="text-sm text-muted-foreground text-center mb-6">
          <span className="flex items-center justify-center gap-1.5">
            <AlertTriangle className="h-3.5 w-3.5 text-warning" />
            This action cannot be undone
          </span>
        </p>

        {/* Actions */}
        <div className="flex items-center gap-3">
          <button
            onClick={handleCancel}
            disabled={isDeleting}
            className={cn(
              'flex-1 inline-flex items-center justify-center rounded-lg px-4 py-2.5',
              'text-sm font-medium text-muted-foreground',
              'bg-secondary hover:bg-secondary/80 hover:text-foreground',
              'transition-all duration-200',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
              'disabled:pointer-events-none disabled:opacity-50'
            )}
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={isDeleting}
            className={cn(
              'flex-1 inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2.5',
              'text-sm font-semibold transition-all duration-200',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
              'disabled:pointer-events-none disabled:opacity-50',
              'bg-destructive text-destructive-foreground',
              'hover:bg-destructive/90',
              'shadow-sm hover:shadow-md hover:shadow-destructive/10'
            )}
          >
            {isDeleting ? (
              <>
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
                Deleting...
              </>
            ) : (
              <>
                <Trash2 className="h-4 w-4" />
                Delete
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  )

  // Draggable version
  if (draggable) {
    return (
      <DraggableModal
        open={open}
        onClose={handleCancel}
        initialWidth={400}
        minWidth={320}
        maxWidth={480}
        resizable={false}
        showDragHandle={true}
      >
        {content}
      </DraggableModal>
    )
  }

  // Standard Radix version
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        {content}
      </AlertDialogContent>
    </AlertDialog>
  )
}

// ============================================================================
// Exports
// ============================================================================

export {
  AlertDialog,
  AlertDialogPortal,
  AlertDialogOverlay,
  AlertDialogTrigger,
  AlertDialogContent,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogAction,
  AlertDialogCancel,
}
