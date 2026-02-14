/**
 * Notification UI Context Tests
 *
 * Tests for notification UI context provider and hooks.
 */

import { describe, it, expect } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { ReactNode } from 'react'
import {
  NotificationUIProvider,
  useNotificationUIStore,
} from '../contexts/notification-ui-context'

// Wrapper component for hooks
function wrapper({ children }: { children: ReactNode }) {
  return <NotificationUIProvider>{children}</NotificationUIProvider>
}

describe('Notification UI Context', () => {
  describe('useNotificationUIStore', () => {
    it('returns initial state with isOpen false', () => {
      const { result } = renderHook(() => useNotificationUIStore(), { wrapper })

      expect(result.current.isOpen).toBe(false)
    })

    it('throws error when used outside provider', () => {
      expect(() => {
        renderHook(() => useNotificationUIStore())
      }).toThrow('useNotificationUIStore must be used within a NotificationUIProvider')
    })

    it('works with selector', () => {
      const { result } = renderHook(
        () => useNotificationUIStore((state) => state.isOpen),
        { wrapper }
      )

      expect(result.current).toBe(false)
    })
  })

  describe('setOpen', () => {
    it('sets isOpen to true', () => {
      const { result } = renderHook(() => useNotificationUIStore(), { wrapper })

      act(() => {
        result.current.setOpen(true)
      })

      expect(result.current.isOpen).toBe(true)
    })

    it('sets isOpen to false', () => {
      const { result } = renderHook(() => useNotificationUIStore(), { wrapper })

      act(() => {
        result.current.setOpen(true)
      })

      expect(result.current.isOpen).toBe(true)

      act(() => {
        result.current.setOpen(false)
      })

      expect(result.current.isOpen).toBe(false)
    })
  })

  describe('toggleOpen', () => {
    it('toggles from false to true', () => {
      const { result } = renderHook(() => useNotificationUIStore(), { wrapper })

      expect(result.current.isOpen).toBe(false)

      act(() => {
        result.current.toggleOpen()
      })

      expect(result.current.isOpen).toBe(true)
    })

    it('toggles from true to false', () => {
      const { result } = renderHook(() => useNotificationUIStore(), { wrapper })

      act(() => {
        result.current.setOpen(true)
      })

      expect(result.current.isOpen).toBe(true)

      act(() => {
        result.current.toggleOpen()
      })

      expect(result.current.isOpen).toBe(false)
    })

    it('toggles multiple times correctly', () => {
      const { result } = renderHook(() => useNotificationUIStore(), { wrapper })

      expect(result.current.isOpen).toBe(false)

      act(() => {
        result.current.toggleOpen()
      })
      expect(result.current.isOpen).toBe(true)

      act(() => {
        result.current.toggleOpen()
      })
      expect(result.current.isOpen).toBe(false)

      act(() => {
        result.current.toggleOpen()
      })
      expect(result.current.isOpen).toBe(true)
    })
  })
})
