/**
 * Dashboard Page
 *
 * Main dashboard layout with sidebar navigation and header.
 * This is the primary authenticated view of the application.
 *
 * Features:
 * - Collapsible sidebar navigation
 * - Header with search, theme toggle, and user menu
 * - Content area for current page/view
 * - Responsive layout
 * - State persistence for sidebar collapse
 */

import { useState, useCallback, useEffect, ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { Sidebar, type NavItem } from '@/components/layout/sidebar'
import { Header } from '@/components/layout/header'
import { ApplicationsPage } from '@/pages/applications/index'
import { ApplicationDetailPage } from '@/pages/applications/[id]'
import type { Application } from '@/stores/applications-store'
import {
  FolderKanban,
  ListTodo,
  StickyNote,
  LayoutDashboard,
  ArrowRight,
  Clock,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react'

// ============================================================================
// Types
// ============================================================================

type Theme = 'light' | 'dark' | 'system'

export interface DashboardProps {
  /**
   * Current theme
   */
  theme?: Theme
  /**
   * Callback when theme changes
   */
  onThemeChange?: (theme: Theme) => void
}

interface StatCardProps {
  icon: ReactNode
  label: string
  value: string | number
  trend?: {
    value: number
    isPositive: boolean
  }
  className?: string
}

interface QuickActionProps {
  icon: ReactNode
  label: string
  description: string
  onClick?: () => void
}

interface RecentActivityProps {
  type: 'task' | 'project' | 'note'
  title: string
  description: string
  time: string
  status?: 'completed' | 'in-progress' | 'pending'
}

// ============================================================================
// Helper Components
// ============================================================================

function StatCard({ icon, label, value, trend, className }: StatCardProps): JSX.Element {
  return (
    <div
      className={cn(
        'rounded-lg border border-border bg-card p-4 transition-colors hover:bg-accent/50',
        className
      )}
    >
      <div className="flex items-center justify-between">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
          {icon}
        </div>
        {trend && (
          <span
            className={cn(
              'text-xs font-medium',
              trend.isPositive ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
            )}
          >
            {trend.isPositive ? '+' : '-'}{Math.abs(trend.value)}%
          </span>
        )}
      </div>
      <div className="mt-3">
        <p className="text-2xl font-bold text-foreground">{value}</p>
        <p className="text-sm text-muted-foreground">{label}</p>
      </div>
    </div>
  )
}

function QuickAction({ icon, label, description, onClick }: QuickActionProps): JSX.Element {
  return (
    <button
      onClick={onClick}
      className={cn(
        'flex items-center gap-4 rounded-lg border border-border bg-card p-4 text-left transition-colors',
        'hover:border-primary/50 hover:bg-accent/50',
        'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2'
      )}
    >
      <div className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
        {icon}
      </div>
      <div className="flex-1 min-w-0">
        <p className="font-medium text-foreground">{label}</p>
        <p className="text-sm text-muted-foreground truncate">{description}</p>
      </div>
      <ArrowRight className="h-5 w-5 flex-shrink-0 text-muted-foreground" />
    </button>
  )
}

function RecentActivityItem({ type, title, description, time, status }: RecentActivityProps): JSX.Element {
  const getIcon = () => {
    switch (type) {
      case 'task':
        return <ListTodo className="h-4 w-4" />
      case 'project':
        return <FolderKanban className="h-4 w-4" />
      case 'note':
        return <StickyNote className="h-4 w-4" />
    }
  }

  const getStatusIcon = () => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 className="h-4 w-4 text-green-600 dark:text-green-400" />
      case 'in-progress':
        return <Clock className="h-4 w-4 text-yellow-600 dark:text-yellow-400" />
      case 'pending':
        return <AlertCircle className="h-4 w-4 text-muted-foreground" />
      default:
        return null
    }
  }

  return (
    <div className="flex items-start gap-3 py-3">
      <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
        {getIcon()}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="font-medium text-foreground truncate">{title}</p>
          {getStatusIcon()}
        </div>
        <p className="text-sm text-muted-foreground truncate">{description}</p>
      </div>
      <span className="flex-shrink-0 text-xs text-muted-foreground">{time}</span>
    </div>
  )
}

// ============================================================================
// Dashboard Content Component
// ============================================================================

interface DashboardContentProps {
  onNavigateToApplications?: () => void
  onNavigateToTasks?: () => void
  onNavigateToNotes?: () => void
}

