/**
 * Personality Tab
 *
 * Part of the Developer AI Settings Panel. Allows customizing
 * Blair's system prompt. Developer-only access.
 *
 * Features:
 * - Textarea for custom system prompt (min 6 rows, resizable)
 * - Save + Reset to Default buttons
 * - Dirty state tracking with unsaved changes warning
 * - Character count display (current / 2000 max)
 * - Confirmation dialog for reset
 */

import { useState, useCallback, useEffect } from 'react'
import { Loader2, RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { toast } from 'sonner'
import { useAuthToken } from '@/contexts/auth-context'

// ============================================================================
// Constants
// ============================================================================

const MAX_PROMPT_LENGTH = 2000

const DEFAULT_SYSTEM_PROMPT = `You are Blair, an AI assistant for project management. You help users with their tasks, projects, and knowledge base. Be concise, helpful, and professional.`

// ============================================================================
// PersonalityTab
// ============================================================================

export function PersonalityTab() {
  const token = useAuthToken()
  const [prompt, setPrompt] = useState('')
  const [savedPrompt, setSavedPrompt] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [showResetDialog, setShowResetDialog] = useState(false)

  const isDirty = prompt !== savedPrompt
  const charCount = prompt.length

  // Load current system prompt from backend
  useEffect(() => {
    async function loadPrompt() {
      if (!window.electronAPI || !token) {
        setIsLoading(false)
        return
      }

      try {
        const response = await window.electronAPI.get<{ prompt: string }>(
          '/api/ai/config/system-prompt',
          { Authorization: `Bearer ${token}` },
        )

        if (response.status === 200 && response.data?.prompt) {
          setPrompt(response.data.prompt)
          setSavedPrompt(response.data.prompt)
        } else {
          // No custom prompt set, use default
          setPrompt(DEFAULT_SYSTEM_PROMPT)
          setSavedPrompt(DEFAULT_SYSTEM_PROMPT)
        }
      } catch {
        // Fallback to default
        setPrompt(DEFAULT_SYSTEM_PROMPT)
        setSavedPrompt(DEFAULT_SYSTEM_PROMPT)
      } finally {
        setIsLoading(false)
      }
    }

    void loadPrompt()
  }, [token])

  const handleSave = useCallback(async () => {
    if (!window.electronAPI || !token) return

    setIsSaving(true)
    try {
      const response = await window.electronAPI.put(
        '/api/ai/config/system-prompt',
        { prompt },
        { Authorization: `Bearer ${token}` },
      )

      if (response.status === 200) {
        setSavedPrompt(prompt)
        toast.success("Blair's personality updated")
      } else {
        toast.error('Failed to save system prompt')
      }
    } catch {
      toast.error('Failed to save system prompt')
    } finally {
      setIsSaving(false)
    }
  }, [prompt, token])

  const handleReset = useCallback(async () => {
    if (!window.electronAPI || !token) return

    setIsSaving(true)
    try {
      // Save empty/default prompt to backend
      const response = await window.electronAPI.put(
        '/api/ai/config/system-prompt',
        { prompt: '' },
        { Authorization: `Bearer ${token}` },
      )

      if (response.status === 200) {
        setPrompt(DEFAULT_SYSTEM_PROMPT)
        setSavedPrompt(DEFAULT_SYSTEM_PROMPT)
        toast.success("Blair's personality reset to default")
      } else {
        toast.error('Failed to reset system prompt')
      }
    } catch {
      toast.error('Failed to reset system prompt')
    } finally {
      setIsSaving(false)
      setShowResetDialog(false)
    }
  }, [token])

  if (isLoading) {
    return (
      <div aria-busy="true" aria-label="Loading personality settings" className="space-y-4">
        {/* Title + description */}
        <div>
          <Skeleton className="h-4 w-36 mb-2" />
          <Skeleton className="h-3 w-72" />
        </div>
        {/* Label + textarea */}
        <div className="space-y-1.5">
          <Skeleton className="h-3 w-32" />
          <Skeleton className="h-[120px] w-full rounded-md" />
          <div className="flex items-center justify-between">
            <Skeleton className="h-2.5 w-20" />
          </div>
        </div>
        {/* Description text */}
        <Skeleton className="h-3 w-64" />
        {/* Buttons */}
        <div className="flex items-center gap-2">
          <Skeleton className="h-8 w-16 rounded-md" />
          <Skeleton className="h-8 w-28 rounded-md" />
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold">Blair's Personality</h3>
        <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
          Customize the system prompt that defines how Blair responds. Blair's name
          will always be "Blair" regardless of this prompt.
        </p>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="system-prompt">Custom System Prompt</Label>
        <textarea
          id="system-prompt"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value.slice(0, MAX_PROMPT_LENGTH))}
          rows={6}
          className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 resize-y min-h-[120px]"
          placeholder="Enter a custom system prompt for Blair..."
          aria-describedby="prompt-char-count"
        />
        <div className="flex items-center justify-between">
          <p
            id="prompt-char-count"
            className={`text-[10px] ${
              charCount > MAX_PROMPT_LENGTH * 0.9
                ? 'text-amber-600'
                : 'text-muted-foreground'
            }`}
          >
            {charCount} / {MAX_PROMPT_LENGTH} characters
          </p>
          {isDirty && (
            <p className="text-[10px] text-amber-600">Unsaved changes</p>
          )}
        </div>
      </div>

      <p className="text-xs text-muted-foreground leading-relaxed">
        This overrides Blair's default personality. Leave empty to use the
        default (concise, professional). Note: Blair's name is always "Blair"
        regardless of custom prompt.
      </p>

      <div className="flex items-center gap-2">
        <Button
          size="sm"
          onClick={handleSave}
          disabled={!isDirty || isSaving}
        >
          {isSaving && <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />}
          Save
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setShowResetDialog(true)}
          disabled={prompt === DEFAULT_SYSTEM_PROMPT || isSaving}
        >
          <RotateCcw className="h-3.5 w-3.5 mr-1.5" />
          Reset to Default
        </Button>
      </div>

      {/* Reset Confirmation Dialog */}
      <Dialog open={showResetDialog} onOpenChange={setShowResetDialog}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Reset to Default?</DialogTitle>
            <DialogDescription>
              This will clear your custom prompt and revert to Blair's default
              personality (concise, professional).
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowResetDialog(false)}
              disabled={isSaving}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleReset}
              disabled={isSaving}
            >
              {isSaving && (
                <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />
              )}
              Reset
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

export default PersonalityTab
