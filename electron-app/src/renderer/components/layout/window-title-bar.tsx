/**
 * Custom Window Title Bar Component
 *
 * Unified title bar with logo, utility controls, and window buttons.
 * Consolidates all top-level controls into a single compact bar.
 * Features:
 * - Custom PMS logo
 * - Integrated search, theme toggle, notifications, user menu
 * - Draggable region for window movement
 * - Minimize, Maximize/Restore, Close buttons
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { cn } from '@/lib/utils'
import { useAuth, useCurrentUser } from '@/hooks/use-auth'
import {
  Minus,
  Square,
  X,
  Copy,
  Search,
  Sun,
  Moon,
  Monitor,
  LogOut,
  User,
  ChevronDown,
  Command,
} from 'lucide-react'
import { NotificationBell, type Notification } from '@/components/notifications'

// ============================================================================
// Types
// ============================================================================

type Theme = 'light' | 'dark' | 'system'

export interface WindowTitleBarProps {
  className?: string
  variant?: 'default' | 'auth'
  theme?: Theme
  onThemeChange?: (theme: Theme) => void
}

// ============================================================================
// PMS Logo Component
// ============================================================================

function PMSLogo({ variant = 'default' }: { variant?: 'default' | 'auth' }): JSX.Element {
  return (
    <div className="flex items-center gap-3">
      {/* Logo Icon */}
      <div className={cn(
        'relative flex items-center justify-center rounded-lg',
        'transition-all duration-300',
        variant === 'auth' ? 'h-7 w-7' : 'h-6 w-6'
      )}>
        {/* Modern geometric logo */}
        <svg
          viewBox="0 0 32 32"
          fill="none"
          className={cn(
            'w-full h-full',
            variant === 'auth' ? 'drop-shadow-lg' : ''
          )}
        >
          {/* Background gradient circle */}
          <defs>
            <linearGradient id="pms-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#F59E0B" />
              <stop offset="50%" stopColor="#EA580C" />
              <stop offset="100%" stopColor="#F59E0B" />
            </linearGradient>
            <linearGradient id="pms-shine" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#FCD34D" stopOpacity="0.8" />
              <stop offset="50%" stopColor="#F59E0B" stopOpacity="0" />
            </linearGradient>
          </defs>

          {/* Main shape - rounded square */}
          <rect
            x="2"
            y="2"
            width="28"
            height="28"
            rx="8"
            fill="url(#pms-gradient)"
          />

          {/* Shine overlay */}
          <rect
            x="2"
            y="2"
            width="28"
            height="14"
            rx="8"
            fill="url(#pms-shine)"
          />

          {/* P letter - stylized */}
          <path
            d="M10 8H17C19.7614 8 22 10.2386 22 13C22 15.7614 19.7614 18 17 18H14V24H10V8Z"
            fill="white"
            fillOpacity="0.95"
          />
          <path
            d="M14 11V15H16.5C17.6046 15 18.5 14.1046 18.5 13C18.5 11.8954 17.6046 11 16.5 11H14Z"
            fill="url(#pms-gradient)"
          />
        </svg>
      </div>

      {/* Logo Text */}
      <div className="flex flex-col">
        <span className={cn(
          'font-bold tracking-tight leading-none',
          variant === 'auth'
            ? 'text-white text-sm'
            : 'text-sidebar-foreground text-xs'
        )}>
          PMS
        </span>
        <span className={cn(
          'text-[9px] font-medium uppercase tracking-[0.15em] leading-tight',
          variant === 'auth'
            ? 'text-white/50'
            : 'text-sidebar-foreground/40'
        )}>
          Project Manager
        </span>
      </div>
    </div>
  )
}

// ============================================================================
// Search Button with Popup
// ============================================================================

