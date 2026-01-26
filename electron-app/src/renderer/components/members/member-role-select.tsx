/**
 * Member Role Select Component
 *
 * Dropdown component for selecting a member's role in an application.
 * Uses Radix UI Select for accessible dropdown functionality.
 *
 * Features:
 * - Role selection (owner, editor, viewer)
 * - Role descriptions and icons
 * - Disabled roles support
 * - Loading and disabled states
 * - Compact and default variants
 * - Keyboard accessible
 */

import { forwardRef, useCallback } from 'react'
import * as Select from '@radix-ui/react-select'
import { cn } from '@/lib/utils'
import {
  ChevronDown,
  Check,
  Crown,
  Edit2,
  Eye,
  Loader2,
} from 'lucide-react'
import type { ApplicationRole } from '@/hooks/use-members'

// ============================================================================
// Types
// ============================================================================

export interface RoleOption {
  value: ApplicationRole
  label: string
  description: string
  icon: JSX.Element
  colorClass: string
}

export interface MemberRoleSelectProps {
  /**
   * Currently selected role
   */
  value: ApplicationRole
  /**
   * Callback when role changes
   */
  onChange: (role: ApplicationRole) => void
  /**
   * Roles that should be disabled (not selectable)
   */
  disabledRoles?: ApplicationRole[]
  /**
   * Whether the select is disabled
   */
  disabled?: boolean
  /**
   * Whether an operation is loading
   */
  isLoading?: boolean
  /**
   * Visual variant
   * - 'default': Full-width with border
   * - 'compact': Minimal style for inline use
   * - 'badge': Badge-like appearance
   */
  variant?: 'default' | 'compact' | 'badge'
  /**
   * Size of the component
   */
  size?: 'sm' | 'md'
  /**
   * Additional CSS classes for trigger
   */
  className?: string
  /**
   * ID for the select element
   */
  id?: string
  /**
   * Accessible label for the select
   */
  'aria-label'?: string
  /**
   * Placeholder when no value selected
   */
  placeholder?: string
  /**
   * Whether to show role descriptions in the dropdown
   */
  showDescriptions?: boolean
}

// ============================================================================
// Constants
// ============================================================================

export const ROLE_OPTIONS: RoleOption[] = [
  {
    value: 'owner',
    label: 'Owner',
    description: 'Full access including delete and member management',
    icon: <Crown className="h-3.5 w-3.5" />,
    colorClass: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  },
  {
    value: 'editor',
    label: 'Editor',
    description: 'Can edit content but cannot delete the application',
    icon: <Edit2 className="h-3.5 w-3.5" />,
    colorClass: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  },
  {
    value: 'viewer',
    label: 'Viewer',
    description: 'Read-only access to application content',
    icon: <Eye className="h-3.5 w-3.5" />,
    colorClass: 'bg-slate-100 text-slate-700 dark:bg-slate-900/30 dark:text-slate-400',
  },
]

/**
 * Get role option by value
 */
export function getRoleOption(role: ApplicationRole): RoleOption | undefined {
  return ROLE_OPTIONS.find((option) => option.value === role)
}

// ============================================================================
// Component
// ============================================================================

