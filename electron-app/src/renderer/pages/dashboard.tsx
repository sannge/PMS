/**
 * Dashboard Page
 *
 * Modern dashboard with refined statistics, quick actions, and activity feed.
 * Features:
 * - Animated stat cards with trend indicators
 * - Quick action cards with hover effects
 * - Activity timeline with status indicators
 * - Smooth staggered animations
 */

import { useState, useCallback, useEffect, useRef, ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { Sidebar, type NavItem } from '@/components/layout/sidebar'
import { WindowTitleBar } from '@/components/layout/window-title-bar'
import { NotificationPanel } from '@/components/layout/notification-panel'
import { ApplicationsPage } from '@/pages/applications/index'
import { ApplicationDetailPage } from '@/pages/applications/[id]'
import { ProjectsPage } from '@/pages/projects/index'
import { ProjectDetailPage } from '@/pages/projects/[id]'
import { NotesPage } from '@/pages/notes/index'
import { useInvitationNotifications, useWebSocket, useNotificationReadSync } from '@/hooks/use-websocket'
import { useNotificationsStore, requestNotificationPermission } from '@/stores/notifications-store'
import { useAuthStore } from '@/stores/auth-store'
import { useMembersStore } from '@/stores/members-store'
import { useApplicationsStore, type Application } from '@/stores/applications-store'
import type { Project } from '@/stores/projects-store'
import {
  FolderKanban,
  ListTodo,
  StickyNote,
  LayoutDashboard,
  ArrowRight,
  Clock,
  CheckCircle2,
  AlertCircle,
  TrendingUp,
  TrendingDown,
  Sparkles,
  Zap,
  Target,
  Activity,
} from 'lucide-react'

// ============================================================================
// Types
// ============================================================================

type Theme = 'light' | 'dark' | 'system'

export interface DashboardProps {
  theme?: Theme
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
  color: 'amber' | 'violet' | 'emerald' | 'blue'
  index?: number
}

interface QuickActionProps {
  icon: ReactNode
  label: string
  description: string
  color: 'amber' | 'violet' | 'emerald'
  onClick?: () => void
  index?: number
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

const colorClasses = {
  amber: {
    bg: 'bg-gradient-to-br from-amber-400/20 via-orange-500/15 to-amber-600/10',
    icon: 'text-amber-600 dark:text-amber-400',
    ring: 'ring-amber-500/20',
    shadow: 'group-hover:shadow-amber-500/20',
  },
  violet: {
    bg: 'bg-gradient-to-br from-violet-400/20 via-purple-500/15 to-violet-600/10',
    icon: 'text-violet-600 dark:text-violet-400',
    ring: 'ring-violet-500/20',
    shadow: 'group-hover:shadow-violet-500/20',
  },
  emerald: {
    bg: 'bg-gradient-to-br from-emerald-400/20 via-green-500/15 to-emerald-600/10',
    icon: 'text-emerald-600 dark:text-emerald-400',
    ring: 'ring-emerald-500/20',
    shadow: 'group-hover:shadow-emerald-500/20',
  },
  blue: {
    bg: 'bg-gradient-to-br from-blue-400/20 via-cyan-500/15 to-blue-600/10',
    icon: 'text-blue-600 dark:text-blue-400',
    ring: 'ring-blue-500/20',
    shadow: 'group-hover:shadow-blue-500/20',
  },
}

function StatCard({ icon, label, value, trend, color, index = 0 }: StatCardProps): JSX.Element {
  const colors = colorClasses[color]

  return (
    <div
      className={cn(
        'group relative rounded-2xl border border-border bg-card p-5',
        'transition-all duration-300 ease-out',
        'hover:-translate-y-1 hover:shadow-xl hover:shadow-black/5',
        'animate-fade-in opacity-0'
      )}
      style={{ animationDelay: `${index * 100}ms` }}
    >
      {/* Gradient overlay on hover */}
      <div className={cn(
        'absolute inset-0 rounded-2xl opacity-0 transition-opacity duration-300',
        'group-hover:opacity-100 pointer-events-none',
        colors.bg
      )} />

      <div className="relative flex items-center justify-between">
        <div className={cn(
          'flex h-12 w-12 items-center justify-center rounded-xl',
          colors.bg,
          colors.icon,
          'ring-1',
          colors.ring,
          'transition-all duration-300',
          'group-hover:shadow-lg',
          colors.shadow,
          'group-hover:scale-105'
        )}>
          {icon}
        </div>

        {trend && (
          <div className={cn(
            'flex items-center gap-1 rounded-full px-2.5 py-1',
            'text-xs font-semibold',
            trend.isPositive
              ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
              : 'bg-red-500/10 text-red-600 dark:text-red-400'
          )}>
            {trend.isPositive ? (
              <TrendingUp className="h-3.5 w-3.5" />
            ) : (
              <TrendingDown className="h-3.5 w-3.5" />
            )}
            <span>{Math.abs(trend.value)}%</span>
          </div>
        )}
      </div>

      <div className="relative mt-4">
        <p className="text-3xl font-bold tracking-tight text-foreground">{value}</p>
        <p className="mt-1 text-sm text-muted-foreground">{label}</p>
      </div>
    </div>
  )
}

function QuickAction({ icon, label, description, color, onClick, index = 0 }: QuickActionProps): JSX.Element {
  const colors = colorClasses[color]

  return (
    <button
      onClick={onClick}
      className={cn(
        'group relative flex items-center gap-4 rounded-2xl border border-border bg-card p-5 text-left',
        'transition-all duration-300 ease-out',
        'hover:-translate-y-1 hover:shadow-xl hover:shadow-black/5',
        'hover:border-accent/30',
        'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
        'animate-fade-in opacity-0'
      )}
      style={{ animationDelay: `${index * 75 + 200}ms` }}
    >
      {/* Gradient overlay on hover */}
      <div className={cn(
        'absolute inset-0 rounded-2xl opacity-0 transition-opacity duration-300',
        'group-hover:opacity-100 pointer-events-none',
        colors.bg
      )} />

      <div className={cn(
        'relative flex h-14 w-14 flex-shrink-0 items-center justify-center rounded-xl',
        colors.bg,
        colors.icon,
        'ring-1',
        colors.ring,
        'transition-all duration-300',
        'group-hover:shadow-lg',
        colors.shadow,
        'group-hover:scale-105'
      )}>
        {icon}
      </div>

      <div className="relative flex-1 min-w-0">
        <p className="font-semibold text-foreground group-hover:text-accent transition-colors duration-300">
          {label}
        </p>
        <p className="mt-0.5 text-sm text-muted-foreground truncate">{description}</p>
      </div>

      <div className={cn(
        'relative opacity-0 translate-x-2',
        'transition-all duration-300',
        'group-hover:opacity-100 group-hover:translate-x-0'
      )}>
        <ArrowRight className="h-5 w-5 text-accent" />
      </div>
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
        return <CheckCircle2 className="h-4 w-4 text-emerald-500" />
      case 'in-progress':
        return <Activity className="h-4 w-4 text-amber-500" />
      case 'pending':
        return <Clock className="h-4 w-4 text-muted-foreground" />
      default:
        return null
    }
  }

  return (
    <div className="group flex items-start gap-4 py-4 transition-colors duration-200 hover:bg-muted/30 px-2 -mx-2 rounded-lg">
      <div className={cn(
        'flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl',
        'bg-muted/50 text-muted-foreground',
        'transition-all duration-200',
        'group-hover:bg-accent/10 group-hover:text-accent'
      )}>
        {getIcon()}
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="font-medium text-foreground truncate">{title}</p>
          {getStatusIcon()}
        </div>
        <p className="mt-0.5 text-sm text-muted-foreground truncate">{description}</p>
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
    <div className="space-y-8">
      {/* Welcome Section */}
      <div className={cn(
        'relative overflow-hidden rounded-2xl p-8',
        'bg-gradient-to-br from-sidebar via-sidebar to-sidebar-muted/50',
        'border border-sidebar-muted/30',
        'animate-fade-in'
      )}>
        {/* Background decorations */}
        <div className="absolute -top-24 -right-24 h-64 w-64 rounded-full bg-gradient-to-br from-amber-500/20 to-orange-500/10 blur-3xl" />
        <div className="absolute -bottom-24 -left-24 h-64 w-64 rounded-full bg-gradient-to-br from-violet-500/10 to-purple-500/10 blur-3xl" />

        <div className="relative">
          <div className="flex items-center gap-3 mb-2">
            <Sparkles className="h-6 w-6 text-amber-400" />
            <span className="text-sm font-medium text-amber-400">Dashboard</span>
          </div>
          <h2 className="text-3xl font-bold tracking-tight text-white">
            Good morning!
          </h2>
          <p className="mt-2 text-slate-400 max-w-lg">
            Here's an overview of your projects and recent activity. Let's make today productive.
          </p>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          icon={<FolderKanban className="h-6 w-6" />}
          label="Applications"
          value={0}
          color="amber"
          index={0}
        />
        <StatCard
          icon={<LayoutDashboard className="h-6 w-6" />}
          label="Projects"
          value={0}
          color="violet"
          index={1}
        />
        <StatCard
          icon={<Target className="h-6 w-6" />}
          label="Active Tasks"
          value={0}
          color="blue"
          index={2}
        />
        <StatCard
          icon={<CheckCircle2 className="h-6 w-6" />}
          label="Completed"
          value={0}
          trend={{ value: 0, isPositive: true }}
          color="emerald"
          index={3}
        />
      </div>

      {/* Quick Actions */}
      <div>
        <div className="mb-5 flex items-center gap-3">
          <Zap className="h-5 w-5 text-amber-500" />
          <h3 className="text-lg font-semibold text-foreground">Quick Actions</h3>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <QuickAction
            icon={<FolderKanban className="h-6 w-6" />}
            label="Create Application"
            description="Start a new project container"
            color="amber"
            onClick={onNavigateToApplications}
            index={0}
          />
          <QuickAction
            icon={<ListTodo className="h-6 w-6" />}
            label="Add Task"
            description="Create a new task or issue"
            color="violet"
            onClick={onNavigateToTasks}
            index={1}
          />
          <QuickAction
            icon={<StickyNote className="h-6 w-6" />}
            label="New Note"
            description="Start writing a new note"
            color="emerald"
            onClick={onNavigateToNotes}
            index={2}
          />
        </div>
      </div>

      {/* Recent Activity */}
      <div>
        <div className="mb-5 flex items-center gap-3">
          <Activity className="h-5 w-5 text-violet-500" />
          <h3 className="text-lg font-semibold text-foreground">Recent Activity</h3>
        </div>
        <div className={cn(
          'rounded-2xl border border-border bg-card overflow-hidden',
          'animate-fade-in opacity-0'
        )} style={{ animationDelay: '400ms' }}>
          <div className="p-6">
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <div className={cn(
                'flex h-16 w-16 items-center justify-center rounded-2xl mb-4',
                'bg-muted/50'
              )}>
                <LayoutDashboard className="h-8 w-8 text-muted-foreground/50" />
              </div>
              <p className="font-medium text-foreground">No recent activity</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Your recent updates will appear here
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}


// ============================================================================
// Dashboard Page Component
// ============================================================================

export function DashboardPage({
  theme = 'system',
  onThemeChange,
}: DashboardProps): JSX.Element {
  const [activeItem, setActiveItem] = useState<NavItem>('dashboard')
  const [selectedApplicationId, setSelectedApplicationId] = useState<string | null>(null)
  const [selectedApplicationName, setSelectedApplicationName] = useState<string | null>(null)
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null)

  const [isCollapsed, setIsCollapsed] = useState<boolean>(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('pm-sidebar-collapsed')
      return saved === 'true'
    }
    return false
  })

  // Auth store
  const token = useAuthStore((state) => state.token)

  // Notification store
  const addNotification = useNotificationsStore((state) => state.addNotification)
  const fetchNotifications = useNotificationsStore((state) => state.fetchNotifications)

  // WebSocket status for reconnect handling
  const { status: wsStatus } = useWebSocket()

  // Track previous connection state to detect reconnection vs initial connection
  const prevConnectedRef = useRef<boolean | null>(null)
  const fetchTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Track current application ID for WebSocket handlers (to detect if user is viewing removed application)
  const selectedApplicationIdRef = useRef<string | null>(selectedApplicationId)
  selectedApplicationIdRef.current = selectedApplicationId

  // Sync notification read status across tabs/devices
  useNotificationReadSync()

  // Request browser notification permission on mount
  useEffect(() => {
    requestNotificationPermission()
  }, [])

  // Fetch notifications on initial load and WebSocket reconnect (with debouncing)
  useEffect(() => {
    const wasConnected = prevConnectedRef.current
    prevConnectedRef.current = wsStatus.isConnected

    // Only fetch if:
    // 1. We have a token
    // 2. We're now connected
    // 3. Either this is the first connection (wasConnected === null) OR we reconnected (wasConnected === false)
    if (token && wsStatus.isConnected && (wasConnected === null || wasConnected === false)) {
      // Debounce fetch to prevent multiple rapid calls during reconnection flapping
      if (fetchTimeoutRef.current) {
        clearTimeout(fetchTimeoutRef.current)
      }

      fetchTimeoutRef.current = setTimeout(() => {
        fetchNotifications(token)
        fetchTimeoutRef.current = null
      }, 500) // 500ms debounce
    }

    return () => {
      if (fetchTimeoutRef.current) {
        clearTimeout(fetchTimeoutRef.current)
      }
    }
  }, [token, wsStatus.isConnected, fetchNotifications])

  // Listen for invitation-related WebSocket events
  useInvitationNotifications({
    onInvitationReceived: (data) => {
      // Refresh notifications from backend to get the persisted notification with correct ID
      // This ensures read state is properly synced
      if (token) {
        fetchNotifications(token)
      }
    },
    onInvitationResponse: (data) => {
      // Refresh notifications from backend to get the persisted notification with correct ID
      if (token) {
        fetchNotifications(token)
      }
    },
    onMemberAdded: (data) => {
      console.log('[Dashboard] onMemberAdded triggered:', data)

      // Check if current user is the one who was added (just joined via invitation)
      const currentUserId = useAuthStore.getState().user?.id
      const isCurrentUserAdded = currentUserId === data.user_id

      // Refresh notifications from backend to get persisted notification with correct ID
      if (token) {
        fetchNotifications(token)
      }

      // If current user just joined, refresh applications list to show the new application
      if (isCurrentUserAdded && token) {
        console.log('[Dashboard] Current user was added, refreshing applications')
        useApplicationsStore.getState().fetchApplications(token)
      }

      // Re-fetch members if viewing this application to get full member data
      const membersStore = useMembersStore.getState()
      console.log('[Dashboard] Checking currentApplicationId:', {
        currentAppId: membersStore.currentApplicationId,
        dataAppId: data.application_id,
        match: membersStore.currentApplicationId === data.application_id
      })
      if (membersStore.currentApplicationId === data.application_id && token) {
        console.log('[Dashboard] Fetching members for application:', data.application_id)
        membersStore.fetchMembers(token, data.application_id)
      }
    },
    onMemberRemoved: (data) => {
      // Check if current user is the one being removed
      const currentUserId = useAuthStore.getState().user?.id
      const isCurrentUserRemoved = currentUserId === data.user_id

      // Refresh notifications from backend to get persisted notification with correct ID
      if (token) {
        fetchNotifications(token)
      }

      // If current user was removed, kick them out if viewing that application
      if (isCurrentUserRemoved) {
        // Check if user is currently viewing the application they were removed from
        if (selectedApplicationIdRef.current === data.application_id) {
          // Kick user back to applications list
          setSelectedApplicationId(null)
          setSelectedApplicationName(null)
          setSelectedProjectId(null)
        }
        // Refresh applications list to remove the application they no longer have access to
        if (token) {
          useApplicationsStore.getState().fetchApplications(token)
        }
      } else {
        // Update members store if viewing this application (for other team members)
        const membersStore = useMembersStore.getState()
        if (membersStore.currentApplicationId === data.application_id) {
          membersStore.removeMemberFromList(data.user_id)
        }
      }
    },
    onRoleUpdated: (data) => {
      // Refresh notifications from backend to get persisted notification with correct ID
      if (token) {
        fetchNotifications(token)
      }

      // Update members store if viewing this application
      const membersStore = useMembersStore.getState()
      if (membersStore.currentApplicationId === data.application_id) {
        // Find and update the member in the list
        const member = membersStore.members.find(m => m.user_id === data.user_id)
        if (member) {
          membersStore.updateMemberInList({
            ...member,
            role: data.new_role,
          })
        }
      }
    },
  })

  useEffect(() => {
    localStorage.setItem('pm-sidebar-collapsed', String(isCollapsed))
  }, [isCollapsed])

  const handleNavigate = useCallback((item: NavItem) => {
    setActiveItem(item)
    if (item !== 'applications') {
      setSelectedApplicationId(null)
      setSelectedApplicationName(null)
    }
    if (item !== 'projects') {
      setSelectedProjectId(null)
    }
  }, [])

  const handleSelectApplication = useCallback((application: Application) => {
    setSelectedApplicationId(application.id)
    setSelectedApplicationName(application.name)
  }, [])

  const handleBackToApplications = useCallback(() => {
    setSelectedApplicationId(null)
    setSelectedApplicationName(null)
    setSelectedProjectId(null)
  }, [])

  const handleSelectProjectFromApp = useCallback((projectId: string) => {
    setSelectedProjectId(projectId)
  }, [])

  const handleSelectProject = useCallback((project: Project) => {
    setSelectedProjectId(project.id)
  }, [])

  const handleBackToProjects = useCallback(() => {
    setSelectedProjectId(null)
  }, [])

  const handleCollapsedChange = useCallback((collapsed: boolean) => {
    setIsCollapsed(collapsed)
  }, [])

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
        if (selectedApplicationId && selectedProjectId) {
          return (
            <ProjectDetailPage
              projectId={selectedProjectId}
              onBack={handleBackToProjects}
              onDeleted={handleBackToProjects}
            />
          )
        }
        if (selectedApplicationId) {
          return (
            <ApplicationDetailPage
              applicationId={selectedApplicationId}
              onBack={handleBackToApplications}
              onDeleted={handleBackToApplications}
              onSelectProject={handleSelectProjectFromApp}
            />
          )
        }
        return (
          <ApplicationsPage
            onSelectApplication={handleSelectApplication}
          />
        )
      case 'projects':
        if (selectedProjectId) {
          return (
            <ProjectDetailPage
              projectId={selectedProjectId}
              onBack={handleBackToProjects}
              onDeleted={handleBackToProjects}
            />
          )
        }
        if (selectedApplicationId) {
          return (
            <ProjectsPage
              applicationId={selectedApplicationId}
              applicationName={selectedApplicationName || undefined}
              onSelectProject={handleSelectProject}
              onBack={handleBackToApplications}
            />
          )
        }
        return (
          <div className="flex flex-1 items-center justify-center">
            <div className="text-center animate-fade-in">
              <div className={cn(
                'mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-2xl',
                'bg-muted/50'
              )}>
                <LayoutDashboard className="h-10 w-10 text-muted-foreground/50" />
              </div>
              <h2 className="text-xl font-semibold text-foreground">Projects</h2>
              <p className="mt-2 text-muted-foreground">
                Select an application to view its projects
              </p>
              <button
                onClick={() => handleNavigate('applications')}
                className={cn(
                  'mt-6 inline-flex items-center gap-2 rounded-xl px-5 py-2.5',
                  'text-sm font-semibold',
                  'bg-gradient-to-r from-amber-500 to-orange-500 text-white',
                  'transition-all duration-300',
                  'hover:from-amber-400 hover:to-orange-400 hover:shadow-lg hover:shadow-amber-500/25',
                  'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2'
                )}
              >
                Go to Applications
                <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        )
      case 'tasks':
        return (
          <div className="flex flex-1 items-center justify-center">
            <div className="text-center animate-fade-in">
              <div className={cn(
                'mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-2xl',
                'bg-muted/50'
              )}>
                <ListTodo className="h-10 w-10 text-muted-foreground/50" />
              </div>
              <h2 className="text-xl font-semibold text-foreground">Tasks</h2>
              <p className="mt-2 text-muted-foreground">
                Task management coming soon...
              </p>
            </div>
          </div>
        )
      case 'notes':
        return (
          <NotesPage
            applicationId={selectedApplicationId}
          />
        )
      case 'settings':
        return (
          <div className="flex flex-1 items-center justify-center">
            <div className="text-center animate-fade-in">
              <h2 className="text-xl font-semibold text-foreground">Settings</h2>
              <p className="mt-2 text-muted-foreground">
                Settings page coming soon...
              </p>
            </div>
          </div>
        )
      default:
        return <DashboardContent />
    }
  }

  return (
    <div className="flex h-screen flex-col bg-background">
      {/* Unified Title Bar with utility controls */}
      <WindowTitleBar theme={theme} onThemeChange={onThemeChange} />

      {/* Main Layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <Sidebar
          activeItem={activeItem}
          onNavigate={handleNavigate}
          isCollapsed={isCollapsed}
          onCollapsedChange={handleCollapsedChange}
        />

        {/* Main Content Area - reduced padding for space efficiency */}
        <main className="flex-1 overflow-auto p-4 lg:p-5">
          {renderContent()}
        </main>
      </div>

      {/* Notification Panel */}
      <NotificationPanel sidebarCollapsed={isCollapsed} />
    </div>
  )
}

export default DashboardPage