function SearchButton(): JSX.Element {
  const [isOpen, setIsOpen] = useState(false)
  const [query, setQuery] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // Handle keyboard shortcut
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setIsOpen(true)
      }
      if (e.key === 'Escape' && isOpen) {
        setIsOpen(false)
        setQuery('')
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen])

  // Focus input when opened
  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus()
    }
  }, [isOpen])

  // Close on click outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false)
        setQuery('')
      }
    }
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [isOpen])

  return (
    <div className="relative app-no-drag" ref={containerRef}>
      {/* Search Icon Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          'flex h-6 w-6 items-center justify-center rounded',
          'text-sidebar-foreground/50 transition-colors',
          'hover:bg-sidebar-muted/40 hover:text-sidebar-foreground',
          isOpen && 'bg-sidebar-muted/40 text-sidebar-foreground'
        )}
        title="Search (⌘K)"
      >
        <Search className="h-3.5 w-3.5" />
      </button>

      {/* Search Popup */}
      {isOpen && (
        <div className="absolute right-0 top-full z-50 mt-1 w-72 rounded-lg border border-border bg-card shadow-xl overflow-hidden">
          {/* Search Input */}
          <div className="flex items-center gap-2 border-b border-border px-3 py-2">
            <Search className="h-4 w-4 text-muted-foreground flex-shrink-0" />
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search everything..."
              className={cn(
                'flex-1 bg-transparent text-sm text-foreground',
                'placeholder:text-muted-foreground',
                'focus:outline-none'
              )}
            />
            <kbd className="flex h-5 items-center rounded border border-border bg-muted px-1.5 text-[10px] font-medium text-muted-foreground">
              ESC
            </kbd>
          </div>

          {/* Search Results Placeholder */}
          <div className="max-h-64 overflow-y-auto p-2">
            {query ? (
              <div className="py-8 text-center">
                <Search className="mx-auto h-8 w-8 text-muted-foreground/30" />
                <p className="mt-2 text-sm text-muted-foreground">
                  Search results for "{query}"
                </p>
                <p className="text-xs text-muted-foreground/70">
                  Coming soon...
                </p>
              </div>
            ) : (
              <div className="py-6 text-center">
                <p className="text-xs text-muted-foreground">
                  Type to search applications, projects, tasks, and notes
                </p>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between border-t border-border px-3 py-1.5 text-[10px] text-muted-foreground">
            <span>Press <kbd className="mx-0.5 rounded border border-border bg-muted px-1">⌘K</kbd> to open</span>
            <span>Global Search</span>
          </div>
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Theme Toggle Component
// ============================================================================

function ThemeToggle({
  theme,
  onThemeChange,
}: {
  theme: Theme
  onThemeChange?: (theme: Theme) => void
}): JSX.Element {
  const cycleTheme = useCallback(() => {
    const themes: Theme[] = ['light', 'dark', 'system']
    const currentIndex = themes.findIndex((t) => t === theme)
    const nextIndex = (currentIndex + 1) % themes.length
    onThemeChange?.(themes[nextIndex])
  }, [theme, onThemeChange])

  const icon = theme === 'light' ? <Sun className="h-3.5 w-3.5" /> :
               theme === 'dark' ? <Moon className="h-3.5 w-3.5" /> :
               <Monitor className="h-3.5 w-3.5" />

  return (
    <button
      onClick={cycleTheme}
      className={cn(
        'flex h-6 w-6 items-center justify-center rounded app-no-drag',
        'text-sidebar-foreground/50 transition-colors',
        'hover:bg-sidebar-muted/40 hover:text-sidebar-foreground'
      )}
      title={`Theme: ${theme}`}
    >
      {icon}
    </button>
  )
}

// ============================================================================
// User Menu Component
// ============================================================================

function CompactUserMenu(): JSX.Element {
  const [isOpen, setIsOpen] = useState(false)
  const { logout, isLoading } = useAuth()
  const user = useCurrentUser()
  const menuRef = useRef<HTMLDivElement>(null)

  const handleLogout = useCallback(async () => {
    setIsOpen(false)
    await logout()
  }, [logout])

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const getInitials = (name?: string | null, email?: string | null): string => {
    if (name) {
      const parts = name.split(' ')
      if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase()
      return name.substring(0, 2).toUpperCase()
    }
    if (email) return email.substring(0, 2).toUpperCase()
    return 'U'
  }

  return (
    <div className="relative app-no-drag" ref={menuRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          'flex items-center gap-1 rounded px-1 py-0.5',
          'transition-colors hover:bg-sidebar-muted/40'
        )}
      >
        <div className="relative">
          <div className={cn(
            'flex h-5 w-5 items-center justify-center rounded text-[9px] font-bold',
            'bg-gradient-to-br from-amber-400 to-orange-500 text-white'
          )}>
            {getInitials(user?.display_name, user?.email)}
          </div>
          <span className="absolute -bottom-0.5 -right-0.5 h-1.5 w-1.5 rounded-full bg-green-400 ring-1 ring-sidebar" />
        </div>
        <ChevronDown className={cn(
          'h-2.5 w-2.5 text-sidebar-foreground/40 transition-transform',
          isOpen && 'rotate-180'
        )} />
      </button>

      {isOpen && (
        <div className="absolute right-0 top-full z-50 mt-1 w-44 rounded-lg border border-border bg-card shadow-lg overflow-hidden">
          <div className="bg-muted/50 px-3 py-2 border-b border-border">
            <p className="text-xs font-medium text-foreground truncate">
              {user?.display_name || 'User'}
            </p>
            <p className="text-[10px] text-muted-foreground truncate">
              {user?.email}
            </p>
          </div>
          <div className="p-1">
            <button
              onClick={() => setIsOpen(false)}
              className={cn(
                'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs',
                'text-foreground hover:bg-muted transition-colors'
              )}
            >
              <User className="h-3.5 w-3.5 text-muted-foreground" />
              Profile
            </button>
            <button
              onClick={handleLogout}
              disabled={isLoading}
              className={cn(
                'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs',
                'text-destructive hover:bg-destructive/10 transition-colors',
                'disabled:opacity-50'
              )}
            >
              <LogOut className="h-3.5 w-3.5" />
              {isLoading ? 'Signing out...' : 'Sign out'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Utility Controls (Search, Theme, Notifications, User)
// ============================================================================

function UtilityControls({
  theme,
  onThemeChange,
}: {
  theme: Theme
  onThemeChange?: (theme: Theme) => void
}): JSX.Element {
  const [notifications, setNotifications] = useState<Notification[]>([])
  const unreadCount = notifications.filter((n) => !n.is_read).length

  const handleNotificationClick = useCallback((notification: Notification) => {
    setNotifications((prev) =>
      prev.map((n) => (n.id === notification.id ? { ...n, is_read: true } : n))
    )
  }, [])

  const handleMarkAsRead = useCallback((notification: Notification) => {
    setNotifications((prev) =>
      prev.map((n) => (n.id === notification.id ? { ...n, is_read: true } : n))
    )
  }, [])

  const handleMarkAllAsRead = useCallback(() => {
    setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })))
  }, [])

  const handleDeleteNotification = useCallback((notification: Notification) => {
    setNotifications((prev) => prev.filter((n) => n.id !== notification.id))
  }, [])

  return (
    <div className="flex items-center gap-1 app-no-drag">
      <SearchButton />

      <ThemeToggle theme={theme} onThemeChange={onThemeChange} />

      <div className="[&_button]:h-6 [&_button]:w-6 [&_svg]:h-3.5 [&_svg]:w-3.5">
        <NotificationBell
          notifications={notifications}
          unreadCount={unreadCount}
          isLoading={false}
          onNotificationClick={handleNotificationClick}
          onMarkAsRead={handleMarkAsRead}
          onMarkAllAsRead={handleMarkAllAsRead}
          onDelete={handleDeleteNotification}
        />
      </div>

      <div className="h-4 w-px bg-sidebar-muted/20 mx-0.5" />

      <CompactUserMenu />
    </div>
  )
}

// ============================================================================
// Window Control Buttons
// ============================================================================

function WindowControls({ variant = 'default' }: { variant?: 'default' | 'auth' }): JSX.Element {
  const [isMaximized, setIsMaximized] = useState(false)

  useEffect(() => {
    // Get initial maximized state
    window.electronAPI?.isMaximized().then(setIsMaximized)

    // Subscribe to maximized state changes
    const unsubscribe = window.electronAPI?.onMaximizedChange((maximized) => {
      setIsMaximized(maximized)
    })

    return () => {
      unsubscribe?.()
    }
  }, [])

  const handleMinimize = useCallback(() => {
    window.electronAPI?.minimize()
  }, [])

  const handleMaximize = useCallback(() => {
    window.electronAPI?.maximize()
  }, [])

  const handleClose = useCallback(() => {
    window.electronAPI?.close()
  }, [])

  const buttonBaseClass = cn(
    'flex items-center justify-center w-11 h-8 transition-colors duration-150',
    variant === 'auth'
      ? 'text-white/60 hover:text-white'
      : 'text-sidebar-foreground/50 hover:text-sidebar-foreground'
  )

  return (
    <div className="flex items-center -mr-1 app-no-drag">
      {/* Minimize */}
      <button
        onClick={handleMinimize}
        className={cn(
          buttonBaseClass,
          variant === 'auth'
            ? 'hover:bg-white/10'
            : 'hover:bg-sidebar-muted/50'
        )}
        title="Minimize"
      >
        <Minus className="h-4 w-4" />
      </button>

      {/* Maximize / Restore */}
      <button
        onClick={handleMaximize}
        className={cn(
          buttonBaseClass,
          variant === 'auth'
            ? 'hover:bg-white/10'
            : 'hover:bg-sidebar-muted/50'
        )}
        title={isMaximized ? 'Restore' : 'Maximize'}
      >
        {isMaximized ? (
          <Copy className="h-3.5 w-3.5" />
        ) : (
          <Square className="h-3.5 w-3.5" />
        )}
      </button>

      {/* Close */}
      <button
        onClick={handleClose}
        className={cn(
          buttonBaseClass,
          'hover:bg-red-500 hover:text-white rounded-tr-lg'
        )}
        title="Close"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  )
}

// ============================================================================
// Main Component
// ============================================================================

export function WindowTitleBar({
  className,
  variant = 'default',
  theme = 'system',
  onThemeChange,
}: WindowTitleBarProps): JSX.Element {
  return (
    <div
      className={cn(
        'flex items-center justify-between h-9 select-none app-drag',
        variant === 'auth'
          ? 'bg-transparent'
          : 'bg-sidebar border-b border-sidebar-muted/20',
        className
      )}
    >
      {/* Left - Logo */}
      <div className="flex items-center pl-3 app-no-drag">
        <PMSLogo variant={variant} />
      </div>

      {/* Center/Right - Utility Controls + Window Controls */}
      <div className="flex items-center">
        {variant !== 'auth' && (
          <UtilityControls theme={theme} onThemeChange={onThemeChange} />
        )}
        <WindowControls variant={variant} />
      </div>
    </div>
  )
}

export default WindowTitleBar
