/**
 * Application Card Component
 *
 * Ultra-compact row-based application display optimized for dense lists.
 * Features:
 * - Single-row layout with all information inline
 * - Hover-reveal actions dropdown
 * - Description tooltip on hover
 * - Smooth micro-interactions
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import { cn } from '@/lib/utils'
import {
  FolderKanban,
  Edit2,
  Trash2,
  Clock,
  Layers,
  MoreHorizontal,
  ChevronRight,
} from 'lucide-react'
import type { Application } from '@/stores/applications-store'

// ============================================================================
// Types
// ============================================================================

export interface ApplicationCardProps {
  application: Application
  onClick?: (application: Application) => void
  onEdit?: (application: Application) => void
  onDelete?: (application: Application) => void
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
  const dropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleToggle = (e: React.MouseEvent) => {
    e.stopPropagation()
    setIsOpen(!isOpen)
  }

  return (
    <div ref={dropdownRef} className="relative">
      <button
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
          className={cn(
            'absolute right-0 top-full z-50 mt-1 min-w-[120px]',
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

export function ApplicationCard({
  application,
  onClick,
  onEdit,
  onDelete,
  disabled = false,
  className,
  index = 0,
}: ApplicationCardProps): JSX.Element {
  const [showTooltip, setShowTooltip] = useState(false)
  const tooltipTimeout = useRef<NodeJS.Timeout>()

  const handleClick = useCallback(() => {
    if (!disabled && onClick) {
      onClick(application)
    }
  }, [application, disabled, onClick])

  const handleMouseEnter = () => {
    if (application.description) {
      tooltipTimeout.current = setTimeout(() => setShowTooltip(true), 500)
    }
  }

  const handleMouseLeave = () => {
    clearTimeout(tooltipTimeout.current)
    setShowTooltip(false)
  }

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
        'group relative flex h-11 items-center gap-2 rounded-lg border border-border/60 bg-card px-3 overflow-hidden',
        'transition-all duration-150 ease-out',
        onClick && !disabled && [
          'cursor-pointer',
          'hover:border-amber-500/30 hover:bg-amber-500/[0.03]',
          'hover:shadow-sm',
        ],
        disabled && 'opacity-50 cursor-not-allowed',
        'focus:outline-none focus:ring-1 focus:ring-ring',
        'animate-fade-in opacity-0',
        className
      )}
      style={{ animationDelay: `${index * 40}ms` }}
    >
      {/* Icon */}
      <div
        className={cn(
          'flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md',
          'bg-amber-500/10 text-amber-600 dark:text-amber-400',
          'transition-transform duration-150',
          'group-hover:scale-105'
        )}
      >
        <FolderKanban className="h-3.5 w-3.5" />
      </div>

      {/* Name */}
      <span className="flex-shrink-0 max-w-[180px] truncate text-sm font-medium text-foreground group-hover:text-amber-600 dark:group-hover:text-amber-400 transition-colors">
        {application.name}
      </span>

      {/* Description indicator (dot) - shows if has description */}
      {application.description && (
        <span className="flex-shrink-0 h-1 w-1 rounded-full bg-muted-foreground/40" title="Has description" />
      )}

      {/* Spacer */}
      <div className="flex-1 min-w-0" />

      {/* Project Count */}
      <div
        className={cn(
          'flex-shrink-0 flex items-center gap-1 text-[10px] font-medium text-muted-foreground',
          'transition-colors',
          'group-hover:text-amber-600/70 dark:group-hover:text-amber-400/70'
        )}
      >
        <Layers className="h-3 w-3" />
        <span>{application.projects_count}</span>
      </div>

      {/* Timestamp */}
      <div className="flex-shrink-0 flex items-center gap-1 text-[10px] text-muted-foreground/70">
        <Clock className="h-2.5 w-2.5" />
        <span className="whitespace-nowrap">{formatDate(application.updated_at)}</span>
      </div>

      {/* Actions */}
      <div
        className={cn(
          'flex-shrink-0 opacity-0 transition-opacity duration-100',
          'group-hover:opacity-100'
        )}
      >
        {(onEdit || onDelete) && (
          <ActionsDropdown
            onEdit={onEdit ? () => onEdit(application) : undefined}
            onDelete={onDelete ? () => onDelete(application) : undefined}
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
            'group-hover:text-amber-500'
          )}
        />
      )}

      {/* Description Tooltip */}
      {showTooltip && application.description && (
        <div
          className={cn(
            'absolute left-0 top-full z-50 mt-1.5 max-w-xs p-2',
            'rounded-md border border-border bg-popover text-xs text-popover-foreground shadow-md',
            'animate-in fade-in-0 slide-in-from-top-1 duration-150'
          )}
        >
          {application.description}
        </div>
      )}
    </div>
  )
}

export default ApplicationCard
