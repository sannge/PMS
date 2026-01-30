/**
 * Notification Utilities
 *
 * Desktop notification helper functions using Electron's native notifications.
 */

/**
 * Request browser notification permission if not already granted.
 * In Electron, this is a no-op since Electron notifications don't require explicit permission.
 */
export function requestNotificationPermission(): void {
  // Electron notifications don't require permission prompts like browser notifications
  // This function exists for API compatibility
}

/**
 * Show a desktop notification using Electron's native notification system.
 */
export function showBrowserNotification(title: string, message: string): void {
  console.log('[Notification] showBrowserNotification called:', { title, message })

  if (!title || !message) {
    console.log('[Notification] Skipped - missing title or message')
    return
  }

  // Use Electron's notification API via preload
  if (window.electronAPI?.showNotification) {
    console.log('[Notification] Calling electronAPI.showNotification')
    window.electronAPI.showNotification({
      title,
      body: message,
      type: 'info',
    }).then((result) => {
      console.log('[Notification] showNotification result:', result)
    }).catch((err) => {
      console.error('[Notification] showNotification error:', err)
    })
  } else {
    console.log('[Notification] electronAPI.showNotification not available')
  }
}
