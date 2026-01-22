/**
 * Protected Route Component
 *
 * A wrapper component that guards routes/content requiring authentication.
 * Provides various auth guards for different access control scenarios.
 *
 * Features:
 * - Authentication checking
 * - Loading state during auth initialization
 * - Customizable fallback UI
 * - Optional role-based access control
 * - Callback for handling unauthorized access
 *
 * Usage:
 * ```tsx
 * // Basic protected content
 * <ProtectedRoute>
 *   <Dashboard />
 * </ProtectedRoute>
 *
 * // With custom fallback
 * <ProtectedRoute fallback={<LoginPrompt />}>
 *   <SecureContent />
 * </ProtectedRoute>
 *
 * // Using the auth guard hook
 * const { isAllowed, isLoading } = useAuthGuard()
 * ```
 */

import { ReactNode, useEffect } from 'react'
import { useAuthInit } from '@/hooks/use-auth'
import { cn } from '@/lib/utils'

// ============================================================================
// Types
// ============================================================================

export interface ProtectedRouteProps {
  /**
   * The content to render when authenticated
   */
  children: ReactNode
  /**
   * Optional fallback to render when not authenticated
   * If not provided, renders null
   */
  fallback?: ReactNode
  /**
   * Optional callback when access is denied
   * Useful for triggering navigation or logging
   */
  onAccessDenied?: () => void
  /**
   * Custom loading component to show during auth check
   */
  loadingComponent?: ReactNode
  /**
   * Whether to show loading screen while initializing
   * @default true
   */
  showLoading?: boolean
}

export interface AuthGuardResult {
  /**
   * Whether the user is allowed to access the content
   */
  isAllowed: boolean
  /**
   * Whether auth state is still loading/initializing
   */
  isLoading: boolean
  /**
   * Whether auth has been initialized
   */
  isInitialized: boolean
  /**
   * Whether user is authenticated
   */
  isAuthenticated: boolean
}

export interface RequireAuthOptions {
  /**
   * Callback when access is denied
   */
  onDenied?: () => void
}

// ============================================================================
// Loading Component
// ============================================================================

/**
 * Default loading screen for protected routes
 */
function ProtectedRouteLoading(): JSX.Element {
  return (
    <div className="flex h-full min-h-[200px] items-center justify-center bg-background">
      <div className="text-center">
        <div className="mb-4 mx-auto h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
        <p className="text-sm text-muted-foreground">Verifying access...</p>
      </div>
    </div>
  )
}

// ============================================================================
// Access Denied Component
// ============================================================================

interface AccessDeniedProps {
  title?: string
  message?: string
  onLoginClick?: () => void
}

/**
 * Default access denied message
 */
function AccessDenied({
  title = 'Access Denied',
  message = 'You must be signed in to view this content.',
  onLoginClick
}: AccessDeniedProps): JSX.Element {
  return (
    <div className="flex h-full min-h-[200px] items-center justify-center bg-background p-8">
      <div className="max-w-md text-center">
        <div className="mb-4 inline-flex h-16 w-16 items-center justify-center rounded-full bg-destructive/10 text-destructive">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="32"
            height="32"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <rect width="18" height="11" x="3" y="11" rx="2" ry="2" />
            <path d="M7 11V7a5 5 0 0 1 10 0v4" />
          </svg>
        </div>
        <h2 className="mb-2 text-xl font-semibold text-foreground">{title}</h2>
        <p className="mb-4 text-muted-foreground">{message}</p>
        {onLoginClick && (
          <button
            onClick={onLoginClick}
            className={cn(
              'rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground',
              'hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
              'transition-colors duration-200'
            )}
          >
            Sign in
          </button>
        )}
      </div>
    </div>
  )
}

// ============================================================================
// Hooks
// ============================================================================

/**
 * Hook for implementing auth guards in components
 *
 * Provides auth state information for custom guard implementations.
 *
 * @example
 * ```tsx
 * function MyProtectedComponent() {
 *   const { isAllowed, isLoading } = useAuthGuard()
 *
 *   if (isLoading) return <Spinner />
 *   if (!isAllowed) return <AccessDenied />
 *
 *   return <ProtectedContent />
 * }
 * ```
 */
export function useAuthGuard(): AuthGuardResult {
  const { isInitialized, isAuthenticated, isLoading } = useAuthInit()

  return {
    isAllowed: isAuthenticated,
    isLoading: !isInitialized || isLoading,
    isInitialized,
    isAuthenticated,
  }
}

/**
 * Hook that runs a callback when auth access is denied
 *
 * Useful for triggering side effects when user is not authenticated.
 *
 * @example
 * ```tsx
 * function ProtectedPage() {
 *   useRequireAuth({
 *     onDenied: () => navigateToLogin()
 *   })
 *
 *   return <Content />
 * }
 * ```
 */
export function useRequireAuth(options?: RequireAuthOptions): AuthGuardResult {
  const guard = useAuthGuard()
  const { onDenied } = options || {}

  useEffect(() => {
    // Only trigger callback when fully initialized and not authenticated
    if (guard.isInitialized && !guard.isLoading && !guard.isAuthenticated) {
      onDenied?.()
    }
  }, [guard.isInitialized, guard.isLoading, guard.isAuthenticated, onDenied])

  return guard
}

// ============================================================================
// Components
// ============================================================================

