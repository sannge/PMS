/**
 * Authentication Store (Re-export)
 *
 * This file re-exports from the auth-context for backward compatibility.
 * The actual implementation has been migrated from Zustand to React Context.
 */

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
} from '../contexts/auth-context'

// Re-export useAuthStore as default for backward compatibility
import { useAuthStore as _useAuthStore } from '../contexts/auth-context'
export default _useAuthStore
