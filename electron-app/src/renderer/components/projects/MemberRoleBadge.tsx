/**
 * MemberRoleBadge Component
 *
 * Displays project member roles (admin/member) with distinctive premium styling.
 * Features glass morphism effects, subtle gradients, and elegant micro-interactions.
 *
 * Roles:
 * - Admin: Can manage project members + edit/move tasks (crown icon, indigo/violet)
 * - Member: Can edit/move tasks only (user icon, slate/neutral)
 *
 * @module components/projects/MemberRoleBadge
 */

import { memo } from 'react'
import * as Tooltip from '@radix-ui/react-tooltip'
import { cn } from '@/lib/utils'
import { Crown, User, ShieldCheck, Users } from 'lucide-react'
import type { ProjectMemberRole } from '@/stores/project-members-store'

// ============================================================================
// Types
// ============================================================================

export interface MemberRoleBadgeProps {
  /**
   * The project member role to display
   */
  role: ProjectMemberRole
  /**
   * Size variant
   * - 'xs': Extra small, icon only
   * - 'sm': Small, icon + abbreviated text
   * - 'md': Medium, full text (default)
   * - 'lg': Large, full text with description
   */
  size?: 'xs' | 'sm' | 'md' | 'lg'
  /**
   * Whether to show the tooltip with role description
   * @default true
   */
  showTooltip?: boolean
  /**
   * Whether to use glass morphism effect
   * @default true
   */
  glassMorphism?: boolean
  /**
   * Additional CSS classes
   */
  className?: string
}

// ============================================================================
// Role Configuration
// ============================================================================

interface RoleConfig {
  label: string
  shortLabel: string
  description: string
  icon: JSX.Element
  iconLg: JSX.Element
  // Light mode colors
  bgLight: string
  textLight: string
  borderLight: string
  glowLight: string
  // Dark mode colors
  bgDark: string
  textDark: string
  borderDark: string
  glowDark: string
  // Glass effect gradient
  gradientFrom: string
  gradientTo: string
}

const ROLE_CONFIG: Record<ProjectMemberRole, RoleConfig> = {
  admin: {
    label: 'Admin',
    shortLabel: 'Admin',
    description: 'Can manage members, edit tasks, and change project settings',
    icon: <Crown className="h-3 w-3" strokeWidth={2.5} />,
    iconLg: <ShieldCheck className="h-4 w-4" strokeWidth={2} />,
    // Light mode - regal violet/indigo
    bgLight: 'bg-gradient-to-br from-violet-50 via-indigo-50 to-purple-50',
    textLight: 'text-violet-700',
    borderLight: 'border-violet-200/80',
    glowLight: 'shadow-violet-200/50',
    // Dark mode
    bgDark: 'dark:bg-gradient-to-br dark:from-violet-950/40 dark:via-indigo-950/40 dark:to-purple-950/40',
    textDark: 'dark:text-violet-300',
    borderDark: 'dark:border-violet-700/50',
    glowDark: 'dark:shadow-violet-900/30',
    // Glass gradient overlay
    gradientFrom: 'from-violet-400/10',
    gradientTo: 'to-indigo-400/5',
  },
  member: {
    label: 'Member',
    shortLabel: 'Member',
    description: 'Can edit and move tasks within this project',
    icon: <User className="h-3 w-3" strokeWidth={2.5} />,
    iconLg: <Users className="h-4 w-4" strokeWidth={2} />,
    // Light mode - sophisticated slate
    bgLight: 'bg-gradient-to-br from-slate-50 via-zinc-50 to-gray-50',
    textLight: 'text-slate-600',
    borderLight: 'border-slate-200/80',
    glowLight: 'shadow-slate-200/50',
    // Dark mode
    bgDark: 'dark:bg-gradient-to-br dark:from-slate-900/50 dark:via-zinc-900/50 dark:to-gray-900/50',
    textDark: 'dark:text-slate-400',
    borderDark: 'dark:border-slate-700/50',
    glowDark: 'dark:shadow-slate-800/30',
    // Glass gradient overlay
    gradientFrom: 'from-slate-400/10',
    gradientTo: 'to-zinc-400/5',
  },
}

// ============================================================================
// Size Configuration
// ============================================================================

const SIZE_CLASSES = {
  xs: {
    badge: 'h-5 w-5 p-0',
    text: 'sr-only',
    iconSize: 'h-3 w-3',
    gap: '',
    rounded: 'rounded-md',
  },
  sm: {
    badge: 'px-1.5 py-0.5',
    text: 'text-[10px] font-semibold tracking-wide uppercase',
    iconSize: 'h-2.5 w-2.5',
    gap: 'gap-1',
    rounded: 'rounded-md',
  },
  md: {
    badge: 'px-2 py-0.5',
    text: 'text-[11px] font-semibold tracking-wide uppercase',
    iconSize: 'h-3 w-3',
    gap: 'gap-1.5',
    rounded: 'rounded-lg',
  },
  lg: {
    badge: 'px-3 py-1',
    text: 'text-xs font-semibold tracking-wide',
    iconSize: 'h-3.5 w-3.5',
    gap: 'gap-2',
    rounded: 'rounded-lg',
  },
}

