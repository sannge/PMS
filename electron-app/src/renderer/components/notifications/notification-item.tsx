/**
 * Notification Item Component
 *
 * Displays a single notification with icon, title, message, and time.
 *
 * Features:
 * - Type-specific icons
 * - Read/unread visual states
 * - Relative time display
 * - Click to mark as read
 * - Click to navigate to related entity
 * - Delete action on hover
 */

import { useCallback } from 'react'
import { cn } from '@/lib/utils'
import {
  Bell,
  CheckCircle2,
  MessageSquare,
  AtSign,
  Clock,
  UserPlus,
  AlertCircle,
  Trash2,
  FileText,
  FolderKanban,
  Layers,
  ExternalLink,
} from 'lucide-react'

// ============================================================================
// Types
// ============================================================================

/**
 * Notification type enumeration (matching backend)
 */
export type NotificationType =
  | 'task_assigned'
  | 'task_updated'
  | 'task_commented'
  | 'mention'
  | 'status_change'
  | 'due_date_reminder'
  | 'project_invite'
  | 'system'

/**
 * Entity type enumeration (matching backend)
 */
export type EntityType = 'task' | 'note' | 'project' | 'application' | 'comment'

/**
 * Notification data structure
 */
export interface Notification {
  id: string
  user_id: string
  type: NotificationType
  title: string
  message: string | null
  is_read: boolean
  entity_type: EntityType | null
  entity_id: string | null
  created_at: string
}

export interface NotificationItemProps {
  /**
   * Notification data
   */
  notification: Notification
  /**
   * Callback when notification is clicked
   */
  onClick?: (notification: Notification) => void
  /**
   * Callback when mark as read is clicked
   */
  onMarkAsRead?: (notification: Notification) => void
  /**
   * Callback when delete is clicked
   */
  onDelete?: (notification: Notification) => void
  /**
   * Whether actions are disabled
   */
  disabled?: boolean
  /**
   * Additional CSS classes
   */
  className?: string
}

interface TypeConfig {
  icon: JSX.Element
  iconBg: string
}

// ============================================================================
// Constants
// ============================================================================

