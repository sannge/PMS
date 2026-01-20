/**
 * Project Card Component
 *
 * Ultra-compact row-based project display optimized for dense lists.
 * Features:
 * - Single-row layout with all information inline
 * - Hover-reveal actions dropdown
 * - Description tooltip on hover
 * - Smooth micro-interactions
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import { cn } from '@/lib/utils'
import {
  LayoutDashboard,
  Edit2,
  Trash2,
  Clock,
  ListTodo,
  Columns,
  RefreshCw,
  Hash,
  MoreHorizontal,
  ChevronRight,
  Circle,
  Timer,
  Eye,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react'
import type { Project, ProjectDerivedStatus } from '@/stores/projects-store'

// ============================================================================
// Types
// ============================================================================

export interface ProjectCardProps {
  project: Project
  onClick?: (project: Project) => void
  onEdit?: (project: Project) => void
  onDelete?: (project: Project) => void
  disabled?: boolean
  className?: string
  index?: number
}

// ============================================================================
// Helper Functions
// ============================================================================

function formatDate(dateString: string): string {
  let dateStr = dateString
  if (!dateStr.endsWith('Z') && !dateStr.includes('+') && !dateStr.includes('-', 10)) {
    dateStr = dateStr + 'Z'
  }

  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()

  if (diffMs < 0) {
    return 'Now'
  }

  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

  if (diffDays === 0) {
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60))
    if (diffHours === 0) {
      const diffMinutes = Math.floor(diffMs / (1000 * 60))
      if (diffMinutes === 0) {
        return 'Now'
      }
      return `${diffMinutes}m`
    }
    return `${diffHours}h`
  }
  if (diffDays === 1) {
    return '1d'
  }
  if (diffDays < 7) {
    return `${diffDays}d`
  }
  if (diffDays < 30) {
    const weeks = Math.floor(diffDays / 7)
    return `${weeks}w`
  }

  return date.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
  })
}

function getProjectTypeInfo(projectType: string): {
  icon: JSX.Element
  label: string
  abbrev: string
  color: string
} {
  switch (projectType) {
    case 'scrum':
      return {
        icon: <RefreshCw className="h-3 w-3" />,
        label: 'Scrum',
        abbrev: 'S',
        color: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
      }
    case 'kanban':
    default:
      return {
        icon: <Columns className="h-3 w-3" />,
        label: 'Kanban',
        abbrev: 'K',
        color: 'bg-blue-500/15 text-blue-600 dark:text-blue-400',
      }
  }
}

/**
 * Get derived status display info (icon, color, label)
 */
function getDerivedStatusInfo(status: ProjectDerivedStatus | null): {
  icon: JSX.Element
  label: string
  color: string
  bgColor: string
} {
  switch (status) {
    case 'Done':
      return {
        icon: <CheckCircle2 className="h-3 w-3" />,
        label: 'Done',
        color: 'text-green-600 dark:text-green-400',
        bgColor: 'bg-green-500/15',
      }
    case 'Issue':
      return {
        icon: <AlertCircle className="h-3 w-3" />,
        label: 'Issue',
        color: 'text-red-600 dark:text-red-400',
        bgColor: 'bg-red-500/15',
      }
    case 'In Review':
      return {
        icon: <Eye className="h-3 w-3" />,
        label: 'In Review',
        color: 'text-purple-600 dark:text-purple-400',
        bgColor: 'bg-purple-500/15',
      }
    case 'In Progress':
      return {
        icon: <Timer className="h-3 w-3" />,
        label: 'In Progress',
        color: 'text-blue-600 dark:text-blue-400',
        bgColor: 'bg-blue-500/15',
      }
    case 'Todo':
    default:
      return {
        icon: <Circle className="h-3 w-3" />,
        label: 'Todo',
        color: 'text-slate-500 dark:text-slate-400',
        bgColor: 'bg-slate-500/15',
      }
  }
}

