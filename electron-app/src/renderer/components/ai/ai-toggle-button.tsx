/**
 * AI Toggle Button
 *
 * Compact button with Sparkles icon for the window title bar.
 * Toggles the Blair AI sidebar. Shows active state when open.
 * Styled to match the title bar's utility controls (Search, Theme, User).
 */

import { Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAiSidebar } from './use-ai-sidebar'

export function AiToggleButton(): JSX.Element {
  const { isOpen, toggle } = useAiSidebar()

  return (
    <button
      type="button"
      onClick={toggle}
      className={cn(
        'flex h-6 w-6 items-center justify-center rounded',
        'text-sidebar-foreground/50 transition-colors',
        'hover:bg-sidebar-muted/40 hover:text-sidebar-foreground',
        isOpen && 'bg-sidebar-muted/40 text-sidebar-foreground'
      )}
      title="Blair (Ctrl+Shift+A)"
      aria-label="Toggle Blair AI sidebar"
      aria-pressed={isOpen}
    >
      <Sparkles className="h-3.5 w-3.5" />
    </button>
  )
}
