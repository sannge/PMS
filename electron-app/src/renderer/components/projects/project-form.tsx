/**
 * Project Form Component
 *
 * Form for creating and editing projects with validation.
 *
 * Features:
 * - Create and edit modes
 * - Field validation
 * - Project key generation from name
 * - Project type selection
 * - Loading and error states
 */

import { useState, useCallback, useEffect } from 'react'
import { cn } from '@/lib/utils'
import {
  LayoutDashboard,
  Loader2,
  AlertCircle,
  X,
  Columns,
  RefreshCw,
} from 'lucide-react'
import type { Project, ProjectCreate, ProjectUpdate, ProjectType } from '@/hooks/use-queries'

// ============================================================================
// Types
// ============================================================================

export interface ProjectFormProps {
  /**
   * Project to edit (null for create mode)
   */
  project?: Project | null
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
  onSubmit: (data: ProjectCreate | ProjectUpdate) => void
  /**
   * Callback when form is cancelled
   */
  onCancel: () => void
}

interface FormData {
  name: string
  key: string
  description: string
  project_type: ProjectType
}

interface FormErrors {
  name?: string
  key?: string
  description?: string
  project_type?: string
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Generate a project key from the name
 */
function generateKey(name: string): string {
  return name
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, '')
    .slice(0, 10)
}

/**
 * Validate form data
 */
function validateForm(data: FormData): FormErrors {
  const errors: FormErrors = {}

  if (!data.name.trim()) {
    errors.name = 'Name is required'
  } else if (data.name.length > 255) {
    errors.name = 'Name must be less than 255 characters'
  }

  if (!data.key.trim()) {
    errors.key = 'Key is required'
  } else if (!/^[A-Z][A-Z0-9]*$/.test(data.key)) {
    errors.key = 'Key must start with a letter and contain only uppercase letters and numbers'
  } else if (data.key.length > 10) {
    errors.key = 'Key must be 10 characters or less'
  }

  return errors
}

// ============================================================================
// Component
// ============================================================================

