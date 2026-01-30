/**
 * Notes Context Tests
 *
 * Tests for notes context provider and hooks.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { ReactNode } from 'react'
import {
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
} from '../contexts/notes-context'

// Wrapper component for hooks
function wrapper({ children }: { children: ReactNode }) {
  return <NotesProvider>{children}</NotesProvider>
}

// Mock note data
const mockNote: Note = {
  id: 'note-1',
  title: 'Test Note',
  content: 'Test content',
  tab_order: 0,
  application_id: 'app-1',
  parent_id: null,
  created_by: 'user-1',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
  children_count: 0,
}

const mockNote2: Note = {
  id: 'note-2',
  title: 'Test Note 2',
  content: 'Test content 2',
  tab_order: 1,
  application_id: 'app-1',
  parent_id: null,
  created_by: 'user-1',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
  children_count: 0,
}

describe('Notes Context', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('useNotesStore', () => {
    it('returns initial state', () => {
      const { result } = renderHook(() => useNotesStore(), { wrapper })

      expect(result.current.notes).toEqual([])
      expect(result.current.noteTree).toEqual([])
      expect(result.current.selectedNote).toBeNull()
      expect(result.current.openTabs).toEqual([])
      expect(result.current.activeTabId).toBeNull()
      expect(result.current.isLoading).toBe(false)
      expect(result.current.error).toBeNull()
    })

    it('throws error when used outside provider', () => {
      expect(() => {
        renderHook(() => useNotesStore())
      }).toThrow('useNotesStore must be used within a NotesProvider')
    })

    it('works with selector', () => {
      const { result } = renderHook(() => useNotesStore(selectNotes), { wrapper })
      expect(result.current).toEqual([])
    })
  })

  describe('fetchNotes', () => {
    it('fetches notes successfully', async () => {
      const mockNotes = [mockNote, mockNote2]

      ;(window.electronAPI.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        status: 200,
        data: mockNotes,
      })

      const { result } = renderHook(() => useNotesStore(), { wrapper })

      await act(async () => {
        await result.current.fetchNotes('token', 'app-1')
      })

      expect(result.current.notes).toEqual(mockNotes)
      expect(result.current.isLoading).toBe(false)
      expect(result.current.currentApplicationId).toBe('app-1')
    })

    it('handles fetch error', async () => {
      ;(window.electronAPI.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        status: 500,
        data: { detail: 'Server error' },
      })

      const { result } = renderHook(() => useNotesStore(), { wrapper })

      await act(async () => {
        await result.current.fetchNotes('token', 'app-1')
      })

      expect(result.current.error?.message).toBe('Server error')
      expect(result.current.isLoading).toBe(false)
    })
  })

  describe('fetchNoteTree', () => {
    it('fetches note tree successfully', async () => {
      const mockTree = [{ ...mockNote, children: [] }]

      ;(window.electronAPI.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        status: 200,
        data: mockTree,
      })

      const { result } = renderHook(() => useNotesStore(), { wrapper })

      await act(async () => {
        await result.current.fetchNoteTree('token', 'app-1')
      })

      expect(result.current.noteTree).toEqual(mockTree)
    })
  })

  describe('createNote', () => {
    it('creates note successfully', async () => {
      ;(window.electronAPI.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        status: 201,
        data: mockNote,
      })
      ;(window.electronAPI.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        status: 200,
        data: [],
      })

      const { result } = renderHook(() => useNotesStore(), { wrapper })

      let createdNote: Note | null
      await act(async () => {
        createdNote = await result.current.createNote('token', 'app-1', {
          title: 'Test Note',
          content: 'Test content',
        })
      })

      expect(createdNote!).toEqual(mockNote)
      expect(result.current.notes).toContainEqual(mockNote)
    })

    it('handles create error', async () => {
      ;(window.electronAPI.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        status: 400,
        data: { detail: 'Invalid data' },
      })

      const { result } = renderHook(() => useNotesStore(), { wrapper })

      let createdNote: Note | null
      await act(async () => {
        createdNote = await result.current.createNote('token', 'app-1', {
          title: 'Test Note',
        })
      })

      expect(createdNote!).toBeNull()
      expect(result.current.error?.message).toBe('Invalid data')
    })
  })

  describe('updateNote', () => {
    it('updates note successfully', async () => {
      const updatedNote = { ...mockNote, title: 'Updated Title' }

      ;(window.electronAPI.put as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        status: 200,
        data: updatedNote,
      })
      ;(window.electronAPI.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        status: 200,
        data: [],
      })

      const { result } = renderHook(() => useNotesStore(), { wrapper })

      // First add the note to state
      act(() => {
        result.current.openTab(mockNote)
      })

      let updated: Note | null
      await act(async () => {
        updated = await result.current.updateNote('token', 'note-1', {
          title: 'Updated Title',
        })
      })

      expect(updated!).toEqual(updatedNote)
    })
  })

  describe('deleteNote', () => {
    it('deletes note successfully', async () => {
      ;(window.electronAPI.delete as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        status: 204,
        data: null,
      })
      ;(window.electronAPI.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
        status: 200,
        data: [],
      })

      const { result } = renderHook(() => useNotesStore(), { wrapper })

      let success: boolean
      await act(async () => {
        success = await result.current.deleteNote('token', 'note-1')
      })

      expect(success!).toBe(true)
    })
  })

  describe('Tab Management', () => {
    describe('openTab', () => {
      it('opens a new tab', () => {
        const { result } = renderHook(() => useNotesStore(), { wrapper })

        act(() => {
          result.current.openTab(mockNote)
        })

        expect(result.current.openTabs).toHaveLength(1)
        expect(result.current.openTabs[0].id).toBe(mockNote.id)
        expect(result.current.openTabs[0].title).toBe(mockNote.title)
        expect(result.current.activeTabId).toBe(mockNote.id)
      })

      it('does not duplicate existing tab', () => {
        const { result } = renderHook(() => useNotesStore(), { wrapper })

        act(() => {
          result.current.openTab(mockNote)
        })

        act(() => {
          result.current.openTab(mockNote)
        })

        expect(result.current.openTabs).toHaveLength(1)
      })

      it('opens multiple different tabs', () => {
        const { result } = renderHook(() => useNotesStore(), { wrapper })

        act(() => {
          result.current.openTab(mockNote)
        })

        act(() => {
          result.current.openTab(mockNote2)
        })

        expect(result.current.openTabs).toHaveLength(2)
        expect(result.current.activeTabId).toBe(mockNote2.id)
      })
    })

    describe('closeTab', () => {
      it('closes a tab', () => {
        const { result } = renderHook(() => useNotesStore(), { wrapper })

        act(() => {
          result.current.openTab(mockNote)
        })

        act(() => {
          result.current.closeTab(mockNote.id)
        })

        expect(result.current.openTabs).toHaveLength(0)
        expect(result.current.activeTabId).toBeNull()
      })

      it('switches to previous tab when closing active tab', () => {
        const { result } = renderHook(() => useNotesStore(), { wrapper })

        act(() => {
          result.current.openTab(mockNote)
        })

        act(() => {
          result.current.openTab(mockNote2)
        })

        act(() => {
          result.current.closeTab(mockNote2.id)
        })

        expect(result.current.openTabs).toHaveLength(1)
        expect(result.current.activeTabId).toBe(mockNote.id)
      })
    })

    describe('setActiveTab', () => {
      it('sets active tab', () => {
        const { result } = renderHook(() => useNotesStore(), { wrapper })

        act(() => {
          result.current.openTab(mockNote)
        })

        act(() => {
          result.current.openTab(mockNote2)
        })

        act(() => {
          result.current.setActiveTab(mockNote.id)
        })

        expect(result.current.activeTabId).toBe(mockNote.id)
      })
    })

    describe('updateTabContent', () => {
      it('updates tab content and marks as dirty', () => {
        const { result } = renderHook(() => useNotesStore(), { wrapper })

        act(() => {
          result.current.openTab(mockNote)
        })

        act(() => {
          result.current.updateTabContent(mockNote.id, 'New content')
        })

        expect(result.current.openTabs[0].content).toBe('New content')
        expect(result.current.openTabs[0].isDirty).toBe(true)
      })
    })

    describe('markTabDirty', () => {
      it('marks tab as dirty', () => {
        const { result } = renderHook(() => useNotesStore(), { wrapper })

        act(() => {
          result.current.openTab(mockNote)
        })

        act(() => {
          result.current.markTabDirty(mockNote.id, true)
        })

        expect(result.current.openTabs[0].isDirty).toBe(true)
      })

      it('marks tab as clean', () => {
        const { result } = renderHook(() => useNotesStore(), { wrapper })

        act(() => {
          result.current.openTab(mockNote)
        })

        act(() => {
          result.current.markTabDirty(mockNote.id, true)
        })

        act(() => {
          result.current.markTabDirty(mockNote.id, false)
        })

        expect(result.current.openTabs[0].isDirty).toBe(false)
      })
    })

    describe('closeAllTabs', () => {
      it('closes all tabs', () => {
        const { result } = renderHook(() => useNotesStore(), { wrapper })

        act(() => {
          result.current.openTab(mockNote)
        })

        act(() => {
          result.current.openTab(mockNote2)
        })

        act(() => {
          result.current.closeAllTabs()
        })

        expect(result.current.openTabs).toHaveLength(0)
        expect(result.current.activeTabId).toBeNull()
      })
    })

    describe('closeOtherTabs', () => {
      it('closes all tabs except specified one', () => {
        const { result } = renderHook(() => useNotesStore(), { wrapper })

        act(() => {
          result.current.openTab(mockNote)
        })

        act(() => {
          result.current.openTab(mockNote2)
        })

        act(() => {
          result.current.closeOtherTabs(mockNote.id)
        })

        expect(result.current.openTabs).toHaveLength(1)
        expect(result.current.openTabs[0].id).toBe(mockNote.id)
        expect(result.current.activeTabId).toBe(mockNote.id)
      })
    })
  })

  describe('selectNote', () => {
    it('selects a note', () => {
      const { result } = renderHook(() => useNotesStore(), { wrapper })

      act(() => {
        result.current.selectNote(mockNote)
      })

      expect(result.current.selectedNote).toEqual(mockNote)
    })

    it('clears selection', () => {
      const { result } = renderHook(() => useNotesStore(), { wrapper })

      act(() => {
        result.current.selectNote(mockNote)
      })

      act(() => {
        result.current.selectNote(null)
      })

      expect(result.current.selectedNote).toBeNull()
    })
  })

  describe('clearError', () => {
    it('clears error', async () => {
      // Reset and set up fresh mock for this test
      const getMock = window.electronAPI.get as ReturnType<typeof vi.fn>
      getMock.mockReset()
      getMock.mockResolvedValue({
        status: 500,
        data: { detail: 'Server error' },
      })

      const { result } = renderHook(() => useNotesStore(), { wrapper })

      await act(async () => {
        await result.current.fetchNotes('token', 'app-1')
      })

      expect(result.current.error).not.toBeNull()
      expect(result.current.error?.message).toBe('Server error')

      act(() => {
        result.current.clearError()
      })

      expect(result.current.error).toBeNull()
    })
  })

  describe('reset', () => {
    it('resets to initial state', () => {
      const { result } = renderHook(() => useNotesStore(), { wrapper })

      act(() => {
        result.current.openTab(mockNote)
        result.current.selectNote(mockNote)
      })

      expect(result.current.openTabs).toHaveLength(1)
      expect(result.current.selectedNote).not.toBeNull()

      act(() => {
        result.current.reset()
      })

      expect(result.current.notes).toEqual([])
      expect(result.current.noteTree).toEqual([])
      expect(result.current.selectedNote).toBeNull()
      expect(result.current.openTabs).toEqual([])
      expect(result.current.activeTabId).toBeNull()
    })
  })

  describe('selectors', () => {
    it('selectNotes returns notes', () => {
      const state = { notes: [mockNote] } as any
      expect(selectNotes(state)).toEqual([mockNote])
    })

    it('selectNoteTree returns note tree', () => {
      const tree = [{ ...mockNote, children: [] }]
      const state = { noteTree: tree } as any
      expect(selectNoteTree(state)).toEqual(tree)
    })

    it('selectSelectedNote returns selected note', () => {
      const state = { selectedNote: mockNote } as any
      expect(selectSelectedNote(state)).toEqual(mockNote)
    })

    it('selectOpenTabs returns open tabs', () => {
      const tabs = [{ id: 'note-1', title: 'Test', isDirty: false, content: null }]
      const state = { openTabs: tabs } as any
      expect(selectOpenTabs(state)).toEqual(tabs)
    })

    it('selectActiveTabId returns active tab id', () => {
      const state = { activeTabId: 'note-1' } as any
      expect(selectActiveTabId(state)).toBe('note-1')
    })

    it('selectActiveTab returns active tab', () => {
      const tabs = [
        { id: 'note-1', title: 'Test', isDirty: false, content: null },
        { id: 'note-2', title: 'Test 2', isDirty: false, content: null },
      ]
      const state = { openTabs: tabs, activeTabId: 'note-2' } as any
      expect(selectActiveTab(state)).toEqual(tabs[1])
    })

    it('selectIsLoading returns loading state', () => {
      const state = { isLoading: true } as any
      expect(selectIsLoading(state)).toBe(true)
    })

    it('selectError returns error', () => {
      const state = { error: { message: 'Error' } } as any
      expect(selectError(state)).toEqual({ message: 'Error' })
    })
  })
})
