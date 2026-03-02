/**
 * Rewind UI Components
 *
 * Time travel / conversation rollback UI for the Blair AI sidebar.
 * - RewindBanner: banner above chat input showing rewind state with cancel
 */

import { RotateCcw, X } from 'lucide-react'
import { Button } from '@/components/ui/button'

// ============================================================================
// RewindBanner
// ============================================================================

interface RewindBannerProps {
  /** Truncated preview text of the message being rewound to */
  messagePreview: string
  /** Called when the user cancels rewind mode */
  onCancel: () => void
}

/**
 * Banner shown above the chat input when in rewind mode.
 * Displays which message the conversation is rewound to,
 * with a cancel button to restore the full conversation.
 */
export function RewindBanner({ messagePreview, onCancel }: RewindBannerProps): JSX.Element {
  const truncated =
    messagePreview.length > 60
      ? `${messagePreview.slice(0, 60)}...`
      : messagePreview

  return (
    <div className="blair-rewind-banner flex items-center gap-2 px-4 py-2">
      <RotateCcw className="h-3.5 w-3.5 shrink-0 text-yellow-600 dark:text-yellow-500" />
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium text-foreground truncate">
          Rewound to: &quot;{truncated}&quot;
        </p>
        <p className="text-xs text-muted-foreground">
          Send a message to branch from here, or cancel to restore.
        </p>
      </div>
      <Button
        variant="ghost"
        size="sm"
        onClick={onCancel}
        className="h-7 shrink-0 gap-1 px-2 text-xs"
      >
        <X className="h-3 w-3" />
        Cancel
      </Button>
    </div>
  )
}
