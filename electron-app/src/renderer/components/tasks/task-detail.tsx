/**
 * Task Detail Component
 *
 * Slide-over panel for viewing and editing task details.
 * Provides a comprehensive view of task information with inline editing.
 *
 * Features:
 * - Slide-over panel animation
 * - Task header with key and type
 * - Status transitions with dropdown
 * - Priority selection
 * - Inline title and description editing
 * - Due date picker
 * - Story points input
 * - Assignee display
 * - Subtasks list (placeholder)
 * - Activity feed (placeholder)
 * - Delete confirmation
 * - Keyboard navigation (Escape to close)
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import { cn } from '@/lib/utils'
import {
  X,
  ExternalLink,
  Trash2,
  AlertCircle,
  Loader2,
  Clock,
  User,
  Calendar,
  Hash,
  FileText,
  Flag,
  CheckCircle2,
  Bug,
  Bookmark,
  Layers,
  ChevronRight,
  Paperclip,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'
import type { Task, TaskStatus, TaskUpdate, TaskPriority, TaskType } from '@/stores/tasks-store'
import { TaskStatusBadge } from './task-status-badge'
import { FileUpload } from '@/components/files/file-upload'
import { AttachmentList } from '@/components/files/attachment-list'

// ============================================================================
// Types
// ============================================================================

export interface TaskDetailProps {
  /**
   * Task to display
   */
  task: Task
  /**
   * Whether the panel is open
   */
  isOpen: boolean
  /**
   * Whether the task is being updated
   */
  isUpdating?: boolean
  /**
   * Whether the task is being deleted
   */
  isDeleting?: boolean
  /**
   * Error message
   */
  error?: string | null
  /**
   * Callback to close the panel
   */
  onClose: () => void
  /**
   * Callback when task is updated
   */
  onUpdate?: (data: TaskUpdate) => void
  /**
   * Callback when task is deleted
   */
  onDelete?: () => void
  /**
   * Callback to open in full page view
   */
  onOpenFull?: () => void
}

// ============================================================================
// Constants
// ============================================================================

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
 * Get task type icon
 */
function getTaskTypeIcon(taskType: TaskType): JSX.Element {
  switch (taskType) {
    case 'bug':
      return <Bug className="h-5 w-5 text-red-500" />
    case 'epic':
      return <Bookmark className="h-5 w-5 text-purple-500" />
    case 'story':
      return <Bookmark className="h-5 w-5 text-green-500" />
    case 'subtask':
      return <Layers className="h-5 w-5 text-blue-400" />
    case 'task':
    default:
      return <CheckCircle2 className="h-5 w-5 text-blue-500" />
  }
}

/**
 * Get task type label
 */
function getTaskTypeLabel(taskType: TaskType): string {
  switch (taskType) {
    case 'bug':
      return 'Bug'
    case 'epic':
      return 'Epic'
    case 'story':
      return 'Story'
    case 'subtask':
      return 'Subtask'
    case 'task':
    default:
      return 'Task'
  }
}

/**
 * Format date for display
 */
