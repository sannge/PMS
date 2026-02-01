/**
 * Scope Filter Dropdown
 *
 * Allows users to switch between document scopes:
 * - All Documents: Shows all accessible documents
 * - My Notes: Shows only personal documents
 * - Application: Shows documents scoped to a specific application
 * - Project: Shows documents scoped to a specific project
 *
 * Uses Radix Select (shadcn/ui) and reads/writes scope via KnowledgeBaseContext.
 */

import { useMemo } from 'react'
import { Globe, User, Building2, FolderKanban } from 'lucide-react'
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useKnowledgeBase } from '@/contexts/knowledge-base-context'
import { useApplications, useProjects, type Application } from '@/hooks/use-queries'

// ============================================================================
// Helpers
// ============================================================================

/**
 * Encode scope + scopeId into a single string value for Radix Select.
 */
function encodeValue(scope: string, scopeId: string | null): string {
  if (scope === 'all') return 'all'
  if (scope === 'personal') return 'personal'
  if (scope === 'application' && scopeId) return `application:${scopeId}`
  if (scope === 'project' && scopeId) return `project:${scopeId}`
  return 'all'
}

// ============================================================================
// Component
// ============================================================================

export function ScopeFilter(): JSX.Element {
  const { scope, scopeId, setScope } = useKnowledgeBase()
  const { data: applications, isLoading: appsLoading } = useApplications()

  // Fetch projects for each application to build project groups
  // We need all projects across all apps for the scope filter dropdown
  const appIds = useMemo(
    () => (applications ?? []).map((a) => a.id),
    [applications]
  )

  const handleValueChange = (value: string) => {
    if (value === 'all') {
      setScope('all', null)
    } else if (value === 'personal') {
      setScope('personal', null)
    } else if (value.startsWith('application:')) {
      setScope('application', value.split(':')[1])
    } else if (value.startsWith('project:')) {
      setScope('project', value.split(':')[1])
    }
  }

  const currentValue = encodeValue(scope, scopeId)

  return (
    <Select value={currentValue} onValueChange={handleValueChange}>
      <SelectTrigger className="h-8 text-sm border-0 shadow-none focus:ring-0 px-0 gap-1.5">
        <ScopeTriggerContent
          scope={scope}
          scopeId={scopeId}
          applications={applications}
        />
      </SelectTrigger>
      <SelectContent>
        {/* Global scopes */}
        <SelectItem value="all">
          <span className="flex items-center gap-2">
            <Globe className="h-3.5 w-3.5 text-muted-foreground" />
            All Documents
          </span>
        </SelectItem>
        <SelectItem value="personal">
          <span className="flex items-center gap-2">
            <User className="h-3.5 w-3.5 text-muted-foreground" />
            My Notes
          </span>
        </SelectItem>

        {/* Applications group */}
        {appsLoading ? (
          <>
            <SelectSeparator />
            <SelectGroup>
              <SelectLabel className="text-xs text-muted-foreground">Loading...</SelectLabel>
            </SelectGroup>
          </>
        ) : applications && applications.length > 0 ? (
          <>
            <SelectSeparator />
            <SelectGroup>
              <SelectLabel className="text-xs text-muted-foreground">Applications</SelectLabel>
              {applications.map((app) => (
                <SelectItem key={app.id} value={`application:${app.id}`}>
                  <span className="flex items-center gap-2">
                    <Building2 className="h-3.5 w-3.5 text-muted-foreground" />
                    {app.name}
                  </span>
                </SelectItem>
              ))}
            </SelectGroup>

            {/* Projects group */}
            <SelectSeparator />
            <ProjectsGroup applications={applications} appIds={appIds} />
          </>
        ) : null}
      </SelectContent>
    </Select>
  )
}

// ============================================================================
// Sub-components
// ============================================================================

/**
 * Display content for the select trigger showing current scope with icon.
 */
function ScopeTriggerContent({
  scope,
  scopeId,
  applications,
}: {
  scope: string
  scopeId: string | null
  applications: Application[] | undefined
}): JSX.Element {
  if (scope === 'personal') {
    return (
      <span className="flex items-center gap-1.5">
        <User className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
        <SelectValue placeholder="My Notes" />
      </span>
    )
  }

  if (scope === 'application' && scopeId && applications) {
    const app = applications.find((a) => a.id === scopeId)
    return (
      <span className="flex items-center gap-1.5">
        <Building2 className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
        <SelectValue placeholder={app?.name ?? 'Application'} />
      </span>
    )
  }

  if (scope === 'project') {
    return (
      <span className="flex items-center gap-1.5">
        <FolderKanban className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
        <SelectValue placeholder="Project" />
      </span>
    )
  }

  // Default: 'all'
  return (
    <span className="flex items-center gap-1.5">
      <Globe className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
      <SelectValue placeholder="All Documents" />
    </span>
  )
}

/**
 * Renders the projects group by fetching projects per application.
 * Only rendered when applications are loaded and non-empty.
 */
function ProjectsGroup({
  applications,
  appIds,
}: {
  applications: Application[]
  appIds: string[]
}): JSX.Element {
  return (
    <SelectGroup>
      <SelectLabel className="text-xs text-muted-foreground">Projects</SelectLabel>
      {appIds.map((appId) => (
        <ProjectItems key={appId} appId={appId} applications={applications} />
      ))}
    </SelectGroup>
  )
}

/**
 * Renders project items for a single application.
 * Each component instance calls useProjects for its application.
 */
function ProjectItems({
  appId,
  applications,
}: {
  appId: string
  applications: Application[]
}): JSX.Element | null {
  const { data: projects, isLoading } = useProjects(appId)
  const app = applications.find((a) => a.id === appId)

  if (isLoading) {
    return (
      <SelectItem value={`_loading_${appId}`} disabled>
        <span className="text-muted-foreground text-xs">Loading projects...</span>
      </SelectItem>
    )
  }

  if (!projects || projects.length === 0) {
    return null
  }

  return (
    <>
      {projects.map((project) => (
        <SelectItem key={project.id} value={`project:${project.id}`}>
          <span className="flex items-center gap-2">
            <FolderKanban className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="truncate">
              {app ? `${app.name} / ${project.name}` : project.name}
            </span>
          </span>
        </SelectItem>
      ))}
    </>
  )
}

export default ScopeFilter
