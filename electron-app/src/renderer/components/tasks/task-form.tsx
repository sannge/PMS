/**
 * Task Form Component
 *
 * Form for creating and editing tasks with validation.
 *
 * Features:
 * - Create and edit modes
 * - Field validation
 * - Task type selection
 * - Status selection
 * - Priority selection
 * - Due date picker
 * - Story points input
 * - Description textarea
 * - Loading and error states
 */

import { useState, useCallback, useEffect } from 'react'
import { cn } from '@/lib/utils'
import {
  CheckCircle2,
  Loader2,
  AlertCircle,
  X,
  Calendar,
  Bug,
  Bookmark,
  Layers,
  User,
} from 'lucide-react'
import type {
  Task,
  TaskCreate,
  TaskUpdate,
  TaskType,
  TaskStatusValue as TaskStatus,
  TaskPriority,
} from '@/hooks/use-queries'
import { getStatusOptions } from './task-status-badge'
import { RichTextEditor } from '@/components/editor/RichTextEditor'

// ============================================================================
// Assignee Types
// ============================================================================

export interface AssigneeOption {
  id: string
  display_name?: string | null
  email?: string
  avatar_url?: string | null
}

// ============================================================================
// Types
// ============================================================================

export interface TaskFormProps {
  /**
   * Task to edit (null for create mode)
   */
  task?: Task | null
  /**
   * Initial status when creating a task
   */
  initialStatus?: TaskStatus
  /**
   * Available assignees (project members)
   */
  assignees?: AssigneeOption[]
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
  onSubmit: (data: TaskCreate | TaskUpdate) => void
  /**
   * Callback when form is cancelled
   */
  onCancel: () => void
}

interface FormData {
  title: string
  description: string
  task_type: TaskType
  status: TaskStatus
  priority: TaskPriority
  story_points: string
  due_date: string
  assignee_id: string
}

interface FormErrors {
  title?: string
  description?: string
  story_points?: string
  due_date?: string
}

// ============================================================================
// Constants
// ============================================================================

const TASK_TYPES: { value: TaskType; label: string; icon: JSX.Element }[] = [
  { value: 'task', label: 'Task', icon: <CheckCircle2 className="h-4 w-4 text-blue-500" /> },
  { value: 'story', label: 'Story', icon: <Bookmark className="h-4 w-4 text-green-500" /> },
  { value: 'bug', label: 'Bug', icon: <Bug className="h-4 w-4 text-red-500" /> },
  { value: 'epic', label: 'Epic', icon: <Bookmark className="h-4 w-4 text-purple-500" /> },
  { value: 'subtask', label: 'Subtask', icon: <Layers className="h-4 w-4 text-blue-400" /> },
]

const PRIORITIES: { value: TaskPriority; label: string; color: string }[] = [
  { value: 'highest', label: 'Highest', color: 'text-red-500' },
  { value: 'high', label: 'High', color: 'text-orange-500' },
  { value: 'medium', label: 'Medium', color: 'text-yellow-500' },
  { value: 'low', label: 'Low', color: 'text-blue-500' },
  { value: 'lowest', label: 'Lowest', color: 'text-slate-400' },
]

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Validate form data
 */
function validateForm(data: FormData): FormErrors {
  const errors: FormErrors = {}

  if (!data.title.trim()) {
    errors.title = 'Title is required'
  } else if (data.title.length > 500) {
    errors.title = 'Title must be less than 500 characters'
  }

  if (data.story_points) {
    const points = parseInt(data.story_points, 10)
    if (isNaN(points) || points < 0) {
      errors.story_points = 'Story points must be a positive number'
    } else if (points > 100) {
      errors.story_points = 'Story points cannot exceed 100'
    }
  }

  if (data.due_date) {
    const date = new Date(data.due_date)
    if (isNaN(date.getTime())) {
      errors.due_date = 'Invalid date'
    }
  }

  return errors
}

/**
 * Format date for input
 */
function formatDateForInput(dateString: string | null): string {
  if (!dateString) return ''
  const date = new Date(dateString)
  if (isNaN(date.getTime())) return ''
  return date.toISOString().split('T')[0]
}

