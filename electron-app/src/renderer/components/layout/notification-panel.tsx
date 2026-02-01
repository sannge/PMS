/**
 * Notification Panel Component
 *
 * Displays in-app notifications in a slide-out panel.
 * Shows real-time alerts for invitations, member changes, etc.
 * Adapts positioning based on sidebar collapsed state.
 *
 * Uses TanStack Query for data fetching and caching.
 */

import { useEffect, useRef, useState, useCallback } from 'react'
import { cn } from '@/lib/utils'
import { useAuthStore, getAuthHeaders } from '@/contexts/auth-context'
import { useNotificationUIStore } from '@/contexts/notification-ui-context'
import {
  useNotifications,
  useMarkAsRead,
  useMarkAllAsRead,
  useDeleteNotification,
  useClearAllNotifications,
  type Notification,
} from '@/hooks/use-notifications'
import {
  useAcceptInvitation,
  useRejectInvitation,
  type InvitationWithDetails,
} from '@/hooks/use-invitations'
import {
  X,
  Bell,
  Mail,
  UserPlus,
  UserMinus,
  Shield,
  Check,
  AlertCircle,
  Info,
  CheckCircle,
  Loader2,
  Calendar,
  User,
  Building2,
} from 'lucide-react'

// ============================================================================
// Props
// ============================================================================

export interface NotificationPanelProps {
  /** Whether sidebar is collapsed (affects panel positioning) */
  sidebarCollapsed?: boolean
}

// ============================================================================
// Types
// ============================================================================

type NotificationType =
  | 'task_assigned'
  | 'task_status_changed'
  | 'comment_mention'
  | 'comment_added'
  | 'member_added'
  | 'member_removed'
  | 'role_changed'
  | 'project_member_added'
  | 'project_member_removed'
  | 'project_role_changed'
  | 'invitation_received'
  | 'invitation_accepted'
  | 'invitation_rejected'
  | 'application_invite'
  | 'success'
  | 'warning'
  | 'error'
  | 'info'

// ============================================================================
// Helper Functions
// ============================================================================

function getNotificationIcon(type: string) {
  switch (type) {
    case 'invitation_received':
    case 'application_invite':
      return <Mail className="h-4 w-4 text-blue-500" />
    case 'invitation_accepted':
      return <CheckCircle className="h-4 w-4 text-emerald-500" />
    case 'invitation_rejected':
      return <X className="h-4 w-4 text-red-500" />
    case 'member_added':
    case 'project_member_added':
      return <UserPlus className="h-4 w-4 text-blue-500" />
    case 'member_removed':
    case 'project_member_removed':
      return <UserMinus className="h-4 w-4 text-orange-500" />
    case 'role_changed':
    case 'project_role_changed':
      return <Shield className="h-4 w-4 text-violet-500" />
    case 'task_assigned':
      return <AlertCircle className="h-4 w-4 text-amber-500" />
    case 'success':
      return <CheckCircle className="h-4 w-4 text-emerald-500" />
    case 'warning':
      return <AlertCircle className="h-4 w-4 text-amber-500" />
    case 'error':
      return <AlertCircle className="h-4 w-4 text-red-500" />
    default:
      return <Info className="h-4 w-4 text-blue-500" />
  }
}

function formatTimeAgo(dateStr: string): string {
  // Ensure UTC parsing - append 'Z' if no timezone indicator
  // Backend sends timestamps in UTC without the 'Z' suffix
  let normalizedDateStr = dateStr
  if (!dateStr.endsWith('Z') && !dateStr.includes('+') && !dateStr.includes('-', 10)) {
    normalizedDateStr = dateStr + 'Z'
  }

  const date = new Date(normalizedDateStr)
  const now = new Date()
  const diffInSeconds = Math.floor((now.getTime() - date.getTime()) / 1000)

  // Handle future dates or very recent (within 60 seconds)
  if (diffInSeconds < 0 || diffInSeconds < 60) {
    return 'Just now'
  }
  if (diffInSeconds < 3600) {
    const mins = Math.floor(diffInSeconds / 60)
    return `${mins}m ago`
  }
  if (diffInSeconds < 86400) {
    const hours = Math.floor(diffInSeconds / 3600)
    return `${hours}h ago`
  }
  const days = Math.floor(diffInSeconds / 86400)
  return `${days}d ago`
}

