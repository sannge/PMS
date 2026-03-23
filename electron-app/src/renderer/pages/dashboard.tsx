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

import React, { useState, useCallback, useEffect, useRef, useMemo, ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { Sidebar, type NavItem } from '@/components/layout/sidebar'
import { WindowTitleBar } from '@/components/layout/window-title-bar'
import { NotificationPanel } from '@/components/layout/notification-panel'
import { ApplicationsPage } from '@/pages/applications/index'
import { ApplicationDetailPage } from '@/pages/applications/[id]'
import { ProjectsPage } from '@/pages/projects/index'
import { ProjectDetailPage } from '@/pages/projects/[id]'
import { NotesPage } from '@/pages/notes/index'
import { TeamActivityPage } from '@/pages/team-activity-page'
import { AiSettingsPanel, AiToggleButton, AiSidebar } from '@/components/ai'
import { checkScreenGuard } from '@/lib/screen-navigation-guard'
import { setScreenSwitcher, clearScreenSwitcher } from '@/lib/ai-navigation'
import { MyProjectsPanel } from '@/components/dashboard/MyProjectsPanel'
import { DashboardTasksList } from '@/components/dashboard/DashboardTasksList'
import { useInvitationNotifications, useWebSocket, useNotificationReadSync, useProjectDeletedSync, useNotifications } from '@/hooks/use-websocket'
import { useWebSocketCacheInvalidation } from '@/hooks/use-websocket-cache'
import { requestNotificationPermission } from '@/lib/notifications'
import { useAuthStore } from '@/contexts/auth-context'
import { useQueryClient } from '@tanstack/react-query'
import { queryKeys } from '@/lib/query-client'
import { useDashboardStats, useApplications, useCreateApplication, useCreateProject } from '@/hooks/use-queries'
import type { ApplicationCreate, ProjectCreate } from '@/hooks/use-queries'
import { useDashboardWebSocket } from '@/hooks/use-dashboard-websocket'
import { DashboardSkeleton } from '@/components/dashboard/DashboardSkeleton'
import { TaskDistributionChart } from '@/components/dashboard/TaskDistributionChart'
import { CompletionTrendChart } from '@/components/dashboard/CompletionTrendChart'
import { ProjectHealthChart } from '@/components/dashboard/ProjectHealthChart'
import { OverdueTasksList } from '@/components/dashboard/OverdueTasksList'
import { RecentlyCompletedList } from '@/components/dashboard/RecentlyCompletedList'
import { PulseIndicator } from '@/components/ui/skeleton'
import type { Project, Application, Task } from '@/hooks/use-queries'

// Narrow navigation types to avoid unsafe `as Project`/`as Task` casts
type ProjectNavTarget = Pick<Project, 'id' | 'application_id'> & { application_name?: string | null }
type TaskNavTarget = Pick<Task, 'id'> & {
  application_id?: string | null
  application_name?: string | null
  project_id: string
}
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
  AlertTriangle,
  X,
  Layers,
  Plus,
  ChevronRight,
} from 'lucide-react'
import { toast } from 'sonner'

// ============================================================================
// Types
// ============================================================================

export interface DashboardProps {
  // Reserved for future props
}

interface StatCardProps {
  icon: ReactNode
  label: string
  value: string | number
  trend?: {
    value: number
    isPositive: boolean
  }
  color: 'amber' | 'violet' | 'emerald' | 'blue' | 'red' | 'slate'
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
  red: {
    bg: 'bg-gradient-to-br from-red-400/20 via-rose-500/15 to-red-600/10',
    icon: 'text-red-600 dark:text-red-400',
    ring: 'ring-red-500/20',
    shadow: 'group-hover:shadow-red-500/20',
  },
  slate: {
    bg: 'bg-gradient-to-br from-slate-400/20 via-slate-500/15 to-slate-600/10',
    icon: 'text-slate-600 dark:text-slate-400',
    ring: 'ring-slate-500/20',
    shadow: 'group-hover:shadow-slate-500/20',
  },
}

