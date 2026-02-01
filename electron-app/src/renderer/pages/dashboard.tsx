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

import { useState, useCallback, useEffect, useRef, useMemo, ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { Sidebar, type NavItem } from '@/components/layout/sidebar'
import { WindowTitleBar } from '@/components/layout/window-title-bar'
import { NotificationPanel } from '@/components/layout/notification-panel'
import { ApplicationsPage } from '@/pages/applications/index'
import { ApplicationDetailPage } from '@/pages/applications/[id]'
import { ProjectsPage } from '@/pages/projects/index'
import { ProjectDetailPage } from '@/pages/projects/[id]'
import { NotesPage } from '@/pages/notes/index'
import { MyTasksPanel } from '@/components/tasks/MyTasksPanel'
import { MyProjectsPanel } from '@/components/dashboard/MyProjectsPanel'
import { DashboardTasksList } from '@/components/dashboard/DashboardTasksList'
import { useInvitationNotifications, useWebSocket, useNotificationReadSync, useProjectDeletedSync, useNotifications } from '@/hooks/use-websocket'
import { useWebSocketCacheInvalidation } from '@/hooks/use-websocket-cache'
import { requestNotificationPermission } from '@/lib/notifications'
import { useAuthStore } from '@/contexts/auth-context'
import { useQueryClient } from '@tanstack/react-query'
import { queryKeys } from '@/lib/query-client'
import { useApplications } from '@/hooks/use-queries'
import type { Project, Application, Task } from '@/hooks/use-queries'
import {
  FolderKanban,
  ListTodo,
  LayoutDashboard,
  ArrowRight,
  CheckCircle2,
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

// ============================================================================
// Dashboard Content Component
// ============================================================================

interface DashboardContentProps {
  applicationId?: string | null
  onNavigateToApplications?: () => void
  onNavigateToTasks?: () => void
  onProjectClick?: (project: Project) => void
  onTaskClick?: (task: Task) => void
}

function DashboardContent({
  applicationId,
  onNavigateToApplications,
  onNavigateToTasks,
  onProjectClick,
  onTaskClick,
}: DashboardContentProps): JSX.Element {
  const { data: applications } = useApplications()
  const appCount = applications?.length ?? 0
  const projectCount = applications?.reduce((sum, app) => sum + app.projects_count, 0) ?? 0

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
          value={appCount}
          color="amber"
          index={0}
        />
        <StatCard
          icon={<LayoutDashboard className="h-6 w-6" />}
          label="Projects"
          value={projectCount}
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
          color="emerald"
          index={3}
        />
      </div>

      {/* Two-column layout: Projects + Tasks */}
      {applicationId && (
        <div className="grid gap-6 lg:grid-cols-2" style={{ minHeight: '400px' }}>
          <MyProjectsPanel
            applicationId={applicationId}
            onProjectClick={onProjectClick}
          />
          <DashboardTasksList
            applicationId={applicationId}
            onTaskClick={onTaskClick}
          />
        </div>
      )}

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
        </div>
      </div>

      {/* Prompt to select application if none selected */}
      {!applicationId && (
        <div>
          <div className="mb-5 flex items-center gap-3">
            <Activity className="h-5 w-5 text-violet-500" />
            <h3 className="text-lg font-semibold text-foreground">Projects & Tasks</h3>
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
                <p className="font-medium text-foreground">Select an application</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Choose an application from the sidebar to see your projects and tasks
                </p>
                <button
                  onClick={onNavigateToApplications}
                  className={cn(
                    'mt-4 inline-flex items-center gap-2 rounded-xl px-5 py-2.5',
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
          </div>
        </div>
      )}
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
  const [initialTaskId, setInitialTaskId] = useState<string | null>(null)
  const handleInitialTaskConsumed = useCallback(() => setInitialTaskId(null), [])

  const [isCollapsed, setIsCollapsed] = useState<boolean>(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('pm-sidebar-collapsed')
      return saved === 'true'
    }
    return false
  })

  // Auth store
  const token = useAuthStore((state) => state.token)
  const currentUser = useAuthStore((state) => state.user)

  // TanStack Query client for cache invalidation
  const queryClient = useQueryClient()

  // WebSocket status for reconnect handling
  const { status: wsStatus } = useWebSocket()

  // Track previous connection state to detect reconnection vs initial connection
  const prevConnectedRef = useRef<boolean | null>(null)
  const fetchTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Track current application ID for WebSocket handlers (to detect if user is viewing removed application)
  const selectedApplicationIdRef = useRef<string | null>(selectedApplicationId)
  selectedApplicationIdRef.current = selectedApplicationId

  // Track current project ID for WebSocket handlers (to detect if user is viewing deleted project)
  const selectedProjectIdRef = useRef<string | null>(selectedProjectId)
  selectedProjectIdRef.current = selectedProjectId

  // Sync notification read status across tabs/devices
  useNotificationReadSync()

  // Sync project deletions across tabs/devices
  useProjectDeletedSync()

  // Memoize the callback to avoid recreating the options object on every render
  const handleCurrentUserRemoved = useCallback((applicationId: string) => {
    console.log('[Dashboard] onCurrentUserRemoved callback:', applicationId)
    console.log('[Dashboard] selectedApplicationIdRef.current:', selectedApplicationIdRef.current)
    // If user is viewing the application they were removed from, redirect to apps list
    if (selectedApplicationIdRef.current === applicationId) {
      console.log('[Dashboard] User was viewing removed app, redirecting to applications list')
      setSelectedApplicationId(null)
      setSelectedApplicationName(null)
      setSelectedProjectId(null)
      setActiveItem('applications')
    }
  }, []) // Empty deps - uses refs and stable setters

  // Handle project deletion - redirect if user is viewing deleted project
  const handleProjectDeleted = useCallback((projectId: string, _applicationId: string) => {
    console.log('[Dashboard] onProjectDeleted callback:', projectId)
    console.log('[Dashboard] selectedProjectIdRef.current:', selectedProjectIdRef.current)
    // If user is viewing the project that was deleted, redirect to application view
    if (selectedProjectIdRef.current === projectId) {
      console.log('[Dashboard] User was viewing deleted project, redirecting to application view')
      setSelectedProjectId(null)
      // Stay in the same application, just clear the project
    }
  }, []) // Empty deps - uses refs and stable setters

  // Memoize options to prevent unnecessary effect runs
  const cacheOptions = useMemo(() => ({
    onCurrentUserRemoved: handleCurrentUserRemoved,
    onProjectDeleted: handleProjectDeleted,
  }), [handleCurrentUserRemoved, handleProjectDeleted])

  // WebSocket cache invalidation with redirect handling for member removal
  useWebSocketCacheInvalidation(cacheOptions)

  // Request browser notification permission on mount
  useEffect(() => {
    requestNotificationPermission()
  }, [])

  // Invalidate notifications on initial load and WebSocket reconnect (with debouncing)
  useEffect(() => {
    const wasConnected = prevConnectedRef.current
    prevConnectedRef.current = wsStatus.isConnected

    // Only invalidate if:
    // 1. We have a token
    // 2. We're now connected
    // 3. Either this is the first connection (wasConnected === null) OR we reconnected (wasConnected === false)
    if (token && wsStatus.isConnected && (wasConnected === null || wasConnected === false)) {
      // Debounce to prevent multiple rapid calls during reconnection flapping
      if (fetchTimeoutRef.current) {
        clearTimeout(fetchTimeoutRef.current)
      }

      fetchTimeoutRef.current = setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: queryKeys.notifications })
        fetchTimeoutRef.current = null
      }, 500) // 500ms debounce
    }

    return () => {
      if (fetchTimeoutRef.current) {
        clearTimeout(fetchTimeoutRef.current)
      }
    }
  }, [token, wsStatus.isConnected, queryClient])

  // Listen for invitation-related WebSocket events
  useInvitationNotifications({
    onInvitationReceived: (_data) => {
      // Invalidate notifications to refetch from backend
      queryClient.invalidateQueries({ queryKey: queryKeys.notifications })
    },
    onInvitationResponse: (_data) => {
      // Invalidate notifications to refetch from backend
      queryClient.invalidateQueries({ queryKey: queryKeys.notifications })
    },
    onMemberAdded: (data) => {
      console.log('[Dashboard] onMemberAdded triggered:', data)

      // Check if current user is the one who was added (just joined via invitation)
      const currentUserId = currentUser?.id
      const isCurrentUserAdded = currentUserId === data.user_id

      // Invalidate notifications
      queryClient.invalidateQueries({ queryKey: queryKeys.notifications })

      // If current user just joined, invalidate applications list to show the new application
      if (isCurrentUserAdded) {
        console.log('[Dashboard] Current user was added, invalidating applications')
        queryClient.invalidateQueries({ queryKey: queryKeys.applications })
      }

      // Invalidate members for this application (TanStack Query will refetch if needed)
      queryClient.invalidateQueries({ queryKey: queryKeys.appMembers(data.application_id) })
    },
    onMemberRemoved: (data) => {
      // Note: Cache invalidation and redirect are handled by useWebSocketCacheInvalidation
      // This handler is kept for notification invalidation (different from NOTIFICATION event)
      console.log('[Dashboard] onMemberRemoved from useInvitationNotifications:', data)
      queryClient.invalidateQueries({ queryKey: queryKeys.notifications })
    },
    onRoleUpdated: (data) => {
      // Invalidate notifications
      queryClient.invalidateQueries({ queryKey: queryKeys.notifications })

      // Invalidate members for this application (will show updated role)
      queryClient.invalidateQueries({ queryKey: queryKeys.appMembers(data.application_id) })
    },
  })

  // Listen for generic notification messages (project role changes, task assignments, etc.)
  useNotifications((_data) => {
    // Invalidate notifications when any notification is received
    // This ensures project-level notifications (role changes, etc.) are captured
    queryClient.invalidateQueries({ queryKey: queryKeys.notifications })
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
            applicationId={selectedApplicationId}
            onNavigateToApplications={() => handleNavigate('applications')}
            onNavigateToTasks={() => handleNavigate('tasks')}
            onProjectClick={(project) => {
              setSelectedApplicationId(project.application_id)
              setSelectedProjectId(project.id)
              setActiveItem('applications')
            }}
            onTaskClick={(task) => {
              if (task.project_id) {
                setSelectedApplicationId(task.application_id || null)
                setSelectedApplicationName(task.application_name || null)
                setSelectedProjectId(task.project_id)
                setInitialTaskId(task.id)
                setActiveItem('projects')
              }
            }}
          />
        )
      case 'applications':
        if (selectedApplicationId && selectedProjectId) {
          return (
            <ProjectDetailPage
              projectId={selectedProjectId}
              applicationId={selectedApplicationId}
              initialTaskId={initialTaskId}
              onInitialTaskConsumed={handleInitialTaskConsumed}
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
        if (selectedProjectId && selectedApplicationId) {
          return (
            <ProjectDetailPage
              projectId={selectedProjectId}
              applicationId={selectedApplicationId}
              initialTaskId={initialTaskId}
              onInitialTaskConsumed={handleInitialTaskConsumed}
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
          <div className="flex absolute inset-0">
            {/* Left pane: Projects */}
            <div className="w-1/2 border-r border-border p-4 pb-0">
              <MyProjectsPanel
                onProjectClick={(project) => {
                  setSelectedApplicationId(project.application_id)
                  setSelectedApplicationName(project.application_name || null)
                  setSelectedProjectId(project.id)
                  setActiveItem('projects')
                }}
              />
            </div>
            {/* Right pane: Tasks */}
            <div className="w-1/2 p-4 pb-0">
              <DashboardTasksList
                onTaskClick={(task) => {
                  if (task.project_id) {
                    setSelectedApplicationId(task.application_id || null)
                    setSelectedApplicationName(task.application_name || null)
                    setSelectedProjectId(task.project_id)
                    setInitialTaskId(task.id)
                    setActiveItem('projects')
                  }
                }}
              />
            </div>
          </div>
        )
      case 'notes':
        return (
          <NotesPage applicationId={selectedApplicationId} />
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
        <main className={cn("flex-1 overflow-auto p-4 lg:p-5", activeItem === 'tasks' && "relative", activeItem === 'notes' && "p-0 overflow-hidden")}>
          {renderContent()}
        </main>
      </div>

      {/* Notification Panel */}
      <NotificationPanel sidebarCollapsed={isCollapsed} />
    </div>
  )
}

export default DashboardPage
