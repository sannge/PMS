/**
 * Header Component
 *
 * Top navigation bar for the application dashboard.
 * Features:
 * - Page title display
 * - Search functionality (placeholder for future)
 * - Theme toggle
 * - User menu with logout
 * - Notification indicator
 */

import { useState, useCallback, ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { useAuth, useCurrentUser } from '@/hooks/use-auth'
import {
  Search,
  Sun,
  Moon,
  Monitor,
  Bell,
  LogOut,
  User,
  ChevronDown,
} from 'lucide-react'

// ============================================================================
// Types
// ============================================================================

type Theme = 'light' | 'dark' | 'system'

export interface HeaderProps {
  /**
   * Page title to display
   */
  title?: string
  /**
   * Current theme
   */
  theme?: Theme
  /**
   * Callback when theme is changed
   */
  onThemeChange?: (theme: Theme) => void
  /**
   * Optional className for the header container
   */
  className?: string
  /**
   * Optional breadcrumb or subtitle
   */
  subtitle?: ReactNode
}

// ============================================================================
// Theme Icon Component
// ============================================================================

function ThemeIcon({ theme }: { theme: Theme }): JSX.Element {
  switch (theme) {
    case 'dark':
      return <Moon className="h-4 w-4" />
    case 'light':
      return <Sun className="h-4 w-4" />
    default:
      return <Monitor className="h-4 w-4" />
  }
}

// ============================================================================
// User Menu Component
// ============================================================================

interface UserMenuProps {
  onLogout: () => Promise<void>
  isLoading?: boolean
}

function UserMenu({ onLogout, isLoading }: UserMenuProps): JSX.Element {
  const [isOpen, setIsOpen] = useState(false)
  const user = useCurrentUser()

  const handleLogout = useCallback(async () => {
    setIsOpen(false)
    await onLogout()
  }, [onLogout])

  const toggleMenu = useCallback(() => {
    setIsOpen((prev) => !prev)
  }, [])

  const closeMenu = useCallback(() => {
    setIsOpen(false)
  }, [])

  // Get user initials for avatar
  const getInitials = (name?: string, email?: string): string => {
    if (name) {
      const parts = name.split(' ')
      if (parts.length >= 2) {
        return `${parts[0][0]}${parts[1][0]}`.toUpperCase()
      }
      return name.substring(0, 2).toUpperCase()
    }
    if (email) {
      return email.substring(0, 2).toUpperCase()
    }
    return 'U'
  }

  return (
    <div className="relative">
      <button
        onClick={toggleMenu}
        className={cn(
          'flex items-center gap-2 rounded-lg border border-border px-2 py-1.5 text-sm',
          'hover:bg-accent hover:text-accent-foreground transition-colors',
          'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2'
        )}
      >
        <div className="flex h-7 w-7 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
          {getInitials(user?.display_name, user?.email)}
        </div>
        <span className="hidden max-w-[100px] truncate text-foreground sm:block">
          {user?.display_name || user?.email || 'User'}
        </span>
        <ChevronDown className={cn(
          'h-4 w-4 text-muted-foreground transition-transform',
          isOpen && 'rotate-180'
        )} />
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-40"
            onClick={closeMenu}
          />

          {/* Menu */}
          <div className="absolute right-0 top-full z-50 mt-2 w-56 rounded-lg border border-border bg-card shadow-lg">
            {/* User Info */}
            <div className="border-b border-border p-3">
              <p className="text-sm font-medium text-foreground truncate">
                {user?.display_name || 'User'}
              </p>
              <p className="text-xs text-muted-foreground truncate">
                {user?.email}
              </p>
            </div>

            {/* Menu Items */}
            <div className="p-1">
              <button
                onClick={() => setIsOpen(false)}
                className={cn(
                  'flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-foreground',
                  'hover:bg-accent hover:text-accent-foreground transition-colors'
                )}
              >
                <User className="h-4 w-4" />
                Profile
              </button>

              <button
                onClick={handleLogout}
                disabled={isLoading}
                className={cn(
                  'flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm',
                  'text-destructive hover:bg-destructive/10 transition-colors',
                  'disabled:opacity-50 disabled:cursor-not-allowed'
                )}
              >
                <LogOut className="h-4 w-4" />
                {isLoading ? 'Signing out...' : 'Sign out'}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

// ============================================================================
// Header Component
// ============================================================================

export function Header({
  title = 'Dashboard',
  theme = 'system',
  onThemeChange,
  className,
  subtitle,
}: HeaderProps): JSX.Element {
  const { logout, isLoading } = useAuth()
  const [isThemeMenuOpen, setIsThemeMenuOpen] = useState(false)

  // Cycle through themes
  const cycleTheme = useCallback(() => {
    const themes: Theme[] = ['light', 'dark', 'system']
    const currentIndex = themes.indexOf(theme)
    const nextIndex = (currentIndex + 1) % themes.length
    onThemeChange?.(themes[nextIndex])
  }, [theme, onThemeChange])

  // Handle theme selection from dropdown
  const selectTheme = useCallback((newTheme: Theme) => {
    onThemeChange?.(newTheme)
    setIsThemeMenuOpen(false)
  }, [onThemeChange])

  return (
    <header
      className={cn(
        'flex items-center justify-between border-b border-border bg-background px-6 py-3',
        className
      )}
    >
      {/* Left Section - Title */}
      <div className="flex flex-col">
        <h1 className="text-xl font-semibold text-foreground">{title}</h1>
        {subtitle && (
          <div className="text-sm text-muted-foreground">{subtitle}</div>
        )}
      </div>

      {/* Right Section - Actions */}
      <div className="flex items-center gap-2">
        {/* Search */}
        <div className="relative hidden sm:block">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search..."
            className={cn(
              'w-48 rounded-md border border-input bg-background py-1.5 pl-9 pr-3 text-sm',
              'placeholder:text-muted-foreground text-foreground',
              'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background',
              'lg:w-64'
            )}
          />
        </div>

        {/* Theme Toggle */}
        <div className="relative">
          <button
            onClick={cycleTheme}
            onContextMenu={(e) => {
              e.preventDefault()
              setIsThemeMenuOpen(!isThemeMenuOpen)
            }}
            className={cn(
              'flex h-9 w-9 items-center justify-center rounded-md border border-border',
              'text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors',
              'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2'
            )}
            title={`Theme: ${theme} (click to cycle, right-click for menu)`}
          >
            <ThemeIcon theme={theme} />
          </button>

          {/* Theme Dropdown */}
          {isThemeMenuOpen && (
            <>
              <div
                className="fixed inset-0 z-40"
                onClick={() => setIsThemeMenuOpen(false)}
              />
              <div className="absolute right-0 top-full z-50 mt-2 w-36 rounded-lg border border-border bg-card shadow-lg">
                <div className="p-1">
                  {(['light', 'dark', 'system'] as Theme[]).map((t) => (
                    <button
                      key={t}
                      onClick={() => selectTheme(t)}
                      className={cn(
                        'flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm capitalize',
                        'hover:bg-accent hover:text-accent-foreground transition-colors',
                        theme === t
                          ? 'bg-primary/10 text-primary'
                          : 'text-foreground'
                      )}
                    >
                      <ThemeIcon theme={t} />
                      {t}
                    </button>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>

        {/* Notifications */}
        <button
          className={cn(
            'relative flex h-9 w-9 items-center justify-center rounded-md border border-border',
            'text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors',
            'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2'
          )}
          title="Notifications"
        >
          <Bell className="h-4 w-4" />
          {/* Notification Badge */}
          <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-destructive text-[10px] font-semibold text-destructive-foreground">
            3
          </span>
        </button>

        {/* User Menu */}
        <UserMenu onLogout={logout} isLoading={isLoading} />
      </div>
    </header>
  )
}

export default Header