function formatDate(dateString: string): string {
  const date = new Date(dateString)
  return date.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
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
// Sub-Components
// ============================================================================

interface EditableFieldProps {
  label: string
  value: string
  placeholder?: string
  multiline?: boolean
  onSave: (value: string) => void
  disabled?: boolean
}

function EditableField({
  label,
  value,
  placeholder,
  multiline = false,
  onSave,
  disabled = false,
}: EditableFieldProps): JSX.Element {
  const [isEditing, setIsEditing] = useState(false)
  const [editValue, setEditValue] = useState(value)
  const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement>(null)

  // Update edit value when value changes
  useEffect(() => {
    setEditValue(value)
  }, [value])

  // Focus input when editing starts
  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus()
      // Move cursor to end
      if (inputRef.current instanceof HTMLInputElement) {
        inputRef.current.setSelectionRange(
          inputRef.current.value.length,
          inputRef.current.value.length
        )
      }
    }
  }, [isEditing])

  const handleSave = useCallback(() => {
    const trimmedValue = editValue.trim()
    if (trimmedValue !== value) {
      onSave(trimmedValue)
    }
    setIsEditing(false)
  }, [editValue, value, onSave])

  const handleCancel = useCallback(() => {
    setEditValue(value)
    setIsEditing(false)
  }, [value])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Escape') {
        handleCancel()
      } else if (e.key === 'Enter' && !multiline) {
        e.preventDefault()
        handleSave()
      } else if (e.key === 'Enter' && e.ctrlKey && multiline) {
        e.preventDefault()
        handleSave()
      }
    },
    [handleCancel, handleSave, multiline]
  )

  if (isEditing) {
    const inputClasses = cn(
      'w-full rounded-md border border-input bg-background px-3 py-2 text-foreground',
      'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1',
      'disabled:cursor-not-allowed disabled:opacity-50'
    )

    return (
      <div className="space-y-1">
        <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          {label}
        </label>
        {multiline ? (
          <textarea
            ref={inputRef as React.RefObject<HTMLTextAreaElement>}
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            onBlur={handleSave}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            disabled={disabled}
            rows={4}
            className={cn(inputClasses, 'resize-none')}
          />
        ) : (
          <input
            ref={inputRef as React.RefObject<HTMLInputElement>}
            type="text"
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            onBlur={handleSave}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            disabled={disabled}
            className={inputClasses}
          />
        )}
        <p className="text-xs text-muted-foreground">
          {multiline ? 'Ctrl+Enter to save, Escape to cancel' : 'Enter to save, Escape to cancel'}
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-1">
      <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
        {label}
      </label>
      <button
        onClick={() => setIsEditing(true)}
        disabled={disabled}
        className={cn(
          'w-full text-left rounded-md px-3 py-2 transition-colors',
          'hover:bg-accent/50',
          'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1',
          'disabled:cursor-not-allowed disabled:opacity-50',
          value ? 'text-foreground' : 'text-muted-foreground'
        )}
      >
        {multiline ? (
          <div className={cn('whitespace-pre-wrap', !value && 'italic')}>
            {value || placeholder}
          </div>
        ) : (
          <span className={!value ? 'italic' : ''}>{value || placeholder}</span>
        )}
      </button>
    </div>
  )
}

// ============================================================================
// Task Attachments Section Component
// ============================================================================

interface TaskAttachmentsSectionProps {
  taskId: string
}

