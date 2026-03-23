/**
 * Export Button
 *
 * Downloads an Excel export of team activity data.
 * Shows a loading spinner while the export is in progress.
 */

import { useState, useCallback } from 'react'
import { Download, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { exportTeamActivity } from '@/hooks/use-team-activity'
import { toast } from 'sonner'

// ============================================================================
// Types
// ============================================================================

interface ExportButtonProps {
  tab: string
  appId: string
  dateFrom: string
  dateTo: string
}

// ============================================================================
// Component
// ============================================================================

export function ExportButton({ tab, appId, dateFrom, dateTo }: ExportButtonProps): JSX.Element {
  const [isExporting, setIsExporting] = useState(false)

  const handleExport = useCallback(async () => {
    setIsExporting(true)
    try {
      await exportTeamActivity(tab, appId, dateFrom, dateTo)
      toast.success('Export downloaded successfully')
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Export failed'
      toast.error(message)
    } finally {
      setIsExporting(false)
    }
  }, [tab, appId, dateFrom, dateTo])

  return (
    <Button
      variant="outline"
      size="sm"
      onClick={handleExport}
      disabled={isExporting}
      className="h-8 gap-1.5 text-xs"
    >
      {isExporting ? (
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
      ) : (
        <Download className="h-3.5 w-3.5" />
      )}
      Export
    </Button>
  )
}
