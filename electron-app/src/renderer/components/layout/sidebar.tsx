/**
 * Sidebar Navigation Component
 *
 * Ultra-compact sidebar optimized for screen real estate.
 * Features:
 * - Minimal expanded width (180px)
 * - Compact icon-only collapsed mode (48px)
 * - Smooth transitions
 * - Space-efficient navigation
 */

import { useCallback, ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { useNotificationsStore } from '@/stores/notifications-store'
import {
  LayoutDashboard,
  FolderKanban,
  ListTodo,
  StickyNote,
  ChevronLeft,
  Settings,
  Bell,
  Plus,
} from 'lucide-react'

// ============================================================================
// Types
// ============================================================================

type NavItem = 'dashboard' | 'applications' | 'projects' | 'tasks' | 'notes' | 'settings'

export interface SidebarProps {
  activeItem?: NavItem
  onNavigate?: (item: NavItem) => void
  isCollapsed?: boolean
  onCollapsedChange?: (collapsed: boolean) => void
  onNotificationClick?: () => void
  className?: string
}

interface NavLinkProps {
  icon: ReactNode
  label: string
  isActive?: boolean
  isCollapsed?: boolean
  onClick?: () => void
  badge?: number
  index?: number
}

// ============================================================================
// Navigation Link Component
// ============================================================================

function NavLink({
  icon,
  label,
  isActive = false,
  isCollapsed = false,
  onClick,
  badge,
}: NavLinkProps): JSX.Element {
  return (
    <button
      onClick={onClick}
      className={cn(
        'group relative flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-xs font-medium',
        'transition-all duration-200',
        isActive
          ? 'bg-sidebar-accent/15 text-sidebar-accent'
          : 'text-sidebar-foreground/60 hover:text-sidebar-foreground hover:bg-sidebar-muted/40',
        isCollapsed && 'justify-center px-2'
      )}
      title={isCollapsed ? label : undefined}
    >
      {/* Active indicator */}
      {isActive && (
        <span className="absolute left-0 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-r-full bg-sidebar-accent" />
      )}

      <span className={cn(
        'flex-shrink-0',
        isActive && 'text-sidebar-accent'
      )}>
        {icon}
      </span>

      {!isCollapsed && (
        <>
          <span className="flex-1 truncate text-left">{label}</span>
          {badge !== undefined && badge > 0 && (
            <span className="flex h-4 min-w-4 items-center justify-center rounded-full bg-sidebar-accent px-1 text-[9px] font-bold text-sidebar">
              {badge > 99 ? '99+' : badge}
            </span>
          )}
        </>
      )}

      {isCollapsed && badge !== undefined && badge > 0 && (
        <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-sidebar-accent" />
      )}
    </button>
  )
}

// ============================================================================
// Sidebar Component
// ============================================================================

export function Sidebar({
  activeItem = 'dashboard',
  onNavigate,
  isCollapsed = false,
  onCollapsedChange,
  onNotificationClick,
  className,
}: SidebarProps): JSX.Element {
  const unreadCount = useNotificationsStore((state) => state.unreadCount)
  const toggleNotifications = useNotificationsStore((state) => state.toggleOpen)

  const handleNavigate = useCallback(
    (item: NavItem) => {
      onNavigate?.(item)
    },
    [onNavigate]
  )

  const toggleCollapsed = useCallback(() => {
    onCollapsedChange?.(!isCollapsed)
  }, [isCollapsed, onCollapsedChange])

  const handleNotificationClick = useCallback(() => {
    if (onNotificationClick) {
      onNotificationClick()
    } else {
      toggleNotifications()
    }
  }, [onNotificationClick, toggleNotifications])

  const navItems = [
    { id: 'dashboard' as NavItem, icon: <LayoutDashboard className="h-4 w-4" />, label: 'Dashboard' },
    { id: 'applications' as NavItem, icon: <FolderKanban className="h-4 w-4" />, label: 'Applications' },
    { id: 'tasks' as NavItem, icon: <ListTodo className="h-4 w-4" />, label: 'Tasks' },
    { id: 'notes' as NavItem, icon: <StickyNote className="h-4 w-4" />, label: 'Notes' },
  ]

  return (
    <aside
      className={cn(
        'flex h-full flex-col bg-sidebar transition-all duration-200',
        'border-r border-sidebar-muted/30',
        isCollapsed ? 'w-12' : 'w-44',
        className
      )}
    >
      {/* Quick Create Button */}
      <div className="p-2">
        <button
          className={cn(
            'flex w-full items-center gap-2 rounded-lg border border-dashed border-sidebar-muted/40 px-2 py-1.5',
            'text-xs font-medium text-sidebar-foreground/50',
            'transition-all duration-200',
            'hover:border-sidebar-accent/50 hover:text-sidebar-accent hover:bg-sidebar-accent/5',
            isCollapsed && 'justify-center px-1.5'
          )}
          title={isCollapsed ? 'Create New' : undefined}
        >
          <Plus className="h-3.5 w-3.5" />
          {!isCollapsed && <span>New</span>}
        </button>
      </div>

      {/* Navigation Section Label */}
      {!isCollapsed && (
        <div className="px-3 pt-2 pb-1">
          <span className="text-[9px] font-semibold uppercase tracking-wider text-sidebar-foreground/30">
            Menu
          </span>
        </div>
      )}

      {/* Main Navigation */}
      <nav className={cn('flex-1 space-y-0.5 px-2', isCollapsed && 'pt-2')}>
        {navItems.map((item, index) => (
          <NavLink
            key={item.id}
            icon={item.icon}
            label={item.label}
            isActive={activeItem === item.id}
            isCollapsed={isCollapsed}
            onClick={() => handleNavigate(item.id)}
            index={index}
          />
        ))}
      </nav>

      {/* Footer Section */}
      <div className="space-y-0.5 border-t border-sidebar-muted/20 p-2">
        <NavLink
          icon={<Bell className="h-4 w-4" />}
          label="Alerts"
          isCollapsed={isCollapsed}
          onClick={handleNotificationClick}
          badge={unreadCount}
          index={5}
        />

        <NavLink
          icon={<Settings className="h-4 w-4" />}
          label="Settings"
          isActive={activeItem === 'settings'}
          isCollapsed={isCollapsed}
          onClick={() => handleNavigate('settings')}
          index={6}
        />

        {/* Collapse Toggle */}
        <button
          onClick={toggleCollapsed}
          className={cn(
            'mt-1 flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-xs',
            'text-sidebar-foreground/40 transition-all duration-200',
            'hover:bg-sidebar-muted/30 hover:text-sidebar-foreground/60',
            isCollapsed && 'justify-center px-1.5'
          )}
          title={isCollapsed ? 'Expand' : 'Collapse'}
        >
          <ChevronLeft className={cn(
            'h-3.5 w-3.5 transition-transform duration-200',
            isCollapsed && 'rotate-180'
          )} />
          {!isCollapsed && <span>Collapse</span>}
        </button>
      </div>
    </aside>
  )
}

export type { NavItem }
export default Sidebar
