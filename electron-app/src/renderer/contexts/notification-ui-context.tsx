/**
 * Notification UI Context
 *
 * Simple React Context for notification panel UI state only.
 * Data fetching is handled by TanStack Query hooks in use-notifications.ts.
 */

import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'

// ============================================================================
// Types
// ============================================================================

interface NotificationUIContextValue {
  isOpen: boolean
  setOpen: (open: boolean) => void
  toggleOpen: () => void
}

// ============================================================================
// Context
// ============================================================================

const NotificationUIContext = createContext<NotificationUIContextValue | null>(null)

export function NotificationUIProvider({ children }: { children: ReactNode }): JSX.Element {
  const [isOpen, setIsOpen] = useState(false)

  const setOpen = useCallback((open: boolean): void => {
    setIsOpen(open)
  }, [])

  const toggleOpen = useCallback((): void => {
    setIsOpen((prev) => !prev)
  }, [])

  const value: NotificationUIContextValue = {
    isOpen,
    setOpen,
    toggleOpen,
  }

  return (
    <NotificationUIContext.Provider value={value}>
      {children}
    </NotificationUIContext.Provider>
  )
}

// ============================================================================
// Hook
// ============================================================================

export function useNotificationUIStore(): NotificationUIContextValue
export function useNotificationUIStore<T>(selector: (state: NotificationUIContextValue) => T): T
export function useNotificationUIStore<T>(
  selector?: (state: NotificationUIContextValue) => T
): NotificationUIContextValue | T {
  const context = useContext(NotificationUIContext)
  if (!context) {
    throw new Error('useNotificationUIStore must be used within a NotificationUIProvider')
  }
  return selector ? selector(context) : context
}

export default NotificationUIContext