// ============================================================================
// Notification Item Component
// ============================================================================

interface NotificationItemProps {
  notification: Notification
  onMarkAsRead: (id: string) => void
  onRemove: (id: string) => void
  onClick?: (notification: Notification) => void
}

function NotificationItem({
  notification,
  onMarkAsRead,
  onRemove,
  onClick,
}: NotificationItemProps) {
  // Check if this is a clickable invitation notification
  const isInvitationNotification =
    notification.notification_type === 'invitation_received' ||
    notification.notification_type === 'application_invite'

  // Get entity status from notification data if available
  const entityStatus = notification.data?.status as string | undefined

  // Check if the invitation is still pending
  const isPendingInvitation = isInvitationNotification &&
    (!entityStatus || entityStatus === 'pending')

  // Get status label for non-pending invitations
  const getInvitationStatusLabel = () => {
    switch (entityStatus) {
      case 'accepted':
        return 'Accepted'
      case 'rejected':
        return 'Declined'
      case 'cancelled':
        return 'Cancelled'
      default:
        return null
    }
  }

  const handleClick = () => {
    if (isInvitationNotification && onClick) {
      onClick(notification)
    }
  }

  return (
    <div
      onClick={handleClick}
      className={cn(
        'group relative flex gap-3 p-3 rounded-lg transition-all duration-200',
        'hover:bg-muted/50',
        !notification.is_read && 'bg-accent/5',
        isInvitationNotification && 'cursor-pointer'
      )}
    >
      {/* Unread indicator */}
      {!notification.is_read && (
        <span className="absolute left-1 top-1/2 -translate-y-1/2 h-2 w-2 rounded-full bg-accent" />
      )}

      {/* Icon */}
      <div className="flex-shrink-0 mt-0.5">
        {getNotificationIcon(notification.notification_type)}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-foreground">
          {notification.title}
        </p>
        <p className="text-xs text-muted-foreground mt-0.5">
          {notification.body}
        </p>
        <div className="flex items-center gap-2 mt-1.5">
          <span className="text-[10px] text-muted-foreground/70">
            {formatTimeAgo(notification.created_at)}
          </span>
          {isPendingInvitation && (
            <span className="text-[10px] font-medium text-accent">
              Click to respond
            </span>
          )}
          {isInvitationNotification && !isPendingInvitation && (
            <span className={cn(
              "text-[10px] font-medium",
              entityStatus === 'accepted' && 'text-emerald-600 dark:text-emerald-400',
              entityStatus === 'rejected' && 'text-red-600 dark:text-red-400',
              entityStatus === 'cancelled' && 'text-amber-600 dark:text-amber-400'
            )}>
              {getInvitationStatusLabel()}
            </span>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="flex-shrink-0 flex items-start gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        {!notification.is_read && (
          <button
            onClick={(e) => {
              e.stopPropagation()
              onMarkAsRead(notification.id)
            }}
            className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground"
            title="Mark as read"
          >
            <Check className="h-3 w-3" />
          </button>
        )}
        <button
          onClick={(e) => {
            e.stopPropagation()
            onRemove(notification.id)
          }}
          className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground"
          title="Dismiss"
        >
          <X className="h-3 w-3" />
        </button>
      </div>
    </div>
  )
}

// ============================================================================
// Invitation Detail Popup Component
// ============================================================================

interface InvitationPopupProps {
  notification: Notification
  onClose: () => void
  onSuccess: () => void
}