function TaskAttachmentsSection({ taskId }: TaskAttachmentsSectionProps): JSX.Element {
  const [isExpanded, setIsExpanded] = useState(true)
  const [showUpload, setShowUpload] = useState(false)

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex items-center gap-2 text-xs font-medium text-muted-foreground uppercase tracking-wide hover:text-foreground transition-colors"
        >
          <Paperclip className="h-3.5 w-3.5" />
          Attachments
          {isExpanded ? (
            <ChevronUp className="h-3.5 w-3.5" />
          ) : (
            <ChevronDown className="h-3.5 w-3.5" />
          )}
        </button>
        {isExpanded && (
          <button
            onClick={() => setShowUpload(!showUpload)}
            className={cn(
              'text-xs font-medium transition-colors',
              showUpload
                ? 'text-primary'
                : 'text-muted-foreground hover:text-foreground'
            )}
          >
            {showUpload ? 'Hide upload' : 'Add file'}
          </button>
        )}
      </div>

      {/* Content */}
      {isExpanded && (
        <div className="space-y-4">
          {/* Upload area */}
          {showUpload && (
            <FileUpload
              entityType="task"
              entityId={taskId}
              onUploadComplete={() => {
                // Optionally hide upload after success
              }}
              className="mb-2"
            />
          )}

          {/* Attachment list */}
          <AttachmentList
            entityType="task"
            entityId={taskId}
            viewMode="list"
            showViewToggle={false}
            compact
          />
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Main Component
// ============================================================================

export function TaskDetail({
  task,
  isOpen,
  isUpdating = false,
  isDeleting = false,
  error,
  onClose,
  onUpdate,
  onDelete,
  onOpenFull,
}: TaskDetailProps): JSX.Element | null {
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const panelRef = useRef<HTMLDivElement>(null)

  // Close on escape key
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape' && !showDeleteConfirm) {
        onClose()
      }
    }

    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown)
      return () => document.removeEventListener('keydown', handleKeyDown)
    }
  }, [isOpen, onClose, showDeleteConfirm])

  // Handle status change
  const handleStatusChange = useCallback(
    (status: TaskStatus) => {
      if (onUpdate) {
        onUpdate({ status })
      }
    },
    [onUpdate]
  )

  // Handle priority change
  const handlePriorityChange = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      if (onUpdate) {
        onUpdate({ priority: e.target.value as TaskPriority })
      }
    },
    [onUpdate]
  )

  // Handle due date change
  const handleDueDateChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (onUpdate) {
        onUpdate({ due_date: e.target.value || null })
      }
    },
    [onUpdate]
  )

  // Handle story points change
  const handleStoryPointsChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (onUpdate) {
        const value = e.target.value ? parseInt(e.target.value, 10) : null
        if (value === null || (!isNaN(value) && value >= 0 && value <= 100)) {
          onUpdate({ story_points: value })
        }
      }
    },
    [onUpdate]
  )

  // Handle delete confirmation
  const handleDelete = useCallback(() => {
    if (onDelete) {
      onDelete()
    }
    setShowDeleteConfirm(false)
  }, [onDelete])

  if (!isOpen) {
    return null
  }

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/50 transition-opacity"
        onClick={onClose}
      />

      {/* Panel */}
      <div
        ref={panelRef}
        className={cn(
          'fixed right-0 top-0 z-50 h-full w-full max-w-xl overflow-hidden',
          'bg-background shadow-xl',
          'transform transition-transform duration-300 ease-out',
          isOpen ? 'translate-x-0' : 'translate-x-full'
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div className="flex items-center gap-3">
            {getTaskTypeIcon(task.task_type)}
            <div>
              <span className="text-sm font-medium text-muted-foreground font-mono">
                {task.task_key}
              </span>
              <span className="mx-2 text-muted-foreground">·</span>
              <span className="text-sm text-muted-foreground">
                {getTaskTypeLabel(task.task_type)}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-1">
            {onOpenFull && (
              <button
                onClick={onOpenFull}
                className={cn(
                  'rounded-md p-2 text-muted-foreground transition-colors',
                  'hover:bg-accent hover:text-accent-foreground',
                  'focus:outline-none focus:ring-2 focus:ring-ring'
                )}
                title="Open in full view"
              >
                <ExternalLink className="h-4 w-4" />
              </button>
            )}
            {onDelete && (
              <button
                onClick={() => setShowDeleteConfirm(true)}
                disabled={isDeleting}
                className={cn(
                  'rounded-md p-2 text-muted-foreground transition-colors',
                  'hover:bg-destructive/10 hover:text-destructive',
                  'focus:outline-none focus:ring-2 focus:ring-ring',
                  'disabled:pointer-events-none disabled:opacity-50'
                )}
                title="Delete task"
              >
                {isDeleting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Trash2 className="h-4 w-4" />
                )}
              </button>
            )}
            <button
              onClick={onClose}
              className={cn(
                'rounded-md p-2 text-muted-foreground transition-colors',
                'hover:bg-accent hover:text-accent-foreground',
                'focus:outline-none focus:ring-2 focus:ring-ring'
              )}
              title="Close"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="h-[calc(100%-60px)] overflow-y-auto">
          {/* Error Alert */}
          {error && (
            <div className="mx-4 mt-4 flex items-center gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
              <AlertCircle className="h-4 w-4 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Loading indicator */}
          {isUpdating && (
            <div className="absolute top-16 right-4 flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Saving...
            </div>
          )}

          <div className="p-4 space-y-6">
            {/* Status */}
            <div className="space-y-2">
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                Status
              </label>
              <TaskStatusBadge
                status={task.status}
                onStatusChange={onUpdate ? handleStatusChange : undefined}
                disabled={isUpdating}
                size="lg"
              />
            </div>

            {/* Title */}
            <EditableField
              label="Title"
              value={task.title}
              placeholder="Task title..."
              onSave={(value) => onUpdate?.({ title: value })}
              disabled={isUpdating || !onUpdate}
            />

            {/* Description */}
            <EditableField
              label="Description"
              value={task.description || ''}
              placeholder="Add a description..."
              multiline
              onSave={(value) => onUpdate?.({ description: value || null })}
              disabled={isUpdating || !onUpdate}
            />

            {/* Divider */}
            <div className="border-t border-border" />

            {/* Priority */}
            <div className="space-y-2">
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide flex items-center gap-1">
                <Flag className="h-3.5 w-3.5" />
                Priority
              </label>
              <select
                value={task.priority}
                onChange={handlePriorityChange}
                disabled={isUpdating || !onUpdate}
                className={cn(
                  'w-full rounded-md border border-input bg-background px-3 py-2 text-foreground',
                  'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1',
                  'disabled:cursor-not-allowed disabled:opacity-50'
                )}
              >
                {PRIORITIES.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Story Points */}
            <div className="space-y-2">
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide flex items-center gap-1">
                <Hash className="h-3.5 w-3.5" />
                Story Points
              </label>
              <input
                type="number"
                value={task.story_points ?? ''}
                onChange={handleStoryPointsChange}
                disabled={isUpdating || !onUpdate}
                placeholder="0"
                min="0"
                max="100"
                className={cn(
                  'w-full rounded-md border border-input bg-background px-3 py-2 text-foreground',
                  'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1',
                  'disabled:cursor-not-allowed disabled:opacity-50'
                )}
              />
            </div>

            {/* Due Date */}
            <div className="space-y-2">
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide flex items-center gap-1">
                <Calendar className="h-3.5 w-3.5" />
                Due Date
              </label>
              <input
                type="date"
                value={formatDateForInput(task.due_date)}
                onChange={handleDueDateChange}
                disabled={isUpdating || !onUpdate}
                className={cn(
                  'w-full rounded-md border border-input bg-background px-3 py-2 text-foreground',
                  'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1',
                  'disabled:cursor-not-allowed disabled:opacity-50'
                )}
              />
            </div>

            {/* Assignee (read-only for now) */}
            <div className="space-y-2">
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide flex items-center gap-1">
                <User className="h-3.5 w-3.5" />
                Assignee
              </label>
              <div className="flex items-center gap-2 px-3 py-2 rounded-md border border-input bg-muted/50">
                {task.assignee_id ? (
                  <>
                    <div className="h-6 w-6 rounded-full bg-primary/10 flex items-center justify-center">
                      <User className="h-3.5 w-3.5 text-primary" />
                    </div>
                    <span className="text-sm text-muted-foreground">Assigned</span>
                  </>
                ) : (
                  <span className="text-sm text-muted-foreground italic">Unassigned</span>
                )}
              </div>
            </div>

            {/* Divider */}
            <div className="border-t border-border" />

            {/* Subtasks Section (placeholder) */}
            {task.subtasks_count != null && task.subtasks_count > 0 && (
              <div className="space-y-2">
                <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide flex items-center gap-1">
                  <Layers className="h-3.5 w-3.5" />
                  Subtasks ({task.subtasks_count})
                </label>
                <button
                  className={cn(
                    'w-full flex items-center justify-between px-3 py-2 rounded-md',
                    'border border-input bg-muted/50 text-sm text-muted-foreground',
                    'hover:bg-accent transition-colors'
                  )}
                >
                  <span>View subtasks</span>
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            )}

            {/* Metadata */}
            <div className="space-y-2">
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide flex items-center gap-1">
                <FileText className="h-3.5 w-3.5" />
                Details
              </label>
              <div className="rounded-md border border-input bg-muted/30 p-3 space-y-2 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Created</span>
                  <span className="text-foreground">{formatDate(task.created_at)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Updated</span>
                  <span className="text-foreground">{formatDate(task.updated_at)}</span>
                </div>
                {task.reporter_id && (
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Reporter</span>
                    <div className="flex items-center gap-1.5">
                      <div className="h-5 w-5 rounded-full bg-primary/10 flex items-center justify-center">
                        <User className="h-3 w-3 text-primary" />
                      </div>
                      <span className="text-foreground">Reported</span>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Divider */}
            <div className="border-t border-border" />

            {/* Attachments Section */}
            <TaskAttachmentsSection taskId={task.id} />
          </div>
        </div>

        {/* Delete Confirmation Modal */}
        {showDeleteConfirm && (
          <>
            <div
              className="fixed inset-0 z-[60] bg-black/50"
              onClick={() => setShowDeleteConfirm(false)}
            />
            <div className="fixed left-1/2 top-1/2 z-[70] w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border bg-card p-6 shadow-xl">
              <div className="flex items-center gap-3 mb-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-destructive/10">
                  <AlertCircle className="h-5 w-5 text-destructive" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-foreground">Delete Task</h3>
                  <p className="text-sm text-muted-foreground">This action cannot be undone.</p>
                </div>
              </div>
              <p className="text-sm text-muted-foreground mb-6">
                Are you sure you want to delete <strong>{task.task_key}</strong>? This will
                permanently remove the task and all associated data.
              </p>
              <div className="flex items-center justify-end gap-3">
                <button
                  onClick={() => setShowDeleteConfirm(false)}
                  className={cn(
                    'rounded-md border border-input bg-background px-4 py-2 text-sm font-medium',
                    'hover:bg-accent hover:text-accent-foreground',
                    'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2'
                  )}
                >
                  Cancel
                </button>
                <button
                  onClick={handleDelete}
                  disabled={isDeleting}
                  className={cn(
                    'rounded-md bg-destructive px-4 py-2 text-sm font-medium text-destructive-foreground',
                    'hover:bg-destructive/90 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
                    'disabled:cursor-not-allowed disabled:opacity-50'
                  )}
                >
                  {isDeleting ? (
                    <span className="flex items-center gap-2">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Deleting...
                    </span>
                  ) : (
                    'Delete'
                  )}
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </>
  )
}

export default TaskDetail
