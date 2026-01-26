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
 * - Real-time updates via WebSocket
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import { cn } from '@/lib/utils'
import {
  X,
  ExternalLink,
  Trash2,
  AlertCircle,
  Loader2,
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
  Wifi,
  WifiOff,
} from 'lucide-react'
import type { Task, TaskStatusValue as TaskStatus, TaskUpdate, TaskPriority, TaskType } from '@/hooks/use-queries'
import { useProjectMembersStore } from '@/stores/project-members-store'
import { useMembersStore } from '@/stores/members-store'
import { useAuthStore } from '@/stores/auth-store'
import { TaskStatusBadge } from './task-status-badge'
import { FileUpload } from '@/components/files/file-upload'
import { AttachmentList } from '@/components/files/attachment-list'
import { CommentThread } from '@/components/comments'
import { ChecklistPanel } from '@/components/checklists'
import {
  useWebSocket,
  MessageType,
  WebSocketClient,
  type TaskUpdateEventData,
} from '@/hooks/use-websocket'

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
  /**
   * Callback when task is updated externally via WebSocket
   */
  onExternalUpdate?: (task: Task) => void
  /**
   * Callback when task is deleted externally via WebSocket
   */
  onExternalDelete?: () => void
  /**
   * Whether to enable real-time updates
   */
  enableRealtime?: boolean
  /**
   * Whether the user can edit attachments and checklists
   * Controls visibility of add/edit/delete actions
   */
  canEdit?: boolean
  /**
   * Application ID for fetching application members for @mentions
   */
  applicationId?: string
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
  canEdit?: boolean
}

