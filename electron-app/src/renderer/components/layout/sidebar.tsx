/**
 * Sidebar Navigation Component
 *
 * Provides the main navigation structure for the application.
 * Features:
 * - Collapsible sidebar with expanded/collapsed states
 * - Navigation links for Applications, Projects, Tasks, Notes
 * - Active state highlighting
 * - User-friendly icons from Lucide
 * - Responsive design with theme support
 */

import { useState, useCallback, ReactNode } from 'react'
import { cn } from '@/lib/utils'
import {
  LayoutDashboard,
  FolderKanban,
  ListTodo,
  StickyNote,
  ChevronLeft,
  ChevronRight,
  Settings,
  Bell,
  Plus,
} from 'lucide-react'

// ============================================================================
// Types
// ============================================================================

type NavItem = 'dashboard' | 'applications' | 'projects' | 'tasks' | 'notes' | 'settings'

export interface SidebarProps {
  /**
   * Currently active navigation item
   */
  activeItem?: NavItem
  /**
   * Callback when navigation item is clicked
   */
  onNavigate?: (item: NavItem) => void
  /**
   * Whether the sidebar is collapsed
   */
  isCollapsed?: boolean
  /**
   * Callback when collapse state changes
   */
  onCollapsedChange?: (collapsed: boolean) => void
  /**
   * Optional className for the sidebar container
   */
  className?: string
}

interface NavLinkProps {
  icon: ReactNode
  label: string
  isActive?: boolean
  isCollapsed?: boolean
  onClick?: () => void
  badge?: number
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
        'flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
        'hover:bg-accent hover:text-accent-foreground',
        'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background',
        isActive
          ? 'bg-primary/10 text-primary'
          : 'text-muted-foreground',
        isCollapsed && 'justify-center px-2'
      )}
      title={isCollapsed ? label : undefined}
    >
      <span className="flex-shrink-0">{icon}</span>
      {!isCollapsed && (
        <>
          <span className="flex-1 truncate text-left">{label}</span>
          {badge !== undefined && badge > 0 && (
            <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-xs font-semibold text-primary-foreground">
              {badge > 99 ? '99+' : badge}
            </span>
          )}
        </>
      )}
      {isCollapsed && badge !== undefined && badge > 0 && (
        <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-primary" />
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
  className,
}: SidebarProps): JSX.Element {
  // Handle navigation
  const handleNavigate = useCallback(
    (item: NavItem) => {
      onNavigate?.(item)
    },
    [onNavigate]
  )

  // Toggle collapse state
  const toggleCollapsed = useCallback(() => {
    onCollapsedChange?.(!isCollapsed)
  }, [isCollapsed, onCollapsedChange])

  return (
    <aside
      className={cn(
        'flex h-full flex-col border-r border-border bg-card transition-all duration-300',
        isCollapsed ? 'w-16' : 'w-64',
        className
      )}
    >
      {/* Header */}
      <div className={cn(
        'flex items-center border-b border-border px-4 py-4',
        isCollapsed ? 'justify-center' : 'justify-between'
      )}>
        {!isCollapsed && (
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground font-bold text-sm">
              PM
            </div>
            <span className="text-lg font-semibold text-foreground">PM Desktop</span>
          </div>
        )}
        {isCollapsed && (
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground font-bold text-sm">
            PM
          </div>
        )}
      </div>

      {/* Main Navigation */}
      <nav className="flex-1 space-y-1 p-3">
        {/* Quick Create Button */}
        <button
          className={cn(
            'flex w-full items-center gap-2 rounded-lg border border-dashed border-border px-3 py-2 text-sm font-medium',
            'text-muted-foreground hover:border-primary hover:text-primary transition-colors',
            'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
            isCollapsed && 'justify-center px-2'
          )}
          title={isCollapsed ? 'Create New' : undefined}
        >
          <Plus className="h-4 w-4" />
          {!isCollapsed && <span>Create New</span>}
        </button>

        {/* Divider */}
        <div className="my-3 border-t border-border" />

        {/* Navigation Links */}
        <NavLink
          icon={<LayoutDashboard className="h-5 w-5" />}
          label="Dashboard"
          isActive={activeItem === 'dashboard'}
          isCollapsed={isCollapsed}
          onClick={() => handleNavigate('dashboard')}
        />
        <NavLink
          icon={<FolderKanban className="h-5 w-5" />}
          label="Applications"
          isActive={activeItem === 'applications'}
          isCollapsed={isCollapsed}
          onClick={() => handleNavigate('applications')}
        />
        <NavLink
          icon={<ListTodo className="h-5 w-5" />}
          label="Tasks"
          isActive={activeItem === 'tasks'}
          isCollapsed={isCollapsed}
          onClick={() => handleNavigate('tasks')}
        />
        <NavLink
          icon={<StickyNote className="h-5 w-5" />}
          label="Notes"
          isActive={activeItem === 'notes'}
          isCollapsed={isCollapsed}
          onClick={() => handleNavigate('notes')}
        />
      </nav>

      {/* Footer */}
      <div className="space-y-1 border-t border-border p-3">
        <NavLink
          icon={<Bell className="h-5 w-5" />}
          label="Notifications"
          isCollapsed={isCollapsed}
          onClick={() => {}}
          badge={3}
        />
        <NavLink
          icon={<Settings className="h-5 w-5" />}
          label="Settings"
          isActive={activeItem === 'settings'}
          isCollapsed={isCollapsed}
          onClick={() => handleNavigate('settings')}
        />

        {/* Collapse Toggle */}
        <button
          onClick={toggleCollapsed}
          className={cn(
            'flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground transition-colors',
            'hover:bg-accent hover:text-accent-foreground',
            'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
            isCollapsed && 'justify-center px-2'
          )}
          title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {isCollapsed ? (
            <ChevronRight className="h-5 w-5" />
          ) : (
            <>
              <ChevronLeft className="h-5 w-5" />
              <span>Collapse</span>
            </>
          )}
        </button>
      </div>
    </aside>
  )
}

export type { NavItem }
export default Sidebar
