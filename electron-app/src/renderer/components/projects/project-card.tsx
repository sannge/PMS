/**
 * Project Card Component
 *
 * Displays a project in a card format with name, description,
 * task count, project type, and action buttons.
 *
 * Features:
 * - Displays project details
 * - Project key badge
 * - Edit and delete action buttons
 * - Task count indicator
 * - Project type badge (kanban/scrum)
 * - Hover effects and accessibility
 */

import { useCallback } from 'react'
import { cn } from '@/lib/utils'
import {
  LayoutDashboard,
  Edit2,
  Trash2,
  ArrowRight,
  Clock,
  ListTodo,
  Columns,
  RefreshCw,
} from 'lucide-react'
import type { Project } from '@/stores/projects-store'

// ============================================================================
// Types
// ============================================================================

export interface ProjectCardProps {
  /**
   * Project data to display
   */
  project: Project
  /**
   * Callback when the card is clicked
   */
  onClick?: (project: Project) => void
  /**
   * Callback when edit is clicked
   */
  onEdit?: (project: Project) => void
  /**
   * Callback when delete is clicked
   */
  onDelete?: (project: Project) => void
  /**
   * Whether actions are disabled
   */
  disabled?: boolean
  /**
   * Additional CSS classes
   */
  className?: string
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Format a date string to a human-readable format
 */
function formatDate(dateString: string): string {
  // Ensure the date is parsed as UTC if no timezone is specified
  let dateStr = dateString
  if (!dateStr.endsWith('Z') && !dateStr.includes('+') && !dateStr.includes('-', 10)) {
    dateStr = dateStr + 'Z'
  }

  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()

  // Handle future dates (negative diff) - show "Just now"
  if (diffMs < 0) {
    return 'Just now'
  }

  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

  if (diffDays === 0) {
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60))
    if (diffHours === 0) {
      const diffMinutes = Math.floor(diffMs / (1000 * 60))
      if (diffMinutes === 0) {
        return 'Just now'
      }
      return `${diffMinutes}m ago`
    }
    return `${diffHours}h ago`
  }
  if (diffDays === 1) {
    return 'Yesterday'
  }
  if (diffDays < 7) {
    return `${diffDays}d ago`
  }
  if (diffDays < 30) {
    const weeks = Math.floor(diffDays / 7)
    return `${weeks}w ago`
  }

  return date.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: date.getFullYear() !== now.getFullYear() ? 'numeric' : undefined,
  })
}

/**
 * Get project type display info
 */
function getProjectTypeInfo(projectType: string): { icon: JSX.Element; label: string } {
  switch (projectType) {
    case 'scrum':
      return {
        icon: <RefreshCw className="h-3 w-3" />,
        label: 'Scrum',
      }
    case 'kanban':
    default:
      return {
        icon: <Columns className="h-3 w-3" />,
        label: 'Kanban',
      }
  }
}

// ============================================================================
// Component
// ============================================================================

export function ProjectCard({
  project,
  onClick,
  onEdit,
  onDelete,
  disabled = false,
  className,
}: ProjectCardProps): JSX.Element {
  // Handle card click
  const handleClick = useCallback(() => {
    if (!disabled && onClick) {
      onClick(project)
    }
  }, [project, disabled, onClick])

  // Handle edit click
  const handleEdit = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation()
      if (!disabled && onEdit) {
        onEdit(project)
      }
    },
    [project, disabled, onEdit]
  )

  // Handle delete click
  const handleDelete = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation()
      if (!disabled && onDelete) {
        onDelete(project)
      }
    },
    [project, disabled, onDelete]
  )

  const typeInfo = getProjectTypeInfo(project.project_type)

  return (
    <div
      onClick={handleClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={(e) => {
        if (onClick && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault()
          handleClick()
        }
      }}
      className={cn(
        'group relative rounded-lg border border-border bg-card p-4 transition-all',
        onClick && !disabled && 'cursor-pointer hover:border-primary/50 hover:shadow-md',
        disabled && 'opacity-50 cursor-not-allowed',
        'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background',
        className
      )}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        {/* Icon and Title */}
        <div className="flex items-start gap-3 min-w-0">
          <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <LayoutDashboard className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h3 className="font-semibold text-foreground truncate">
                {project.name}
              </h3>
              {/* Project Key Badge */}
              <span className="flex-shrink-0 rounded bg-muted px-1.5 py-0.5 text-xs font-mono font-medium text-muted-foreground">
                {project.key}
              </span>
            </div>
            {project.description && (
              <p className="mt-1 text-sm text-muted-foreground line-clamp-2">
                {project.description}
              </p>
            )}
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          {onEdit && (
            <button
              onClick={handleEdit}
              disabled={disabled}
              className={cn(
                'rounded-md p-1.5 text-muted-foreground transition-colors',
                'hover:bg-accent hover:text-accent-foreground',
                'focus:outline-none focus:ring-2 focus:ring-ring',
                'disabled:pointer-events-none disabled:opacity-50'
              )}
              title="Edit project"
            >
              <Edit2 className="h-4 w-4" />
            </button>
          )}
          {onDelete && (
            <button
              onClick={handleDelete}
              disabled={disabled}
              className={cn(
                'rounded-md p-1.5 text-muted-foreground transition-colors',
                'hover:bg-destructive/10 hover:text-destructive',
                'focus:outline-none focus:ring-2 focus:ring-ring',
                'disabled:pointer-events-none disabled:opacity-50'
              )}
              title="Delete project"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      {/* Footer */}
      <div className="mt-4 flex items-center justify-between text-sm text-muted-foreground">
        {/* Project Info */}
        <div className="flex items-center gap-4">
          {/* Task Count */}
          <span className="flex items-center gap-1.5">
            <ListTodo className="h-4 w-4" />
            {project.tasks_count} {project.tasks_count === 1 ? 'task' : 'tasks'}
          </span>
          {/* Project Type Badge */}
          <span className="flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs">
            {typeInfo.icon}
            <span>{typeInfo.label}</span>
          </span>
        </div>

        {/* Last Updated */}
        <div className="flex items-center gap-1.5">
          <Clock className="h-3.5 w-3.5" />
          <span className="text-xs">{formatDate(project.updated_at)}</span>
        </div>
      </div>

      {/* Arrow indicator for clickable cards */}
      {onClick && !disabled && (
        <div className="absolute bottom-4 right-4 opacity-0 group-hover:opacity-100 transition-opacity">
          <ArrowRight className="h-4 w-4 text-primary" />
        </div>
      )}
    </div>
  )
}

export default ProjectCard
