/**
 * Notification Bell Component
 *
 * Bell icon button with badge showing unread count and a dropdown
 * containing the notification list.
 *
 * Features:
 * - Unread count badge
 * - Dropdown with notification list
 * - Click outside to close
 * - Keyboard accessible
 * - Animation on new notifications
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import { cn } from '@/lib/utils'
import { Bell } from 'lucide-react'
import { NotificationList } from './notification-list'
import type { Notification } from './notification-item'

// ============================================================================
// Types
// ============================================================================

export interface NotificationBellProps {
  /**
   * Array of notifications to display
   */
  notifications: Notification[]
  /**
   * Number of unread notifications
   */
  unreadCount: number
  /**
   * Whether notifications are loading
   */
  isLoading?: boolean
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
   * Callback when dropdown is opened
   */
  onOpen?: () => void
  /**
   * Callback when dropdown is closed
   */
  onClose?: () => void
  /**
   * Additional CSS classes
   */
  className?: string
}

// ============================================================================
// Component
// ============================================================================

export function NotificationBell({
  notifications,
  unreadCount,
  isLoading = false,
  onNotificationClick,
  onMarkAsRead,
  onMarkAllAsRead,
  onDelete,
  onViewAll,
  onOpen,
  onClose,
  className,
}: NotificationBellProps): JSX.Element {
  const [isOpen, setIsOpen] = useState(false)
  const [shouldAnimate, setShouldAnimate] = useState(false)
  const previousUnreadCount = useRef(unreadCount)
  const containerRef = useRef<HTMLDivElement>(null)

  // Animate badge when unread count increases
  useEffect(() => {
    if (unreadCount > previousUnreadCount.current) {
      setShouldAnimate(true)
      const timer = setTimeout(() => setShouldAnimate(false), 1000)
      return () => clearTimeout(timer)
    }
    previousUnreadCount.current = unreadCount
  }, [unreadCount])

  // Handle click outside to close dropdown
  useEffect(() => {
    if (!isOpen) return

    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false)
        onClose?.()
      }
    }

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsOpen(false)
        onClose?.()
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    document.addEventListener('keydown', handleEscape)

    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('keydown', handleEscape)
    }
  }, [isOpen, onClose])

  // Toggle dropdown
  const toggleDropdown = useCallback(() => {
    setIsOpen((prev) => {
      const next = !prev
      if (next) {
        onOpen?.()
      } else {
        onClose?.()
      }
      return next
    })
  }, [onOpen, onClose])

  // Handle notification click - close dropdown and forward
  const handleNotificationClick = useCallback(
    (notification: Notification) => {
      setIsOpen(false)
      onClose?.()
      onNotificationClick?.(notification)
    },
    [onNotificationClick, onClose]
  )

  // Handle view all - close dropdown and forward
  const handleViewAll = useCallback(() => {
    setIsOpen(false)
    onClose?.()
    onViewAll?.()
  }, [onViewAll, onClose])

  return (
    <div ref={containerRef} className={cn('relative', className)}>
      {/* Bell Button */}
      <button
        onClick={toggleDropdown}
        className={cn(
          'relative flex h-9 w-9 items-center justify-center rounded-md border border-border',
          'text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors',
          'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
          isOpen && 'bg-accent text-accent-foreground'
        )}
        title={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ''}`}
        aria-expanded={isOpen}
        aria-haspopup="true"
        aria-label={`Notifications${unreadCount > 0 ? `, ${unreadCount} unread` : ''}`}
      >
        <Bell className={cn('h-4 w-4', shouldAnimate && 'animate-wiggle')} />

        {/* Badge */}
        {unreadCount > 0 && (
          <span
            className={cn(
              'absolute -right-1 -top-1 flex h-4 min-w-[16px] items-center justify-center',
              'rounded-full bg-destructive px-1 text-[10px] font-semibold text-destructive-foreground',
              shouldAnimate && 'animate-bounce'
            )}
          >
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {/* Dropdown */}
      {isOpen && (
        <>
          {/* Backdrop for mobile */}
          <div
            className="fixed inset-0 z-40 sm:hidden"
            onClick={() => {
              setIsOpen(false)
              onClose?.()
            }}
          />

          {/* Dropdown Content */}
          <div
            className={cn(
              'absolute right-0 top-full z-50 mt-2 w-80 sm:w-96',
              'rounded-lg border border-border bg-card shadow-lg',
              'animate-in fade-in-0 zoom-in-95 slide-in-from-top-2',
              'origin-top-right duration-200'
            )}
          >
            <NotificationList
              notifications={notifications}
              isLoading={isLoading}
              unreadCount={unreadCount}
              onNotificationClick={handleNotificationClick}
              onMarkAsRead={onMarkAsRead}
              onMarkAllAsRead={onMarkAllAsRead}
              onDelete={onDelete}
              onViewAll={handleViewAll}
              maxHeight={400}
            />
          </div>
        </>
      )}
    </div>
  )
}

// ============================================================================
// Exports
// ============================================================================

export default NotificationBell
