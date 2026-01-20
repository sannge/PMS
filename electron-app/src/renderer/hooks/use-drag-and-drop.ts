/**
 * useDragAndDrop Hook
 *
 * Encapsulates @dnd-kit drag-and-drop logic for Kanban task boards.
 * Handles:
 * - Cross-column task movement
 * - Within-column task reordering
 * - Collision detection and sensors
 * - Accessibility (keyboard navigation)
 *
 * @example
 * ```tsx
 * const { sensors, activeTask, handleDragStart, handleDragEnd, handleDragOver } = useDragAndDrop({
 *   tasks,
 *   onTaskMove: async (taskId, targetStatus, beforeTaskId, afterTaskId) => {
 *     await moveTask(token, taskId, { target_status: targetStatus })
 *   },
 * })
 * ```
 */

import { useState, useCallback } from 'react'
import {
  DragStartEvent,
  DragEndEvent,
  DragOverEvent,
  UniqueIdentifier,
  useSensor,
  useSensors,
  PointerSensor,
  KeyboardSensor,
  TouchSensor,
} from '@dnd-kit/core'
import { sortableKeyboardCoordinates } from '@dnd-kit/sortable'
import type { Task, TaskStatus } from '@/stores/tasks-store'

// ============================================================================
// Types
// ============================================================================

export interface UseDragAndDropOptions {
  /**
   * All tasks in the board
   */
  tasks: Task[]
  /**
   * Callback when a task is moved
   * @param taskId - The task being moved
   * @param targetStatus - The target column status
   * @param beforeTaskId - Task ID to place after (null for first position)
   * @param afterTaskId - Task ID to place before (null for last position)
   */
  onTaskMove: (
    taskId: string,
    targetStatus: TaskStatus,
    beforeTaskId: string | null,
    afterTaskId: string | null
  ) => Promise<boolean>
  /**
   * Whether drag operations are disabled
   */
  disabled?: boolean
}

export interface UseDragAndDropReturn {
  /**
   * DnD-kit sensors configuration
   */
  sensors: ReturnType<typeof useSensors>
  /**
   * Currently dragging task (null when not dragging)
   */
  activeTask: Task | null
  /**
   * Active task ID (for overlay)
   */
  activeId: UniqueIdentifier | null
  /**
   * Column ID being hovered during drag
   */
  overColumnId: TaskStatus | null
  /**
   * Handler for drag start
   */
  handleDragStart: (event: DragStartEvent) => void
  /**
   * Handler for drag end (performs actual move)
   */
  handleDragEnd: (event: DragEndEvent) => void
  /**
   * Handler for drag over (tracks hover state)
   */
  handleDragOver: (event: DragOverEvent) => void
  /**
   * Handler for drag cancel
   */
  handleDragCancel: () => void
  /**
   * Whether a drag operation is in progress
   */
  isDragging: boolean
}

// ============================================================================
// Utilities
// ============================================================================

/**
 * Extract status from a sortable ID
 * IDs are formatted as "task-{taskId}" for tasks and "{status}" for columns
 */
export function getStatusFromId(id: UniqueIdentifier): TaskStatus | null {
  const strId = String(id)
  const validStatuses: TaskStatus[] = [
    'todo',
    'in_progress',
    'in_review',
    'issue',
    'done',
  ]
  if (validStatuses.includes(strId as TaskStatus)) {
    return strId as TaskStatus
  }
  return null
}

/**
 * Extract task ID from a sortable ID
 * Task IDs are formatted as "task-{taskId}"
 */
export function getTaskIdFromSortableId(
  id: UniqueIdentifier
): string | null {
  const strId = String(id)
  if (strId.startsWith('task-')) {
    return strId.replace('task-', '')
  }
  return null
}

/**
 * Create a sortable ID for a task
 */
export function createSortableId(taskId: string): string {
  return `task-${taskId}`
}

/**
 * Find a task by its sortable ID
 */
export function findTaskBySortableId(
  tasks: Task[],
  sortableId: UniqueIdentifier
): Task | null {
  const taskId = getTaskIdFromSortableId(sortableId)
  if (!taskId) return null
  return tasks.find((t) => t.id === taskId) || null
}

/**
 * Find neighboring tasks for positioning
 */
export function findNeighboringTasks(
  tasks: Task[],
  taskId: string,
  targetStatus: TaskStatus,
  overIndex: number
): { beforeTaskId: string | null; afterTaskId: string | null } {
  // Get tasks in the target column, sorted by rank
  const columnTasks = tasks
    .filter((t) => t.status === targetStatus && t.id !== taskId)
    .sort((a, b) => {
      if (!a.task_rank && !b.task_rank) return 0
      if (!a.task_rank) return 1
      if (!b.task_rank) return -1
      return a.task_rank.localeCompare(b.task_rank)
    })

  // If placing at the beginning
  if (overIndex <= 0 || columnTasks.length === 0) {
    return {
      beforeTaskId: null,
      afterTaskId: columnTasks[0]?.id || null,
    }
  }

  // If placing at the end
  if (overIndex >= columnTasks.length) {
    return {
      beforeTaskId: columnTasks[columnTasks.length - 1]?.id || null,
      afterTaskId: null,
    }
  }

  // Placing in the middle
  return {
    beforeTaskId: columnTasks[overIndex - 1]?.id || null,
    afterTaskId: columnTasks[overIndex]?.id || null,
  }
}

