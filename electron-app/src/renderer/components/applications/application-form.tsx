/**
 * Application Form Component
 *
 * Form for creating and editing applications.
 * Handles validation and submission.
 *
 * Features:
 * - Create and edit modes
 * - Form validation
 * - Loading states
 * - Error handling
 */

import { useState, useCallback, FormEvent, ChangeEvent, useEffect } from 'react'
import { cn } from '@/lib/utils'
import {
  Loader2,
  X,
  FolderKanban,
  AlertCircle,
} from 'lucide-react'
import type { Application, ApplicationCreate, ApplicationUpdate } from '@/hooks/use-queries'

// ============================================================================
// Types
// ============================================================================

export interface ApplicationFormProps {
  /**
   * Application to edit (if in edit mode)
   */
  application?: Application | null
  /**
   * Whether the form is submitting
   */
  isSubmitting?: boolean
  /**
   * Error message to display
   */
  error?: string | null
  /**
   * Callback when form is submitted
   */
  onSubmit: (data: ApplicationCreate | ApplicationUpdate) => void
  /**
   * Callback when form is cancelled
   */
  onCancel?: () => void
  /**
   * Additional CSS classes
   */
  className?: string
}

interface FormErrors {
  name?: string
  description?: string
}

// ============================================================================
// Validation
// ============================================================================

function validateName(name: string): string | undefined {
  const trimmed = name.trim()
  if (!trimmed) {
    return 'Name is required'
  }
  if (trimmed.length > 255) {
    return 'Name must be 255 characters or less'
  }
  return undefined
}

function validateDescription(description: string): string | undefined {
  if (description.length > 2000) {
    return 'Description must be 2000 characters or less'
  }
  return undefined
}

// ============================================================================
// Component
// ============================================================================

