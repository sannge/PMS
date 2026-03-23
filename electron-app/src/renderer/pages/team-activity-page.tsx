/**
 * Team Activity Page
 *
 * Main page for the Team Activity feature. Provides a workspace selector,
 * date range picker, and tabbed view for overview, members, projects,
 * and activity feed.
 *
 * All state is local (no Zustand store needed).
 * Date inputs are debounced to avoid rapid API calls.
 */

import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { useApplications } from '@/hooks/use-queries'
import { useAuthStore } from '@/contexts/auth-context'
import { PerformanceFilters } from '@/components/team-activity/performance-filters'
import { ExportButton } from '@/components/team-activity/export-button'
import { OverviewTab } from '@/components/team-activity/overview-tab'
import { MembersTab } from '@/components/team-activity/members-tab'
import { ProjectsTab } from '@/components/team-activity/projects-tab'

// ============================================================================
// Constants
// ============================================================================

const DATE_DEBOUNCE_MS = 500

// ============================================================================
// Helpers
// ============================================================================

function defaultDateFrom(): string {
  const d = new Date()
  d.setDate(d.getDate() - 7)
  return d.toISOString().split('T')[0]
}

function defaultDateTo(): string {
  return new Date().toISOString().split('T')[0]
}

// ============================================================================
// Component
// ============================================================================

export function TeamActivityPage(): JSX.Element {
  const currentUser = useAuthStore((state) => state.user)
  const { data: applications } = useApplications()

  // Filter to owned applications only
  const ownedApps = useMemo(() => {
    if (!applications || !currentUser) return []
    return applications
      .filter((app) => app.owner_id === currentUser.id)
      .map((app) => ({ id: app.id, name: app.name }))
  }, [applications, currentUser])

  // Tab state
  const [activeTab, setActiveTab] = useState('overview')

  // App selection
  const [selectedAppId, setSelectedAppId] = useState('all')

  // Raw date inputs (updated immediately)
  const [rawDateFrom, setRawDateFrom] = useState(defaultDateFrom)
  const [rawDateTo, setRawDateTo] = useState(defaultDateTo)

  // Debounced date values (used for queries)
  const [dateFrom, setDateFrom] = useState(defaultDateFrom)
  const [dateTo, setDateTo] = useState(defaultDateTo)

  // Debounce timer refs
  const dateFromTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const dateToTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Debounce dateFrom
  useEffect(() => {
    if (dateFromTimerRef.current) clearTimeout(dateFromTimerRef.current)
    dateFromTimerRef.current = setTimeout(() => {
      if (/^\d{4}-\d{2}-\d{2}$/.test(rawDateFrom)) {
        setDateFrom(rawDateFrom)
      }
    }, DATE_DEBOUNCE_MS)
    return () => {
      if (dateFromTimerRef.current) clearTimeout(dateFromTimerRef.current)
    }
  }, [rawDateFrom])

  // Debounce dateTo
  useEffect(() => {
    if (dateToTimerRef.current) clearTimeout(dateToTimerRef.current)
    dateToTimerRef.current = setTimeout(() => {
      if (/^\d{4}-\d{2}-\d{2}$/.test(rawDateTo)) {
        setDateTo(rawDateTo)
      }
    }, DATE_DEBOUNCE_MS)
    return () => {
      if (dateToTimerRef.current) clearTimeout(dateToTimerRef.current)
    }
  }, [rawDateTo])

  const handleDateFromChange = useCallback((value: string) => {
    setRawDateFrom(value)
  }, [])

  const handleDateToChange = useCallback((value: string) => {
    setRawDateTo(value)
  }, [])

  return (
    <div className="flex flex-col h-full select-text">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-border">
        <h1 className="text-lg font-semibold text-foreground">Team Activity</h1>
        <PerformanceFilters
          applications={ownedApps}
          selectedAppId={selectedAppId}
          onAppChange={setSelectedAppId}
          dateFrom={rawDateFrom}
          dateTo={rawDateTo}
          onDateFromChange={handleDateFromChange}
          onDateToChange={handleDateToChange}
        />
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col min-h-0">
        <div className="flex items-center justify-between px-6 border-b border-border">
          <TabsList className="border-b-0">
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="members">Members</TabsTrigger>
            <TabsTrigger value="projects">Projects</TabsTrigger>
          </TabsList>
          <ExportButton
            tab={activeTab}
            appId={selectedAppId}
            dateFrom={dateFrom}
            dateTo={dateTo}
          />
        </div>

        <TabsContent value="overview" className="flex-1 overflow-y-auto p-6">
          <OverviewTab appId={selectedAppId} dateFrom={dateFrom} dateTo={dateTo} />
        </TabsContent>

        <TabsContent value="members" className="flex-1 overflow-y-auto p-6">
          <MembersTab appId={selectedAppId} dateFrom={dateFrom} dateTo={dateTo} />
        </TabsContent>

        <TabsContent value="projects" className="flex-1 overflow-y-auto p-6">
          <ProjectsTab appId={selectedAppId} dateFrom={dateFrom} dateTo={dateTo} />
        </TabsContent>
      </Tabs>
    </div>
  )
}