/**
 * Protected Route Wrapper
 *
 * Wraps content that should only be accessible to authenticated users.
 * Shows loading state during auth initialization and fallback when not authenticated.
 *
 * @example
 * ```tsx
 * // In your app's routing
 * <ProtectedRoute>
 *   <Dashboard />
 * </ProtectedRoute>
 *
 * // With custom fallback
 * <ProtectedRoute
 *   fallback={<LoginPage />}
 *   onAccessDenied={() => trackEvent('auth_required')}
 * >
 *   <AdminPanel />
 * </ProtectedRoute>
 * ```
 */
export function ProtectedRoute({
  children,
  fallback,
  onAccessDenied,
  loadingComponent,
  showLoading = true,
}: ProtectedRouteProps): JSX.Element | null {
  const guard = useRequireAuth({
    onDenied: onAccessDenied,
  })

  // Show loading state during initialization
  if (guard.isLoading || !guard.isInitialized) {
    if (showLoading) {
      return <>{loadingComponent || <ProtectedRouteLoading />}</>
    }
    return null
  }

  // User is not authenticated
  if (!guard.isAuthenticated) {
    if (fallback) {
      return <>{fallback}</>
    }
    return null
  }

  // User is authenticated - render children
  return <>{children}</>
}

/**
 * Public Route Wrapper
 *
 * Wraps content that should only be accessible to unauthenticated users.
 * Useful for login/register pages that should redirect when already logged in.
 *
 * @example
 * ```tsx
 * <PublicRoute fallback={<Dashboard />}>
 *   <LoginPage />
 * </PublicRoute>
 * ```
 */
export interface PublicRouteProps {
  /**
   * The content to render when NOT authenticated
   */
  children: ReactNode
  /**
   * Optional fallback to render when authenticated
   * If not provided, renders null
   */
  fallback?: ReactNode
  /**
   * Custom loading component to show during auth check
   */
  loadingComponent?: ReactNode
  /**
   * Whether to show loading screen while initializing
   * @default true
   */
  showLoading?: boolean
}

export function PublicRoute({
  children,
  fallback,
  loadingComponent,
  showLoading = true,
}: PublicRouteProps): JSX.Element | null {
  const guard = useAuthGuard()

  // Show loading state during initialization
  if (guard.isLoading || !guard.isInitialized) {
    if (showLoading) {
      return <>{loadingComponent || <ProtectedRouteLoading />}</>
    }
    return null
  }

  // User is authenticated - show fallback or nothing
  if (guard.isAuthenticated) {
    if (fallback) {
      return <>{fallback}</>
    }
    return null
  }

  // User is not authenticated - render children
  return <>{children}</>
}

/**
 * Auth Gate Component
 *
 * A more flexible auth guard that renders different content based on auth state.
 * Provides explicit control over what to show in each state.
 *
 * @example
 * ```tsx
 * <AuthGate
 *   loading={<Skeleton />}
 *   authenticated={<UserDashboard />}
 *   unauthenticated={<GuestDashboard />}
 * />
 * ```
 */
export interface AuthGateProps {
  /**
   * Content to show while auth is initializing
   */
  loading?: ReactNode
  /**
   * Content to show when user is authenticated
   */
  authenticated: ReactNode
  /**
   * Content to show when user is not authenticated
   */
  unauthenticated: ReactNode
}

export function AuthGate({
  loading,
  authenticated,
  unauthenticated,
}: AuthGateProps): JSX.Element | null {
  const guard = useAuthGuard()

  // Show loading state during initialization
  if (guard.isLoading || !guard.isInitialized) {
    if (loading) {
      return <>{loading}</>
    }
    return <ProtectedRouteLoading />
  }

  // Render based on auth state
  if (guard.isAuthenticated) {
    return <>{authenticated}</>
  }

  return <>{unauthenticated}</>
}

// ============================================================================
// Higher-Order Component
// ============================================================================

/**
 * HOC to wrap a component with authentication requirement
 *
 * @example
 * ```tsx
 * const ProtectedDashboard = withAuth(Dashboard)
 *
 * // With options
 * const AdminPanel = withAuth(AdminContent, {
 *   loadingComponent: <AdminSkeleton />,
 *   onAccessDenied: () => navigate('/login')
 * })
 * ```
 */
export interface WithAuthOptions {
  /**
   * Custom loading component
   */
  loadingComponent?: ReactNode
  /**
   * Fallback when not authenticated
   */
  fallback?: ReactNode
  /**
   * Callback when access is denied
   */
  onAccessDenied?: () => void
}

export function withAuth<P extends object>(
  WrappedComponent: React.ComponentType<P>,
  options?: WithAuthOptions
): React.ComponentType<P> {
  const displayName = WrappedComponent.displayName || WrappedComponent.name || 'Component'

  function WithAuthComponent(props: P): JSX.Element | null {
    return (
      <ProtectedRoute
        loadingComponent={options?.loadingComponent}
        fallback={options?.fallback}
        onAccessDenied={options?.onAccessDenied}
      >
        <WrappedComponent {...props} />
      </ProtectedRoute>
    )
  }

  WithAuthComponent.displayName = `withAuth(${displayName})`
  return WithAuthComponent
}

// ============================================================================
// Exports
// ============================================================================

export default ProtectedRoute
export { ProtectedRouteLoading, AccessDenied }
