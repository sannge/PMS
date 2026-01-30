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
  Pencil,
  Save,
  RotateCcw,
} from 'lucide-react'
import type { Task, TaskStatusValue as TaskStatus, TaskUpdate, TaskPriority, TaskType } from '@/hooks/use-queries'
import { useProjectMembers, useAppMembers } from '@/hooks/use-members'
import { useAuthStore } from '@/stores/auth-store'
import { TaskStatusBadge } from './task-status-badge'
import { FileUpload } from '@/components/files/file-upload'
import { AttachmentList } from '@/components/files/attachment-list'
import { CommentThread } from '@/components/comments'
import { ChecklistPanel } from '@/components/checklists'
import { RichTextEditor } from '@/components/editor/RichTextEditor'
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
  /**
   * Callback to revert task selection when user chooses to keep editing
   * unsaved description changes instead of switching tasks.
   * Called with the current task so parent can restore selection.
   */
  onRevertTaskSelection?: (task: Task) => void
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
  onRevertTaskSelection,
}: TaskDetailProps): JSX.Element | null {
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [assigneeError, setAssigneeError] = useState<string | null>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const [externalUpdateNotice, setExternalUpdateNotice] = useState<string | null>(null)
  const [mentionSuggestions, setMentionSuggestions] = useState<Array<{ id: string; name: string; email?: string; avatar_url?: string }>>([])

  // Local state for description - only save on explicit action
  const [localDescription, setLocalDescription] = useState(task.description || '')
  const [hasDescriptionChanges, setHasDescriptionChanges] = useState(false)
  const [isEditingDescription, setIsEditingDescription] = useState(false)
  const [editorError, setEditorError] = useState<string | null>(null)
  const [pendingTask, setPendingTask] = useState<Task | null>(null)
  const [showUnsavedDialog, setShowUnsavedDialog] = useState(false)

  // Track previous task id to detect task switches
  const prevTaskIdRef = useRef(task.id)

  // Sync local description when task changes from external source
  useEffect(() => {
    const isTaskSwitch = prevTaskIdRef.current !== task.id
    prevTaskIdRef.current = task.id

    if (isTaskSwitch && hasDescriptionChanges && isEditingDescription) {
      // Task switched while editing - show unsaved dialog
      setPendingTask(task)
      setShowUnsavedDialog(true)
      return
    }

    setLocalDescription(task.description || '')
    setHasDescriptionChanges(false)
    if (isTaskSwitch) {
      setIsEditingDescription(false)
    }
  }, [task.description, task.id]) // eslint-disable-line react-hooks/exhaustive-deps

  // Clear assignee error when task changes or status becomes todo
  useEffect(() => {
    setAssigneeError(null)
  }, [task.id, task.status])

  // Auto-dismiss editor error after 5 seconds
  useEffect(() => {
    if (editorError) {
      const timer = setTimeout(() => setEditorError(null), 5000)
      return () => clearTimeout(timer)
    }
  }, [editorError])

  // Check if task is done or archived (locked for editing except status change)
  const isDone = task.status === 'done'
  const isArchived = task.archived_at !== null
  const isReadOnly = isDone || isArchived

  // Auth
  const token = useAuthStore((s) => s.token)

  // Project members for assignee selector (auto-fetches when enabled)
  const { data: projectMembers = [] } = useProjectMembers(isOpen ? task.project_id : undefined)

  // Application members for @mentions (includes viewers) (auto-fetches when enabled)
  const { data: appMembersData = [] } = useAppMembers(isOpen ? applicationId : undefined)

  // Handle @mention search - filter application members by query (includes viewers)
  // Search by display_name first, then email. Display name (or email username if no name)
  const handleMentionSearch = useCallback(
    (query: string) => {
      const lowerQuery = query.toLowerCase()
      const suggestions = appMembersData
        .filter((member) => {
          // Search by display_name first, then by email
          const name = member.user_display_name
          const email = member.user_email
          if (name && name.toLowerCase().includes(lowerQuery)) return true
          if (email && email.toLowerCase().includes(lowerQuery)) return true
          return false
        })
        .slice(0, 10) // Limit to 10 suggestions
        .map((member) => {
          // Use display_name if available, otherwise extract username from email
          const displayName = member.user_display_name ||
            member.user_email?.split('@')[0] ||
            'Unknown'
          return {
            id: member.user_id,
            name: displayName,
            email: member.user_email,
            avatar_url: member.user_avatar_url || undefined,
          }
        })
      setMentionSuggestions(suggestions)
    },
    [appMembersData]
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
        // Prevent unassigning if task is not in todo status
        if (!value && task.status !== 'todo') {
          setAssigneeError("Cannot unassign a task that is not in 'Todo' status. Move the task back to 'Todo' first.")
          return
        }
        setAssigneeError(null)
        onUpdate({ assignee_id: value })
      }
    },
    [onUpdate, task.status]
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

      {/* Panel - Wide with split layout for rich text editing */}
      <div
        ref={panelRef}
        className={cn(
          'fixed right-0 top-0 z-50 h-full w-full max-w-4xl overflow-hidden',
          'bg-gradient-to-b from-background to-background/98 shadow-2xl',
          'transform transition-transform duration-300 ease-out',
          isOpen ? 'translate-x-0' : 'translate-x-full'
        )}
      >
        {/* Header - Refined */}
        <div className="flex items-center justify-between border-b border-border/50 bg-muted/30 px-5 py-3.5">
          <div className="flex items-center gap-4">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-background shadow-sm ring-1 ring-border/50">
              {getTaskTypeIcon(task.task_type)}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-foreground font-mono tracking-tight">
                  {task.task_key}
                </span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
                  {getTaskTypeLabel(task.task_type)}
                </span>
              </div>
              {/* Real-time connection indicator */}
              {enableRealtime && (
                <div
                  className={cn(
                    'flex items-center gap-1.5 text-xs mt-0.5',
                    status.isConnected ? 'text-green-600' : 'text-muted-foreground'
                  )}
                  title={status.isConnected ? 'Real-time updates active' : 'Not connected'}
                >
                  {status.isConnected ? (
                    <>
                      <Wifi className="h-3 w-3" />
                      <span>Live</span>
                    </>
                  ) : (
                    <>
                      <WifiOff className="h-3 w-3" />
                      <span>Offline</span>
                    </>
                  )}
                </div>
              )}
            </div>
          </div>

          <div className="flex items-center gap-1">
            {onOpenFull && (
              <button
                onClick={onOpenFull}
                className={cn(
                  'rounded-lg p-2.5 text-muted-foreground transition-all duration-200',
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
                  'rounded-lg p-2.5 text-muted-foreground transition-all duration-200',
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
                'rounded-lg p-2.5 text-muted-foreground transition-all duration-200',
                'hover:bg-destructive/10 hover:text-destructive',
                'focus:outline-none focus:ring-2 focus:ring-ring'
              )}
              title="Close"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Content - Split Layout */}
        <div className="h-[calc(100%-60px)] overflow-y-auto">
          {/* Error Alert */}
          {error && (
            <div className="mx-5 mt-4 flex items-center gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              <AlertCircle className="h-4 w-4 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* External Update Notice */}
          {externalUpdateNotice && (
            <div className="mx-5 mt-4 flex items-center gap-3 rounded-lg border border-blue-500/30 bg-blue-500/5 px-4 py-3 text-sm text-blue-600 dark:text-blue-400 animate-in fade-in slide-in-from-top-2 duration-200">
              <Wifi className="h-4 w-4 flex-shrink-0" />
              <span>{externalUpdateNotice}</span>
            </div>
          )}

          {/* Loading indicator */}
          {isUpdating && (
            <div className="absolute top-16 right-5 flex items-center gap-2 px-3 py-1.5 rounded-full bg-primary/10 text-sm text-primary">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              <span className="text-xs font-medium">Saving...</span>
            </div>
          )}

          <div className="p-5 space-y-6">
            {/* Status and Title Section */}
            <div className="space-y-4">
              {/* Status Badge - Prominent (disabled for archived tasks) */}
              <div className="flex items-center gap-3">
                <TaskStatusBadge
                  status={task.status}
                  onStatusChange={onUpdate && !isArchived ? handleStatusChange : undefined}
                  disabled={isUpdating || isArchived}
                  size="lg"
                />
                {isReadOnly && (
                  <span className="text-xs text-muted-foreground bg-muted px-2 py-1 rounded">
                    {isArchived ? 'Archived - Status locked' : 'Read-only'}
                  </span>
                )}
              </div>

              {/* Title - Large and prominent */}
              <EditableField
                label="Title"
                value={task.title}
                placeholder="Task title..."
                onSave={(value) => onUpdate?.({ title: value })}
                disabled={isUpdating || !onUpdate || isReadOnly}
              />
            </div>

            {/* Properties Row - Compact horizontal layout */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 p-4 rounded-lg border border-border/50 bg-muted/20">
              {/* Priority */}
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground flex items-center gap-1">
                  <Flag className="h-3 w-3" />
                  Priority
                </label>
                <select
                  value={task.priority}
                  onChange={handlePriorityChange}
                  disabled={isUpdating || !onUpdate || isReadOnly}
                  className={cn(
                    'w-full rounded-md border border-input bg-background px-2 py-1.5 text-sm text-foreground',
                    'focus:outline-none focus:ring-1 focus:ring-primary/30',
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
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground flex items-center gap-1">
                  <Hash className="h-3 w-3" />
                  Points
                </label>
                <input
                  type="number"
                  value={task.story_points ?? ''}
                  onChange={handleStoryPointsChange}
                  disabled={isUpdating || !onUpdate || isReadOnly}
                  placeholder="0"
                  min="0"
                  max="100"
                  className={cn(
                    'w-full rounded-md border border-input bg-background px-2 py-1.5 text-sm text-foreground',
                    'focus:outline-none focus:ring-1 focus:ring-primary/30',
                    'disabled:cursor-not-allowed disabled:opacity-50'
                  )}
                />
              </div>

              {/* Due Date / Completed Date */}
              {isDone && task.completed_at ? (
                <div className="space-y-1">
                  <label className="text-xs font-medium text-muted-foreground flex items-center gap-1">
                    <CheckCircle2 className="h-3 w-3 text-green-600" />
                    Completed
                  </label>
                  <div className="rounded-md border border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/20 px-2 py-1.5 text-sm text-green-700 dark:text-green-400">
                    {new Date(task.completed_at).toLocaleDateString(undefined, {
                      month: 'short',
                      day: 'numeric',
                    })}
                  </div>
                </div>
              ) : (
                <div className="space-y-1">
                  <label className="text-xs font-medium text-muted-foreground flex items-center gap-1">
                    <Calendar className="h-3 w-3" />
                    Due Date
                  </label>
                  <input
                    type="date"
                    value={formatDateForInput(task.due_date)}
                    onChange={handleDueDateChange}
                    disabled={isUpdating || !onUpdate || isReadOnly}
                    className={cn(
                      'w-full rounded-md border border-input bg-background px-2 py-1.5 text-sm text-foreground',
                      'focus:outline-none focus:ring-1 focus:ring-primary/30',
                      'disabled:cursor-not-allowed disabled:opacity-50'
                    )}
                  />
                </div>
              )}

              {/* Assignee */}
              <div className="space-y-1">
                <label className="text-xs font-medium text-muted-foreground flex items-center gap-1">
                  <User className="h-3 w-3" />
                  Assignee
                </label>
                {onUpdate && !isReadOnly ? (
                  <>
                    <select
                      value={task.assignee_id || ''}
                      onChange={handleAssigneeChange}
                      disabled={isUpdating}
                      className={cn(
                        'w-full rounded-md border bg-background px-2 py-1.5 text-sm text-foreground',
                        'focus:outline-none focus:ring-1 focus:ring-primary/30',
                        'disabled:cursor-not-allowed disabled:opacity-50',
                        assigneeError ? 'border-destructive' : 'border-input'
                      )}
                    >
                      <option value="">Unassigned</option>
                      {projectMembers.map((member) => (
                        <option key={member.user_id} value={member.user_id}>
                          {member.user_display_name || member.user_email?.split('@')[0] || 'Unknown'}
                        </option>
                      ))}
                    </select>
                    {assigneeError && (
                      <p className="text-[11px] text-destructive flex items-start gap-1 mt-1">
                        <AlertCircle className="h-3 w-3 flex-shrink-0 mt-0.5" />
                        {assigneeError}
                      </p>
                    )}
                  </>
                ) : (
                  <div className="flex items-center gap-1.5 px-2 py-1.5 rounded-md border border-input bg-muted/30 text-sm">
                    {task.assignee ? (
                      <span className="truncate">
                        {task.assignee.display_name || task.assignee.email.split('@')[0]}
                      </span>
                    ) : (
                      <span className="text-muted-foreground italic">Unassigned</span>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* Description - View/Edit Mode */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  Description
                </label>
                {!isEditingDescription && !isReadOnly && onUpdate && (
                  <button
                    onClick={() => setIsEditingDescription(true)}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                  >
                    <Pencil className="h-3 w-3" />
                    Edit
                  </button>
                )}
              </div>

              {/* Editor error banner */}
              {editorError && (
                <div className="flex items-center gap-2 px-3 py-2 rounded-lg border border-destructive/30 bg-destructive/5 text-sm text-destructive">
                  <AlertCircle className="h-3.5 w-3.5 flex-shrink-0" />
                  <span>{editorError}</span>
                </div>
              )}

              {isEditingDescription ? (
                <>
                  {/* Save/Discard bar */}
                  {hasDescriptionChanges && (
                    <div className="flex items-center justify-between px-3 py-2 rounded-lg bg-amber-500/10 border border-amber-500/30">
                      <div className="flex items-center gap-2 text-xs text-amber-700 dark:text-amber-400">
                        <span className="relative flex h-2 w-2">
                          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
                          <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500" />
                        </span>
                        Unsaved changes
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => {
                            setLocalDescription(task.description || '')
                            setHasDescriptionChanges(false)
                            setIsEditingDescription(false)
                          }}
                          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                        >
                          <RotateCcw className="h-3 w-3" />
                          Discard
                        </button>
                        <button
                          onClick={() => {
                            onUpdate?.({ description: localDescription || null })
                            setHasDescriptionChanges(false)
                            setIsEditingDescription(false)
                          }}
                          disabled={isUpdating}
                          className={cn(
                            'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium',
                            'bg-primary text-primary-foreground hover:bg-primary/90 shadow-sm',
                            'disabled:opacity-50 disabled:cursor-not-allowed',
                            'transition-all duration-200'
                          )}
                        >
                          {isUpdating ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                          ) : (
                            <>
                              <Save className="h-3 w-3" />
                              Save
                            </>
                          )}
                        </button>
                      </div>
                    </div>
                  )}
                  <RichTextEditor
                    value={localDescription}
                    onChange={(value) => {
                      setLocalDescription(value)
                      setHasDescriptionChanges(value !== (task.description || ''))
                    }}
                    onError={(msg) => setEditorError(msg)}
                    placeholder="Add a detailed description with formatting, images, tables..."
                    readOnly={isUpdating || !onUpdate || isReadOnly}
                    maxLength={512000}
                    className="min-h-[200px]"
                  />
                  {!hasDescriptionChanges && (
                    <div className="flex justify-end">
                      <button
                        onClick={() => setIsEditingDescription(false)}
                        className="text-xs text-muted-foreground hover:text-foreground transition-colors px-2 py-1 rounded hover:bg-muted"
                      >
                        Done editing
                      </button>
                    </div>
                  )}
                </>
              ) : (
                /* View mode - rendered HTML */
                <div>
                  {localDescription && localDescription !== '<p></p>' ? (
                    <div
                      className={cn(
                        'prose prose-sm max-w-none rounded-lg border border-border/50 bg-muted/10 px-4 py-3',
                        'prose-headings:font-semibold prose-p:my-2',
                        'prose-ul:my-2 prose-ol:my-2 prose-li:my-1',
                        '[&_table]:border-collapse [&_table]:w-full',
                        '[&_th]:border [&_th]:border-border [&_th]:p-2 [&_th]:bg-muted',
                        '[&_td]:border [&_td]:border-border [&_td]:p-2',
                        '[&_a]:text-primary [&_a]:underline',
                        '[&_img]:max-w-full [&_img]:h-auto [&_img]:rounded-md',
                      )}
                      dangerouslySetInnerHTML={{ __html: localDescription }}
                    />
                  ) : (
                    <div
                      className={cn(
                        'w-full rounded-lg border border-dashed border-border/50 px-4 py-6',
                        'text-sm text-muted-foreground italic',
                      )}
                    >
                      No description
                    </div>
                  )}
                </div>
              )}

              {isReadOnly && (
                <p className="text-xs text-muted-foreground bg-muted/50 px-3 py-2 rounded-lg">
                  {isArchived
                    ? 'Task is archived. Unarchive to edit.'
                    : 'Task is completed. Change status to edit.'}
                </p>
              )}
            </div>

            {/* Subtasks (if any) */}
            {task.subtasks_count != null && task.subtasks_count > 0 && (
              <>
                <div className="border-t border-border/40" />
                <div className="space-y-2">
                  <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
                    <Layers className="h-3.5 w-3.5" />
                    Subtasks ({task.subtasks_count})
                  </label>
                  <button
                    className={cn(
                      'w-full flex items-center justify-between px-3 py-2 rounded-lg',
                      'border border-input bg-background text-sm text-muted-foreground',
                      'hover:bg-accent hover:text-foreground transition-colors'
                    )}
                  >
                    <span>View subtasks</span>
                    <ChevronRight className="h-4 w-4" />
                  </button>
                </div>
              </>
            )}

            {/* Metadata */}
            <div className="border-t border-border/40" />
            <div className="space-y-2">
              <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
                <FileText className="h-3.5 w-3.5" />
                Details
              </label>
              <div className="rounded-lg border border-input bg-muted/20 p-3 space-y-2 text-sm">
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

            {/* Attachments Section */}
            <div className="border-t border-border/40" />
            <TaskAttachmentsSection taskId={task.id} canEdit={canEdit && !isReadOnly} />

            {/* Checklists Section */}
            <div className="border-t border-border/40" />
            <ChecklistPanel taskId={task.id} canEdit={canEdit && !isReadOnly} className="min-h-[150px]" />

            {/* Comments Section */}
            <div className="border-t border-border/40" />
            <CommentThread
              taskId={task.id}
              className="min-h-[250px]"
              onMentionSearch={handleMentionSearch}
              mentionSuggestions={mentionSuggestions}
            />
          </div>
        </div>

        {/* Unsaved Changes Confirmation Modal */}
        {showUnsavedDialog && pendingTask && (
          <>
            <div
              className="fixed inset-0 z-[60] bg-black/50"
              onClick={() => {
                setShowUnsavedDialog(false)
                setPendingTask(null)
              }}
            />
            <div className="fixed left-1/2 top-1/2 z-[70] w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border bg-card p-6 shadow-xl">
              <div className="flex items-center gap-3 mb-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-amber-500/10">
                  <AlertCircle className="h-5 w-5 text-amber-500" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-foreground">Unsaved Changes</h3>
                  <p className="text-sm text-muted-foreground">You have unsaved description changes.</p>
                </div>
              </div>
              <p className="text-sm text-muted-foreground mb-6">
                Do you want to discard your changes and switch to the other task, or keep editing?
              </p>
              <div className="flex items-center justify-end gap-3">
                <button
                  onClick={() => {
                    // Keep editing - revert task selection
                    setShowUnsavedDialog(false)
                    const currentTask = task
                    setPendingTask(null)
                    onRevertTaskSelection?.(currentTask)
                  }}
                  className={cn(
                    'rounded-md border border-input bg-background px-4 py-2 text-sm font-medium',
                    'hover:bg-accent hover:text-accent-foreground',
                    'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2'
                  )}
                >
                  Keep Editing
                </button>
                <button
                  onClick={() => {
                    // Discard and switch
                    setShowUnsavedDialog(false)
                    setIsEditingDescription(false)
                    setHasDescriptionChanges(false)
                    if (pendingTask) {
                      setLocalDescription(pendingTask.description || '')
                    }
                    setPendingTask(null)
                  }}
                  className={cn(
                    'rounded-md bg-amber-500 px-4 py-2 text-sm font-medium text-white',
                    'hover:bg-amber-600 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2'
                  )}
                >
                  Discard Changes
                </button>
              </div>
            </div>
          </>
        )}

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
