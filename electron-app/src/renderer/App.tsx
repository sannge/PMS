/**
 * Root React Component
 *
 * This is the main application component that serves as the entry point
 * for the React application. It provides:
 * - Error boundary for graceful error handling
 * - Theme context for dark/light mode
 * - Authentication state management
 * - Simple state-based routing (login, register, main app)
 */
import { Component, createContext, useContext, useEffect, useState, useCallback, ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { useAuthInit, useAuth } from '@/hooks/use-auth'
import { LoginPage } from '@/pages/login'
import { RegisterPage } from '@/pages/register'

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

interface AppInfo {
  name: string
  version: string
  platform: string
  electronVersion: string
  nodeVersion: string
  chromeVersion: string
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
// Welcome Screen Component (Temporary - will be replaced by dashboard)
// ============================================================================

interface WelcomeScreenProps {
  onLogout?: () => Promise<void>
}

function WelcomeScreen({ onLogout }: WelcomeScreenProps): JSX.Element {
  const { theme, setTheme, resolvedTheme } = useTheme()
  const [appInfo, setAppInfo] = useState<AppInfo | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isLoggingOut, setIsLoggingOut] = useState(false)

  useEffect(() => {
    const fetchAppInfo = async (): Promise<void> => {
      try {
        // Check if electronAPI is available (running in Electron)
        if (window.electronAPI) {
          const [name, version] = await Promise.all([
            window.electronAPI.getAppName(),
            window.electronAPI.getAppVersion()
          ])

          setAppInfo({
            name,
            version,
            platform: window.electronAPI.platform,
            electronVersion: window.electronAPI.versions.electron,
            nodeVersion: window.electronAPI.versions.node,
            chromeVersion: window.electronAPI.versions.chrome
          })
        } else {
          // Running in browser (development without Electron)
          setAppInfo({
            name: 'PM Desktop',
            version: '1.0.0',
            platform: 'web',
            electronVersion: 'N/A',
            nodeVersion: 'N/A',
            chromeVersion: 'N/A'
          })
        }
      } catch {
        // Fallback if API calls fail
        setAppInfo({
          name: 'PM Desktop',
          version: '1.0.0',
          platform: 'unknown',
          electronVersion: 'N/A',
          nodeVersion: 'N/A',
          chromeVersion: 'N/A'
        })
      } finally {
        setIsLoading(false)
      }
    }

    fetchAppInfo()
  }, [])

  const cycleTheme = (): void => {
    const themes: Theme[] = ['light', 'dark', 'system']
    const currentIndex = themes.indexOf(theme)
    const nextIndex = (currentIndex + 1) % themes.length
    setTheme(themes[nextIndex])
  }

  const handleLogout = async (): Promise<void> => {
    if (onLogout) {
      setIsLoggingOut(true)
      try {
        await onLogout()
      } finally {
        setIsLoggingOut(false)
      }
    }
  }

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center bg-background">
        <div className="text-center">
          <div className="mb-4 h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
          <p className="text-muted-foreground">Loading...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col bg-background">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-border px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-primary-foreground font-bold text-lg">
            PM
          </div>
          <div>
            <h1 className="text-lg font-semibold text-foreground">
              {appInfo?.name || 'PM Desktop'}
            </h1>
            <p className="text-xs text-muted-foreground">
              Project Management Application
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={cycleTheme}
            className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
            title={`Current theme: ${theme}`}
          >
            {resolvedTheme === 'dark' ? (
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
              </svg>
            ) : (
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="5" />
                <line x1="12" y1="1" x2="12" y2="3" />
                <line x1="12" y1="21" x2="12" y2="23" />
                <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
                <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
                <line x1="1" y1="12" x2="3" y2="12" />
                <line x1="21" y1="12" x2="23" y2="12" />
                <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
                <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
              </svg>
            )}
            <span className="capitalize">{theme}</span>
          </button>
          {onLogout && (
            <button
              onClick={handleLogout}
              disabled={isLoggingOut}
              className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive hover:border-destructive/50 disabled:opacity-50 disabled:cursor-not-allowed"
              title="Sign out"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                <polyline points="16 17 21 12 16 7" />
                <line x1="21" y1="12" x2="9" y2="12" />
              </svg>
              <span>{isLoggingOut ? 'Signing out...' : 'Sign out'}</span>
            </button>
          )}
        </div>
      </header>

      {/* Main Content */}
      <main className="flex flex-1 items-center justify-center p-8">
        <div className="max-w-2xl text-center">
          <div className="mb-8">
            <div className="mb-4 inline-flex h-20 w-20 items-center justify-center rounded-2xl bg-primary/10 text-primary">
              <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                <polyline points="22 4 12 14.01 9 11.01" />
              </svg>
            </div>
            <h2 className="mb-2 text-3xl font-bold text-foreground">
              Application Initialized Successfully
            </h2>
            <p className="text-lg text-muted-foreground">
              Electron + React + Tailwind CSS + ShadCN UI
            </p>
          </div>

          {/* Feature Cards */}
          <div className="mb-8 grid gap-4 sm:grid-cols-3">
            <FeatureCard
              icon={
                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
                  <line x1="8" y1="21" x2="16" y2="21" />
                  <line x1="12" y1="17" x2="12" y2="21" />
                </svg>
              }
              title="Desktop Ready"
              description="Native Electron app with secure IPC"
            />
            <FeatureCard
              icon={
                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="2" y1="12" x2="22" y2="12" />
                  <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
                </svg>
              }
              title="React 18"
              description="Modern React with concurrent features"
            />
            <FeatureCard
              icon={
                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" />
                </svg>
              }
              title="Dark Mode"
              description="System-aware theme switching"
            />
          </div>

          {/* System Info */}
          {appInfo && (
            <div className="rounded-lg border border-border bg-card p-4">
              <h3 className="mb-3 text-sm font-medium text-foreground">System Information</h3>
              <div className="grid gap-2 text-sm sm:grid-cols-2">
                <InfoRow label="Version" value={appInfo.version} />
                <InfoRow label="Platform" value={appInfo.platform} />
                <InfoRow label="Electron" value={appInfo.electronVersion} />
                <InfoRow label="Node.js" value={appInfo.nodeVersion} />
                <InfoRow label="Chrome" value={appInfo.chromeVersion} />
                <InfoRow label="Theme" value={theme} />
              </div>
            </div>
          )}
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-border px-6 py-3 text-center text-xs text-muted-foreground">
        Ready for authentication and navigation setup
      </footer>
    </div>
  )
}