// ============================================================================
// Component
// ============================================================================

function MemberRoleBadgeBase({
  role,
  size = 'md',
  showTooltip = true,
  glassMorphism = true,
  className,
}: MemberRoleBadgeProps): JSX.Element {
  const config = ROLE_CONFIG[role]
  const sizeConfig = SIZE_CLASSES[size]
  const isAdmin = role === 'admin'

  const badge = (
    <span
      className={cn(
        // Base layout
        'relative inline-flex items-center justify-center',
        sizeConfig.badge,
        sizeConfig.gap,
        sizeConfig.rounded,
        // Background gradient
        config.bgLight,
        config.bgDark,
        // Text color
        config.textLight,
        config.textDark,
        // Border
        'border',
        config.borderLight,
        config.borderDark,
        // Subtle shadow/glow
        'shadow-sm',
        config.glowLight,
        config.glowDark,
        // Glass morphism effect
        glassMorphism && [
          'backdrop-blur-sm',
          'before:absolute before:inset-0 before:rounded-[inherit]',
          'before:bg-gradient-to-br',
          `before:${config.gradientFrom}`,
          `before:${config.gradientTo}`,
          'before:pointer-events-none',
        ],
        // Subtle hover effect
        'transition-all duration-200 ease-out',
        'hover:shadow-md',
        isAdmin && 'hover:border-violet-300 dark:hover:border-violet-600',
        !isAdmin && 'hover:border-slate-300 dark:hover:border-slate-600',
        // Additional classes
        className
      )}
    >
      {/* Icon */}
      <span
        className={cn(
          'relative z-10 flex items-center justify-center',
          'transition-transform duration-200',
          'group-hover:scale-105'
        )}
      >
        {size === 'lg' ? config.iconLg : config.icon}
      </span>

      {/* Label */}
      {size !== 'xs' && (
        <span className={cn('relative z-10', sizeConfig.text)}>
          {size === 'lg' ? config.label : config.shortLabel}
        </span>
      )}

      {/* Admin sparkle effect */}
      {isAdmin && glassMorphism && (
        <span
          className={cn(
            'absolute -top-px -right-px h-1.5 w-1.5 rounded-full',
            'bg-gradient-to-br from-amber-300 to-yellow-400',
            'dark:from-amber-400 dark:to-yellow-500',
            'shadow-sm shadow-amber-300/50 dark:shadow-amber-500/30',
            'animate-pulse'
          )}
          aria-hidden="true"
        />
      )}
    </span>
  )

  // Without tooltip
  if (!showTooltip) {
    return badge
  }

  // With tooltip
  return (
    <Tooltip.Provider delayDuration={300}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>{badge}</Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Content
            side="top"
            align="center"
            sideOffset={6}
            className={cn(
              'z-50 overflow-hidden rounded-lg',
              'border border-border/50',
              'bg-popover/95 backdrop-blur-md',
              'px-3 py-2 shadow-xl',
              'animate-in fade-in-0 zoom-in-95 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95',
              'data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2'
            )}
          >
            <div className="flex items-start gap-2.5">
              <span
                className={cn(
                  'mt-0.5 flex h-6 w-6 items-center justify-center rounded-md',
                  isAdmin
                    ? 'bg-violet-100 text-violet-600 dark:bg-violet-900/50 dark:text-violet-400'
                    : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400'
                )}
              >
                {config.iconLg}
              </span>
              <div className="space-y-0.5">
                <p
                  className={cn(
                    'text-sm font-semibold',
                    isAdmin
                      ? 'text-violet-700 dark:text-violet-300'
                      : 'text-slate-700 dark:text-slate-300'
                  )}
                >
                  {config.label}
                </p>
                <p className="text-xs text-muted-foreground max-w-[200px] leading-relaxed">
                  {config.description}
                </p>
              </div>
            </div>
            <Tooltip.Arrow
              className="fill-popover/95"
              width={12}
              height={6}
            />
          </Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  )
}

// ============================================================================
// Memoized Export
// ============================================================================

export const MemberRoleBadge = memo(MemberRoleBadgeBase)

// ============================================================================
// Helper Exports
// ============================================================================

/**
 * Get role configuration for custom rendering
 */
export function getRoleConfig(role: ProjectMemberRole) {
  return ROLE_CONFIG[role]
}

/**
 * Get display label for a role
 */
export function getRoleLabel(role: ProjectMemberRole): string {
  return ROLE_CONFIG[role].label
}

/**
 * Get role description
 */
export function getRoleDescription(role: ProjectMemberRole): string {
  return ROLE_CONFIG[role].description
}

export default MemberRoleBadge
