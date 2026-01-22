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
import { CheckSquare, Plus, AlertCircle, X } from 'lucide-react'
import { useChecklistsStore } from '@/stores/checklists-store'
import { useAuthStore } from '@/stores/auth-store'
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
  const token = useAuthStore((state) => state.token)
  const [isAdding, setIsAdding] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const {
    checklists,
    isLoading,
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
    handleChecklistUpdated,
    handleChecklistDeleted,
    handleChecklistsReordered,
    handleItemToggled,
    handleItemAdded,
    handleItemUpdated,
    handleItemDeleted,
    handleItemsReordered,
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

  // Subscribe to WebSocket events for real-time updates
  useEffect(() => {
    if (!taskId) return

    const roomId = `task:${taskId}`

    // Join the room for this task
    wsClient.joinRoom(roomId)

    // Handle checklist created event
    const onChecklistCreated = (data: { d?: { id: string; tid: string; title: string } }) => {
      if (data.d?.tid === taskId) {
        // Fetch fresh data since the WebSocket only sends minimal data
        fetchChecklists(token, taskId)
      }
    }

    // Handle checklist updated event
    const onChecklistUpdated = (data: { d?: { id: string; title: string } }) => {
      if (data.d?.id) {
        handleChecklistUpdated(data.d.id, data.d.title)
      }
    }

    // Handle checklist deleted event
    const onChecklistDeleted = (data: { d?: { id: string } }) => {
      if (data.d?.id) {
        handleChecklistDeleted(data.d.id)
      }
    }

    // Handle item toggled event
    const onItemToggled = (data: { d?: { id: string; clid: string; done: boolean } }) => {
      if (data.d?.clid && data.d?.id) {
        handleItemToggled(data.d.clid, data.d.id, data.d.done)
      }
    }

    // Handle item added event - refetch to get full item data
    const onItemAdded = (data: { d?: { clid: string } }) => {
      if (data.d?.clid) {
        // Refetch to get full item data
        fetchChecklists(token, taskId)
      }
    }

    // Handle item updated event
    const onItemUpdated = (data: { d?: { id: string; content: string } }) => {
      if (data.d?.id) {
        handleItemUpdated(data.d.id, data.d.content)
      }
    }

    // Handle item deleted event
    const onItemDeleted = (data: { d?: { id: string; clid: string } }) => {
      if (data.d?.clid && data.d?.id) {
        handleItemDeleted(data.d.clid, data.d.id)
      }
    }

    // Handle checklists reordered event
    const onChecklistsReordered = (data: { d?: { ids: string[] } }) => {
      if (data.d?.ids) {
        handleChecklistsReordered(data.d.ids)
      }
    }

    // Handle items reordered event
    const onItemsReordered = (data: { d?: { clid: string; ids: string[] } }) => {
      if (data.d?.clid && data.d?.ids) {
        handleItemsReordered(data.d.clid, data.d.ids)
      }
    }

    // Subscribe to events
    wsClient.on(MessageType.CHECKLIST_CREATED, onChecklistCreated)
    wsClient.on(MessageType.CHECKLIST_UPDATED, onChecklistUpdated)
    wsClient.on(MessageType.CHECKLIST_DELETED, onChecklistDeleted)
    wsClient.on(MessageType.CHECKLISTS_REORDERED, onChecklistsReordered)
    wsClient.on(MessageType.CHECKLIST_ITEM_TOGGLED, onItemToggled)
    wsClient.on(MessageType.CHECKLIST_ITEM_ADDED, onItemAdded)
    wsClient.on(MessageType.CHECKLIST_ITEM_UPDATED, onItemUpdated)
    wsClient.on(MessageType.CHECKLIST_ITEM_DELETED, onItemDeleted)
    wsClient.on(MessageType.CHECKLIST_ITEMS_REORDERED, onItemsReordered)

    // Cleanup: leave room and unsubscribe
    return () => {
      wsClient.leaveRoom(roomId)
      wsClient.off(MessageType.CHECKLIST_CREATED, onChecklistCreated)
      wsClient.off(MessageType.CHECKLIST_UPDATED, onChecklistUpdated)
      wsClient.off(MessageType.CHECKLIST_DELETED, onChecklistDeleted)
      wsClient.off(MessageType.CHECKLISTS_REORDERED, onChecklistsReordered)
      wsClient.off(MessageType.CHECKLIST_ITEM_TOGGLED, onItemToggled)
      wsClient.off(MessageType.CHECKLIST_ITEM_ADDED, onItemAdded)
      wsClient.off(MessageType.CHECKLIST_ITEM_UPDATED, onItemUpdated)
      wsClient.off(MessageType.CHECKLIST_ITEM_DELETED, onItemDeleted)
      wsClient.off(MessageType.CHECKLIST_ITEMS_REORDERED, onItemsReordered)
    }
  }, [taskId, token, fetchChecklists, handleChecklistUpdated, handleChecklistDeleted, handleChecklistsReordered, handleItemToggled, handleItemAdded, handleItemUpdated, handleItemDeleted, handleItemsReordered])

  // Get progress
  const progress = getProgress()

  // Handlers
  const handleCreateChecklist = useCallback(async () => {
    const trimmed = newTitle.trim()
    if (!trimmed) return

    // Clear form immediately since we use optimistic updates
    setNewTitle('')
    setIsAdding(false)

    // Create checklist (appears instantly via optimistic update)
    await createChecklist(token, taskId, { title: trimmed })
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
    async (itemId: string, content: string) => {
      await updateItem(token, itemId, content)
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
    async (checklistId: string, content: string) => {
      await createItem(token, checklistId, { content })
    },
    [token, createItem]
  )

  const handleItemReorder = useCallback(
    async (checklistId: string, itemIds: string[]) => {
      await reorderItems(token, checklistId, itemIds)
    },
    [token, reorderItems]
  )

  // Checklists are already sorted by rank from the store
  const sortedChecklists = checklists

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
        {sortedChecklists.length === 0 && !isAdding && (
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
        {sortedChecklists.map((checklist) => (
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
          canEdit && sortedChecklists.length > 0 && (
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