export const MemberRoleSelect = forwardRef<HTMLButtonElement, MemberRoleSelectProps>(
  function MemberRoleSelect(
    {
      value,
      onChange,
      disabledRoles = [],
      disabled = false,
      isLoading = false,
      variant = 'default',
      size = 'md',
      className,
      id,
      'aria-label': ariaLabel = 'Select role',
      placeholder = 'Select a role',
      showDescriptions = true,
    },
    ref
  ) {
    // Get current role option
    const currentRole = getRoleOption(value)

    // Handle role change
    const handleChange = useCallback(
      (newValue: string) => {
        onChange(newValue as ApplicationRole)
      },
      [onChange]
    )

    // Check if role is disabled
    const isRoleDisabled = useCallback(
      (role: ApplicationRole): boolean => {
        return disabledRoles.includes(role)
      },
      [disabledRoles]
    )

    // Determine sizing classes
    const sizeClasses = {
      sm: {
        trigger: 'py-1 px-2 text-xs gap-1',
        icon: 'h-3 w-3',
        chevron: 'h-3 w-3',
        content: 'text-xs',
        item: 'py-1.5 px-2',
      },
      md: {
        trigger: 'py-2 px-3 text-sm gap-2',
        icon: 'h-3.5 w-3.5',
        chevron: 'h-4 w-4',
        content: 'text-sm',
        item: 'py-2 px-3',
      },
    }
    const sizes = sizeClasses[size]

    // Determine variant classes
    const variantClasses = {
      default: cn(
        'w-full justify-between rounded-md border border-input bg-background',
        'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
        'hover:bg-accent/50'
      ),
      compact: cn(
        'inline-flex justify-center rounded-md border border-transparent',
        'hover:bg-accent focus:outline-none focus:ring-2 focus:ring-ring'
      ),
      badge: cn(
        'inline-flex justify-center rounded-full',
        currentRole?.colorClass || 'bg-muted text-muted-foreground',
        'hover:opacity-80 focus:outline-none focus:ring-2 focus:ring-ring'
      ),
    }

    return (
      <Select.Root
        value={value}
        onValueChange={handleChange}
        disabled={disabled || isLoading}
      >
        <Select.Trigger
          ref={ref}
          id={id}
          className={cn(
            'flex items-center font-medium transition-colors',
            sizes.trigger,
            variantClasses[variant],
            'disabled:cursor-not-allowed disabled:opacity-50',
            className
          )}
          aria-label={ariaLabel}
        >
          <Select.Value placeholder={placeholder}>
            {currentRole && (
              <span className="flex items-center gap-1.5">
                {variant !== 'badge' && (
                  <span className={sizes.icon}>{currentRole.icon}</span>
                )}
                {variant === 'badge' && (
                  <span className={sizes.icon}>{currentRole.icon}</span>
                )}
                <span>{currentRole.label}</span>
              </span>
            )}
          </Select.Value>
          <Select.Icon className="ml-auto">
            {isLoading ? (
              <Loader2 className={cn(sizes.chevron, 'animate-spin text-muted-foreground')} />
            ) : (
              <ChevronDown className={cn(sizes.chevron, 'text-muted-foreground')} />
            )}
          </Select.Icon>
        </Select.Trigger>

        <Select.Portal>
          <Select.Content
            className={cn(
              'z-50 min-w-[180px] overflow-hidden rounded-md border border-border bg-popover shadow-lg',
              'data-[state=open]:animate-in data-[state=closed]:animate-out',
              'data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
              'data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95',
              'data-[side=bottom]:slide-in-from-top-2 data-[side=top]:slide-in-from-bottom-2',
              sizes.content
            )}
            position="popper"
            sideOffset={4}
            align="start"
          >
            <Select.Viewport className="p-1">
              {ROLE_OPTIONS.map((option) => {
                const roleDisabled = isRoleDisabled(option.value)
                return (
                  <Select.Item
                    key={option.value}
                    value={option.value}
                    disabled={roleDisabled}
                    className={cn(
                      'relative flex cursor-pointer select-none flex-col rounded-sm outline-none',
                      sizes.item,
                      'focus:bg-accent focus:text-accent-foreground',
                      'data-[disabled]:pointer-events-none data-[disabled]:opacity-50'
                    )}
                  >
                    <div className="flex items-center gap-2">
                      {/* Indicator (checkmark when selected) */}
                      <span className="w-4 flex-shrink-0">
                        <Select.ItemIndicator>
                          <Check className={sizes.icon} />
                        </Select.ItemIndicator>
                      </span>

                      {/* Role icon with color */}
                      <span
                        className={cn(
                          'flex h-5 w-5 items-center justify-center rounded-full',
                          option.colorClass
                        )}
                      >
                        <span className="[&>svg]:h-2.5 [&>svg]:w-2.5">{option.icon}</span>
                      </span>

                      {/* Role label */}
                      <Select.ItemText>
                        <span className="font-medium">{option.label}</span>
                      </Select.ItemText>
                    </div>

                    {/* Role description */}
                    {showDescriptions && (
                      <span className="ml-11 mt-0.5 text-xs text-muted-foreground">
                        {option.description}
                      </span>
                    )}
                  </Select.Item>
                )
              })}
            </Select.Viewport>
          </Select.Content>
        </Select.Portal>
      </Select.Root>
    )
  }
)

// ============================================================================
// Role Badge Component (for display only)
// ============================================================================

export interface RoleBadgeProps {
  /**
   * Role to display
   */
  role: ApplicationRole
  /**
   * Size of the badge
   */
  size?: 'sm' | 'md'
  /**
   * Whether to show the role icon
   */
  showIcon?: boolean
  /**
   * Additional CSS classes
   */
  className?: string
}

export function RoleBadge({
  role,
  size = 'sm',
  showIcon = true,
  className,
}: RoleBadgeProps): JSX.Element {
  const roleOption = getRoleOption(role)

  if (!roleOption) {
    return (
      <span className={cn('rounded-full px-2 py-0.5 text-xs font-medium bg-muted text-muted-foreground', className)}>
        Unknown
      </span>
    )
  }

  const sizeClasses = {
    sm: 'px-2 py-0.5 text-xs gap-1',
    md: 'px-2.5 py-1 text-sm gap-1.5',
  }

  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full font-medium',
        sizeClasses[size],
        roleOption.colorClass,
        className
      )}
    >
      {showIcon && <span className={size === 'sm' ? '[&>svg]:h-3 [&>svg]:w-3' : '[&>svg]:h-3.5 [&>svg]:w-3.5'}>{roleOption.icon}</span>}
      {roleOption.label}
    </span>
  )
}

// ============================================================================
// Exports
// ============================================================================

export default MemberRoleSelect
