/**
 * Desktop Notifications Module
 *
 * This module handles native desktop notifications using Electron's Notification API.
 * It provides functionality to:
 * - Show native system notifications
 * - Handle notification clicks
 * - Forward notification events to the renderer process
 * - Support for different notification types (info, success, warning, error)
 *
 * Security considerations:
 * - Notification content is sanitized
 * - Only allowed notification types are supported
 */

import { Notification, BrowserWindow, ipcMain, nativeImage, app } from 'electron'
import { join } from 'path'

/**
 * Notification payload interface matching the preload types
 */
export interface NotificationPayload {
  id: string
  type: string
  title: string
  message: string
  entityType?: string
  entityId?: string
  timestamp: string
}

/**
 * Options for showing a notification
 */
export interface ShowNotificationOptions {
  id?: string
  type?: 'info' | 'success' | 'warning' | 'error' | 'task' | 'mention' | 'comment'
  title: string
  body: string
  entityType?: string
  entityId?: string
  silent?: boolean
  urgency?: 'normal' | 'critical' | 'low'
  timeoutType?: 'default' | 'never'
}

/**
 * Notification result returned to renderer
 */
interface NotificationResult {
  id: string
  clicked: boolean
  closed: boolean
}

// Store for active notifications
const activeNotifications = new Map<string, Notification>()

// Counter for generating unique IDs
let notificationCounter = 0

/**
 * Generates a unique notification ID
 */
function generateNotificationId(): string {
  notificationCounter += 1
  return `notification-${Date.now()}-${notificationCounter}`
}

/**
 * Gets the app icon for notifications
 * Returns undefined if no icon is available (uses system default)
 */
function getNotificationIcon(): Electron.NativeImage | undefined {
  try {
    // Try to load app icon from resources
    const iconPath = join(__dirname, '../../resources/icon.png')
    const icon = nativeImage.createFromPath(iconPath)
    if (!icon.isEmpty()) {
      return icon
    }
  } catch {
    // Icon not found, will use system default
  }
  return undefined
}

/**
 * Gets the focused BrowserWindow or first available window
 */
function getMainWindow(): BrowserWindow | null {
  return BrowserWindow.getFocusedWindow() || BrowserWindow.getAllWindows()[0] || null
}

/**
 * Checks if notifications are supported on the current platform
 */
export function isNotificationSupported(): boolean {
  return Notification.isSupported()
}

/**
 * Shows a native desktop notification
 *
 * @param options - Notification options
 * @returns Promise resolving to notification result
 */
export async function showNotification(
  options: ShowNotificationOptions
): Promise<NotificationResult> {
  const {
    id = generateNotificationId(),
    type = 'info',
    title,
    body,
    entityType,
    entityId,
    silent = false,
    urgency = 'normal',
    timeoutType = 'default'
  } = options

  console.log('[Main-Notification] showNotification called:', { title, body, type })

  // Check if notifications are supported
  if (!Notification.isSupported()) {
    console.log('[Main-Notification] Notifications not supported on this platform')
    return { id, clicked: false, closed: true }
  }
  console.log('[Main-Notification] Notifications are supported')

  return new Promise((resolve) => {
    const icon = getNotificationIcon()

    // Create notification options
    const notificationOptions: Electron.NotificationConstructorOptions = {
      title: sanitizeText(title),
      body: sanitizeText(body),
      silent,
      urgency,
      timeoutType
    }

    // Add icon if available
    if (icon) {
      notificationOptions.icon = icon
    }

    // Create the notification
    console.log('[Main-Notification] Creating notification with options:', notificationOptions)
    const notification = new Notification(notificationOptions)

    // Store reference
    activeNotifications.set(id, notification)
    console.log('[Main-Notification] Notification created, calling show()')

    // Handle notification click
    notification.on('click', () => {
      const mainWindow = getMainWindow()

      // Bring app to foreground
      if (mainWindow) {
        if (mainWindow.isMinimized()) {
          mainWindow.restore()
        }
        mainWindow.focus()

        // Send notification payload to renderer
        const payload: NotificationPayload = {
          id,
          type,
          title,
          message: body,
          entityType,
          entityId,
          timestamp: new Date().toISOString()
        }

        mainWindow.webContents.send('notification', payload)
      }

      // Clean up
      activeNotifications.delete(id)
      resolve({ id, clicked: true, closed: false })
    })

    // Handle notification close
    notification.on('close', () => {
      activeNotifications.delete(id)
      resolve({ id, clicked: false, closed: true })
    })

    // Handle notification failed
    notification.on('failed', (_event, error) => {
      console.error('[Main-Notification] Notification failed:', error)
      activeNotifications.delete(id)
      resolve({ id, clicked: false, closed: true })
    })

    // Show the notification
    notification.show()
    console.log('[Main-Notification] notification.show() called')
  })
}

/**
 * Closes a specific notification by ID
 *
 * @param id - Notification ID to close
 */
export function closeNotification(id: string): void {
  const notification = activeNotifications.get(id)
  if (notification) {
    notification.close()
    activeNotifications.delete(id)
  }
}

