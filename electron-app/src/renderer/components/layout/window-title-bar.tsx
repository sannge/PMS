/**
 * Custom Window Title Bar Component
 *
 * Unified title bar with logo, utility controls, and window buttons.
 * Consolidates all top-level controls into a single compact bar.
 * Features:
 * - Custom PMS logo
 * - Integrated search, theme toggle, user menu
 * - Draggable region for window movement
 * - Minimize, Maximize/Restore, Close buttons
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { cn } from '@/lib/utils'
import appIcon from '@/icon.png'
import { useAuth, useCurrentUser } from '@/hooks/use-auth'
import {
  Minus,
  Square,
  X,
  Copy,
  LogOut,
  User,
  ChevronDown,
  RefreshCw,
} from 'lucide-react'
import { toast } from 'sonner'
import { clearQueryCache } from '@/lib/query-client'
import { clearEventDedup } from '@/hooks/use-websocket-cache'
import { wsClient } from '@/lib/websocket'

// ============================================================================
// Types
// ============================================================================

export interface WindowTitleBarProps {
  className?: string
  variant?: 'default' | 'auth'
  extraControls?: React.ReactNode
}

// ============================================================================
// PMS Logo Component
// ============================================================================

function PMSLogo({ variant = 'default' }: { variant?: 'default' | 'auth' }): JSX.Element {
  return (
    <div className="flex items-center gap-3">
      {/* Logo Icon */}
      <img
        src={appIcon}
        alt="PMS"
        className={cn(
          'rounded-lg object-contain',
          variant === 'auth' ? 'h-7 w-7 drop-shadow-lg' : 'h-6 w-6'
        )}
      />

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
    if (!isOpen) return
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [isOpen])

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
// Hard Refresh Button
// ============================================================================

function HardRefreshButton(): JSX.Element {
  const [isRefreshing, setIsRefreshing] = useState(false)
  const refreshingRef = useRef(false)
  const mountedRef = useRef(true)

  useEffect(() => () => { mountedRef.current = false }, [])

  const handleRefresh = useCallback(async () => {
    if (refreshingRef.current) return
    refreshingRef.current = true
    setIsRefreshing(true)
    try {
      // Snapshot active rooms before disconnect so we can rejoin
      const activeRooms = wsClient.getRooms()
      wsClient.disconnect()
      clearEventDedup()
      try {
        await clearQueryCache()
      } finally {
        // Always reconnect — rooms are restored so rejoinRooms()
        // in handleOpen() sends JOIN_ROOM for each (no duplicates)
        for (const room of activeRooms) {
          wsClient.joinRoom(room)
        }
        wsClient.connect()
      }
      if (mountedRef.current) toast.success('Reconnected', { duration: 2000 })
    } catch {
      if (mountedRef.current) toast.error('Refresh failed', { duration: 3000 })
    } finally {
      refreshingRef.current = false
      if (mountedRef.current) setIsRefreshing(false)
    }
  }, [])

  return (
    <button
      onClick={handleRefresh}
      disabled={isRefreshing}
      aria-label="Refresh connection and clear cache"
      className={cn(
        'flex h-6 w-6 items-center justify-center rounded app-no-drag',
        'text-sidebar-foreground/50 transition-colors',
        'hover:bg-sidebar-muted/40 hover:text-sidebar-foreground',
        'disabled:opacity-50'
      )}
      title="Refresh connection & clear cache"
    >
      <RefreshCw className={cn('h-3.5 w-3.5', isRefreshing && 'animate-spin')} />
    </button>
  )
}

// ============================================================================
// Utility Controls (User Menu, Refresh)
// ============================================================================

function UtilityControls({
  extraControls,
}: {
  extraControls?: React.ReactNode
}): JSX.Element {
  return (
    <div className="flex items-center gap-1 app-no-drag">
      {extraControls}

      <HardRefreshButton />

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
  extraControls,
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
          <UtilityControls extraControls={extraControls} />
        )}
        <WindowControls variant={variant} />
      </div>
    </div>
  )
}

export default WindowTitleBar
