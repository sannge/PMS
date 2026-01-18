/**
 * Notification Panel Component
 *
 * Displays in-app notifications in a slide-out panel.
 * Shows real-time alerts for invitations, member changes, etc.
 * Adapts positioning based on sidebar collapsed state.
 */

import { useEffect, useRef, useState } from 'react'
import { cn } from '@/lib/utils'
import { useAuthStore, getAuthHeaders } from '@/stores/auth-store'
import {
  useNotificationsStore,
  type InAppNotification,
} from '@/stores/notifications-store'
import { useInvitationsStore, type InvitationWithDetails } from '@/stores/invitations-store'
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
// Helper Functions
// ============================================================================

function getNotificationIcon(type: InAppNotification['type']) {
  switch (type) {
    case 'invitation_received':
    case 'application_invite':
      return <Mail className="h-4 w-4 text-blue-500" />
    case 'invitation_accepted':
      return <CheckCircle className="h-4 w-4 text-emerald-500" />
    case 'invitation_rejected':
      return <X className="h-4 w-4 text-red-500" />
    case 'member_added':
    case 'member_joined':
      return <UserPlus className="h-4 w-4 text-blue-500" />
    case 'member_removed':
    case 'member_left':
      return <UserMinus className="h-4 w-4 text-orange-500" />
    case 'role_updated':
    case 'role_changed':
      return <Shield className="h-4 w-4 text-violet-500" />
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

function formatTimeAgo(date: Date): string {
  const now = new Date()
  const diffInSeconds = Math.floor((now.getTime() - date.getTime()) / 1000)

  if (diffInSeconds < 60) {
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
  notification: InAppNotification
  onMarkAsRead: (id: string) => void
  onRemove: (id: string) => void
  onClick?: (notification: InAppNotification) => void
}

function NotificationItem({
  notification,
  onMarkAsRead,
  onRemove,
  onClick,
}: NotificationItemProps) {
  // Check if this is a clickable invitation notification
  const isInvitationNotification =
    notification.type === 'invitation_received' ||
    notification.type === 'application_invite'

  // Check if the invitation is still pending
  // entityStatus will be 'pending', 'accepted', 'rejected', or 'cancelled'
  // If entityStatus is undefined (realtime notifications), treat as pending
  const isPendingInvitation = isInvitationNotification &&
    (!notification.entityStatus || notification.entityStatus === 'pending')

  // Get status label for non-pending invitations
  const getInvitationStatusLabel = () => {
    switch (notification.entityStatus) {
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
        !notification.read && 'bg-accent/5',
        isInvitationNotification && 'cursor-pointer'
      )}
    >
      {/* Unread indicator */}
      {!notification.read && (
        <span className="absolute left-1 top-1/2 -translate-y-1/2 h-2 w-2 rounded-full bg-accent" />
      )}

      {/* Icon */}
      <div className="flex-shrink-0 mt-0.5">
        {getNotificationIcon(notification.type)}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-foreground">
          {notification.title}
        </p>
        <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
          {notification.message}
        </p>
        <div className="flex items-center gap-2 mt-1.5">
          <span className="text-[10px] text-muted-foreground/70">
            {formatTimeAgo(notification.timestamp)}
          </span>
          {notification.source === 'realtime' && (
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-accent/10 text-accent font-medium">
              New
            </span>
          )}
          {isPendingInvitation && (
            <span className="text-[10px] font-medium text-accent">
              Click to respond
            </span>
          )}
          {isInvitationNotification && !isPendingInvitation && (
            <span className={cn(
              "text-[10px] font-medium",
              notification.entityStatus === 'accepted' && 'text-emerald-600 dark:text-emerald-400',
              notification.entityStatus === 'rejected' && 'text-red-600 dark:text-red-400',
              notification.entityStatus === 'cancelled' && 'text-amber-600 dark:text-amber-400'
            )}>
              {getInvitationStatusLabel()}
            </span>
          )}
          {notification.action && (
            <button
              onClick={(e) => {
                e.stopPropagation()
                notification.action?.onClick()
              }}
              className="text-[10px] font-medium text-accent hover:underline"
            >
              {notification.action.label}
            </button>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="flex-shrink-0 flex items-start gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        {!notification.read && (
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
  notification: InAppNotification
  onClose: () => void
  onSuccess: () => void
}

function InvitationDetailPopup({ notification, onClose, onSuccess }: InvitationPopupProps) {
  const token = useAuthStore((state) => state.token)
  const { acceptInvitation, rejectInvitation } = useInvitationsStore()

  const [invitation, setInvitation] = useState<InvitationWithDetails | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isAccepting, setIsAccepting] = useState(false)
  const [isRejecting, setIsRejecting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Get invitation ID from notification
  const invitationId = (notification.data?.invitationId as string | undefined) ||
    (notification.entityType === 'invitation' ? notification.entityId : undefined)

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
    if (!invitationId || isAccepting || isRejecting) return

    setIsAccepting(true)
    setError(null)
    try {
      const success = await acceptInvitation(token, invitationId)
      if (success) {
        onSuccess()
        onClose()
      } else {
        setError('Failed to accept invitation')
      }
    } finally {
      setIsAccepting(false)
    }
  }

  const handleReject = async () => {
    if (!invitationId || isAccepting || isRejecting) return

    setIsRejecting(true)
    setError(null)
    try {
      const success = await rejectInvitation(token, invitationId)
      if (success) {
        onSuccess()
        onClose()
      } else {
        setError('Failed to decline invitation')
      }
    } finally {
      setIsRejecting(false)
    }
  }

  const isProcessing = isAccepting || isRejecting
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
                    {invitation.inviter?.full_name || invitation.inviter?.email || 'Unknown'}
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
              {isRejecting ? (
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
              {isAccepting ? (
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

  // Auth store for token
  const token = useAuthStore((state) => state.token)

  // Notification store
  const isOpen = useNotificationsStore((state) => state.isOpen)
  const notifications = useNotificationsStore((state) => state.notifications)
  const unreadCount = useNotificationsStore((state) => state.unreadCount)
  const isLoading = useNotificationsStore((state) => state.isLoading)
  const isLoadingMore = useNotificationsStore((state) => state.isLoadingMore)
  const hasMore = useNotificationsStore((state) => state.hasMore)
  const setOpen = useNotificationsStore((state) => state.setOpen)
  const markAsRead = useNotificationsStore((state) => state.markAsRead)
  const markAllAsRead = useNotificationsStore((state) => state.markAllAsRead)
  const removeNotification = useNotificationsStore((state) => state.removeNotification)
  const clearAll = useNotificationsStore((state) => state.clearAll)
  const loadMoreNotifications = useNotificationsStore((state) => state.loadMoreNotifications)

  // Invitation popup state
  const [selectedInvitationNotification, setSelectedInvitationNotification] = useState<InAppNotification | null>(null)

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

  // Infinite scroll - load more when scrolling near bottom
  useEffect(() => {
    const scrollContainer = scrollContainerRef.current
    if (!scrollContainer || !isOpen) return

    const handleScroll = () => {
      const { scrollTop, scrollHeight, clientHeight } = scrollContainer
      // Load more when user scrolls within 100px of bottom
      if (scrollHeight - scrollTop - clientHeight < 100) {
        if (hasMore && !isLoadingMore && token) {
          loadMoreNotifications(token)
        }
      }
    }

    scrollContainer.addEventListener('scroll', handleScroll)
    return () => scrollContainer.removeEventListener('scroll', handleScroll)
  }, [isOpen, hasMore, isLoadingMore, token, loadMoreNotifications])

  // Handlers with token
  const handleMarkAsRead = (id: string) => {
    markAsRead(id, token)
  }

  const handleMarkAllAsRead = () => {
    markAllAsRead(token)
  }

  const handleRemove = (id: string) => {
    removeNotification(id, token)
  }

  const handleClearAll = () => {
    clearAll(token)
  }

  // Handle invitation notification click
  const handleInvitationClick = (notification: InAppNotification) => {
    setSelectedInvitationNotification(notification)
    // Mark as read when opened
    if (!notification.read) {
      markAsRead(notification.id, token)
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
      removeNotification(selectedInvitationNotification.id, token)
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
              className="text-[10px] font-medium text-muted-foreground hover:text-foreground px-2 py-1 rounded hover:bg-muted"
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

      {/* Content */}
      <div ref={scrollContainerRef} className="max-h-96 overflow-y-auto">
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
            {/* Loading more indicator */}
            {isLoadingMore && (
              <div className="flex items-center justify-center py-3">
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                <span className="ml-2 text-xs text-muted-foreground">Loading more...</span>
              </div>
            )}
            {/* End of list indicator */}
            {!hasMore && notifications.length > 0 && (
              <div className="text-center py-3 text-xs text-muted-foreground/70">
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
            className="w-full text-center text-xs text-muted-foreground hover:text-foreground py-1.5 rounded hover:bg-muted"
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