/**
 * Closes all active notifications
 */
export function closeAllNotifications(): void {
  activeNotifications.forEach((notification, id) => {
    notification.close()
    activeNotifications.delete(id)
  })
}

/**
 * Sanitizes text to prevent injection
 */
function sanitizeText(text: string): string {
  if (typeof text !== 'string') {
    return ''
  }
  // Limit length to prevent overly long notifications
  return text.slice(0, 256).trim()
}

/**
 * Validates notification type
 */
function isValidNotificationType(
  type: string
): type is 'info' | 'success' | 'warning' | 'error' | 'task' | 'mention' | 'comment' {
  const validTypes = ['info', 'success', 'warning', 'error', 'task', 'mention', 'comment']
  return validTypes.includes(type)
}

/**
 * Registers IPC handlers for notifications
 * This allows the renderer process to trigger notifications
 */
export function registerNotificationHandlers(): void {
  // Show notification handler
  ipcMain.handle(
    'notifications:show',
    async (
      _event,
      options: {
        title: string
        body: string
        type?: string
        entityType?: string
        entityId?: string
        silent?: boolean
      }
    ) => {
      // Validate required fields
      if (!options.title || typeof options.title !== 'string') {
        throw new Error('Notification title is required')
      }
      if (!options.body || typeof options.body !== 'string') {
        throw new Error('Notification body is required')
      }

      // Validate type if provided
      const type = options.type && isValidNotificationType(options.type) ? options.type : 'info'

      return showNotification({
        title: options.title,
        body: options.body,
        type,
        entityType: options.entityType,
        entityId: options.entityId,
        silent: options.silent
      })
    }
  )

  // Check if notifications are supported
  ipcMain.handle('notifications:isSupported', () => {
    return Notification.isSupported()
  })

  // Close specific notification
  ipcMain.handle('notifications:close', (_event, { id }: { id: string }) => {
    if (!id || typeof id !== 'string') {
      throw new Error('Invalid notification ID')
    }
    closeNotification(id)
    return { success: true }
  })

  // Close all notifications
  ipcMain.handle('notifications:closeAll', () => {
    closeAllNotifications()
    return { success: true }
  })
}

/**
 * Removes all notification IPC handlers
 * Useful for cleanup during testing or hot-reloading
 */
export function removeNotificationHandlers(): void {
  const handlers = [
    'notifications:show',
    'notifications:isSupported',
    'notifications:close',
    'notifications:closeAll'
  ]

  handlers.forEach((channel) => {
    ipcMain.removeHandler(channel)
  })
}

/**
 * Sends a notification event to the renderer process
 * Used for pushing notifications from main process (e.g., from WebSocket)
 *
 * @param payload - Notification payload to send
 */
export function sendNotificationToRenderer(payload: NotificationPayload): void {
  const mainWindow = getMainWindow()
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('notification', payload)
  }
}

/**
 * Shows a notification and sends it to the renderer
 * Convenience function for internal use
 *
 * @param options - Notification options
 */
export async function notifyUser(options: ShowNotificationOptions): Promise<void> {
  // Show native notification
  await showNotification(options)

  // Also send to renderer for in-app notification display
  const payload: NotificationPayload = {
    id: options.id || generateNotificationId(),
    type: options.type || 'info',
    title: options.title,
    message: options.body,
    entityType: options.entityType,
    entityId: options.entityId,
    timestamp: new Date().toISOString()
  }

  sendNotificationToRenderer(payload)
}

/**
 * Pre-defined notification helpers for common scenarios
 */
export const notifications = {
  /**
   * Shows an info notification
   */
  info: (title: string, body: string) =>
    showNotification({ title, body, type: 'info' }),

  /**
   * Shows a success notification
   */
  success: (title: string, body: string) =>
    showNotification({ title, body, type: 'success' }),

  /**
   * Shows a warning notification
   */
  warning: (title: string, body: string) =>
    showNotification({ title, body, type: 'warning', urgency: 'critical' }),

  /**
   * Shows an error notification
   */
  error: (title: string, body: string) =>
    showNotification({ title, body, type: 'error', urgency: 'critical' }),

  /**
   * Shows a task-related notification
   */
  task: (title: string, body: string, taskId: string) =>
    showNotification({ title, body, type: 'task', entityType: 'task', entityId: taskId }),

  /**
   * Shows a mention notification
   */
  mention: (title: string, body: string, entityType?: string, entityId?: string) =>
    showNotification({ title, body, type: 'mention', entityType, entityId }),

  /**
   * Shows a comment notification
   */
  comment: (title: string, body: string, entityType?: string, entityId?: string) =>
    showNotification({ title, body, type: 'comment', entityType, entityId })
}

export default {
  showNotification,
  closeNotification,
  closeAllNotifications,
  isNotificationSupported,
  registerNotificationHandlers,
  removeNotificationHandlers,
  sendNotificationToRenderer,
  notifyUser,
  notifications
}
