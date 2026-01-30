/**
 * Notification UI Store (Re-export)
 *
 * This file re-exports from the notification-ui-context for backward compatibility.
 * The actual implementation has been migrated from Zustand to React Context.
 */

export {
  NotificationUIProvider,
  useNotificationUIStore,
} from '../contexts/notification-ui-context'

// Re-export useNotificationUIStore as default for backward compatibility
import { useNotificationUIStore as _useNotificationUIStore } from '../contexts/notification-ui-context'
export default _useNotificationUIStore
