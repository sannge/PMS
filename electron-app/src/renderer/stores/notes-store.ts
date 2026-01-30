/**
 * Notes Store (Re-export)
 *
 * This file re-exports from the notes-context for backward compatibility.
 * The actual implementation has been migrated from Zustand to React Context.
 */

export {
  NotesProvider,
  useNotesStore,
  selectNotes,
  selectNoteTree,
  selectSelectedNote,
  selectOpenTabs,
  selectActiveTabId,
  selectActiveTab,
  selectIsLoading,
  selectError,
  type Note,
  type NoteTree,
  type NoteCreate,
  type NoteUpdate,
  type NoteTab,
  type NoteError,
} from '../contexts/notes-context'

// Re-export useNotesStore as default for backward compatibility
import { useNotesStore as _useNotesStore } from '../contexts/notes-context'
export default _useNotesStore
