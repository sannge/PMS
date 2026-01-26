/**
 * Notification Utilities
 *
 * Browser notification helper functions.
 */

/**
 * Request browser notification permission if not already granted.
 * Safe to call multiple times - only prompts when permission is 'default'.
 */
export function requestNotificationPermission(): void {
  if (typeof Notification !== 'undefined' && Notification.permission === 'default') {
    Notification.requestPermission()
  }
}

/**
 * Show a browser notification if permission is granted.
 */
export function showBrowserNotification(title: string, message: string): void {
  if (typeof Notification === 'undefined') return
  if (Notification.permission !== 'granted') return

  try {
    new Notification(title, {
      body: message,
      icon: '/icon.png',
      tag: 'pm-notification',
    })
  } catch {
    // Ignore notification errors
  }
}
