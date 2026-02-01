/**
 * Root React Component
 *
 * This is the main application component that serves as the entry point
 * for the React application. It provides:
 * - Error boundary for graceful error handling
 * - Theme context for dark/light mode
 * - Authentication state management
 * - Simple state-based routing (login, register, main app)
 * - TanStack Query client provider with IndexedDB persistence
 * - WebSocket cache invalidation
 */
import { Component, createContext, useContext, useEffect, useState, useCallback, useRef, ReactNode } from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { LoginPage } from '@/pages/login'
import { RegisterPage } from '@/pages/register'
import { DashboardPage } from '@/pages/dashboard'
import { AuthGate } from '@/components/protected-route'
import { queryClient, initializeQueryPersistence, clearQueryCache } from '@/lib/query-client'
import { AuthProvider, useAuthStore, NotificationUIProvider } from '@/contexts'

// ============================================================================
// Types
// ============================================================================

type Theme = 'light' | 'dark' | 'system'
type AuthView = 'login' | 'register'

interface ThemeContextValue {
  theme: Theme
  setTheme: (theme: Theme) => void
  resolvedTheme: 'light' | 'dark'
}

interface ErrorBoundaryProps {
  children: ReactNode
  fallback?: ReactNode
}

interface ErrorBoundaryState {
  hasError: boolean
  error?: Error
}

// ============================================================================
// Theme Context
// ============================================================================

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined)

/**
 * Hook to access theme context
 */
export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext)
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider')
  }
  return context
}

/**
 * Theme provider component that manages dark/light mode
 */
