/**
 * ChecklistPanel Component
 *
 * Container for all checklists on a task with overall progress.
 * Features:
 * - Overall progress indicator
 * - List of checklist cards
 * - Add new checklist
 * - Empty state
 */

import { useEffect, useCallback, useState, useRef } from 'react'
import { cn } from '@/lib/utils'
import { CheckSquare, Plus, Loader2, AlertCircle, X } from 'lucide-react'
import { useChecklistsStore } from '@/stores/checklists-store'
import { useAuthStore } from '@/stores/auth-store'
import { ChecklistCard } from './ChecklistCard'

// ============================================================================
// Types
// ============================================================================

export interface ChecklistPanelProps {
  taskId: string
  className?: string
}

// ============================================================================
// Component
// ============================================================================

export function ChecklistPanel({
  taskId,
  className,
}: ChecklistPanelProps): JSX.Element {
  const token = useAuthStore((state) => state.token)
  const [isAdding, setIsAdding] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const {
    checklists,
    isLoading,
    isCreating,
    error,
    fetchChecklists,
    createChecklist,
    updateChecklist,
    deleteChecklist,
    createItem,
    updateItem,
    toggleItem,
    deleteItem,
    reorderItems,
    getProgress,
    clearError,
  } = useChecklistsStore()

  // Fetch checklists on mount
  useEffect(() => {
    fetchChecklists(token, taskId)
  }, [token, taskId, fetchChecklists])

  // Focus input when adding
  useEffect(() => {
    if (isAdding && inputRef.current) {
      inputRef.current.focus()
    }
  }, [isAdding])

  // Get progress
  const progress = getProgress()

  // Handlers
  const handleCreateChecklist = useCallback(async () => {
    const trimmed = newTitle.trim()
    if (!trimmed) return

    await createChecklist(token, taskId, { title: trimmed })
    setNewTitle('')
    setIsAdding(false)
  }, [token, taskId, newTitle, createChecklist])

  const handleTitleUpdate = useCallback(
    async (checklistId: string, title: string) => {
      await updateChecklist(token, checklistId, title)
    },
    [token, updateChecklist]
  )

  const handleDelete = useCallback(
    async (checklistId: string) => {
      await deleteChecklist(token, checklistId)
    },
    [token, deleteChecklist]
  )

  const handleItemToggle = useCallback(
    async (itemId: string) => {
      await toggleItem(token, itemId)
    },
    [token, toggleItem]
  )

  const handleItemUpdate = useCallback(
    async (itemId: string, text: string) => {
      await updateItem(token, itemId, text)
    },
    [token, updateItem]
  )

  const handleItemDelete = useCallback(
    async (itemId: string) => {
      await deleteItem(token, itemId)
    },
    [token, deleteItem]
  )

  const handleItemCreate = useCallback(
    async (checklistId: string, text: string) => {
      await createItem(token, checklistId, { text })
    },
    [token, createItem]
  )

  const handleItemReorder = useCallback(
    async (checklistId: string, itemIds: string[]) => {
      await reorderItems(token, checklistId, itemIds)
    },
    [token, reorderItems]
  )

  // Sort checklists by position
  const sortedChecklists = [...checklists].sort((a, b) => a.position - b.position)

  // Loading state
  if (isLoading && checklists.length === 0) {
    return (
      <div className={cn('flex flex-col', className)}>
        <div className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      </div>
    )
  }

  return (
    <div className={cn('flex flex-col h-full', className)}>
      {/* Header */}
      <div className="flex items-center justify-between px-2 py-2 border-b border-border">
        <div className="flex items-center gap-2">
          <CheckSquare className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-medium text-foreground">Checklists</span>
          {progress.total > 0 && (
            <span className="text-xs text-muted-foreground">
              ({progress.done}/{progress.total})
            </span>
          )}
        </div>

        {/* Overall progress */}
        {progress.total > 0 && (
          <div className="flex items-center gap-2">
            <div className="w-24 h-1.5 bg-muted rounded-full overflow-hidden">
              <div
                className={cn(
                  'h-full transition-all duration-300',
                  progress.percent === 100 ? 'bg-green-500' : 'bg-primary'
                )}
                style={{ width: `${progress.percent}%` }}
              />
            </div>
            <span className="text-xs text-muted-foreground tabular-nums w-8">
              {progress.percent}%
            </span>
          </div>
        )}
      </div>

      {/* Error banner */}
      {error && (
        <div className="flex items-center gap-2 px-3 py-2 bg-destructive/10 border-b border-destructive/20">
          <AlertCircle className="h-4 w-4 text-destructive flex-shrink-0" />
          <p className="text-xs text-destructive flex-1">{error.message}</p>
          <button onClick={clearError} className="text-xs text-destructive underline">
            Dismiss
          </button>
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {/* Empty state */}
        {sortedChecklists.length === 0 && !isAdding && (
          <div className="flex flex-col items-center justify-center py-8 px-4">
            <CheckSquare className="h-10 w-10 text-muted-foreground/50 mb-2" />
            <p className="text-sm text-muted-foreground text-center mb-3">
              No checklists yet. Add one to track sub-tasks.
            </p>
            <button
              onClick={() => setIsAdding(true)}
              className={cn(
                'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md',
                'bg-primary text-primary-foreground text-sm font-medium',
                'hover:bg-primary/90',
                'transition-colors'
              )}
            >
              <Plus className="h-4 w-4" />
              Add checklist
            </button>
          </div>
        )}

        {/* Checklists */}
        {sortedChecklists.map((checklist) => (
          <ChecklistCard
            key={checklist.id}
            checklist={checklist}
            onTitleUpdate={handleTitleUpdate}
            onDelete={handleDelete}
            onItemToggle={handleItemToggle}
            onItemUpdate={handleItemUpdate}
            onItemDelete={handleItemDelete}
            onItemCreate={handleItemCreate}
            onItemReorder={handleItemReorder}
            disabled={isCreating}
          />
        ))}

        {/* Add checklist */}
        {isAdding ? (
          <div className="flex items-center gap-2 p-2 rounded-lg border border-dashed border-border">
            <CheckSquare className="h-4 w-4 flex-shrink-0 text-primary" />
            <input
              ref={inputRef}
              type="text"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleCreateChecklist()
                if (e.key === 'Escape') {
                  setIsAdding(false)
                  setNewTitle('')
                }
              }}
              placeholder="Checklist title..."
              className={cn(
                'flex-1 px-2 py-1.5 rounded',
                'bg-background border border-border',
                'text-sm text-foreground',
                'placeholder:text-muted-foreground',
                'focus:outline-none focus:ring-1 focus:ring-ring'
              )}
              disabled={isCreating}
            />
            <button
              onClick={handleCreateChecklist}
              disabled={!newTitle.trim() || isCreating}
              className={cn(
                'px-3 py-1.5 rounded-md',
                'bg-primary text-primary-foreground text-xs font-medium',
                'hover:bg-primary/90',
                'disabled:opacity-50 disabled:cursor-not-allowed',
                'transition-colors'
              )}
            >
              {isCreating ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Add'}
            </button>
            <button
              onClick={() => {
                setIsAdding(false)
                setNewTitle('')
              }}
              className={cn(
                'p-1.5 rounded text-muted-foreground hover:bg-muted',
                'transition-colors'
              )}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        ) : (
          sortedChecklists.length > 0 && (
            <button
              onClick={() => setIsAdding(true)}
              className={cn(
                'flex items-center gap-2 w-full p-2 rounded-lg',
                'border border-dashed border-border',
                'text-sm text-muted-foreground',
                'hover:border-primary/50 hover:text-foreground hover:bg-muted/30',
                'transition-colors'
              )}
            >
              <Plus className="h-4 w-4" />
              Add another checklist
            </button>
          )
        )}
      </div>
    </div>
  )
}

export default ChecklistPanel