// ============================================================================
// Actions Dropdown Component
// ============================================================================

interface ActionsDropdownProps {
  onEdit?: () => void
  onDelete?: () => void
  disabled?: boolean
}

function ActionsDropdown({ onEdit, onDelete, disabled }: ActionsDropdownProps): JSX.Element {
  const [isOpen, setIsOpen] = useState(false)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const [position, setPosition] = useState({ top: 0, left: 0 })

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node) &&
        buttonRef.current &&
        !buttonRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleToggle = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (!isOpen && buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect()
      setPosition({
        top: rect.bottom + 4,
        left: rect.right - 120, // 120px is min-w of dropdown
      })
    }
    setIsOpen(!isOpen)
  }

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        onClick={handleToggle}
        disabled={disabled}
        className={cn(
          'flex h-6 w-6 items-center justify-center rounded-md',
          'text-muted-foreground transition-colors',
          'hover:bg-muted hover:text-foreground',
          'focus:outline-none focus:ring-1 focus:ring-ring',
          'disabled:pointer-events-none disabled:opacity-50'
        )}
        title="Actions"
      >
        <MoreHorizontal className="h-3.5 w-3.5" />
      </button>

      {isOpen && (
        <div
          ref={dropdownRef}
          style={{ top: position.top, left: position.left }}
          className={cn(
            'fixed z-[100] min-w-[120px]',
            'rounded-md border border-border bg-popover shadow-lg',
            'animate-in fade-in-0 zoom-in-95 duration-100'
          )}
        >
          {onEdit && (
            <button
              onClick={(e) => {
                e.stopPropagation()
                onEdit()
                setIsOpen(false)
              }}
              className={cn(
                'flex w-full items-center gap-2 px-3 py-1.5 text-xs',
                'text-foreground hover:bg-accent',
                'transition-colors first:rounded-t-md'
              )}
            >
              <Edit2 className="h-3 w-3" />
              Edit
            </button>
          )}
          {onDelete && (
            <button
              onClick={(e) => {
                e.stopPropagation()
                onDelete()
                setIsOpen(false)
              }}
              className={cn(
                'flex w-full items-center gap-2 px-3 py-1.5 text-xs',
                'text-destructive hover:bg-destructive/10',
                'transition-colors last:rounded-b-md'
              )}
            >
              <Trash2 className="h-3 w-3" />
              Delete
            </button>
          )}
        </div>
      )}
    </div>
  )
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
  index = 0,
}: ProjectCardProps): JSX.Element {
  const [showTooltip, setShowTooltip] = useState(false)
  const tooltipTimeout = useRef<NodeJS.Timeout>()

  const handleClick = useCallback(() => {
    if (!disabled && onClick) {
      onClick(project)
    }
  }, [project, disabled, onClick])

  const handleMouseEnter = () => {
    if (project.description) {
      tooltipTimeout.current = setTimeout(() => setShowTooltip(true), 500)
    }
  }

  const handleMouseLeave = () => {
    clearTimeout(tooltipTimeout.current)
    setShowTooltip(false)
  }

  const typeInfo = getProjectTypeInfo(project.project_type)
  const statusInfo = getDerivedStatusInfo(project.derived_status || null)

  return (
    <div
      onClick={handleClick}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={(e) => {
        if (onClick && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault()
          handleClick()
        }
      }}
      className={cn(
        'group relative rounded-lg border border-border/60 bg-card p-2.5',
        'transition-all duration-150 ease-out',
        onClick && !disabled && [
          'cursor-pointer',
          'hover:border-violet-500/30 hover:bg-violet-500/[0.03]',
          'hover:shadow-sm',
        ],
        disabled && 'opacity-50 cursor-not-allowed',
        'focus:outline-none focus:ring-1 focus:ring-ring',
        'animate-fade-in opacity-0',
        className
      )}
      style={{ animationDelay: `${index * 40}ms` }}
    >
      {/* Row 1: Icon, Name, Actions */}
      <div className="flex items-center gap-2">
        {/* Icon */}
        <div
          className={cn(
            'flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md',
            'bg-violet-500/10 text-violet-600 dark:text-violet-400',
            'transition-transform duration-150',
            'group-hover:scale-105'
          )}
        >
          <LayoutDashboard className="h-3.5 w-3.5" />
        </div>

        {/* Name */}
        <span className="flex-1 min-w-0 truncate text-sm font-medium text-foreground group-hover:text-violet-600 dark:group-hover:text-violet-400 transition-colors">
          {project.name}
        </span>

        {/* Actions (hover-reveal) */}
        <div
          className={cn(
            'flex-shrink-0 opacity-0 transition-opacity duration-100',
            'group-hover:opacity-100'
          )}
        >
          {(onEdit || onDelete) && (
            <ActionsDropdown
              onEdit={onEdit ? () => onEdit(project) : undefined}
              onDelete={onDelete ? () => onDelete(project) : undefined}
              disabled={disabled}
            />
          )}
        </div>

        {/* Arrow indicator */}
        {onClick && !disabled && (
          <ChevronRight
            className={cn(
              'h-3.5 w-3.5 flex-shrink-0 text-muted-foreground/50',
              'opacity-0 -translate-x-1 transition-all duration-150',
              'group-hover:opacity-100 group-hover:translate-x-0',
              'group-hover:text-violet-500'
            )}
          />
        )}
      </div>

      {/* Row 2: Metadata */}
      <div className="flex items-center gap-1.5 mt-2 flex-wrap">
        {/* Project Key */}
        <span
          className={cn(
            'inline-flex items-center gap-0.5 rounded px-1.5 py-0.5',
            'bg-muted/70 text-[10px] font-mono font-medium text-muted-foreground',
            'border border-border/50'
          )}
        >
          <Hash className="h-2.5 w-2.5" />
          {project.key}
        </span>

        {/* Task Count */}
        <div
          className={cn(
            'flex items-center gap-1 text-[10px] font-medium text-muted-foreground',
            'transition-colors',
            'group-hover:text-violet-600/70 dark:group-hover:text-violet-400/70'
          )}
        >
          <ListTodo className="h-3 w-3" />
          <span>{project.tasks_count}</span>
        </div>

        {/* Project Type Badge */}
        <div
          className={cn(
            'flex h-5 items-center justify-center rounded px-1',
            'text-[10px] font-bold',
            typeInfo.color
          )}
          title={typeInfo.label}
        >
          {typeInfo.abbrev}
        </div>

        {/* Derived Status Badge */}
        {project.derived_status && (
          <div
            className={cn(
              'flex items-center gap-1 rounded px-1.5 py-0.5',
              'text-[10px] font-medium',
              statusInfo.bgColor,
              statusInfo.color
            )}
            title={`Status: ${project.derived_status}`}
          >
            {statusInfo.icon}
          </div>
        )}

        {/* Description indicator (dot) */}
        {project.description && (
          <span className="h-1 w-1 rounded-full bg-muted-foreground/40" title="Has description" />
        )}

        {/* Timestamp */}
        <div className="flex items-center gap-1 text-[10px] text-muted-foreground/70 ml-auto">
          <Clock className="h-2.5 w-2.5" />
          <span className="whitespace-nowrap">{formatDate(project.updated_at)}</span>
        </div>
      </div>

      {/* Description Tooltip */}
      {showTooltip && project.description && (
        <div
          className={cn(
            'absolute left-0 top-full z-50 mt-1.5 max-w-xs p-2',
            'rounded-md border border-border bg-popover text-xs text-popover-foreground shadow-md',
            'animate-in fade-in-0 slide-in-from-top-1 duration-150'
          )}
        >
          {project.description}
        </div>
      )}
    </div>
  )
}

export default ProjectCard
