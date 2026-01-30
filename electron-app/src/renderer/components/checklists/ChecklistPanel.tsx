/**
 * ChecklistPanel Component
 *
 * Container for all checklists on a task with overall progress.
 * Features:
 * - Overall progress indicator
 * - List of checklist cards
 * - Add new checklist
 * - Empty state
 * - Real-time updates via WebSocket cache invalidation
 */

import { useEffect, useCallback, useState, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { cn } from '@/lib/utils'
import { CheckSquare, Plus, AlertCircle, X } from 'lucide-react'
import {
  useChecklists,
  useChecklistProgress,
  useCreateChecklist,
  useUpdateChecklist,
  useDeleteChecklist,
  useCreateChecklistItem,
  useUpdateChecklistItem,
  useToggleChecklistItem,
  useDeleteChecklistItem,
  useReorderChecklistItems,
} from '@/hooks/use-checklists'
import { queryKeys } from '@/lib/query-client'
import { ChecklistCard } from './ChecklistCard'
import { SkeletonChecklists } from '@/components/ui/skeleton'
import { wsClient, MessageType } from '@/lib/websocket'

// ============================================================================
// Types
// ============================================================================

export interface ChecklistPanelProps {
  taskId: string
  className?: string
  /**
   * Whether the user can edit checklists (add/edit/delete)
   */
  canEdit?: boolean
}

// ============================================================================
// Component
// ============================================================================

export function ChecklistPanel({
  taskId,
  className,
  canEdit = true,
}: ChecklistPanelProps): JSX.Element {
  const queryClient = useQueryClient()
  const [isAdding, setIsAdding] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [error, setError] = useState<Error | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Queries
  const { data: checklists = [], isLoading } = useChecklists(taskId)
  const progress = useChecklistProgress(taskId)

  // Mutations
  const createChecklist = useCreateChecklist(taskId)
  const updateChecklist = useUpdateChecklist(taskId)
  const deleteChecklist = useDeleteChecklist(taskId)
  const createItem = useCreateChecklistItem(taskId)
  const updateItem = useUpdateChecklistItem(taskId)
  const toggleItem = useToggleChecklistItem(taskId)
  const deleteItem = useDeleteChecklistItem(taskId)
  const reorderItems = useReorderChecklistItems(taskId)

  // Focus input when adding
  useEffect(() => {
    if (isAdding && inputRef.current) {
      inputRef.current.focus()
    }
  }, [isAdding])

  // Subscribe to WebSocket events for real-time cache invalidation
  useEffect(() => {
    if (!taskId) return

    const roomId = `task:${taskId}`

    // Join the room for this task
    wsClient.joinRoom(roomId)

    // Invalidate checklists cache on any checklist event
    const invalidateChecklists = () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.checklists(taskId) })
    }

    // Subscribe to all checklist events - invalidate cache to refetch
    wsClient.on(MessageType.CHECKLIST_CREATED, invalidateChecklists)
    wsClient.on(MessageType.CHECKLIST_UPDATED, invalidateChecklists)
    wsClient.on(MessageType.CHECKLIST_DELETED, invalidateChecklists)
    wsClient.on(MessageType.CHECKLISTS_REORDERED, invalidateChecklists)
    wsClient.on(MessageType.CHECKLIST_ITEM_TOGGLED, invalidateChecklists)
    wsClient.on(MessageType.CHECKLIST_ITEM_ADDED, invalidateChecklists)
    wsClient.on(MessageType.CHECKLIST_ITEM_UPDATED, invalidateChecklists)
    wsClient.on(MessageType.CHECKLIST_ITEM_DELETED, invalidateChecklists)
    wsClient.on(MessageType.CHECKLIST_ITEMS_REORDERED, invalidateChecklists)

    // Cleanup: leave room and unsubscribe
    return () => {
      wsClient.leaveRoom(roomId)
      wsClient.off(MessageType.CHECKLIST_CREATED, invalidateChecklists)
      wsClient.off(MessageType.CHECKLIST_UPDATED, invalidateChecklists)
      wsClient.off(MessageType.CHECKLIST_DELETED, invalidateChecklists)
      wsClient.off(MessageType.CHECKLISTS_REORDERED, invalidateChecklists)
      wsClient.off(MessageType.CHECKLIST_ITEM_TOGGLED, invalidateChecklists)
      wsClient.off(MessageType.CHECKLIST_ITEM_ADDED, invalidateChecklists)
      wsClient.off(MessageType.CHECKLIST_ITEM_UPDATED, invalidateChecklists)
      wsClient.off(MessageType.CHECKLIST_ITEM_DELETED, invalidateChecklists)
      wsClient.off(MessageType.CHECKLIST_ITEMS_REORDERED, invalidateChecklists)
    }
  }, [taskId, queryClient])

  // Handlers
  const handleCreateChecklist = useCallback(async () => {
    const trimmed = newTitle.trim()
    if (!trimmed) return

    // Clear form immediately since we use optimistic updates
    setNewTitle('')
    setIsAdding(false)

    try {
      await createChecklist.mutateAsync({ title: trimmed })
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Failed to create checklist'))
    }
  }, [newTitle, createChecklist])

  const handleTitleUpdate = useCallback(
    async (checklistId: string, title: string) => {
      try {
        await updateChecklist.mutateAsync({ checklistId, title })
      } catch (err) {
        setError(err instanceof Error ? err : new Error('Failed to update checklist'))
      }
    },
    [updateChecklist]
  )

  const handleDelete = useCallback(
    async (checklistId: string) => {
      try {
        await deleteChecklist.mutateAsync(checklistId)
      } catch (err) {
        setError(err instanceof Error ? err : new Error('Failed to delete checklist'))
      }
    },
    [deleteChecklist]
  )

  const handleItemToggle = useCallback(
    async (itemId: string) => {
      try {
        await toggleItem.mutateAsync(itemId)
      } catch (err) {
        setError(err instanceof Error ? err : new Error('Failed to toggle item'))
      }
    },
    [toggleItem]
  )

  const handleItemUpdate = useCallback(
    async (itemId: string, content: string) => {
      try {
        await updateItem.mutateAsync({ itemId, content })
      } catch (err) {
        setError(err instanceof Error ? err : new Error('Failed to update item'))
      }
    },
    [updateItem]
  )

  const handleItemDelete = useCallback(
    async (itemId: string) => {
      try {
        await deleteItem.mutateAsync(itemId)
      } catch (err) {
        setError(err instanceof Error ? err : new Error('Failed to delete item'))
      }
    },
    [deleteItem]
  )

  const handleItemCreate = useCallback(
    async (checklistId: string, content: string) => {
      try {
        await createItem.mutateAsync({ checklistId, data: { content } })
      } catch (err) {
        setError(err instanceof Error ? err : new Error('Failed to create item'))
      }
    },
    [createItem]
  )

  const handleItemReorder = useCallback(
    async (checklistId: string, itemIds: string[]) => {
      try {
        await reorderItems.mutateAsync({ checklistId, itemIds })
      } catch (err) {
        setError(err instanceof Error ? err : new Error('Failed to reorder items'))
      }
    },
    [reorderItems]
  )

  const clearError = useCallback(() => {
    setError(null)
  }, [])

  // Loading state - show skeleton
  if (isLoading && checklists.length === 0) {
    return (
      <div className={cn('flex flex-col h-full', className)}>
        {/* Header */}
        <div className="flex items-center justify-between px-2 py-2 border-b border-border">
          <div className="flex items-center gap-2">
            <CheckSquare className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-medium text-foreground">Checklists</span>
          </div>
        </div>
        {/* Skeleton content */}
        <div className="flex-1 overflow-y-auto p-3">
          <SkeletonChecklists count={2} />
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

      {/* Error banner - hide permission errors since UI already disables actions */}
      {error && !error.message.toLowerCase().includes('access denied') && !error.message.toLowerCase().includes('permission') && (
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
        {checklists.length === 0 && !isAdding && (
          <div className="flex flex-col items-center justify-center py-8 px-4">
            <CheckSquare className="h-10 w-10 text-muted-foreground/50 mb-2" />
            <p className="text-sm text-muted-foreground text-center mb-3">
              {canEdit ? 'No checklists yet. Add one to track sub-tasks.' : 'No checklists yet.'}
            </p>
            {canEdit && (
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
            )}
          </div>
        )}

        {/* Checklists */}
        {checklists.map((checklist) => (
          <ChecklistCard
            key={checklist.id}
            checklist={checklist}
            onTitleUpdate={canEdit ? handleTitleUpdate : undefined}
            onDelete={canEdit ? handleDelete : undefined}
            onItemToggle={canEdit ? handleItemToggle : undefined}
            onItemUpdate={canEdit ? handleItemUpdate : undefined}
            onItemDelete={canEdit ? handleItemDelete : undefined}
            onItemCreate={canEdit ? handleItemCreate : undefined}
            onItemReorder={canEdit ? handleItemReorder : undefined}
            disabled={checklist.id.startsWith('temp-')}
          />
        ))}

        {/* Add checklist */}
        {canEdit && isAdding ? (
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
            />
            <button
              onClick={handleCreateChecklist}
              disabled={!newTitle.trim()}
              className={cn(
                'px-3 py-1.5 rounded-md',
                'bg-primary text-primary-foreground text-xs font-medium',
                'hover:bg-primary/90',
                'disabled:opacity-50 disabled:cursor-not-allowed',
                'transition-colors'
              )}
            >
              Add
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
          canEdit && checklists.length > 0 && (
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
