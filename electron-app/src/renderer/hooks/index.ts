/**
 * Hooks
 *
 * Re-exports all custom hooks for easy imports.
 */

export { useAuth } from './use-auth'

export {
  useWebSocket,
  useTaskUpdates,
  type TaskUpdateEventData,
} from './use-websocket'

export {
  useDragAndDrop,
  findTaskBySortableId,
  type UseDragAndDropOptions,
  type UseDragAndDropReturn,
} from './use-drag-and-drop'

export {
  usePresence,
  type PresenceUser,
  type UsePresenceOptions,
  type UsePresenceReturn,
} from './use-presence'

export {
  useTaskViewers,
  type TaskViewer,
  type UseTaskViewersOptions,
  type UseTaskViewersReturn,
} from './use-task-viewers'