export function ApplicationForm({
  application,
  isSubmitting = false,
  error,
  onSubmit,
  onCancel,
  className,
}: ApplicationFormProps): JSX.Element {
  const isEditMode = !!application

  // Form state
  const [name, setName] = useState(application?.name || '')
  const [description, setDescription] = useState(application?.description || '')
  const [formErrors, setFormErrors] = useState<FormErrors>({})
  const [touched, setTouched] = useState<Record<string, boolean>>({})

  // Reset form when application changes
  useEffect(() => {
    if (application) {
      setName(application.name)
      setDescription(application.description || '')
      setFormErrors({})
      setTouched({})
    }
  }, [application])

  // Handle name change
  const handleNameChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      const value = e.target.value
      setName(value)
      if (touched.name) {
        setFormErrors((prev) => ({ ...prev, name: validateName(value) }))
      }
    },
    [touched.name]
  )

  // Handle description change
  const handleDescriptionChange = useCallback(
    (e: ChangeEvent<HTMLTextAreaElement>) => {
      const value = e.target.value
      setDescription(value)
      if (touched.description) {
        setFormErrors((prev) => ({ ...prev, description: validateDescription(value) }))
      }
    },
    [touched.description]
  )

  // Handle field blur for validation
  const handleBlur = useCallback((field: 'name' | 'description') => {
    setTouched((prev) => ({ ...prev, [field]: true }))
    if (field === 'name') {
      setFormErrors((prev) => ({ ...prev, name: validateName(name) }))
    } else {
      setFormErrors((prev) => ({ ...prev, description: validateDescription(description) }))
    }
  }, [name, description])

  // Handle form submission
  const handleSubmit = useCallback(
    (e: FormEvent) => {
      e.preventDefault()

      // Validate all fields
      const nameError = validateName(name)
      const descriptionError = validateDescription(description)

      setFormErrors({ name: nameError, description: descriptionError })
      setTouched({ name: true, description: true })

      // Don't submit if there are validation errors
      if (nameError || descriptionError) {
        return
      }

      const trimmedName = name.trim()
      const trimmedDescription = description.trim()

      if (isEditMode) {
        // For updates, only include changed fields
        const updateData: ApplicationUpdate = {}
        if (trimmedName !== application?.name) {
          updateData.name = trimmedName
        }
        if (trimmedDescription !== (application?.description || '')) {
          updateData.description = trimmedDescription || null
        }
        onSubmit(updateData)
      } else {
        // For create, include all fields
        const createData: ApplicationCreate = {
          name: trimmedName,
          description: trimmedDescription || null,
        }
        onSubmit(createData)
      }
    },
    [name, description, isEditMode, application, onSubmit]
  )

  return (
    <div className={cn('rounded-lg border border-border bg-card', className)}>
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <FolderKanban className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-foreground">
              {isEditMode ? 'Edit Application' : 'Create Application'}
            </h2>
            <p className="text-sm text-muted-foreground">
              {isEditMode
                ? 'Update the application details below'
                : 'Fill in the details to create a new application'}
            </p>
          </div>
        </div>
        {onCancel && (
          <button
            onClick={onCancel}
            disabled={isSubmitting}
            className={cn(
              'rounded-md p-2 text-muted-foreground transition-colors',
              'hover:bg-accent hover:text-accent-foreground',
              'focus:outline-none focus:ring-2 focus:ring-ring',
              'disabled:pointer-events-none disabled:opacity-50'
            )}
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        )}
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="p-6 space-y-4">
        {/* API Error Message */}
        {error && (
          <div className="flex items-center gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
            <AlertCircle className="h-4 w-4 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Name Field */}
        <div className="space-y-2">
          <label
            htmlFor="app-name"
            className="text-sm font-medium text-foreground"
          >
            Name <span className="text-destructive">*</span>
          </label>
          <input
            id="app-name"
            type="text"
            value={name}
            onChange={handleNameChange}
            onBlur={() => handleBlur('name')}
            placeholder="Enter application name"
            disabled={isSubmitting}
            autoFocus
            className={cn(
              'w-full rounded-md border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground',
              'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background',
              'disabled:cursor-not-allowed disabled:opacity-50',
              formErrors.name && touched.name
                ? 'border-destructive focus:ring-destructive'
                : 'border-input'
            )}
          />
          {formErrors.name && touched.name && (
            <p className="text-xs text-destructive">{formErrors.name}</p>
          )}
        </div>

        {/* Description Field */}
        <div className="space-y-2">
          <label
            htmlFor="app-description"
            className="text-sm font-medium text-foreground"
          >
            Description
          </label>
          <textarea
            id="app-description"
            value={description}
            onChange={handleDescriptionChange}
            onBlur={() => handleBlur('description')}
            placeholder="Enter a description for this application (optional)"
            disabled={isSubmitting}
            rows={4}
            className={cn(
              'w-full rounded-md border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground resize-none',
              'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background',
              'disabled:cursor-not-allowed disabled:opacity-50',
              formErrors.description && touched.description
                ? 'border-destructive focus:ring-destructive'
                : 'border-input'
            )}
          />
          <div className="flex items-center justify-between">
            {formErrors.description && touched.description ? (
              <p className="text-xs text-destructive">{formErrors.description}</p>
            ) : (
              <span />
            )}
            <span className="text-xs text-muted-foreground">
              {description.length}/2000
            </span>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center justify-end gap-3 pt-4 border-t border-border">
          {onCancel && (
            <button
              type="button"
              onClick={onCancel}
              disabled={isSubmitting}
              className={cn(
                'rounded-md border border-input bg-background px-4 py-2 text-sm font-medium text-foreground',
                'hover:bg-accent hover:text-accent-foreground',
                'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
                'disabled:cursor-not-allowed disabled:opacity-50',
                'transition-colors duration-200'
              )}
            >
              Cancel
            </button>
          )}
          <button
            type="submit"
            disabled={isSubmitting}
            className={cn(
              'rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground',
              'hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
              'disabled:cursor-not-allowed disabled:opacity-50',
              'transition-colors duration-200'
            )}
          >
            {isSubmitting ? (
              <span className="flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" />
                {isEditMode ? 'Saving...' : 'Creating...'}
              </span>
            ) : isEditMode ? (
              'Save Changes'
            ) : (
              'Create Application'
            )}
          </button>
        </div>
      </form>
    </div>
  )
}

export default ApplicationForm