// ============================================================================
// Helper Components
// ============================================================================

interface FeatureCardProps {
  icon: ReactNode
  title: string
  description: string
}

function FeatureCard({ icon, title, description }: FeatureCardProps): JSX.Element {
  return (
    <div className="rounded-lg border border-border bg-card p-4 text-left transition-colors hover:bg-accent/50">
      <div className="mb-2 text-primary">{icon}</div>
      <h3 className="font-medium text-foreground">{title}</h3>
      <p className="text-sm text-muted-foreground">{description}</p>
    </div>
  )
}

interface InfoRowProps {
  label: string
  value: string
}

function InfoRow({ label, value }: InfoRowProps): JSX.Element {
  return (
    <div className="flex justify-between rounded bg-muted/50 px-3 py-1.5">
      <span className="text-muted-foreground">{label}</span>
      <span className={cn('selectable font-medium text-foreground')}>{value}</span>
    </div>
  )
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
// Auth Router Component
// ============================================================================

/**
 * Handles routing between auth pages and main application
 * Based on authentication state
 */
function AuthRouter(): JSX.Element {
  const { isInitialized, isAuthenticated, isLoading } = useAuthInit()
  const { user, logout } = useAuth()
  const [authView, setAuthView] = useState<AuthView>('login')

  // Navigation handlers
  const navigateToRegister = useCallback(() => {
    setAuthView('register')
  }, [])

  const navigateToLogin = useCallback(() => {
    setAuthView('login')
  }, [])

  // Show loading screen while auth is initializing
  if (!isInitialized || isLoading) {
    return <LoadingScreen />
  }

  // Show auth pages if not authenticated
  if (!isAuthenticated) {
    if (authView === 'register') {
      return <RegisterPage onNavigateToLogin={navigateToLogin} />
    }
    return <LoginPage onNavigateToRegister={navigateToRegister} />
  }

  // User is authenticated - show main application
  // WelcomeScreen is a temporary placeholder until dashboard is implemented
  return <WelcomeScreen onLogout={logout} />
}

// ============================================================================
// Main App Component
// ============================================================================

/**
 * Root Application Component
 *
 * This component wraps the entire application with necessary providers:
 * - ThemeProvider: Manages dark/light mode
 * - ErrorBoundary: Catches and displays rendering errors
 * - AuthRouter: Handles authentication-based routing
 */
function App(): JSX.Element {
  return (
    <ThemeProvider>
      <ErrorBoundary>
        <AuthRouter />
      </ErrorBoundary>
    </ThemeProvider>
  )
}

export default App