function DashboardContent({
  onNavigateToApplications,
  onNavigateToTasks,
  onNavigateToNotes,
}: DashboardContentProps): JSX.Element {
  return (
    <div className="space-y-6">
      {/* Welcome Section */}
      <div className="rounded-lg border border-border bg-gradient-to-r from-primary/10 to-transparent p-6">
        <h2 className="text-2xl font-bold text-foreground">Welcome back!</h2>
        <p className="mt-1 text-muted-foreground">
          Here's an overview of your projects and tasks.
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          icon={<FolderKanban className="h-5 w-5" />}
          label="Applications"
          value={0}
          trend={{ value: 0, isPositive: true }}
        />
        <StatCard
          icon={<LayoutDashboard className="h-5 w-5" />}
          label="Projects"
          value={0}
        />
        <StatCard
          icon={<ListTodo className="h-5 w-5" />}
          label="Active Tasks"
          value={0}
        />
        <StatCard
          icon={<CheckCircle2 className="h-5 w-5" />}
          label="Completed"
          value={0}
          trend={{ value: 0, isPositive: true }}
        />
      </div>

      {/* Quick Actions */}
      <div>
        <h3 className="mb-4 text-lg font-semibold text-foreground">Quick Actions</h3>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <QuickAction
            icon={<FolderKanban className="h-6 w-6" />}
            label="Create Application"
            description="Start a new project container"
            onClick={onNavigateToApplications}
          />
          <QuickAction
            icon={<ListTodo className="h-6 w-6" />}
            label="Add Task"
            description="Create a new task or issue"
            onClick={onNavigateToTasks}
          />
          <QuickAction
            icon={<StickyNote className="h-6 w-6" />}
            label="New Note"
            description="Start writing a new note"
            onClick={onNavigateToNotes}
          />
        </div>
      </div>

      {/* Recent Activity */}
      <div>
        <h3 className="mb-4 text-lg font-semibold text-foreground">Recent Activity</h3>
        <div className="rounded-lg border border-border bg-card">
          <div className="divide-y divide-border px-4">
            <div className="py-8 text-center text-muted-foreground">
              <LayoutDashboard className="mx-auto mb-2 h-8 w-8 opacity-50" />
              <p>No recent activity</p>
              <p className="text-sm">Your recent updates will appear here</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ============================================================================
// Page Title Map
// ============================================================================

const pageTitles: Record<NavItem, string> = {
  dashboard: 'Dashboard',
  applications: 'Applications',
  projects: 'Projects',
  tasks: 'Tasks',
  notes: 'Notes',
  settings: 'Settings',
}

// ============================================================================
// Dashboard Page Component
// ============================================================================

export function DashboardPage({
  theme = 'system',
  onThemeChange,
}: DashboardProps): JSX.Element {
  // Navigation state
  const [activeItem, setActiveItem] = useState<NavItem>('dashboard')

  // Application navigation state
  const [selectedApplicationId, setSelectedApplicationId] = useState<string | null>(null)

  // Sidebar collapse state with localStorage persistence
  const [isCollapsed, setIsCollapsed] = useState<boolean>(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('pm-sidebar-collapsed')
      return saved === 'true'
    }
    return false
  })

  // Save collapse state to localStorage
  useEffect(() => {
    localStorage.setItem('pm-sidebar-collapsed', String(isCollapsed))
  }, [isCollapsed])

  // Handle navigation
  const handleNavigate = useCallback((item: NavItem) => {
    setActiveItem(item)
    // Clear selected application when navigating away from applications
    if (item !== 'applications') {
      setSelectedApplicationId(null)
    }
  }, [])

  // Handle application selection
  const handleSelectApplication = useCallback((application: Application) => {
    setSelectedApplicationId(application.id)
  }, [])

  // Handle back to applications list
  const handleBackToApplications = useCallback(() => {
    setSelectedApplicationId(null)
  }, [])

  // Handle sidebar collapse
  const handleCollapsedChange = useCallback((collapsed: boolean) => {
    setIsCollapsed(collapsed)
  }, [])

  // Render content based on active navigation item
  const renderContent = (): ReactNode => {
    switch (activeItem) {
      case 'dashboard':
        return (
          <DashboardContent
            onNavigateToApplications={() => handleNavigate('applications')}
            onNavigateToTasks={() => handleNavigate('tasks')}
            onNavigateToNotes={() => handleNavigate('notes')}
          />
        )
      case 'applications':
        // Show detail page if an application is selected
        if (selectedApplicationId) {
          return (
            <ApplicationDetailPage
              applicationId={selectedApplicationId}
              onBack={handleBackToApplications}
              onDeleted={handleBackToApplications}
            />
          )
        }
        // Otherwise show the list
        return (
          <ApplicationsPage
            onSelectApplication={handleSelectApplication}
          />
        )
      case 'tasks':
        return (
          <div className="flex flex-1 items-center justify-center text-muted-foreground">
            <div className="text-center">
              <ListTodo className="mx-auto mb-4 h-16 w-16 opacity-50" />
              <h2 className="text-xl font-semibold text-foreground">Tasks</h2>
              <p>Task management coming soon...</p>
            </div>
          </div>
        )
      case 'notes':
        return (
          <div className="flex flex-1 items-center justify-center text-muted-foreground">
            <div className="text-center">
              <StickyNote className="mx-auto mb-4 h-16 w-16 opacity-50" />
              <h2 className="text-xl font-semibold text-foreground">Notes</h2>
              <p>Note-taking coming soon...</p>
            </div>
          </div>
        )
      case 'settings':
        return (
          <div className="flex flex-1 items-center justify-center text-muted-foreground">
            <div className="text-center">
              <h2 className="text-xl font-semibold text-foreground">Settings</h2>
              <p>Settings page coming soon...</p>
            </div>
          </div>
        )
      default:
        return <DashboardContent />
    }
  }

  return (
    <div className="flex h-full bg-background">
      {/* Sidebar */}
      <Sidebar
        activeItem={activeItem}
        onNavigate={handleNavigate}
        isCollapsed={isCollapsed}
        onCollapsedChange={handleCollapsedChange}
      />

      {/* Main Content Area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Header */}
        <Header
          title={pageTitles[activeItem]}
          theme={theme}
          onThemeChange={onThemeChange}
        />

        {/* Page Content */}
        <main className="flex-1 overflow-auto p-6">
          {renderContent()}
        </main>
      </div>
    </div>
  )
}

export default DashboardPage