function StatCard({ icon, label, value, trend, color, index = 0 }: StatCardProps): JSX.Element {
  const colors = colorClasses[color]

  return (
    <div
      role="figure"
      aria-label={label}
      className={cn(
        'group relative rounded-2xl border border-border bg-card p-5',
        'transition-all duration-300 ease-out',
        'hover:-translate-y-1 hover:shadow-xl hover:shadow-black/5',
        'animate-fade-in'
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
          <div
            className={cn(
              'flex items-center gap-1 rounded-full px-2.5 py-1',
              'text-xs font-semibold',
              trend.isPositive
                ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                : 'bg-red-500/10 text-red-600 dark:text-red-400'
            )}
            aria-label={`${trend.isPositive ? 'Up' : 'Down'} ${trend.value}%`}
          >
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
        'animate-fade-in'
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
// Chart Error Boundary
// ============================================================================

class ChartErrorBoundary extends React.Component<
  { children: React.ReactNode; fallback?: React.ReactNode },
  { hasError: boolean }
> {
  state = { hasError: false }
  static getDerivedStateFromError() { return { hasError: true } }
  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[ChartErrorBoundary]', error, info)
  }
  render() {
    if (this.state.hasError) {
      return this.props.fallback || (
        <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
          Unable to display chart
        </div>
      )
    }
    return this.props.children
  }
}

// ============================================================================
// Dashboard Content Component
// ============================================================================

interface DashboardContentProps {
  applicationId?: string | null
  onNavigateToApplications?: () => void
  onNavigateToTasks?: () => void
  onProjectClick?: (project: ProjectNavTarget) => void
  onTaskClick?: (task: TaskNavTarget) => void
}

function DashboardContent({
  applicationId,
  onNavigateToApplications,
  onNavigateToTasks,
  onProjectClick,
  onTaskClick,
}: DashboardContentProps): JSX.Element {
  const { data, isLoading, isFetching, isError, refetch } = useDashboardStats()

  // Component-level WS invalidation (only active while dashboard is mounted)
  useDashboardWebSocket()

  // Stabilize inline handlers to avoid re-renders of chart/list children
  const handleHealthProjectClick = useCallback(
    (projectId: string, applicationId: string, applicationName: string) => {
      onProjectClick?.({
        id: projectId,
        application_id: applicationId,
        application_name: applicationName,
      })
    },
    [onProjectClick]
  )

  const handleListTaskClick = useCallback(
    (task: { id: string; project_id: string; application_id: string; application_name: string }) => {
      onTaskClick?.({
        id: task.id,
        project_id: task.project_id,
        application_id: task.application_id,
        application_name: task.application_name,
      })
    },
    [onTaskClick]
  )

  // Dynamic time-of-day greeting (local time)
  const greeting = (() => {
    const hour = new Date().getHours()
    if (hour < 12) return 'Good morning!'
    if (hour < 17) return 'Good afternoon!'
    return 'Good evening!'
  })()

  // Show skeleton on initial load (no cached data)
  if (isLoading && !data) return <DashboardSkeleton />

  // Show error state only if query failed and no cached data
  if (isError && !data) {
    return (
      <div className="flex flex-col items-center justify-center py-20 space-y-4">
        <div className="text-muted-foreground text-sm">Failed to load dashboard data</div>
        <button
          onClick={() => refetch()}
          className="px-4 py-2 text-sm font-medium rounded-md bg-primary text-primary-foreground hover:bg-primary/90"
        >
          Try Again
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      {/* Stale data banner when background refetch failed */}
      {isError && data && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-2 text-sm text-amber-600 dark:text-amber-400">
          <AlertTriangle className="h-4 w-4 flex-shrink-0" />
          <span>Unable to refresh data. Showing cached results.</span>
          <button
            onClick={() => refetch()}
            className="ml-auto text-xs font-medium underline hover:no-underline"
          >
            Retry
          </button>
        </div>
      )}

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
            {isFetching && data && (
              <PulseIndicator color="primary" className="ml-2" />
            )}
          </div>
          <h2 className="text-3xl font-bold tracking-tight text-foreground">
            {greeting}
          </h2>
          <p className="mt-2 text-muted-foreground max-w-lg">
            Here's an overview of your projects and recent activity. Let's make today productive.
          </p>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <StatCard
          icon={<FolderKanban className="h-6 w-6" />}
          label="Workspaces"
          value={data?.applications_count ?? 0}
          color="amber"
          index={0}
        />
        <StatCard
          icon={<LayoutDashboard className="h-6 w-6" />}
          label="Projects"
          value={data?.projects_count ?? 0}
          color="violet"
          index={1}
        />
        <StatCard
          icon={<Target className="h-6 w-6" />}
          label="Active Tasks"
          value={data?.active_tasks_count ?? 0}
          trend={data?.active_tasks_trend ? { value: data.active_tasks_trend.value, isPositive: data.active_tasks_trend.is_positive } : undefined}
          color="blue"
          index={2}
        />
        <StatCard
          icon={<CheckCircle2 className="h-6 w-6" />}
          label="Completed This Week"
          value={data?.completed_this_week ?? 0}
          trend={data?.completed_trend ? { value: data.completed_trend.value, isPositive: data.completed_trend.is_positive } : undefined}
          color="emerald"
          index={3}
        />
        <StatCard
          icon={<AlertTriangle className="h-6 w-6" />}
          label="Overdue"
          value={data?.overdue_tasks_count ?? 0}
          color={(data?.overdue_tasks_count ?? 0) > 0 ? 'red' : 'slate'}
          index={4}
        />
      </div>

      {/* Charts */}
      <div
        className="grid gap-6 md:grid-cols-2 lg:grid-cols-3 animate-fade-in"
        style={{ animationDelay: '200ms' }}
      >
        <ChartErrorBoundary>
          <TaskDistributionChart data={data?.task_status_breakdown ?? { todo: 0, in_progress: 0, in_review: 0, issue: 0, done: 0 }} />
        </ChartErrorBoundary>
        <ChartErrorBoundary>
          <CompletionTrendChart data={data?.completion_trend ?? []} />
        </ChartErrorBoundary>
        <ChartErrorBoundary>
          <ProjectHealthChart
            data={data?.project_health ?? []}
            onProjectClick={handleHealthProjectClick}
          />
        </ChartErrorBoundary>
      </div>

      {/* Actionable Lists */}
      <div
        className="grid gap-6 lg:grid-cols-2 animate-fade-in"
        style={{ animationDelay: '400ms' }}
      >
        <OverdueTasksList
          overdueTasks={data?.overdue_tasks ?? []}
          upcomingTasks={data?.upcoming_tasks ?? []}
          onTaskClick={handleListTaskClick}
        />
        <RecentlyCompletedList
          tasks={data?.recently_completed ?? []}
          onTaskClick={handleListTaskClick}
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
            label="Create Workspace"
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
            'animate-fade-in'
          )} style={{ animationDelay: '400ms' }}>
            <div className="p-6">
              <div className="flex flex-col items-center justify-center py-12 text-center">
                <div className={cn(
                  'flex h-16 w-16 items-center justify-center rounded-2xl mb-4',
                  'bg-muted/50'
                )}>
                  <LayoutDashboard className="h-8 w-8 text-muted-foreground/50" />
                </div>
                <p className="font-medium text-foreground">Select a workspace</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Choose a workspace from the sidebar to see your projects and tasks
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
                  Go to Workspaces
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
// Quick Create Dialog
// ============================================================================

type QuickCreateStep = 'choose' | 'application' | 'project-pick-app' | 'project-form'

function QuickCreateDialog({
  isOpen,
  onClose,
  onCreated,
}: {
  isOpen: boolean
  onClose: () => void
  onCreated: (type: 'application' | 'project', id: string, applicationId?: string) => void
}): JSX.Element | null {
  const [step, setStep] = useState<QuickCreateStep>('choose')
  const [appName, setAppName] = useState('')
  const [appDescription, setAppDescription] = useState('')
  const [projectName, setProjectName] = useState('')
  const [projectDescription, setProjectDescription] = useState('')
  const [selectedAppId, setSelectedAppId] = useState<string | null>(null)
  const [appSearch, setAppSearch] = useState('')

  const { data: applications } = useApplications()
  const createApp = useCreateApplication()
  const createProject = useCreateProject(selectedAppId || '')

  // Reset state when dialog opens
  useEffect(() => {
    if (isOpen) {
      setStep('choose')
      setAppName('')
      setAppDescription('')
      setProjectName('')
      setProjectDescription('')
      setSelectedAppId(null)
      setAppSearch('')
    }
  }, [isOpen])

  const handleCreateApp = useCallback(async (e: React.FormEvent) => {
    e.preventDefault()
    if (!appName.trim()) return
    try {
      const app = await createApp.mutateAsync({ name: appName.trim(), description: appDescription.trim() || undefined } as ApplicationCreate)
      toast.success(`Workspace "${app.name}" created`)
      onCreated('application', app.id)
      onClose()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to create workspace')
    }
  }, [appName, appDescription, createApp, onCreated, onClose])

  const handleCreateProject = useCallback(async (e: React.FormEvent) => {
    e.preventDefault()
    if (!projectName.trim() || !selectedAppId) return
    try {
      const project = await createProject.mutateAsync({ name: projectName.trim(), description: projectDescription.trim() || undefined } as ProjectCreate)
      toast.success(`Project "${project.name}" created`)
      onCreated('project', project.id, selectedAppId)
      onClose()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to create project')
    }
  }, [projectName, projectDescription, selectedAppId, createProject, onCreated, onClose])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />

      {/* Dialog */}
      <div className="relative w-full max-w-md rounded-xl border border-border bg-card shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="text-sm font-semibold text-foreground">
            {step === 'choose' && 'Create New'}
            {step === 'application' && 'New Workspace'}
            {step === 'project-pick-app' && 'Select Workspace'}
            {step === 'project-form' && 'New Project'}
          </h2>
          <button onClick={onClose} className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Content */}
        <div className="p-5">
          {/* Step 1: Choose type */}
          {step === 'choose' && (
            <div className="space-y-2">
              <button
                onClick={() => setStep('application')}
                className={cn(
                  'flex w-full items-center gap-3 rounded-lg border border-border p-4',
                  'text-left transition-colors hover:bg-muted/50 hover:border-accent/50'
                )}
              >
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent/10 text-accent">
                  <Layers className="h-5 w-5" />
                </div>
                <div className="flex-1">
                  <p className="text-sm font-medium text-foreground">Workspace</p>
                  <p className="text-xs text-muted-foreground">Top-level container for projects</p>
                </div>
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              </button>

              <button
                onClick={() => {
                  if (!applications?.length) {
                    toast.error('Create a workspace first before adding a project')
                    return
                  }
                  setStep('project-pick-app')
                }}
                className={cn(
                  'flex w-full items-center gap-3 rounded-lg border border-border p-4',
                  'text-left transition-colors hover:bg-muted/50 hover:border-accent/50'
                )}
              >
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-500/10 text-blue-400">
                  <FolderKanban className="h-5 w-5" />
                </div>
                <div className="flex-1">
                  <p className="text-sm font-medium text-foreground">Project</p>
                  <p className="text-xs text-muted-foreground">Board with tasks under a workspace</p>
                </div>
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              </button>
            </div>
          )}

          {/* Step 2a: Create Application form */}
          {step === 'application' && (
            <form onSubmit={handleCreateApp} className="space-y-4">
              <div>
                <label className="mb-1.5 block text-xs font-medium text-foreground">Name</label>
                <input
                  type="text"
                  value={appName}
                  onChange={(e) => setAppName(e.target.value)}
                  placeholder="e.g. Marketing Team"
                  autoFocus
                  className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-medium text-foreground">Description <span className="text-muted-foreground">(optional)</span></label>
                <input
                  type="text"
                  value={appDescription}
                  onChange={(e) => setAppDescription(e.target.value)}
                  placeholder="Brief description"
                  className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                />
              </div>
              <div className="flex gap-2 justify-end pt-2">
                <button type="button" onClick={() => setStep('choose')} className="rounded-lg px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted transition-colors">
                  Back
                </button>
                <button
                  type="submit"
                  disabled={!appName.trim() || createApp.isPending}
                  className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-accent-foreground hover:bg-accent/90 transition-colors disabled:opacity-50"
                >
                  {createApp.isPending ? 'Creating...' : 'Create Workspace'}
                </button>
              </div>
            </form>
          )}

          {/* Step 2b: Pick application for project */}
          {step === 'project-pick-app' && (() => {
            const filtered = applications?.filter((app) =>
              app.name.toLowerCase().includes(appSearch.toLowerCase())
            ) || []
            return (
              <div className="space-y-2">
                <p className="mb-1 text-xs text-muted-foreground">Which workspace should this project belong to?</p>
                <input
                  type="text"
                  value={appSearch}
                  onChange={(e) => setAppSearch(e.target.value)}
                  placeholder="Search workspaces..."
                  autoFocus
                  className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                />
                <div className="max-h-52 space-y-1 overflow-y-auto">
                  {filtered.length === 0 ? (
                    <p className="py-4 text-center text-xs text-muted-foreground">
                      {appSearch ? 'No workspaces match your search' : 'No workspaces found'}
                    </p>
                  ) : (
                    filtered.map((app) => (
                      <button
                        key={app.id}
                        onClick={() => {
                          setSelectedAppId(app.id)
                          setStep('project-form')
                        }}
                        className={cn(
                          'flex w-full items-center gap-3 rounded-lg border border-border px-3 py-2.5',
                          'text-left text-sm transition-colors hover:bg-muted/50 hover:border-accent/50'
                        )}
                      >
                        <Layers className="h-4 w-4 text-accent flex-shrink-0" />
                        <span className="truncate text-foreground">{app.name}</span>
                        <ChevronRight className="ml-auto h-3.5 w-3.5 text-muted-foreground" />
                      </button>
                    ))
                  )}
                </div>
                <div className="flex justify-start pt-2">
                  <button onClick={() => { setStep('choose'); setAppSearch('') }} className="rounded-lg px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted transition-colors">
                    Back
                  </button>
                </div>
              </div>
            )
          })()}

          {/* Step 3: Create Project form */}
          {step === 'project-form' && (
            <form onSubmit={handleCreateProject} className="space-y-4">
              <div className="rounded-lg bg-muted/50 px-3 py-2 text-xs text-muted-foreground">
                Creating in: <span className="font-medium text-foreground">{applications?.find(a => a.id === selectedAppId)?.name}</span>
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-medium text-foreground">Project Name</label>
                <input
                  type="text"
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  placeholder="e.g. Q1 Campaign"
                  autoFocus
                  className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-medium text-foreground">Description <span className="text-muted-foreground">(optional)</span></label>
                <input
                  type="text"
                  value={projectDescription}
                  onChange={(e) => setProjectDescription(e.target.value)}
                  placeholder="Brief description"
                  className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                />
              </div>
              <div className="flex gap-2 justify-end pt-2">
                <button type="button" onClick={() => setStep('project-pick-app')} className="rounded-lg px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted transition-colors">
                  Back
                </button>
                <button
                  type="submit"
                  disabled={!projectName.trim() || createProject.isPending}
                  className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-accent-foreground hover:bg-accent/90 transition-colors disabled:opacity-50"
                >
                  {createProject.isPending ? 'Creating...' : 'Create Project'}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}

// ============================================================================
// Dashboard Page Component
// ============================================================================

export function DashboardPage({}: DashboardProps): JSX.Element {
  const [activeItem, setActiveItem] = useState<NavItem>('dashboard')
  const [showQuickCreate, setShowQuickCreate] = useState(false)
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

  // Applications data (for Team Activity visibility)
  const { data: allApplications } = useApplications()
  const showTeamActivity = useMemo(() => {
    if (!allApplications || !currentUser) return false
    return allApplications.some((app) => app.owner_id === currentUser.id)
  }, [allApplications, currentUser])

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
        queryClient.invalidateQueries({ queryKey: queryKeys.unreadCount })
        queryClient.invalidateQueries({ queryKey: queryKeys.dashboard })
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
      // Invalidate unread count; full list refreshes when notification panel opens
      queryClient.invalidateQueries({ queryKey: queryKeys.unreadCount })
    },
    onInvitationResponse: (_data) => {
      // Invalidate unread count; full list refreshes when notification panel opens
      queryClient.invalidateQueries({ queryKey: queryKeys.unreadCount })
    },
    onMemberAdded: (data) => {
      console.log('[Dashboard] onMemberAdded triggered:', data)

      // Check if current user is the one who was added (just joined via invitation)
      const currentUserId = currentUser?.id
      const isCurrentUserAdded = currentUserId === data.user_id

      // Invalidate unread count; full list refreshes when notification panel opens
      queryClient.invalidateQueries({ queryKey: queryKeys.unreadCount })

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
      queryClient.invalidateQueries({ queryKey: queryKeys.unreadCount })
    },
    onRoleUpdated: (data) => {
      // Invalidate unread count; full list refreshes when notification panel opens
      queryClient.invalidateQueries({ queryKey: queryKeys.unreadCount })

      // Invalidate members for this application (will show updated role)
      queryClient.invalidateQueries({ queryKey: queryKeys.appMembers(data.application_id) })
    },
  })

  // Listen for generic notification messages (project role changes, task assignments, etc.)
  useNotifications((_data) => {
    // Invalidate unread count; full notification list refreshes when panel opens
    queryClient.invalidateQueries({ queryKey: queryKeys.unreadCount })
  })

  useEffect(() => {
    localStorage.setItem('pm-sidebar-collapsed', String(isCollapsed))
  }, [isCollapsed])

  const handleNavigate = useCallback((item: NavItem) => {
    const proceed = () => {
      setActiveItem(item)
      if (item !== 'applications') {
        setSelectedApplicationId(null)
        setSelectedApplicationName(null)
      }
      if (item !== 'projects') {
        setSelectedProjectId(null)
      }
    }

    // Check if a screen-level guard (e.g., unsaved document edits) blocks navigation
    if (!checkScreenGuard(proceed)) return

    proceed()
  }, [])

  // Register screen switcher for AI navigation bridge
  useEffect(() => {
    setScreenSwitcher((screen: string) => handleNavigate(screen as NavItem))
    return () => clearScreenSwitcher()
  }, [handleNavigate])

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

  const handleQuickCreated = useCallback((type: 'application' | 'project', id: string, applicationId?: string) => {
    if (type === 'application') {
      setSelectedApplicationId(id)
      setSelectedApplicationName(null)
      setActiveItem('applications')
    } else if (type === 'project' && applicationId) {
      setSelectedApplicationId(applicationId)
      setSelectedProjectId(id)
      setActiveItem('applications')
    }
  }, [])

  const renderContent = (): ReactNode => {
    switch (activeItem) {
      case 'dashboard':
        return (
          <DashboardContent
            applicationId={selectedApplicationId}
            onNavigateToApplications={() => handleNavigate('applications')}
            onNavigateToTasks={() => handleNavigate('tasks')}
            onProjectClick={(project: ProjectNavTarget) => {
              setSelectedApplicationId(project.application_id)
              setSelectedApplicationName(project.application_name ?? null)
              setSelectedProjectId(project.id)
              setActiveItem('applications')
            }}
            onTaskClick={(task: TaskNavTarget) => {
              if (task.project_id) {
                setSelectedApplicationId(task.application_id ?? null)
                setSelectedApplicationName(task.application_name ?? null)
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
                Select a workspace to view its projects
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
                Go to Workspaces
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
          <NotesPage />
        )
      case 'team-activity':
        return (
          <TeamActivityPage />
        )
      case 'settings':
        return currentUser?.is_developer ? (
          <AiSettingsPanel />
        ) : (
          <div className="flex flex-1 items-center justify-center">
            <p className="text-muted-foreground">No settings available</p>
          </div>
        )
      default:
        return <DashboardContent />
    }
  }

  return (
    <div className="flex h-screen flex-col bg-background">
      {/* Unified Title Bar with utility controls */}
      <WindowTitleBar extraControls={<AiToggleButton />} />

      {/* Main Layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <Sidebar
          activeItem={activeItem}
          onNavigate={handleNavigate}
          isCollapsed={isCollapsed}
          onCollapsedChange={handleCollapsedChange}
          onQuickCreate={() => setShowQuickCreate(true)}
          showTeamActivity={showTeamActivity}
        />

        {/* Main Content Area - reduced padding for space efficiency */}
        <main className={cn("flex-1 overflow-auto p-4 lg:p-5", activeItem === 'tasks' && "relative", (activeItem === 'notes' || activeItem === 'team-activity') && "p-0 overflow-hidden")}>
          {renderContent()}
        </main>

        {/* Blair AI Sidebar */}
        <AiSidebar />
      </div>

      {/* Notification Panel */}
      <NotificationPanel sidebarCollapsed={isCollapsed} />

      {/* Quick Create Dialog */}
      <QuickCreateDialog
        isOpen={showQuickCreate}
        onClose={() => setShowQuickCreate(false)}
        onCreated={handleQuickCreated}
      />
    </div>
  )
}

export default DashboardPage
