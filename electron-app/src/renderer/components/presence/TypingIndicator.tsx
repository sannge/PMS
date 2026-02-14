/**
 * TypingIndicator Component
 *
 * Shows who is currently typing in the comment section.
 * Features:
 * - Animated dots
 * - Multiple typers support
 * - Auto-hide when no one is typing
 */

import { cn } from '@/lib/utils'

// ============================================================================
// Types
// ============================================================================

export interface TypingIndicatorProps {
  typingUsers: Record<string, { user_name: string; expires_at: number }>
  className?: string
}

// ============================================================================
// Component
// ============================================================================

export function TypingIndicator({
  typingUsers,
  className,
}: TypingIndicatorProps): JSX.Element | null {
  const typingNames = Object.values(typingUsers).map((u) => u.user_name)

  if (typingNames.length === 0) return null

  // Format the typing message
  let message: string
  if (typingNames.length === 1) {
    message = `${typingNames[0]} is typing`
  } else if (typingNames.length === 2) {
    message = `${typingNames[0]} and ${typingNames[1]} are typing`
  } else if (typingNames.length === 3) {
    message = `${typingNames[0]}, ${typingNames[1]}, and ${typingNames[2]} are typing`
  } else {
    message = `${typingNames.length} people are typing`
  }

  return (
    <div
      className={cn(
        'flex items-center gap-2 text-xs text-muted-foreground',
        'animate-in fade-in slide-in-from-bottom-2 duration-200',
        className
      )}
    >
      {/* Animated dots */}
      <div className="flex items-center gap-0.5">
        <span
          className={cn(
            'w-1.5 h-1.5 rounded-full bg-muted-foreground',
            'animate-bounce'
          )}
          style={{ animationDelay: '0ms' }}
        />
        <span
          className={cn(
            'w-1.5 h-1.5 rounded-full bg-muted-foreground',
            'animate-bounce'
          )}
          style={{ animationDelay: '150ms' }}
        />
        <span
          className={cn(
            'w-1.5 h-1.5 rounded-full bg-muted-foreground',
            'animate-bounce'
          )}
          style={{ animationDelay: '300ms' }}
        />
      </div>

      {/* Message */}
      <span>{message}</span>
    </div>
  )
}

export default TypingIndicator
