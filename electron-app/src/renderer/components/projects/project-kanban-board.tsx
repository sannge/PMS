/**
 * Project Kanban Board Component
 *
 * Kanban-style board view for displaying projects grouped by derived status.
 * Projects are automatically organized based on their task distribution.
 *
 * Features:
 * - 5 status columns: Todo, In Progress, In Review, Issue, Done
 * - Project cards with status badges and task counts
 * - Column project counts
 * - Empty state handling
 * - Skeleton loading states
 */

import { useMemo } from 'react'
import { cn } from '@/lib/utils'
import {
  Circle,
  Timer,
  Eye,
  AlertTriangle,
  CheckCircle2,
  LayoutDashboard,
  Plus,
} from 'lucide-react'
import type { Project, ProjectDerivedStatus } from '@/stores/projects-store'
import { ProjectCard } from './project-card'
import { SkeletonProjectCard } from '@/components/ui/skeleton'

// ============================================================================
// Types
// ============================================================================

interface ProjectKanbanColumn {
  id: ProjectDerivedStatus
  title: string
  icon: JSX.Element
  color: string
  bgColor: string
}

export interface ProjectKanbanBoardProps {
  /**
   * Projects to display
   */
  projects: Project[]
  /**
   * Whether projects are loading
   */
  isLoading?: boolean
  /**
   * Callback when a project is clicked
   */
  onProjectClick?: (project: Project) => void
  /**
   * Callback when edit is clicked
   */
  onEdit?: (project: Project) => void
  /**
   * Callback when delete is clicked
   */
  onDelete?: (project: Project) => void
  /**
   * Callback when add project is clicked
   */
  onAddProject?: () => void
  /**
   * Whether editing/deleting is disabled
   */
  disabled?: boolean
  /**
   * Whether user can edit projects
   */
  canEditProjects?: boolean
  /**
   * Whether user can delete projects (only app owners)
   */
  canDeleteProjects?: boolean
  /**
   * Additional CSS classes
   */
  className?: string
}

// ============================================================================
// Constants
// ============================================================================

const PROJECT_COLUMNS: ProjectKanbanColumn[] = [
  {
    id: 'Todo',
    title: 'To Do',
    icon: <Circle className="h-4 w-4" />,
    color: 'text-slate-500',
    bgColor: 'bg-slate-500/10',
  },
  {
    id: 'In Progress',
    title: 'In Progress',
    icon: <Timer className="h-4 w-4" />,
    color: 'text-blue-500',
    bgColor: 'bg-blue-500/10',
  },
  {
    id: 'In Review',
    title: 'In Review',
    icon: <Eye className="h-4 w-4" />,
    color: 'text-purple-500',
    bgColor: 'bg-purple-500/10',
  },
  {
    id: 'Issue',
    title: 'Issue',
    icon: <AlertTriangle className="h-4 w-4" />,
    color: 'text-red-500',
    bgColor: 'bg-red-500/10',
  },
  {
    id: 'Done',
    title: 'Done',
    icon: <CheckCircle2 className="h-4 w-4" />,
    color: 'text-green-500',
    bgColor: 'bg-green-500/10',
  },
]

// ============================================================================
// Column Component
// ============================================================================

interface ProjectColumnProps {
  column: ProjectKanbanColumn
  projects: Project[]
  isLoading?: boolean
  onProjectClick?: (project: Project) => void
  onEdit?: (project: Project) => void
  onDelete?: (project: Project) => void
  onAddProject?: () => void
  disabled?: boolean
  canEditProjects?: boolean
  canDeleteProjects?: boolean
  isFirstColumn?: boolean
}

function ProjectColumn({
  column,
  projects,
  isLoading,
  onProjectClick,
  onEdit,
  onDelete,
  onAddProject,
  disabled,
  canEditProjects,
  canDeleteProjects,
  isFirstColumn,
}: ProjectColumnProps): JSX.Element {
  return (
    <div
      className={cn(
        'flex h-full w-72 flex-shrink-0 flex-col rounded-lg',
        column.bgColor
      )}
    >
      {/* Column Header */}
      <div className="flex items-center justify-between p-3 border-b border-border/50">
        <div className="flex items-center gap-2">
          <div className={cn('flex items-center justify-center', column.color)}>
            {column.icon}
          </div>
          <span className="text-sm font-medium text-foreground">
            {column.title}
          </span>
          <span
            className={cn(
              'flex h-5 min-w-[20px] items-center justify-center rounded-full px-1.5 text-xs font-medium',
              column.bgColor,
              column.color
            )}
          >
            {projects.length}
          </span>
        </div>
        {isFirstColumn && canEditProjects && onAddProject && (
          <button
            onClick={onAddProject}
            className={cn(
              'flex h-6 w-6 items-center justify-center rounded-md',
              'text-muted-foreground hover:text-foreground hover:bg-background/50',
              'transition-colors'
            )}
            title="Add project"
          >
            <Plus className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Column Content */}
      <div className="flex-1 overflow-y-auto p-2 space-y-2">
        {isLoading ? (
          // Skeleton loading
          <>
            <SkeletonProjectCard />
            <SkeletonProjectCard />
          </>
        ) : projects.length === 0 ? (
          // Empty state
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <div
              className={cn(
                'flex h-10 w-10 items-center justify-center rounded-lg',
                column.bgColor
              )}
            >
              <LayoutDashboard className={cn('h-5 w-5', column.color)} />
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              No projects
            </p>
          </div>
        ) : (
          // Project cards
          projects.map((project) => (
            <ProjectCard
              key={project.id}
              project={project}
              onClick={onProjectClick ? () => onProjectClick(project) : undefined}
              onEdit={canEditProjects && onEdit ? () => onEdit(project) : undefined}
              onDelete={canDeleteProjects && onDelete ? () => onDelete(project) : undefined}
              disabled={disabled}
            />
          ))
        )}
      </div>
    </div>
  )
}

// ============================================================================
// Main Component
// ============================================================================

export function ProjectKanbanBoard({
  projects,
  isLoading,
  onProjectClick,
  onEdit,
  onDelete,
  onAddProject,
  disabled,
  canEditProjects = false,
  canDeleteProjects = false,
  className,
}: ProjectKanbanBoardProps): JSX.Element {
  // Group projects by derived status
  const projectsByStatus = useMemo(() => {
    const grouped: Record<ProjectDerivedStatus, Project[]> = {
      'Todo': [],
      'In Progress': [],
      'In Review': [],
      'Issue': [],
      'Done': [],
    }

    projects.forEach((project) => {
      // Default to 'Todo' if no derived status
      const status = project.derived_status || 'Todo'
      if (grouped[status]) {
        grouped[status].push(project)
      } else {
        grouped['Todo'].push(project)
      }
    })

    return grouped
  }, [projects])

  return (
    <div className={cn('flex gap-4 pb-4 overflow-x-auto', className)}>
      {PROJECT_COLUMNS.map((column, index) => (
        <ProjectColumn
          key={column.id}
          column={column}
          projects={projectsByStatus[column.id]}
          isLoading={isLoading}
          onProjectClick={onProjectClick}
          onEdit={onEdit}
          onDelete={onDelete}
          onAddProject={onAddProject}
          disabled={disabled}
          canEditProjects={canEditProjects}
          canDeleteProjects={canDeleteProjects}
          isFirstColumn={index === 0}
        />
      ))}
    </div>
  )
}

export default ProjectKanbanBoard