export function ProjectForm({
  project,
  isSubmitting = false,
  error,
  onSubmit,
  onCancel,
}: ProjectFormProps): JSX.Element {
  const isEditMode = !!project

  // Form state
  const [formData, setFormData] = useState<FormData>({
    name: project?.name || '',
    key: project?.key || '',
    description: project?.description || '',
    project_type: project?.project_type || 'kanban',
  })
  const [touched, setTouched] = useState<Record<string, boolean>>({})
  const [errors, setErrors] = useState<FormErrors>({})
  const [autoGenerateKey, setAutoGenerateKey] = useState(!isEditMode)

  // Validate on data change
  useEffect(() => {
    setErrors(validateForm(formData))
  }, [formData])

  // Update form data when project prop changes (e.g., via WebSocket real-time update)
  // Use specific fields as dependencies to avoid unnecessary updates
  useEffect(() => {
    if (project) {
      setFormData({
        name: project.name || '',
        key: project.key || '',
        description: project.description || '',
        project_type: project.project_type || 'kanban',
      })
    }
  }, [project?.name, project?.key, project?.description, project?.project_type])

  // Auto-generate key from name in create mode
  useEffect(() => {
    if (autoGenerateKey && !isEditMode && formData.name) {
      const generatedKey = generateKey(formData.name)
      if (generatedKey) {
        setFormData((prev) => ({ ...prev, key: generatedKey }))
      }
    }
  }, [formData.name, autoGenerateKey, isEditMode])

  // Handle input change
  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
      const { name, value } = e.target
      setFormData((prev) => ({ ...prev, [name]: value }))

      // Stop auto-generating key if user manually edits it
      if (name === 'key') {
        setAutoGenerateKey(false)
      }
    },
    []
  )

  // Handle project type change
  const handleProjectTypeChange = useCallback((type: ProjectType) => {
    setFormData((prev) => ({ ...prev, project_type: type }))
  }, [])

  // Handle blur
  const handleBlur = useCallback((e: React.FocusEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setTouched((prev) => ({ ...prev, [e.target.name]: true }))
  }, [])

  // Handle submit
  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault()

      // Mark all fields as touched
      setTouched({
        name: true,
        key: true,
        description: true,
        project_type: true,
      })

      // Validate
      const validationErrors = validateForm(formData)
      if (Object.keys(validationErrors).length > 0) {
        setErrors(validationErrors)
        return
      }

      // Submit
      if (isEditMode) {
        const updateData: ProjectUpdate = {}
        if (formData.name !== project?.name) {
          updateData.name = formData.name.trim()
        }
        if (formData.description !== (project?.description || '')) {
          updateData.description = formData.description.trim() || null
        }
        if (formData.project_type !== project?.project_type) {
          updateData.project_type = formData.project_type
        }
        onSubmit(updateData)
      } else {
        const createData: ProjectCreate = {
          name: formData.name.trim(),
          key: formData.key.trim().toUpperCase(),
          description: formData.description.trim() || undefined,
          project_type: formData.project_type,
        }
        onSubmit(createData)
      }
    },
    [formData, isEditMode, project, onSubmit]
  )

  return (
    <div className="rounded-lg border border-border bg-card shadow-lg">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border p-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <LayoutDashboard className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-foreground">
              {isEditMode ? 'Edit Project' : 'New Project'}
            </h2>
            <p className="text-sm text-muted-foreground">
              {isEditMode
                ? 'Update project details'
                : 'Create a new project to organize tasks'}
            </p>
          </div>
        </div>
        <button
          onClick={onCancel}
          className={cn(
            'rounded-md p-2 text-muted-foreground transition-colors',
            'hover:bg-accent hover:text-accent-foreground',
            'focus:outline-none focus:ring-2 focus:ring-ring'
          )}
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      {/* Form */}
      <form onSubmit={handleSubmit} className="p-4 space-y-4">
        {/* Error Alert */}
        {error && (
          <div className="flex items-center gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
            <AlertCircle className="h-4 w-4 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Name Field */}
        <div>
          <label htmlFor="name" className="block text-sm font-medium text-foreground mb-1.5">
            Name <span className="text-destructive">*</span>
          </label>
          <input
            type="text"
            id="name"
            name="name"
            value={formData.name}
            onChange={handleChange}
            onBlur={handleBlur}
            disabled={isSubmitting}
            placeholder="Website Redesign"
            className={cn(
              'w-full rounded-md border bg-background px-3 py-2 text-foreground placeholder:text-muted-foreground',
              'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background',
              'disabled:cursor-not-allowed disabled:opacity-50',
              touched.name && errors.name
                ? 'border-destructive'
                : 'border-input'
            )}
          />
          {touched.name && errors.name && (
            <p className="mt-1 text-sm text-destructive">{errors.name}</p>
          )}
        </div>

        {/* Key Field */}
        <div>
          <label htmlFor="key" className="block text-sm font-medium text-foreground mb-1.5">
            Key <span className="text-destructive">*</span>
          </label>
          <input
            type="text"
            id="key"
            name="key"
            value={formData.key}
            onChange={handleChange}
            onBlur={handleBlur}
            disabled={isSubmitting || isEditMode}
            placeholder="WEB"
            className={cn(
              'w-full rounded-md border bg-background px-3 py-2 text-foreground placeholder:text-muted-foreground font-mono',
              'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background',
              'disabled:cursor-not-allowed disabled:opacity-50',
              touched.key && errors.key
                ? 'border-destructive'
                : 'border-input',
              isEditMode && 'bg-muted'
            )}
          />
          {touched.key && errors.key && (
            <p className="mt-1 text-sm text-destructive">{errors.key}</p>
          )}
          {!isEditMode && (
            <p className="mt-1 text-xs text-muted-foreground">
              Project key is used for task IDs (e.g., WEB-123). Cannot be changed after creation.
            </p>
          )}
        </div>

        {/* Description Field */}
        <div>
          <label htmlFor="description" className="block text-sm font-medium text-foreground mb-1.5">
            Description
          </label>
          <textarea
            id="description"
            name="description"
            value={formData.description}
            onChange={handleChange}
            onBlur={handleBlur}
            disabled={isSubmitting}
            placeholder="Describe the project..."
            rows={3}
            className={cn(
              'w-full rounded-md border border-input bg-background px-3 py-2 text-foreground placeholder:text-muted-foreground',
              'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background',
              'disabled:cursor-not-allowed disabled:opacity-50',
              'resize-none'
            )}
          />
        </div>

        {/* Project Type Field */}
        <div>
          <label className="block text-sm font-medium text-foreground mb-1.5">
            Project Type
          </label>
          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => handleProjectTypeChange('kanban')}
              disabled={isSubmitting}
              className={cn(
                'flex flex-1 items-center gap-3 rounded-lg border p-4 transition-colors',
                'focus:outline-none focus:ring-2 focus:ring-ring',
                formData.project_type === 'kanban'
                  ? 'border-primary bg-primary/5'
                  : 'border-border hover:border-primary/50',
                'disabled:cursor-not-allowed disabled:opacity-50'
              )}
            >
              <div className={cn(
                'flex h-10 w-10 items-center justify-center rounded-lg',
                formData.project_type === 'kanban'
                  ? 'bg-primary/10 text-primary'
                  : 'bg-muted text-muted-foreground'
              )}>
                <Columns className="h-5 w-5" />
              </div>
              <div className="text-left">
                <p className="font-medium text-foreground">Kanban</p>
                <p className="text-sm text-muted-foreground">Continuous flow</p>
              </div>
            </button>

            <button
              type="button"
              onClick={() => handleProjectTypeChange('scrum')}
              disabled={isSubmitting}
              className={cn(
                'flex flex-1 items-center gap-3 rounded-lg border p-4 transition-colors',
                'focus:outline-none focus:ring-2 focus:ring-ring',
                formData.project_type === 'scrum'
                  ? 'border-primary bg-primary/5'
                  : 'border-border hover:border-primary/50',
                'disabled:cursor-not-allowed disabled:opacity-50'
              )}
            >
              <div className={cn(
                'flex h-10 w-10 items-center justify-center rounded-lg',
                formData.project_type === 'scrum'
                  ? 'bg-primary/10 text-primary'
                  : 'bg-muted text-muted-foreground'
              )}>
                <RefreshCw className="h-5 w-5" />
              </div>
              <div className="text-left">
                <p className="font-medium text-foreground">Scrum</p>
                <p className="text-sm text-muted-foreground">Sprint-based</p>
              </div>
            </button>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center justify-end gap-3 pt-4 border-t border-border">
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
          <button
            type="submit"
            disabled={isSubmitting || Object.keys(errors).length > 0}
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
              'Create Project'
            )}
          </button>
        </div>
      </form>
    </div>
  )
}

export default ProjectForm