function TaskAttachmentsSection({ taskId, canEdit = true }: TaskAttachmentsSectionProps): JSX.Element {
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
        {isExpanded && canEdit && (
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
          {showUpload && canEdit && (
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
            allowDelete={canEdit}
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
  onExternalUpdate,
  onExternalDelete,
  enableRealtime = true,
  canEdit = true,
  applicationId,
}: TaskDetailProps): JSX.Element | null {
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const panelRef = useRef<HTMLDivElement>(null)
  const [externalUpdateNotice, setExternalUpdateNotice] = useState<string | null>(null)
  const [mentionSuggestions, setMentionSuggestions] = useState<Array<{ id: string; name: string; email?: string; avatar_url?: string }>>([])

  // Auth and project members for assignee selector
  const token = useAuthStore((s) => s.token)
  const { members: projectMembers, fetchMembers: fetchProjectMembers } = useProjectMembersStore()

  // Application members for @mentions (includes viewers)
  const { members: appMembers, fetchMembers: fetchAppMembers } = useMembersStore()

  // Fetch project members when panel opens (for assignee selector)
  useEffect(() => {
    if (isOpen && token && task.project_id) {
      fetchProjectMembers(token, task.project_id)
    }
  }, [isOpen, token, task.project_id, fetchProjectMembers])

  // Fetch application members when panel opens (for @mentions - includes viewers)
  useEffect(() => {
    if (isOpen && token && applicationId) {
      fetchAppMembers(token, applicationId)
    }
  }, [isOpen, token, applicationId, fetchAppMembers])

  // Handle @mention search - filter application members by query (includes viewers)
  // Search by display_name first, then email. Display name (or email username if no name)
  const handleMentionSearch = useCallback(
    (query: string) => {
      const lowerQuery = query.toLowerCase()
      const suggestions = appMembers
        .filter((member) => {
          if (!member.user) return false
          // Search by display_name first, then by email
          const name = member.user.display_name
          const email = member.user.email
          if (name && name.toLowerCase().includes(lowerQuery)) return true
          if (email && email.toLowerCase().includes(lowerQuery)) return true
          return false
        })
        .slice(0, 10) // Limit to 10 suggestions
        .map((member) => {
          // Use display_name if available, otherwise extract username from email
          const displayName = member.user?.display_name ||
            member.user?.email?.split('@')[0] ||
            'Unknown'
          return {
            id: member.user_id,
            name: displayName,
            email: member.user?.email,
            avatar_url: member.user?.avatar_url || undefined,
          }
        })
      setMentionSuggestions(suggestions)
    },
    [appMembers]
  )

  // WebSocket connection for real-time updates
  const { status, subscribe, joinRoom, leaveRoom } = useWebSocket()
  const callbackRefs = useRef({ onExternalUpdate, onExternalDelete })

  // Keep callback refs up to date
  useEffect(() => {
    callbackRefs.current = { onExternalUpdate, onExternalDelete }
  }, [onExternalUpdate, onExternalDelete])

  // Join task room and subscribe to updates when panel is open
  useEffect(() => {
    if (!isOpen || !enableRealtime || !status.isConnected || !task.project_id) {
      return
    }

    const roomId = WebSocketClient.getProjectRoom(task.project_id)
    joinRoom(roomId)

    // Subscribe to task updates
    const unsubscribeUpdated = subscribe<TaskUpdateEventData>(
      MessageType.TASK_UPDATED,
      (data) => {
        if (data.task_id === task.id) {
          setExternalUpdateNotice('Task was updated by another user')
          setTimeout(() => setExternalUpdateNotice(null), 3000)
          if (callbackRefs.current.onExternalUpdate && data.task) {
            callbackRefs.current.onExternalUpdate(data.task as unknown as Task)
          }
        }
      }
    )

    // Subscribe to task status changes
    const unsubscribeStatus = subscribe<TaskUpdateEventData>(
      MessageType.TASK_STATUS_CHANGED,
      (data) => {
        if (data.task_id === task.id) {
          setExternalUpdateNotice('Task status was changed by another user')
          setTimeout(() => setExternalUpdateNotice(null), 3000)
          if (callbackRefs.current.onExternalUpdate && data.task) {
            callbackRefs.current.onExternalUpdate(data.task as unknown as Task)
          }
        }
      }
    )

    // Subscribe to task deletions
    const unsubscribeDeleted = subscribe<TaskUpdateEventData>(
      MessageType.TASK_DELETED,
      (data) => {
        if (data.task_id === task.id) {
          setExternalUpdateNotice('Task was deleted by another user')
          if (callbackRefs.current.onExternalDelete) {
            callbackRefs.current.onExternalDelete()
          }
        }
      }
    )

    return () => {
      unsubscribeUpdated()
      unsubscribeStatus()
      unsubscribeDeleted()
      leaveRoom(roomId)
    }
  }, [isOpen, enableRealtime, status.isConnected, task.id, task.project_id, subscribe, joinRoom, leaveRoom])

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

  // Handle assignee change
  const handleAssigneeChange = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      if (onUpdate) {
        const value = e.target.value || null
        onUpdate({ assignee_id: value })
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
            {/* Real-time connection indicator */}
            {enableRealtime && (
              <div
                className={cn(
                  'flex items-center gap-1 text-xs',
                  status.isConnected ? 'text-green-500' : 'text-muted-foreground'
                )}
                title={status.isConnected ? 'Real-time updates active' : 'Not connected'}
              >
                {status.isConnected ? (
                  <Wifi className="h-3 w-3" />
                ) : (
                  <WifiOff className="h-3 w-3" />
                )}
              </div>
            )}
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

          {/* External Update Notice */}
          {externalUpdateNotice && (
            <div className="mx-4 mt-4 flex items-center gap-2 rounded-md border border-blue-500/50 bg-blue-500/10 p-3 text-sm text-blue-600 dark:text-blue-400 animate-in fade-in slide-in-from-top-2 duration-200">
              <Wifi className="h-4 w-4 flex-shrink-0" />
              <span>{externalUpdateNotice}</span>
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

            {/* Assignee */}
            <div className="space-y-2">
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide flex items-center gap-1">
                <User className="h-3.5 w-3.5" />
                Assignee
              </label>
              {onUpdate ? (
                <select
                  value={task.assignee_id || ''}
                  onChange={handleAssigneeChange}
                  disabled={isUpdating}
                  className={cn(
                    'w-full rounded-md border border-input bg-background px-3 py-2 text-foreground',
                    'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1',
                    'disabled:cursor-not-allowed disabled:opacity-50'
                  )}
                >
                  <option value="">Unassigned</option>
                  {projectMembers.map((member) => (
                    <option key={member.user_id} value={member.user_id}>
                      {member.user?.display_name || member.user?.email?.split('@')[0] || 'Unknown'} ({member.user?.email})
                    </option>
                  ))}
                </select>
              ) : (
                <div className="flex items-center gap-2 px-3 py-2 rounded-md border border-input bg-muted/50">
                  {task.assignee ? (
                    <>
                      <div className="h-6 w-6 rounded-full bg-primary/10 flex items-center justify-center">
                        <User className="h-3.5 w-3.5 text-primary" />
                      </div>
                      <div className="flex flex-col">
                        <span className="text-sm text-foreground">
                          {task.assignee.display_name || task.assignee.email.split('@')[0]}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {task.assignee.email}
                        </span>
                      </div>
                    </>
                  ) : (
                    <span className="text-sm text-muted-foreground italic">Unassigned</span>
                  )}
                </div>
              )}
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
                {task.reporter && (
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Reporter</span>
                    <div className="flex items-center gap-1.5">
                      <div className="h-5 w-5 rounded-full bg-primary/10 flex items-center justify-center">
                        <User className="h-3 w-3 text-primary" />
                      </div>
                      <span className="text-foreground">
                        {task.reporter.display_name || task.reporter.email.split('@')[0]}
                      </span>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Divider */}
            <div className="border-t border-border" />

            {/* Attachments Section */}
            <TaskAttachmentsSection taskId={task.id} canEdit={canEdit} />

            {/* Divider */}
            <div className="border-t border-border" />

            {/* Checklists Section */}
            <div className="space-y-2">
              <ChecklistPanel taskId={task.id} canEdit={canEdit} className="min-h-[200px]" />
            </div>

            {/* Divider */}
            <div className="border-t border-border" />

            {/* Comments Section */}
            <div className="space-y-2">
              <CommentThread
                taskId={task.id}
                className="min-h-[300px]"
                onMentionSearch={handleMentionSearch}
                mentionSuggestions={mentionSuggestions}
              />
            </div>
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
