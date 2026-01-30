/**
 * ChecklistItem Component
 *
 * A single checklist item with checkbox, text, and actions.
 * Features:
 * - Checkbox toggle with animation
 * - Inline text editing
 * - Delete action on hover
 * - Drag handle for reordering
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import { cn } from '@/lib/utils'
import { Check, X, Trash2, GripVertical } from 'lucide-react'
import type { ChecklistItem as ChecklistItemType } from '@/hooks/use-checklists'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'

// ============================================================================
// Types
// ============================================================================

export interface ChecklistItemProps {
  item: ChecklistItemType
  onToggle?: (itemId: string) => void
  onUpdate?: (itemId: string, content: string) => void
  onDelete?: (itemId: string) => void
  disabled?: boolean
  showDragHandle?: boolean
  dragListeners?: Record<string, unknown>
  className?: string
}

// ============================================================================
// Component
// ============================================================================

export function ChecklistItem({
  item,
  onToggle,
  onUpdate,
  onDelete,
  disabled = false,
  showDragHandle = false,
  dragListeners,
  className,
}: ChecklistItemProps): JSX.Element {
  const [isEditing, setIsEditing] = useState(false)
  const [editText, setEditText] = useState(item?.content || '')
  const [isHovered, setIsHovered] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  // Focus input when entering edit mode
  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus()
      inputRef.current.select()
    }
  }, [isEditing])

  const handleToggle = useCallback(() => {
    if (!disabled && onToggle && item?.id) {
      onToggle(item.id)
    }
  }, [item?.id, disabled, onToggle])

  const handleStartEdit = useCallback(() => {
    if (!disabled && onUpdate) {
      setEditText(item?.content || '')
      setIsEditing(true)
    }
  }, [disabled, onUpdate, item?.content])

  const handleSaveEdit = useCallback(() => {
    const trimmed = editText.trim()
    if (trimmed && trimmed !== item?.content && onUpdate) {
      onUpdate(item.id, trimmed)
    }
    setIsEditing(false)
  }, [item?.id, item?.content, editText, onUpdate])

  const handleCancelEdit = useCallback(() => {
    setEditText(item?.content || '')
    setIsEditing(false)
  }, [item?.content])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') {
        e.preventDefault()
        handleSaveEdit()
      } else if (e.key === 'Escape') {
        handleCancelEdit()
      }
    },
    [handleSaveEdit, handleCancelEdit]
  )

  const handleDeleteClick = useCallback(() => {
    if (!disabled && onDelete) {
      setShowDeleteConfirm(true)
    }
  }, [disabled, onDelete])

  const handleConfirmDelete = useCallback(() => {
    if (onDelete && item?.id) {
      onDelete(item.id)
    }
    setShowDeleteConfirm(false)
  }, [item?.id, onDelete])

  // Guard against undefined item (can happen during optimistic updates)
  if (!item || !item.id) {
    return <div className="h-8" /> // Placeholder during loading
  }

  return (
    <div
      className={cn(
        'group flex items-center gap-2 py-1.5 px-1 rounded-md',
        'transition-colors duration-100',
        !disabled && 'hover:bg-muted/30',
        className
      )}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Drag Handle */}
      {showDragHandle && (
        <div
          className={cn(
            'flex-shrink-0 cursor-grab active:cursor-grabbing',
            'text-muted-foreground/40 hover:text-muted-foreground',
            'transition-colors touch-none'
          )}
          {...dragListeners}
        >
          <GripVertical className="h-4 w-4" />
        </div>
      )}

      {/* Checkbox */}
      <button
        onClick={handleToggle}
        disabled={disabled}
        className={cn(
          'flex-shrink-0 flex h-4 w-4 items-center justify-center rounded border',
          'transition-all duration-150',
          item.is_done
            ? 'bg-primary border-primary text-primary-foreground'
            : 'border-border hover:border-primary/50',
          disabled && 'opacity-50 cursor-not-allowed'
        )}
        aria-checked={item.is_done}
        role="checkbox"
      >
        {item.is_done && <Check className="h-3 w-3" />}
      </button>

      {/* Text / Edit Input */}
      {isEditing ? (
        <div className="flex-1 flex items-center gap-1">
          <input
            ref={inputRef}
            type="text"
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
            onKeyDown={handleKeyDown}
            onBlur={handleSaveEdit}
            className={cn(
              'flex-1 px-1 py-0.5 rounded',
              'bg-background border border-border',
              'text-sm text-foreground',
              'focus:outline-none focus:ring-1 focus:ring-ring'
            )}
            disabled={disabled}
          />
          <button
            onClick={handleSaveEdit}
            disabled={!editText.trim()}
            className={cn(
              'p-1 rounded text-primary hover:bg-primary/10',
              'disabled:opacity-50 disabled:cursor-not-allowed'
            )}
          >
            <Check className="h-3 w-3" />
          </button>
          <button
            onClick={handleCancelEdit}
            className="p-1 rounded text-muted-foreground hover:bg-muted"
          >
            <X className="h-3 w-3" />
          </button>
        </div>
      ) : (
        <span
          onClick={handleStartEdit}
          className={cn(
            'flex-1 text-sm cursor-text min-w-0',
            'transition-all duration-150',
            item.is_done
              ? 'text-muted-foreground line-through'
              : 'text-foreground'
          )}
        >
          {item.content || ''}
        </span>
      )}

      {/* Delete button */}
      {!isEditing && onDelete && (
        <button
          onClick={handleDeleteClick}
          disabled={disabled}
          className={cn(
            'flex-shrink-0 p-1 rounded',
            'text-muted-foreground hover:text-destructive hover:bg-destructive/10',
            'transition-all duration-100',
            isHovered ? 'opacity-100' : 'opacity-0',
            disabled && 'opacity-50 cursor-not-allowed'
          )}
        >
          <Trash2 className="h-3 w-3" />
        </button>
      )}

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        open={showDeleteConfirm}
        onOpenChange={setShowDeleteConfirm}
        title="Delete item?"
        description={`Are you sure you want to delete "${(item.content || '').substring(0, 50)}${(item.content || '').length > 50 ? '...' : ''}"?`}
        confirmLabel="Delete"
        variant="destructive"
        onConfirm={handleConfirmDelete}
      />
    </div>
  )
}

export default ChecklistItem
