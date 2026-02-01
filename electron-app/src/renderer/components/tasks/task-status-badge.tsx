/**
 * Task Status Badge Component
 *
 * Displays the task status with appropriate styling and icons.
 * Supports interactive status transitions when onStatusChange is provided.
 *
 * Features:
 * - Status-specific colors and icons
 * - Hover effects for interactive mode
 * - Click to open status selector dropdown
 * - Keyboard accessible
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import { cn } from '@/lib/utils'
import {
  Circle,
  Timer,
  Eye,
  CheckCircle2,
  XCircle,
  ChevronDown,
} from 'lucide-react'
// Legacy TaskStatus type - kept for internal badge use until full migration
type TaskStatus = 'todo' | 'in_progress' | 'in_review' | 'issue' | 'done'

// ============================================================================
// Types
// ============================================================================

export interface TaskStatusBadgeProps {
  /**
   * Current task status
   */
  status: TaskStatus
  /**
   * Callback when status is changed (enables interactive mode)
   */
  onStatusChange?: (status: TaskStatus) => void
  /**
   * Whether the badge is disabled
   */
  disabled?: boolean
  /**
   * Size variant
   */
  size?: 'sm' | 'md' | 'lg'
  /**
   * Additional CSS classes
   */
  className?: string
}

interface StatusConfig {
  label: string
  icon: JSX.Element
  bgColor: string
  textColor: string
  borderColor: string
}

// ============================================================================
// Constants
// ============================================================================

const STATUS_ORDER: TaskStatus[] = ['todo', 'in_progress', 'in_review', 'issue', 'done']

const STATUS_CONFIG: Record<TaskStatus, StatusConfig> = {
  todo: {
    label: 'To Do',
    icon: <Circle className="h-3.5 w-3.5" />,
    bgColor: 'bg-slate-100 dark:bg-slate-800',
    textColor: 'text-slate-700 dark:text-slate-300',
    borderColor: 'border-slate-300 dark:border-slate-600',
  },
  in_progress: {
    label: 'In Progress',
    icon: <Timer className="h-3.5 w-3.5" />,
    bgColor: 'bg-blue-100 dark:bg-blue-900/50',
    textColor: 'text-blue-700 dark:text-blue-300',
    borderColor: 'border-blue-300 dark:border-blue-700',
  },
  in_review: {
    label: 'In Review',
    icon: <Eye className="h-3.5 w-3.5" />,
    bgColor: 'bg-purple-100 dark:bg-purple-900/50',
    textColor: 'text-purple-700 dark:text-purple-300',
    borderColor: 'border-purple-300 dark:border-purple-700',
  },
  issue: {
    label: 'Issue',
    icon: <XCircle className="h-3.5 w-3.5" />,
    bgColor: 'bg-red-100 dark:bg-red-900/50',
    textColor: 'text-red-700 dark:text-red-300',
    borderColor: 'border-red-300 dark:border-red-700',
  },
  done: {
    label: 'Done',
    icon: <CheckCircle2 className="h-3.5 w-3.5" />,
    bgColor: 'bg-green-100 dark:bg-green-900/50',
    textColor: 'text-green-700 dark:text-green-300',
    borderColor: 'border-green-300 dark:border-green-700',
  },
}

const SIZE_CLASSES = {
  sm: 'px-2 py-0.5 text-xs gap-1',
  md: 'px-2.5 py-1 text-sm gap-1.5',
  lg: 'px-3 py-1.5 text-sm gap-2',
}

// ============================================================================
// Component
// ============================================================================

export function TaskStatusBadge({
  status,
  onStatusChange,
  disabled = false,
  size = 'md',
  className,
}: TaskStatusBadgeProps): JSX.Element {
  const [isOpen, setIsOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)

  const config = STATUS_CONFIG[status]
  const isInteractive = !!onStatusChange && !disabled

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false)
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [isOpen])

  // Close dropdown on escape
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setIsOpen(false)
        buttonRef.current?.focus()
      }
    }

    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown)
      return () => document.removeEventListener('keydown', handleKeyDown)
    }
  }, [isOpen])

  // Handle status selection
  const handleStatusSelect = useCallback(
    (newStatus: TaskStatus) => {
      if (newStatus !== status && onStatusChange) {
        onStatusChange(newStatus)
      }
      setIsOpen(false)
    },
    [status, onStatusChange]
  )

  // Non-interactive badge
  if (!isInteractive) {
    return (
      <span
        className={cn(
          'inline-flex items-center rounded-full border font-medium',
          config.bgColor,
          config.textColor,
          config.borderColor,
          SIZE_CLASSES[size],
          className
        )}
      >
        {config.icon}
        <span>{config.label}</span>
      </span>
    )
  }

  // Interactive badge with dropdown
  return (
    <div ref={dropdownRef} className="relative inline-block">
      <button
        ref={buttonRef}
        onClick={() => setIsOpen(!isOpen)}
        disabled={disabled}
        className={cn(
          'inline-flex items-center rounded-full border font-medium transition-all',
          config.bgColor,
          config.textColor,
          config.borderColor,
          SIZE_CLASSES[size],
          'hover:shadow-sm cursor-pointer',
          'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1',
          'disabled:opacity-50 disabled:cursor-not-allowed',
          className
        )}
      >
        {config.icon}
        <span>{config.label}</span>
        <ChevronDown
          className={cn(
            'h-3 w-3 transition-transform',
            isOpen && 'rotate-180'
          )}
        />
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div
          className={cn(
            'absolute z-50 mt-1 min-w-[140px] rounded-lg border border-border',
            'bg-popover shadow-lg py-1',
            'animate-in fade-in-0 zoom-in-95'
          )}
        >
          {STATUS_ORDER.map((statusOption) => {
            const optionConfig = STATUS_CONFIG[statusOption]
            const isSelected = statusOption === status

            return (
              <button
                key={statusOption}
                onClick={() => handleStatusSelect(statusOption)}
                className={cn(
                  'flex w-full items-center gap-2 px-3 py-2 text-sm transition-colors',
                  'hover:bg-accent',
                  'focus:outline-none focus:bg-accent',
                  isSelected && 'bg-accent'
                )}
              >
                <span className={optionConfig.textColor}>{optionConfig.icon}</span>
                <span className="text-foreground">{optionConfig.label}</span>
                {isSelected && (
                  <CheckCircle2 className="ml-auto h-3.5 w-3.5 text-primary" />
                )}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ============================================================================
// Helper Exports
// ============================================================================

/**
 * Get status configuration
 */
export function getStatusConfig(status: TaskStatus): StatusConfig {
  return STATUS_CONFIG[status]
}

/**
 * Get all available statuses in order
 */
export function getStatusOptions(): { value: TaskStatus; label: string }[] {
  return STATUS_ORDER.map((s) => ({
    value: s,
    label: STATUS_CONFIG[s].label,
  }))
}

export default TaskStatusBadge