// ============================================================================
// Hook Implementation
// ============================================================================

export function useDragAndDrop({
  tasks,
  onTaskMove,
  disabled = false,
}: UseDragAndDropOptions): UseDragAndDropReturn {
  // Active drag state
  const [activeId, setActiveId] = useState<UniqueIdentifier | null>(null)
  const [overColumnId, setOverColumnId] = useState<TaskStatus | null>(null)

  // Configure sensors for different input methods
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        // Require 5px movement before starting drag (prevents accidental drags)
        distance: 5,
      },
    }),
    useSensor(TouchSensor, {
      activationConstraint: {
        delay: 250, // 250ms press delay for touch devices
        tolerance: 5,
      },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  )

  // Get the currently dragging task
  const activeTask = activeId ? findTaskBySortableId(tasks, activeId) : null

  // Handle drag start
  const handleDragStart = useCallback(
    (event: DragStartEvent) => {
      if (disabled) return

      const { active } = event
      setActiveId(active.id)

      // Set initial over column to current task's status
      const task = findTaskBySortableId(tasks, active.id)
      if (task) {
        setOverColumnId(task.status)
      }
    },
    [disabled, tasks]
  )

  // Handle drag over (track which column we're hovering)
  const handleDragOver = useCallback(
    (event: DragOverEvent) => {
      if (disabled) return

      const { over } = event
      if (!over) {
        setOverColumnId(null)
        return
      }

      // Check if hovering over a column directly
      const columnStatus = getStatusFromId(over.id)
      if (columnStatus) {
        setOverColumnId(columnStatus)
        return
      }

      // Check if hovering over a task (get its column)
      const overTask = findTaskBySortableId(tasks, over.id)
      if (overTask) {
        setOverColumnId(overTask.status)
      }
    },
    [disabled, tasks]
  )

  // Handle drag end (perform the actual move)
  const handleDragEnd = useCallback(
    async (event: DragEndEvent) => {
      const { active, over } = event

      // Reset state
      setActiveId(null)
      setOverColumnId(null)

      if (disabled || !over) {
        return
      }

      const taskId = getTaskIdFromSortableId(active.id)
      if (!taskId) {
        return
      }

      const task = tasks.find((t) => t.id === taskId)
      if (!task) {
        return
      }

      // Determine target status
      let targetStatus: TaskStatus | null = getStatusFromId(over.id)

      // If dropped on a task, get that task's status
      if (!targetStatus) {
        const overTask = findTaskBySortableId(tasks, over.id)
        if (overTask) {
          targetStatus = overTask.status
        }
      }

      if (!targetStatus) return

      // Find the position within the column
      const columnTasks = tasks
        .filter((t) => t.status === targetStatus && t.id !== taskId)
        .sort((a, b) => {
          if (!a.task_rank && !b.task_rank) return 0
          if (!a.task_rank) return 1
          if (!b.task_rank) return -1
          return a.task_rank.localeCompare(b.task_rank)
        })

      // Find the index where task should be placed
      let overIndex = columnTasks.length // Default to end

      const overTaskId = getTaskIdFromSortableId(over.id)
      if (overTaskId) {
        const overTaskIndex = columnTasks.findIndex((t) => t.id === overTaskId)
        if (overTaskIndex !== -1) {
          overIndex = overTaskIndex
        }
      }

      // Get neighboring tasks for positioning
      const { beforeTaskId, afterTaskId } = findNeighboringTasks(
        tasks,
        taskId,
        targetStatus,
        overIndex
      )

      // Skip if no change
      if (
        task.status === targetStatus &&
        beforeTaskId === null &&
        afterTaskId === columnTasks[0]?.id
      ) {
        // Trying to move to same position
        return
      }

      // Perform the move
      await onTaskMove(taskId, targetStatus, beforeTaskId, afterTaskId)
    },
    [disabled, tasks, onTaskMove]
  )

  // Handle drag cancel
  const handleDragCancel = useCallback(() => {
    setActiveId(null)
    setOverColumnId(null)
  }, [])

  return {
    sensors,
    activeTask,
    activeId,
    overColumnId,
    handleDragStart,
    handleDragEnd,
    handleDragOver,
    handleDragCancel,
    isDragging: activeId !== null,
  }
}

export default useDragAndDrop
