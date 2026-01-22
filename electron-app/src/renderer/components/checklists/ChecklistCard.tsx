/**
 * ChecklistCard Component
 *
 * A complete checklist with title, progress bar, items, and add item input.
 * Features:
 * - Collapsible card with progress indicator
 * - Title editing
 * - Item list with toggle/edit/delete
 * - Add item input
 * - Delete checklist
 * - Drag-and-drop reordering
 */

import { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import { cn } from '@/lib/utils'
import {
  CheckSquare,
  ChevronDown,
  ChevronRight,
  Edit2,
  Trash2,
  Plus,
  Check,
  X,
} from 'lucide-react'
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import type { Checklist, ChecklistItem as ChecklistItemType } from '@/stores/checklists-store'
import { ChecklistItem } from './ChecklistItem'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'

// ============================================================================
// Types
// ============================================================================

export interface ChecklistCardProps {
  checklist: Checklist
  onTitleUpdate?: (checklistId: string, title: string) => void
  onDelete?: (checklistId: string) => void
  onItemToggle?: (itemId: string) => void
  onItemUpdate?: (itemId: string, content: string) => void
  onItemDelete?: (itemId: string) => void
  onItemCreate?: (checklistId: string, content: string) => void
  onItemReorder?: (checklistId: string, itemIds: string[]) => void
  disabled?: boolean
  defaultExpanded?: boolean
  className?: string
}

// ============================================================================
// Sortable Item Wrapper
// ============================================================================

interface SortableItemProps {
  item: ChecklistItemType
  onToggle?: (itemId: string) => void
  onUpdate?: (itemId: string, content: string) => void
  onDelete?: (itemId: string) => void
  disabled?: boolean
}

function SortableChecklistItem({
  item,
  onToggle,
  onUpdate,
  onDelete,
  disabled,
  canReorder = true,
}: SortableItemProps & { canReorder?: boolean }): JSX.Element {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: item.id, disabled: !canReorder })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  }

  return (
    <div ref={setNodeRef} style={style} {...attributes}>
      <ChecklistItem
        item={item}
        onToggle={onToggle}
        onUpdate={onUpdate}
        onDelete={onDelete}
        disabled={disabled}
        showDragHandle={canReorder}
        dragListeners={canReorder ? listeners : undefined}
      />
    </div>
  )
}

// ============================================================================
// Component
// ============================================================================