const TYPE_CONFIG: Record<NotificationType, TypeConfig> = {
  task_assigned: {
    icon: <CheckCircle2 className="h-4 w-4" />,
    iconBg: 'bg-blue-100 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400',
  },
  task_updated: {
    icon: <CheckCircle2 className="h-4 w-4" />,
    iconBg: 'bg-green-100 text-green-600 dark:bg-green-900/30 dark:text-green-400',
  },
  task_commented: {
    icon: <MessageSquare className="h-4 w-4" />,
    iconBg: 'bg-purple-100 text-purple-600 dark:bg-purple-900/30 dark:text-purple-400',
  },
  mention: {
    icon: <AtSign className="h-4 w-4" />,
    iconBg: 'bg-yellow-100 text-yellow-600 dark:bg-yellow-900/30 dark:text-yellow-400',
  },
  status_change: {
    icon: <Layers className="h-4 w-4" />,
    iconBg: 'bg-indigo-100 text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-400',
  },
  due_date_reminder: {
    icon: <Clock className="h-4 w-4" />,
    iconBg: 'bg-orange-100 text-orange-600 dark:bg-orange-900/30 dark:text-orange-400',
  },
  project_invite: {
    icon: <UserPlus className="h-4 w-4" />,
    iconBg: 'bg-teal-100 text-teal-600 dark:bg-teal-900/30 dark:text-teal-400',
  },
  system: {
    icon: <AlertCircle className="h-4 w-4" />,
    iconBg: 'bg-slate-100 text-slate-600 dark:bg-slate-900/30 dark:text-slate-400',
  },
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Get entity type icon
 */
function getEntityIcon(entityType: EntityType | null): JSX.Element | null {
  switch (entityType) {
    case 'task':
      return <CheckCircle2 className="h-3 w-3" />
    case 'note':
      return <FileText className="h-3 w-3" />
    case 'project':
      return <FolderKanban className="h-3 w-3" />
    case 'application':
      return <Layers className="h-3 w-3" />
    case 'comment':
      return <MessageSquare className="h-3 w-3" />
    default:
      return null
  }
}

/**
 * Format relative time
 */
function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffSec = Math.floor(diffMs / 1000)
  const diffMin = Math.floor(diffSec / 60)
  const diffHour = Math.floor(diffMin / 60)
  const diffDay = Math.floor(diffHour / 24)
  const diffWeek = Math.floor(diffDay / 7)

  if (diffSec < 60) {
    return 'Just now'
  }
  if (diffMin < 60) {
    return `${diffMin}m ago`
  }
  if (diffHour < 24) {
    return `${diffHour}h ago`
  }
  if (diffDay < 7) {
    return `${diffDay}d ago`
  }
  if (diffWeek < 4) {
    return `${diffWeek}w ago`
  }

  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

// ============================================================================
// Component
// ============================================================================

export function NotificationItem({
  notification,
  onClick,
  onMarkAsRead,
  onDelete,
  disabled = false,
  className,
}: NotificationItemProps): JSX.Element {
  const typeConfig = TYPE_CONFIG[notification.type]

  // Handle click
  const handleClick = useCallback(() => {
    if (!disabled && onClick) {
      onClick(notification)
    }
  }, [notification, disabled, onClick])

  // Handle mark as read
  const handleMarkAsRead = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation()
      if (!disabled && onMarkAsRead) {
        onMarkAsRead(notification)
      }
    },
    [notification, disabled, onMarkAsRead]
  )

  // Handle delete
  const handleDelete = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation()
      if (!disabled && onDelete) {
        onDelete(notification)
      }
    },
    [notification, disabled, onDelete]
  )

  return (
    <div
      onClick={handleClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={(e) => {
        if (onClick && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault()
          handleClick()
        }
      }}
      className={cn(
        'group relative flex gap-3 p-3 transition-colors',
        !notification.is_read && 'bg-primary/5',
        onClick && !disabled && 'cursor-pointer hover:bg-accent/50',
        disabled && 'opacity-50 cursor-not-allowed',
        'focus:outline-none focus:bg-accent/50',
        className
      )}
    >
      {/* Unread indicator */}
      {!notification.is_read && (
        <div className="absolute left-1 top-1/2 -translate-y-1/2 h-2 w-2 rounded-full bg-primary" />
      )}

      {/* Type icon */}
      <div
        className={cn(
          'flex-shrink-0 flex h-9 w-9 items-center justify-center rounded-full',
          typeConfig.iconBg
        )}
      >
        {typeConfig.icon}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        {/* Title */}
        <p
          className={cn(
            'text-sm line-clamp-1',
            notification.is_read ? 'text-foreground' : 'font-medium text-foreground'
          )}
        >
          {notification.title}
        </p>

        {/* Message */}
        {notification.message && (
          <p className="mt-0.5 text-xs text-muted-foreground line-clamp-2">
            {notification.message}
          </p>
        )}

        {/* Footer - Time and Entity */}
        <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
          <span>{formatRelativeTime(notification.created_at)}</span>

          {notification.entity_type && (
            <>
              <span>•</span>
              <span className="flex items-center gap-1 capitalize">
                {getEntityIcon(notification.entity_type)}
                {notification.entity_type}
              </span>
            </>
          )}
        </div>
      </div>

      {/* Actions - visible on hover */}
      <div className="flex-shrink-0 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        {/* Navigate to entity */}
        {notification.entity_id && onClick && (
          <button
            onClick={handleClick}
            disabled={disabled}
            className={cn(
              'rounded-md p-1.5 text-muted-foreground transition-colors',
              'hover:bg-accent hover:text-accent-foreground',
              'focus:outline-none focus:ring-2 focus:ring-ring',
              'disabled:pointer-events-none disabled:opacity-50'
            )}
            title="View details"
          >
            <ExternalLink className="h-3.5 w-3.5" />
          </button>
        )}

        {/* Mark as read */}
        {!notification.is_read && onMarkAsRead && (
          <button
            onClick={handleMarkAsRead}
            disabled={disabled}
            className={cn(
              'rounded-md p-1.5 text-muted-foreground transition-colors',
              'hover:bg-accent hover:text-accent-foreground',
              'focus:outline-none focus:ring-2 focus:ring-ring',
              'disabled:pointer-events-none disabled:opacity-50'
            )}
            title="Mark as read"
          >
            <CheckCircle2 className="h-3.5 w-3.5" />
          </button>
        )}

        {/* Delete */}
        {onDelete && (
          <button
            onClick={handleDelete}
            disabled={disabled}
            className={cn(
              'rounded-md p-1.5 text-muted-foreground transition-colors',
              'hover:bg-destructive/10 hover:text-destructive',
              'focus:outline-none focus:ring-2 focus:ring-ring',
              'disabled:pointer-events-none disabled:opacity-50'
            )}
            title="Delete notification"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
    </div>
  )
}

// ============================================================================
// Exports
// ============================================================================

export { formatRelativeTime, TYPE_CONFIG }
export default NotificationItem
