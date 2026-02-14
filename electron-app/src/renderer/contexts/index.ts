/**
 * Contexts
 *
 * Re-exports all React Context providers and hooks.
 */

// Auth context
export {
  AuthProvider,
  useAuthStore,
  getAuthHeaders,
  selectUser,
  selectIsAuthenticated,
  selectIsLoading,
  selectIsInitialized,
  selectError,
  type User,
  type LoginCredentials,
  type RegisterData,
  type TokenResponse,
  type AuthError,
} from './auth-context'

// Notification UI context
export {
  NotificationUIProvider,
  useNotificationUIStore,
} from './notification-ui-context'

