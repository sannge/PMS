/**
 * Header Component
 *
 * Minimal utility header - no page title (sidebar shows section).
 * Contains only global actions: search, theme toggle, user menu.
 * Notifications are handled by the sidebar notification panel.
 */

import { useState, useCallback, ReactNode, useEffect, useRef } from 'react'
import { cn } from '@/lib/utils'
import { useAuth, useCurrentUser } from '@/hooks/use-auth'
import {
  Search,
  Sun,
  Moon,
  Monitor,
  LogOut,
  User,
  ChevronDown,
  Command,
} from 'lucide-react'

// ============================================================================
// Types
// ============================================================================

type Theme = 'light' | 'dark' | 'system'

export interface HeaderProps {
  theme?: Theme
  onThemeChange?: (theme: Theme) => void
  className?: string
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
  const themes: { value: Theme; icon: ReactNode; label: string }[] = [
    { value: 'light', icon: <Sun className="h-3.5 w-3.5" />, label: 'Light' },
    { value: 'dark', icon: <Moon className="h-3.5 w-3.5" />, label: 'Dark' },
    { value: 'system', icon: <Monitor className="h-3.5 w-3.5" />, label: 'System' },
  ]

  const currentTheme = themes.find((t) => t.value === theme) || themes[2]

  const cycleTheme = useCallback(() => {
    const currentIndex = themes.findIndex((t) => t.value === theme)
    const nextIndex = (currentIndex + 1) % themes.length
    onThemeChange?.(themes[nextIndex].value)
  }, [theme, onThemeChange, themes])

  return (
    <button
      onClick={cycleTheme}
      className={cn(
        'flex h-7 w-7 items-center justify-center rounded-md',
        'text-muted-foreground transition-colors',
        'hover:bg-muted hover:text-foreground'
      )}
      title={`Theme: ${theme}`}
    >
      {currentTheme.icon}
    </button>
  )
}

// ============================================================================
// User Menu Component
// ============================================================================

function UserMenu({
  onLogout,
  isLoading,
}: {
  onLogout: () => Promise<void>
  isLoading?: boolean
}): JSX.Element {
  const [isOpen, setIsOpen] = useState(false)
  const user = useCurrentUser()
  const menuRef = useRef<HTMLDivElement>(null)

  const handleLogout = useCallback(async () => {
    setIsOpen(false)
    await onLogout()
  }, [onLogout])

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
    <div className="relative" ref={menuRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          'flex items-center gap-1.5 rounded-md px-1.5 py-1',
          'transition-colors hover:bg-muted'
        )}
      >
        <div className="relative">
          <div className={cn(
            'flex h-6 w-6 items-center justify-center rounded-md text-[10px] font-bold',
            'bg-gradient-to-br from-amber-400 to-orange-500 text-white'
          )}>
            {getInitials(user?.display_name, user?.email)}
          </div>
          <span className="absolute -bottom-0.5 -right-0.5 h-2 w-2 rounded-full bg-green-400 ring-1 ring-background" />
        </div>
        <ChevronDown className={cn(
          'h-3 w-3 text-muted-foreground transition-transform',
          isOpen && 'rotate-180'
        )} />
      </button>

      {isOpen && (
        <div className="absolute right-0 top-full z-50 mt-1 w-48 rounded-lg border border-border bg-card shadow-lg overflow-hidden">
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
// Search Component
// ============================================================================

function SearchBar(): JSX.Element {
  const [isFocused, setIsFocused] = useState(false)

  return (
    <div className={cn(
      'relative hidden sm:flex items-center',
      'transition-all duration-200',
      isFocused ? 'w-64' : 'w-48'
    )}>
      <Search className="absolute left-2.5 h-3.5 w-3.5 text-muted-foreground" />
      <input
        type="text"
        placeholder="Search..."
        onFocus={() => setIsFocused(true)}
        onBlur={() => setIsFocused(false)}
        className={cn(
          'w-full rounded-md border border-input bg-background py-1.5 pl-8 pr-12 text-xs',
          'placeholder:text-muted-foreground text-foreground',
          'transition-all duration-200',
          'focus:outline-none focus:ring-1 focus:ring-ring'
        )}
      />
      <div className={cn(
        'absolute right-2 flex items-center gap-0.5',
        'text-[9px] font-medium text-muted-foreground',
        isFocused && 'opacity-0'
      )}>
        <kbd className="flex h-4 items-center rounded border border-border bg-muted px-1 font-mono">
          <Command className="h-2.5 w-2.5" />
        </kbd>
        <kbd className="flex h-4 items-center rounded border border-border bg-muted px-1 font-mono">
          K
        </kbd>
      </div>
    </div>
  )
}

// ============================================================================
// Header Component
// ============================================================================

export function Header({
  theme = 'system',
  onThemeChange,
  className,
}: HeaderProps): JSX.Element {
  const { logout, isLoading } = useAuth()

  return (
    <header
      className={cn(
        'flex items-center justify-end gap-2 px-4 py-1.5',
        'bg-background/80 backdrop-blur-sm border-b border-border/50',
        'sticky top-0 z-40',
        className
      )}
    >
      <SearchBar />

      <div className="h-4 w-px bg-border/50" />

      <ThemeToggle theme={theme} onThemeChange={onThemeChange} />

      <UserMenu onLogout={logout} isLoading={isLoading} />
    </header>
  )
}

export default Header