export function ChecklistCard({
  checklist,
  onTitleUpdate,
  onDelete,
  onItemToggle,
  onItemUpdate,
  onItemDelete,
  onItemCreate,
  onItemReorder,
  disabled = false,
  defaultExpanded = true,
  className,
}: ChecklistCardProps): JSX.Element {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded)
  const [isEditingTitle, setIsEditingTitle] = useState(false)
  const [editTitle, setEditTitle] = useState(checklist.title)
  const [newItemText, setNewItemText] = useState('')
  const [isAddingItem, setIsAddingItem] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

  const titleInputRef = useRef<HTMLInputElement>(null)
  const addItemInputRef = useRef<HTMLInputElement>(null)

  // DnD sensors
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 8 },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  )

  // Use progress from server (or calculate if needed)
  const progress = checklist.progress_percent ?? (
    checklist.total_items > 0
      ? Math.round((checklist.completed_items / checklist.total_items) * 100)
      : 0
  )

  // Focus title input when editing
  useEffect(() => {
    if (isEditingTitle && titleInputRef.current) {
      titleInputRef.current.focus()
      titleInputRef.current.select()
    }
  }, [isEditingTitle])

  // Focus add item input
  useEffect(() => {
    if (isAddingItem && addItemInputRef.current) {
      addItemInputRef.current.focus()
    }
  }, [isAddingItem])

  // Title editing
  const handleStartEditTitle = useCallback(() => {
    if (!disabled && onTitleUpdate) {
      setEditTitle(checklist.title)
      setIsEditingTitle(true)
    }
  }, [disabled, onTitleUpdate, checklist.title])

  const handleSaveTitle = useCallback(() => {
    const trimmed = editTitle.trim()
    if (trimmed && trimmed !== checklist.title && onTitleUpdate) {
      onTitleUpdate(checklist.id, trimmed)
    }
    setIsEditingTitle(false)
  }, [checklist.id, checklist.title, editTitle, onTitleUpdate])

  const handleCancelTitle = useCallback(() => {
    setEditTitle(checklist.title)
    setIsEditingTitle(false)
  }, [checklist.title])

  // Add item
  const handleAddItem = useCallback(() => {
    const trimmed = newItemText.trim()
    if (trimmed && onItemCreate) {
      onItemCreate(checklist.id, trimmed)
      setNewItemText('')
    }
  }, [checklist.id, newItemText, onItemCreate])

  const handleDeleteClick = useCallback(() => {
    if (onDelete) {
      setShowDeleteConfirm(true)
    }
  }, [onDelete])

  const handleConfirmDelete = useCallback(() => {
    if (onDelete) {
      onDelete(checklist.id)
    }
    setShowDeleteConfirm(false)
  }, [checklist.id, onDelete])

  // Items are already in correct order from the store (after reordering)
  // We only sort by rank on initial load, the store maintains order after that
  const sortedItems = useMemo(
    () => [...checklist.items],
    [checklist.items]
  )

  // Item IDs for sortable context
  const itemIds = useMemo(() => sortedItems.map((item) => item.id), [sortedItems])

  // Handle drag end for reordering
  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event

      if (over && active.id !== over.id) {
        const oldIndex = sortedItems.findIndex((item) => item.id === active.id)
        const newIndex = sortedItems.findIndex((item) => item.id === over.id)

        if (oldIndex !== -1 && newIndex !== -1) {
          const newOrder = arrayMove(sortedItems, oldIndex, newIndex)
          const newItemIds = newOrder.map((item: ChecklistItemType) => item.id)
          onItemReorder?.(checklist.id, newItemIds)
        }
      }
    },
    [checklist.id, sortedItems, onItemReorder]
  )

  return (
    <div
      className={cn(
        'rounded-lg border border-border bg-card',
        'transition-shadow duration-150',
        'hover:shadow-sm',
        className
      )}
    >
      {/* Header */}
      <div className="flex items-center gap-2 p-3 border-b border-border/50">
        {/* Expand toggle */}
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className={cn(
            'flex-shrink-0 p-0.5 rounded',
            'text-muted-foreground hover:text-foreground hover:bg-muted',
            'transition-colors'
          )}
        >
          {isExpanded ? (
            <ChevronDown className="h-4 w-4" />
          ) : (
            <ChevronRight className="h-4 w-4" />
          )}
        </button>

        {/* Icon */}
        <CheckSquare className="h-4 w-4 flex-shrink-0 text-primary" />

        {/* Title */}
        {isEditingTitle ? (
          <div className="flex-1 flex items-center gap-1">
            <input
              ref={titleInputRef}
              type="text"
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSaveTitle()
                if (e.key === 'Escape') handleCancelTitle()
              }}
              onBlur={handleSaveTitle}
              className={cn(
                'flex-1 px-2 py-1 rounded',
                'bg-background border border-border',
                'text-sm font-medium text-foreground',
                'focus:outline-none focus:ring-1 focus:ring-ring'
              )}
            />
            <button onClick={handleSaveTitle} className="p-1 rounded text-primary hover:bg-primary/10">
              <Check className="h-3 w-3" />
            </button>
            <button onClick={handleCancelTitle} className="p-1 rounded text-muted-foreground hover:bg-muted">
              <X className="h-3 w-3" />
            </button>
          </div>
        ) : (
          <span
            onClick={handleStartEditTitle}
            className={cn(
              'flex-1 text-sm font-medium text-foreground',
              onTitleUpdate && 'cursor-pointer hover:text-primary'
            )}
          >
            {checklist.title}
          </span>
        )}

        {/* Progress */}
        <span className="flex-shrink-0 text-xs text-muted-foreground tabular-nums">
          {checklist.completed_items}/{checklist.total_items}
        </span>

        {/* Actions */}
        {!isEditingTitle && (
          <div className="flex items-center gap-1">
            {onTitleUpdate && (
              <button
                onClick={handleStartEditTitle}
                disabled={disabled}
                className={cn(
                  'p-1 rounded text-muted-foreground',
                  'hover:text-foreground hover:bg-muted',
                  'transition-colors',
                  disabled && 'opacity-50 cursor-not-allowed'
                )}
              >
                <Edit2 className="h-3 w-3" />
              </button>
            )}
            {onDelete && (
              <button
                onClick={handleDeleteClick}
                disabled={disabled}
                className={cn(
                  'p-1 rounded text-muted-foreground',
                  'hover:text-destructive hover:bg-destructive/10',
                  'transition-colors',
                  disabled && 'opacity-50 cursor-not-allowed'
                )}
              >
                <Trash2 className="h-3 w-3" />
              </button>
            )}
          </div>
        )}
      </div>

      {/* Progress bar */}
      <div className="h-1 bg-muted">
        <div
          className={cn(
            'h-full transition-all duration-300',
            progress === 100 ? 'bg-green-500' : 'bg-primary'
          )}
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Content */}
      {isExpanded && (
        <div className="p-2">
          {/* Items with drag-and-drop */}
          {sortedItems.length > 0 && (
            <DndContext
              sensors={sensors}
              collisionDetection={closestCenter}
              onDragEnd={handleDragEnd}
            >
              <SortableContext items={itemIds} strategy={verticalListSortingStrategy}>
                <div className="space-y-0.5 mb-2">
                  {sortedItems.map((item) => (
                    <SortableChecklistItem
                      key={item.id}
                      item={item}
                      onToggle={onItemToggle}
                      onUpdate={onItemUpdate}
                      onDelete={onItemDelete}
                      disabled={disabled}
                      canReorder={!!onItemReorder}
                    />
                  ))}
                </div>
              </SortableContext>
            </DndContext>
          )}

          {/* Add item */}
          {onItemCreate && (
            <div className="mt-2">
              {isAddingItem ? (
                <div className="flex items-center gap-2">
                  <input
                    ref={addItemInputRef}
                    type="text"
                    value={newItemText}
                    onChange={(e) => setNewItemText(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        handleAddItem()
                      }
                      if (e.key === 'Escape') {
                        setIsAddingItem(false)
                        setNewItemText('')
                      }
                    }}
                    placeholder="Add an item..."
                    className={cn(
                      'flex-1 px-2 py-1.5 rounded',
                      'bg-background border border-border',
                      'text-sm text-foreground',
                      'placeholder:text-muted-foreground',
                      'focus:outline-none focus:ring-1 focus:ring-ring'
                    )}
                    disabled={disabled}
                  />
                  <button
                    onClick={handleAddItem}
                    disabled={!newItemText.trim() || disabled}
                    className={cn(
                      'px-2 py-1.5 rounded',
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
                      setIsAddingItem(false)
                      setNewItemText('')
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
                <button
                  onClick={() => setIsAddingItem(true)}
                  disabled={disabled}
                  className={cn(
                    'flex items-center gap-1.5 px-2 py-1.5 w-full rounded',
                    'text-xs text-muted-foreground',
                    'hover:bg-muted hover:text-foreground',
                    'transition-colors',
                    disabled && 'opacity-50 cursor-not-allowed'
                  )}
                >
                  <Plus className="h-3 w-3" />
                  Add an item
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        open={showDeleteConfirm}
        onOpenChange={setShowDeleteConfirm}
        title="Delete checklist?"
        description={`Are you sure you want to delete "${checklist.title}"? This will also delete all ${checklist.total_items} item${checklist.total_items !== 1 ? 's' : ''} in this checklist.`}
        confirmLabel="Delete"
        variant="destructive"
        onConfirm={handleConfirmDelete}
      />
    </div>
  )
}

export default ChecklistCard