function InvitationDetailPopup({ notification, onClose, onSuccess }: InvitationPopupProps) {
  const token = useAuthStore((state) => state.token)
  const acceptInvitation = useAcceptInvitation()
  const rejectInvitation = useRejectInvitation()

  const [invitation, setInvitation] = useState<InvitationWithDetails | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Get invitation ID from notification
  const invitationId = (notification.data?.invitation_id as string | undefined) ||
    (notification.data?.invitationId as string | undefined)

  // Fetch invitation details on mount
  useEffect(() => {
    async function fetchInvitation() {
      if (!invitationId || !token || !window.electronAPI) {
        setError('Invalid invitation')
        setIsLoading(false)
        return
      }

      try {
        const response = await window.electronAPI.get<InvitationWithDetails>(
          `/api/invitations/${invitationId}`,
          getAuthHeaders(token)
        )

        if (response.status === 200 && response.data) {
          setInvitation(response.data)
        } else if (response.status === 404) {
          setError('This invitation no longer exists')
        } else {
          setError('Failed to load invitation details')
        }
      } catch {
        setError('Failed to load invitation details')
      } finally {
        setIsLoading(false)
      }
    }

    fetchInvitation()
  }, [invitationId, token])

  const handleAccept = async () => {
    if (!invitationId || acceptInvitation.isPending || rejectInvitation.isPending) return

    setError(null)
    try {
      await acceptInvitation.mutateAsync(invitationId)
      onSuccess()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to accept invitation')
    }
  }

  const handleReject = async () => {
    if (!invitationId || acceptInvitation.isPending || rejectInvitation.isPending) return

    setError(null)
    try {
      await rejectInvitation.mutateAsync(invitationId)
      onSuccess()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to decline invitation')
    }
  }

  const isProcessing = acceptInvitation.isPending || rejectInvitation.isPending
  const isPending = invitation?.status === 'pending'

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  const getRoleDescription = (role: string) => {
    switch (role) {
      case 'owner':
        return 'Full access to manage the application, members, and all projects'
      case 'editor':
        return 'Can create and edit projects, tasks, and notes'
      case 'viewer':
        return 'Can view projects, tasks, and notes but cannot make changes'
      default:
        return ''
    }
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-background/80 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-xl border border-border bg-card shadow-xl animate-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div className="flex items-center gap-2">
            <Mail className="h-5 w-5 text-blue-500" />
            <h3 className="text-lg font-semibold text-foreground">Application Invitation</h3>
          </div>
          <button
            onClick={onClose}
            disabled={isProcessing}
            className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground disabled:opacity-50"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-4">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              <p className="mt-2 text-sm text-muted-foreground">Loading invitation details...</p>
            </div>
          ) : error && !invitation ? (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <AlertCircle className="h-10 w-10 text-destructive mb-3" />
              <p className="text-sm font-medium text-foreground">{error}</p>
              <button
                onClick={onClose}
                className="mt-4 px-4 py-2 text-sm font-medium rounded-md border border-input bg-background hover:bg-muted"
              >
                Close
              </button>
            </div>
          ) : invitation ? (
            <div className="space-y-4">
              {/* Application info */}
              <div className="flex items-start gap-3 p-3 rounded-lg bg-muted/50">
                <Building2 className="h-5 w-5 text-muted-foreground mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-foreground">
                    {invitation.application?.name || 'Unknown Application'}
                  </p>
                  <p className="text-xs text-muted-foreground mt-0.5">Application</p>
                </div>
              </div>

              {/* Inviter info */}
              <div className="flex items-start gap-3 p-3 rounded-lg bg-muted/50">
                <User className="h-5 w-5 text-muted-foreground mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-foreground">
                    {invitation.inviter?.display_name || invitation.inviter?.email || 'Unknown'}
                  </p>
                  <p className="text-xs text-muted-foreground mt-0.5">Invited by</p>
                </div>
              </div>

              {/* Role info */}
              <div className="flex items-start gap-3 p-3 rounded-lg bg-muted/50">
                <Shield className="h-5 w-5 text-muted-foreground mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-foreground capitalize">
                    {invitation.role}
                  </p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {getRoleDescription(invitation.role)}
                  </p>
                </div>
              </div>

              {/* Date info */}
              <div className="flex items-start gap-3 p-3 rounded-lg bg-muted/50">
                <Calendar className="h-5 w-5 text-muted-foreground mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-foreground">
                    {formatDate(invitation.created_at)}
                  </p>
                  <p className="text-xs text-muted-foreground mt-0.5">Sent on</p>
                </div>
              </div>

              {/* Status for non-pending invitations */}
              {!isPending && (
                <div className={cn(
                  'flex items-center gap-2 p-3 rounded-lg',
                  invitation.status === 'accepted' && 'bg-emerald-100 dark:bg-emerald-900/30',
                  invitation.status === 'rejected' && 'bg-red-100 dark:bg-red-900/30',
                  invitation.status === 'cancelled' && 'bg-amber-100 dark:bg-amber-900/30'
                )}>
                  {invitation.status === 'accepted' && <CheckCircle className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />}
                  {invitation.status === 'rejected' && <X className="h-5 w-5 text-red-600 dark:text-red-400" />}
                  {invitation.status === 'cancelled' && <AlertCircle className="h-5 w-5 text-amber-600 dark:text-amber-400" />}
                  <p className="text-sm font-medium capitalize">
                    This invitation has been {invitation.status}
                  </p>
                </div>
              )}

              {/* Error message */}
              {error && (
                <div className="flex items-center gap-2 p-3 rounded-lg bg-destructive/10 text-destructive">
                  <AlertCircle className="h-4 w-4" />
                  <p className="text-sm">{error}</p>
                </div>
              )}
            </div>
          ) : null}
        </div>

        {/* Footer with actions - only show for pending invitations */}
        {invitation && isPending && (
          <div className="flex items-center justify-end gap-3 p-4 border-t border-border">
            <button
              onClick={handleReject}
              disabled={isProcessing}
              className={cn(
                'flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors',
                'border border-input bg-background hover:bg-muted',
                'disabled:opacity-50 disabled:pointer-events-none'
              )}
            >
              {rejectInvitation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <X className="h-4 w-4" />
              )}
              Decline
            </button>
            <button
              onClick={handleAccept}
              disabled={isProcessing}
              className={cn(
                'flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors',
                'bg-primary text-primary-foreground hover:bg-primary/90',
                'disabled:opacity-50 disabled:pointer-events-none'
              )}
            >
              {acceptInvitation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Check className="h-4 w-4" />
              )}
              Accept
            </button>
          </div>
        )}

        {/* Close button for non-pending invitations */}
        {invitation && !isPending && (
          <div className="flex items-center justify-end p-4 border-t border-border">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-md text-sm font-medium border border-input bg-background hover:bg-muted"
            >
              Close
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

// ============================================================================
// Notification Panel Component
// ============================================================================

export function NotificationPanel({ sidebarCollapsed = false }: NotificationPanelProps) {
  const panelRef = useRef<HTMLDivElement>(null)
  const scrollContainerRef = useRef<HTMLDivElement>(null)

  // UI state from minimal store
  const isOpen = useNotificationUIStore((state) => state.isOpen)
  const setOpen = useNotificationUIStore((state) => state.setOpen)

  // TanStack Query hooks for data (with infinite scroll)
  const {
    data: notificationData,
    isLoading,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useNotifications()
  const markAsRead = useMarkAsRead()
  const markAllAsRead = useMarkAllAsRead()
  const deleteNotification = useDeleteNotification()
  const clearAll = useClearAllNotifications()

  const notifications = notificationData?.items || []
  const unreadCount = notificationData?.unread_count || 0

  // Infinite scroll: load more when near bottom
  const handleScroll = useCallback(() => {
    const container = scrollContainerRef.current
    if (!container || !hasNextPage || isFetchingNextPage) return

    const { scrollTop, scrollHeight, clientHeight } = container
    // Load more when within 100px of bottom
    if (scrollHeight - scrollTop - clientHeight < 100) {
      fetchNextPage()
    }
  }, [hasNextPage, isFetchingNextPage, fetchNextPage])

  // Invitation popup state
  const [selectedInvitationNotification, setSelectedInvitationNotification] = useState<Notification | null>(null)

  // Close on click outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [isOpen, setOpen])

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false)
      }
    }

    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown)
    }

    return () => {
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [isOpen, setOpen])

  // Handlers
  const handleMarkAsRead = (id: string) => {
    markAsRead.mutate(id)
  }

  const handleMarkAllAsRead = () => {
    markAllAsRead.mutate()
  }

  const handleRemove = (id: string) => {
    deleteNotification.mutate(id)
  }

  const handleClearAll = () => {
    clearAll.mutate()
  }

  // Handle invitation notification click
  const handleInvitationClick = (notification: Notification) => {
    setSelectedInvitationNotification(notification)
    // Mark as read when opened
    if (!notification.is_read) {
      markAsRead.mutate(notification.id)
    }
  }

  // Handle invitation popup close
  const handleInvitationPopupClose = () => {
    setSelectedInvitationNotification(null)
  }

  // Handle successful invitation response
  const handleInvitationSuccess = () => {
    // Remove the notification after successful accept/reject
    if (selectedInvitationNotification) {
      deleteNotification.mutate(selectedInvitationNotification.id)
    }
  }

  if (!isOpen) return null

  // Dynamic positioning based on sidebar state
  const panelLeft = sidebarCollapsed ? 'left-14' : 'left-48'

  return (
    <div
      ref={panelRef}
      className={cn(
        'fixed bottom-4 z-50 w-80',
        panelLeft,
        'bg-card border border-border rounded-xl shadow-xl',
        'animate-in slide-in-from-left-2 duration-200'
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b border-border">
        <div className="flex items-center gap-2">
          <Bell className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-semibold text-foreground">
            Notifications
          </span>
          {unreadCount > 0 && (
            <span className="flex items-center justify-center h-5 min-w-5 px-1.5 rounded-full bg-accent text-[10px] font-bold text-accent-foreground">
              {unreadCount}
            </span>
          )}
          {isLoading && (
            <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
          )}
        </div>
        <div className="flex items-center gap-1">
          {unreadCount > 0 && (
            <button
              onClick={handleMarkAllAsRead}
              disabled={markAllAsRead.isPending}
              className="text-[10px] font-medium text-muted-foreground hover:text-foreground px-2 py-1 rounded hover:bg-muted disabled:opacity-50"
            >
              Mark all read
            </button>
          )}
          <button
            onClick={() => setOpen(false)}
            className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Content with infinite scroll */}
      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        className="max-h-96 overflow-y-auto"
      >
        {notifications.length === 0 && !isLoading ? (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted/50 mb-3">
              <Bell className="h-6 w-6 text-muted-foreground/50" />
            </div>
            <p className="text-sm font-medium text-foreground">
              No notifications
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              You're all caught up!
            </p>
          </div>
        ) : (
          <div className="p-2 space-y-1">
            {notifications.map((notification) => (
              <NotificationItem
                key={notification.id}
                notification={notification}
                onMarkAsRead={handleMarkAsRead}
                onRemove={handleRemove}
                onClick={handleInvitationClick}
              />
            ))}
            {/* Loading indicator for infinite scroll */}
            {isFetchingNextPage && (
              <div className="flex items-center justify-center py-3">
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                <span className="ml-2 text-xs text-muted-foreground">Loading more...</span>
              </div>
            )}
            {/* End of list indicator */}
            {!hasNextPage && notifications.length > 0 && (
              <div className="text-center py-2 text-[10px] text-muted-foreground/50">
                No more notifications
              </div>
            )}
          </div>
        )}
      </div>

      {/* Footer */}
      {notifications.length > 0 && (
        <div className="p-2 border-t border-border">
          <button
            onClick={handleClearAll}
            disabled={clearAll.isPending}
            className="w-full text-center text-xs text-muted-foreground hover:text-foreground py-1.5 rounded hover:bg-muted disabled:opacity-50"
          >
            Clear all notifications
          </button>
        </div>
      )}

      {/* Invitation Detail Popup */}
      {selectedInvitationNotification && (
        <InvitationDetailPopup
          notification={selectedInvitationNotification}
          onClose={handleInvitationPopupClose}
          onSuccess={handleInvitationSuccess}
        />
      )}
    </div>
  )
}

export default NotificationPanel