// ============================================================================
// Component
// ============================================================================

export function TaskForm({
  task,
  initialStatus = 'todo',
  assignees = [],
  isSubmitting = false,
  error,
  onSubmit,
  onCancel,
}: TaskFormProps): JSX.Element {
  const isEditMode = !!task

  // Form state
  const [formData, setFormData] = useState<FormData>({
    title: task?.title || '',
    description: task?.description || '',
    task_type: task?.task_type || 'task',
    status: task?.status ?? initialStatus ?? 'todo',
    priority: task?.priority || 'medium',
    story_points: task?.story_points?.toString() || '',
    due_date: formatDateForInput(task?.due_date || null),
    assignee_id: task?.assignee_id || '',
  })
  const [touched, setTouched] = useState<Record<string, boolean>>({})
  const [errors, setErrors] = useState<FormErrors>({})

  // Validate on data change
  useEffect(() => {
    setErrors(validateForm(formData))
  }, [formData])

  // Handle input change
  const handleChange = useCallback(
    (
      e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
    ) => {
      const { name, value } = e.target
      setFormData((prev) => ({ ...prev, [name]: value }))
    },
    []
  )

  // Handle blur
  const handleBlur = useCallback(
    (e: React.FocusEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
      setTouched((prev) => ({ ...prev, [e.target.name]: true }))
    },
    []
  )

  // Handle description change (for RichTextEditor)
  const handleDescriptionChange = useCallback((value: string) => {
    setFormData((prev) => ({ ...prev, description: value }))
  }, [])

  // Handle submit
  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault()

      // Mark all fields as touched
      setTouched({
        title: true,
        description: true,
        story_points: true,
        due_date: true,
      })

      // Validate
      const validationErrors = validateForm(formData)
      if (Object.keys(validationErrors).length > 0) {
        setErrors(validationErrors)
        return
      }

      // Prepare data
      const storyPoints = formData.story_points
        ? parseInt(formData.story_points, 10)
        : null

      if (isEditMode) {
        const updateData: TaskUpdate = {}
        if (formData.title !== task?.title) {
          updateData.title = formData.title.trim()
        }
        if (formData.description !== (task?.description || '')) {
          updateData.description = formData.description.trim() || null
        }
        if (formData.task_type !== task?.task_type) {
          updateData.task_type = formData.task_type
        }
        if (formData.status !== task?.status) {
          updateData.status = formData.status
        }
        if (formData.priority !== task?.priority) {
          updateData.priority = formData.priority
        }
        if (storyPoints !== task?.story_points) {
          updateData.story_points = storyPoints
        }
        if (formData.due_date !== formatDateForInput(task?.due_date || null)) {
          updateData.due_date = formData.due_date || null
        }
        // Include assignee_id if changed
        if (formData.assignee_id !== (task?.assignee_id || '')) {
          updateData.assignee_id = formData.assignee_id || null
        }
        onSubmit(updateData)
      } else {
        const createData: TaskCreate = {
          title: formData.title.trim(),
          description: formData.description.trim() || undefined,
          task_type: formData.task_type,
          status: formData.status,
          priority: formData.priority,
          story_points: storyPoints,
          due_date: formData.due_date || undefined,
          assignee_id: formData.assignee_id || undefined,
        }
        onSubmit(createData)
      }
    },
    [formData, isEditMode, task, onSubmit]
  )

  const statusOptions = getStatusOptions()

  return (
    <div className="rounded-xl border border-border/60 bg-gradient-to-b from-card to-card/95 shadow-2xl w-[800px] max-w-[95vw]">
      {/* Header - Refined with subtle gradient */}
      <div className="flex items-center justify-between border-b border-border/40 bg-muted/20 px-6 py-4">
        <div className="flex items-center gap-4">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary/10 text-primary shadow-sm ring-1 ring-primary/20">
            <CheckCircle2 className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-lg font-semibold tracking-tight text-foreground">
              {isEditMode ? 'Edit Task' : 'Create New Task'}
            </h2>
            <p className="text-sm text-muted-foreground">
              {isEditMode ? `Updating ${task?.task_key}` : 'Fill in the details below'}
            </p>
          </div>
        </div>
        <button
          onClick={onCancel}
          className={cn(
            'rounded-lg p-2.5 text-muted-foreground transition-all duration-200',
            'hover:bg-destructive/10 hover:text-destructive',
            'focus:outline-none focus:ring-2 focus:ring-ring'
          )}
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      {/* Form - Two column layout */}
      <form onSubmit={handleSubmit} className="p-6">
        {/* Error Alert */}
        {error && (
          <div className="mb-6 flex items-center gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
            <AlertCircle className="h-4 w-4 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <div className="grid grid-cols-[1fr_280px] gap-6">
          {/* Left Column - Main Content */}
          <div className="space-y-5">
            {/* Title Field - Prominent */}
            <div>
              <label htmlFor="title" className="block text-sm font-medium text-foreground mb-2">
                Task Title <span className="text-destructive">*</span>
              </label>
              <input
                type="text"
                id="title"
                name="title"
                value={formData.title}
                onChange={handleChange}
                onBlur={handleBlur}
                disabled={isSubmitting}
                placeholder="What needs to be done?"
                className={cn(
                  'w-full rounded-lg border bg-background px-4 py-3 text-base text-foreground placeholder:text-muted-foreground/60',
                  'focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary',
                  'disabled:cursor-not-allowed disabled:opacity-50',
                  'transition-all duration-200',
                  touched.title && errors.title ? 'border-destructive ring-destructive/20' : 'border-input'
                )}
              />
              {touched.title && errors.title && (
                <p className="mt-1.5 text-sm text-destructive flex items-center gap-1">
                  <AlertCircle className="h-3.5 w-3.5" />
                  {errors.title}
                </p>
              )}
            </div>

            {/* Description Field - Rich Text Editor - Prominent space */}
            <div className="flex-1">
              <label className="block text-sm font-medium text-foreground mb-2">
                Description
              </label>
              <RichTextEditor
                value={formData.description}
                onChange={handleDescriptionChange}
                placeholder="Add a detailed description with formatting, images, tables..."
                readOnly={isSubmitting}
                maxLength={102400}
                className="min-h-[280px] border-border"
              />
              <p className="mt-1.5 text-xs text-muted-foreground">
                Supports rich text, images, tables, and more
              </p>
            </div>
          </div>

          {/* Right Column - Metadata Panel */}
          <div className="space-y-4 rounded-xl border border-border/50 bg-muted/20 p-4">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground px-1">
              Task Properties
            </h3>

            {/* Task Type */}
            <div>
              <label htmlFor="task_type" className="block text-xs font-medium text-muted-foreground mb-1.5 px-1">
                Type
              </label>
              <select
                id="task_type"
                name="task_type"
                value={formData.task_type}
                onChange={handleChange}
                disabled={isSubmitting}
                className={cn(
                  'w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground',
                  'focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary',
                  'disabled:cursor-not-allowed disabled:opacity-50',
                  'transition-all duration-200'
                )}
              >
                {TASK_TYPES.map((type) => (
                  <option key={type.value} value={type.value}>
                    {type.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Status */}
            <div>
              <label htmlFor="status" className="block text-xs font-medium text-muted-foreground mb-1.5 px-1">
                Status
              </label>
              <select
                id="status"
                name="status"
                value={formData.status}
                onChange={handleChange}
                disabled={isSubmitting}
                className={cn(
                  'w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground',
                  'focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary',
                  'disabled:cursor-not-allowed disabled:opacity-50',
                  'transition-all duration-200'
                )}
              >
                {statusOptions.map((status) => (
                  <option key={status.value} value={status.value}>
                    {status.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Priority */}
            <div>
              <label htmlFor="priority" className="block text-xs font-medium text-muted-foreground mb-1.5 px-1">
                Priority
              </label>
              <select
                id="priority"
                name="priority"
                value={formData.priority}
                onChange={handleChange}
                disabled={isSubmitting}
                className={cn(
                  'w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground',
                  'focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary',
                  'disabled:cursor-not-allowed disabled:opacity-50',
                  'transition-all duration-200'
                )}
              >
                {PRIORITIES.map((priority) => (
                  <option key={priority.value} value={priority.value}>
                    {priority.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="border-t border-border/50 pt-4 mt-4" />

            {/* Story Points */}
            <div>
              <label htmlFor="story_points" className="block text-xs font-medium text-muted-foreground mb-1.5 px-1">
                Story Points
              </label>
              <input
                type="number"
                id="story_points"
                name="story_points"
                value={formData.story_points}
                onChange={handleChange}
                onBlur={handleBlur}
                disabled={isSubmitting}
                placeholder="0"
                min="0"
                max="100"
                className={cn(
                  'w-full rounded-lg border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/60',
                  'focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary',
                  'disabled:cursor-not-allowed disabled:opacity-50',
                  'transition-all duration-200',
                  touched.story_points && errors.story_points ? 'border-destructive' : 'border-input'
                )}
              />
              {touched.story_points && errors.story_points && (
                <p className="mt-1 text-xs text-destructive">{errors.story_points}</p>
              )}
            </div>

            {/* Due Date */}
            <div>
              <label htmlFor="due_date" className="block text-xs font-medium text-muted-foreground mb-1.5 px-1">
                Due Date
              </label>
              <div className="relative">
                <input
                  type="date"
                  id="due_date"
                  name="due_date"
                  value={formData.due_date}
                  onChange={handleChange}
                  onBlur={handleBlur}
                  disabled={isSubmitting}
                  className={cn(
                    'w-full rounded-lg border bg-background px-3 py-2 text-sm text-foreground',
                    'focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary',
                    'disabled:cursor-not-allowed disabled:opacity-50',
                    'transition-all duration-200',
                    touched.due_date && errors.due_date ? 'border-destructive' : 'border-input'
                  )}
                />
                <Calendar className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
              </div>
              {touched.due_date && errors.due_date && (
                <p className="mt-1 text-xs text-destructive">{errors.due_date}</p>
              )}
            </div>

            {/* Assignee */}
            <div>
              <label htmlFor="assignee_id" className="block text-xs font-medium text-muted-foreground mb-1.5 px-1">
                Assignee
              </label>
              <div className="relative">
                <select
                  id="assignee_id"
                  name="assignee_id"
                  value={formData.assignee_id}
                  onChange={handleChange}
                  disabled={isSubmitting || assignees.length === 0}
                  className={cn(
                    'w-full rounded-lg border border-input bg-background px-3 py-2 pr-8 text-sm text-foreground',
                    'focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary',
                    'disabled:cursor-not-allowed disabled:opacity-50',
                    'appearance-none transition-all duration-200'
                  )}
                >
                  <option value="">Unassigned</option>
                  {assignees.map((assignee) => (
                    <option key={assignee.id} value={assignee.id}>
                      {assignee.display_name || assignee.email || 'Unknown user'}
                    </option>
                  ))}
                </select>
                <User className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
              </div>
              {assignees.length === 0 && (
                <p className="mt-1 text-xs text-muted-foreground/70">No team members available</p>
              )}
            </div>
          </div>
        </div>

        {/* Actions - Full width footer */}
        <div className="flex items-center justify-end gap-3 pt-6 mt-6 border-t border-border/40">
          <button
            type="button"
            onClick={onCancel}
            disabled={isSubmitting}
            className={cn(
              'rounded-lg border border-input bg-background px-5 py-2.5 text-sm font-medium text-foreground',
              'hover:bg-muted hover:border-border',
              'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
              'disabled:cursor-not-allowed disabled:opacity-50',
              'transition-all duration-200'
            )}
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={isSubmitting || Object.keys(errors).length > 0}
            className={cn(
              'rounded-lg bg-primary px-6 py-2.5 text-sm font-medium text-primary-foreground shadow-sm',
              'hover:bg-primary/90 hover:shadow-md',
              'focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2',
              'disabled:cursor-not-allowed disabled:opacity-50',
              'transition-all duration-200'
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
              'Create Task'
            )}
          </button>
        </div>
      </form>
    </div>
  )
}

export default TaskForm
