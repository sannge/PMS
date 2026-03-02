/**
 * AI Context Provider
 *
 * Provides a React context for injecting page-level context into AI chat
 * messages. Since CopilotKit is not installed, we inject context by
 * prepending it to the user's message when sending to the AI backend.
 *
 * Usage:
 *   // In a parent layout component:
 *   <AiContextProvider>
 *     <Dashboard />
 *   </AiContextProvider>
 *
 *   // In a page component that wants to inject context:
 *   const { setContext } = useAiContext()
 *   useEffect(() => {
 *     setContext(`Viewing project "${project.name}" (${project.id})`)
 *     return () => setContext(null)
 *   }, [project, setContext])
 *
 *   // In the chat input, prepend context to messages:
 *   const { context } = useAiContext()
 */

import {
  createContext,
  useContext,
  useState,
  useCallback,
  type ReactNode,
} from 'react'

// ============================================================================
// Types
// ============================================================================

interface AiContextValue {
  /** Current page/view context string, or null if none */
  context: string | null
  /** Set the context string (call with null to clear) */
  setContext: (ctx: string | null) => void
}

// ============================================================================
// Context
// ============================================================================

const AiContextContext = createContext<AiContextValue>({
  context: null,
  setContext: () => {},
})

// ============================================================================
// Provider
// ============================================================================

interface AiContextProviderProps {
  children: ReactNode
}

export function AiContextProvider({ children }: AiContextProviderProps): JSX.Element {
  const [context, setContextState] = useState<string | null>(null)

  const setContext = useCallback((ctx: string | null) => {
    setContextState(ctx)
  }, [])

  return (
    <AiContextContext.Provider value={{ context, setContext }}>
      {children}
    </AiContextContext.Provider>
  )
}

// ============================================================================
// Hook
// ============================================================================

/**
 * Access the AI context for the current page/view.
 *
 * - Page components call `setContext(...)` to describe what the user is viewing.
 * - The chat input reads `context` to prepend it to outgoing messages.
 */
export function useAiContext(): AiContextValue {
  return useContext(AiContextContext)
}
