/**
 * Notification List Component
 *
 * Displays a scrollable list of notifications with empty state,
 * loading state, and actions.
 *
 * Features:
 * - Empty state with icon
 * - Loading skeleton
 * - Scrollable notification list
 * - Header with mark all read action
 * - Footer with view all link
 */

import { useCallback } from 'react'
import { cn } from '@/lib/utils'
import {
  Bell,
  CheckCheck,
  Inbox,
} from 'lucide-react'
import { NotificationItem, type Notification } from './notification-item'

// ============================================================================
// Types
// ============================================================================

export interface NotificationListProps {
  /**
   * Array of notifications to display
   */
  notifications: Notification[]
  /**
   * Whether notifications are loading
   */
  isLoading?: boolean
  /**
   * Number of unread notifications
   */
  unreadCount?: number
  /**
   * Callback when a notification is clicked
   */
  onNotificationClick?: (notification: Notification) => void
  /**
   * Callback when mark as read is clicked
   */
  onMarkAsRead?: (notification: Notification) => void
  /**
   * Callback when mark all as read is clicked
   */
  onMarkAllAsRead?: () => void
  /**
   * Callback when delete is clicked
   */
  onDelete?: (notification: Notification) => void
  /**
   * Callback when view all is clicked
   */
  onViewAll?: () => void
  /**
   * Maximum height of the list
   */
  maxHeight?: number | string
  /**
   * Whether to show the header
   */
  showHeader?: boolean
  /**
   * Whether to show the footer
   */
  showFooter?: boolean
  /**
   * Additional CSS classes
   */
  className?: string
}

// ============================================================================
// Loading Skeleton
// ============================================================================

function NotificationSkeleton(): JSX.Element {
  return (
    <div className="flex gap-3 p-3 animate-pulse">
      <div className="flex-shrink-0 h-9 w-9 rounded-full bg-muted" />
      <div className="flex-1 space-y-2">
        <div className="h-4 w-3/4 rounded bg-muted" />
        <div className="h-3 w-full rounded bg-muted" />
        <div className="h-3 w-1/4 rounded bg-muted" />
      </div>
    </div>
  )
}

// ============================================================================
// Empty State
// ============================================================================

function EmptyState(): JSX.Element {
  return (
    <div className="flex flex-col items-center justify-center py-8 px-4 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted mb-3">
        <Inbox className="h-6 w-6 text-muted-foreground" />
      </div>
      <h4 className="text-sm font-medium text-foreground">
        No notifications
      </h4>
      <p className="mt-1 text-xs text-muted-foreground">
        You're all caught up! We'll let you know when something new arrives.
      </p>
    </div>
  )
}

// ============================================================================
// Component
// ============================================================================

export function NotificationList({
  notifications,
  isLoading = false,
  unreadCount = 0,
  onNotificationClick,
  onMarkAsRead,
  onMarkAllAsRead,
  onDelete,
  onViewAll,
  maxHeight = 400,
  showHeader = true,
  showFooter = true,
  className,
}: NotificationListProps): JSX.Element {
  // Handle mark all as read
  const handleMarkAllAsRead = useCallback(() => {
    if (onMarkAllAsRead) {
      onMarkAllAsRead()
    }
  }, [onMarkAllAsRead])

  // Handle view all
  const handleViewAll = useCallback(() => {
    if (onViewAll) {
      onViewAll()
    }
  }, [onViewAll])

  return (
    <div className={cn('flex flex-col', className)}>
      {/* Header */}
      {showHeader && (
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div className="flex items-center gap-2">
            <Bell className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-semibold text-foreground">
              Notifications
            </h3>
            {unreadCount > 0 && (
              <span className="flex h-5 min-w-[20px] items-center justify-center rounded-full bg-primary px-1.5 text-[10px] font-semibold text-primary-foreground">
                {unreadCount > 99 ? '99+' : unreadCount}
              </span>
            )}
          </div>

          {onMarkAllAsRead && unreadCount > 0 && (
            <button
              onClick={handleMarkAllAsRead}
              className={cn(
                'flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium',
                'text-muted-foreground hover:text-foreground hover:bg-accent',
                'transition-colors focus:outline-none focus:ring-2 focus:ring-ring'
              )}
            >
              <CheckCheck className="h-3.5 w-3.5" />
              Mark all read
            </button>
          )}
        </div>
      )}

      {/* List Content */}
      <div
        className="overflow-y-auto divide-y divide-border"
        style={{ maxHeight }}
      >
        {/* Loading State */}
        {isLoading && (
          <>
            <NotificationSkeleton />
            <NotificationSkeleton />
            <NotificationSkeleton />
          </>
        )}

        {/* Empty State */}
        {!isLoading && notifications.length === 0 && <EmptyState />}

        {/* Notifications List */}
        {!isLoading &&
          notifications.map((notification) => (
            <NotificationItem
              key={notification.id}
              notification={notification}
              onClick={onNotificationClick}
              onMarkAsRead={onMarkAsRead}
              onDelete={onDelete}
            />
          ))}
      </div>

      {/* Footer */}
      {showFooter && notifications.length > 0 && onViewAll && (
        <div className="border-t border-border">
          <button
            onClick={handleViewAll}
            className={cn(
              'flex w-full items-center justify-center gap-2 py-3 text-sm font-medium',
              'text-primary hover:bg-accent/50 transition-colors',
              'focus:outline-none focus:bg-accent/50'
            )}
          >
            View all notifications
          </button>
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Exports
// ============================================================================

export { EmptyState, NotificationSkeleton }
export default NotificationList