function ThemeProvider({ children }: { children: ReactNode }): JSX.Element {
  const [theme, setTheme] = useState<Theme>(() => {
    // Try to get saved theme from localStorage
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('pm-desktop-theme') as Theme | null
      if (saved && ['light', 'dark', 'system'].includes(saved)) {
        return saved
      }
    }
    return 'system'
  })

  const [resolvedTheme, setResolvedTheme] = useState<'light' | 'dark'>('light')

  useEffect(() => {
    // Save theme preference
    localStorage.setItem('pm-desktop-theme', theme)

    // Determine resolved theme
    let resolved: 'light' | 'dark'
    if (theme === 'system') {
      resolved = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
    } else {
      resolved = theme
    }
    setResolvedTheme(resolved)

    // Apply theme to document
    const root = document.documentElement
    root.classList.remove('light', 'dark')
    root.classList.add(resolved)
  }, [theme])

  // Listen for system theme changes
  useEffect(() => {
    if (theme !== 'system') return

    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    const handleChange = (e: MediaQueryListEvent): void => {
      setResolvedTheme(e.matches ? 'dark' : 'light')
      document.documentElement.classList.remove('light', 'dark')
      document.documentElement.classList.add(e.matches ? 'dark' : 'light')
    }

    mediaQuery.addEventListener('change', handleChange)
    return () => mediaQuery.removeEventListener('change', handleChange)
  }, [theme])

  return (
    <ThemeContext.Provider value={{ theme, setTheme, resolvedTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}

// ============================================================================
// Error Boundary
// ============================================================================

/**
 * Error boundary component to catch and display React rendering errors
 */
class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback
      }

      return (
        <div className="flex h-full items-center justify-center bg-background p-8">
          <div className="max-w-md text-center">
            <div className="mb-4 text-6xl">:(</div>
            <h1 className="mb-2 text-2xl font-bold text-foreground">Something went wrong</h1>
            <p className="mb-4 text-muted-foreground">
              An unexpected error occurred. Please try refreshing the application.
            </p>
            {this.state.error && (
              <pre className="selectable mb-4 overflow-auto rounded-lg bg-muted p-4 text-left text-sm text-muted-foreground">
                {this.state.error.message}
              </pre>
            )}
            <button
              onClick={() => window.location.reload()}
              className="rounded-lg bg-primary px-4 py-2 text-primary-foreground transition-colors hover:bg-primary/90"
            >
              Reload Application
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}

// ============================================================================
// Loading Screen Component
// ============================================================================

/**
 * Loading screen shown during auth initialization
 */
function LoadingScreen(): JSX.Element {
  return (
    <div className="flex h-full items-center justify-center bg-background">
      <div className="text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-primary text-primary-foreground font-bold text-xl">
          PM
        </div>
        <div className="mb-4 h-8 w-8 mx-auto animate-spin rounded-full border-4 border-primary border-t-transparent" />
        <p className="text-muted-foreground">Loading...</p>
      </div>
    </div>
  )
}

// ============================================================================
// Auth Pages Component
// ============================================================================

/**
 * Handles switching between login and register pages
 * Used within PublicRoute to show auth forms when not logged in
 */
function AuthPages(): JSX.Element {
  const [authView, setAuthView] = useState<AuthView>('login')

  // Navigation handlers
  const navigateToRegister = useCallback(() => {
    setAuthView('register')
  }, [])

  const navigateToLogin = useCallback(() => {
    setAuthView('login')
  }, [])

  if (authView === 'register') {
    return <RegisterPage onNavigateToLogin={navigateToLogin} />
  }
  return <LoginPage onNavigateToRegister={navigateToRegister} />
}

// ============================================================================
// Cache Clear on Logout Hook
// ============================================================================

/**
 * Hook that clears query cache when user logs out.
 * This ensures sensitive data is not persisted after logout.
 */
function useCacheClearOnLogout(): void {
  const token = useAuthStore((s) => s.token)
  const prevTokenRef = useRef<string | null>(null)

  useEffect(() => {
    // Check if user just logged out (had token, now doesn't)
    if (prevTokenRef.current !== null && token === null) {
      clearQueryCache()
    }
    prevTokenRef.current = token
  }, [token])
}

// ============================================================================
// Authenticated App Component
// ============================================================================

/**
 * The main application content shown when user is authenticated
 * Renders the dashboard layout with sidebar navigation
 *
 * Note: WebSocket cache invalidation is handled in DashboardPage
 * so it has access to navigation state for member removal redirect.
 */
function AuthenticatedApp(): JSX.Element {
  const { theme, setTheme } = useTheme()

  return <DashboardPage theme={theme} onThemeChange={setTheme} />
}

// ============================================================================
// Auth Router Component
// ============================================================================

/**
 * Handles routing between auth pages and main application
 * Based on authentication state
 *
 * Uses the ProtectedRoute and PublicRoute components for auth guards.
 * The AuthGate component provides a declarative way to show different
 * content based on authentication state.
 */
function AuthRouter(): JSX.Element {
  return (
    <AuthGate
      loading={<LoadingScreen />}
      authenticated={<AuthenticatedApp />}
      unauthenticated={<AuthPages />}
    />
  )
}

// ============================================================================
// Query Client Initializer Component
// ============================================================================

/**
 * Initializes query persistence on mount.
 * Also clears cache on logout.
 */
function QueryClientInitializer({ children }: { children: ReactNode }): JSX.Element {
  const [isReady, setIsReady] = useState(false)

  // Clear cache on logout
  useCacheClearOnLogout()

  useEffect(() => {
    // Initialize IndexedDB persistence
    initializeQueryPersistence()
      .then(() => setIsReady(true))
      .catch((error) => {
        console.warn('[QueryClient] Persistence init failed:', error)
        setIsReady(true) // Continue without persistence
      })
  }, [])

  // Show loading until persistence is ready
  // This prevents flash of stale UI on refresh
  if (!isReady) {
    return (
      <div className="flex h-full items-center justify-center bg-background">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    )
  }

  return <>{children}</>
}

// ============================================================================
// Main App Component
// ============================================================================

/**
 * Root Application Component
 *
 * This component wraps the entire application with necessary providers:
 * - QueryClientProvider: TanStack Query client with IndexedDB persistence
 * - ThemeProvider: Manages dark/light mode
 * - ErrorBoundary: Catches and displays rendering errors
 * - AuthRouter: Handles authentication-based routing
 */
function App(): JSX.Element {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <NotificationUIProvider>
          <ThemeProvider>
            <ErrorBoundary>
              <QueryClientInitializer>
                <AuthRouter />
              </QueryClientInitializer>
            </ErrorBoundary>
          </ThemeProvider>
        </NotificationUIProvider>
      </AuthProvider>
      {/* React Query Devtools - only shown in development */}
      {import.meta.env.DEV && <ReactQueryDevtools initialIsOpen={false} />}
    </QueryClientProvider>
  )
}

export default App
