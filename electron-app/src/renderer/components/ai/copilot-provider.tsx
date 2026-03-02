/**
 * CopilotKit Provider Wrapper
 *
 * Wraps children in CopilotKit context for useCopilotReadable.
 * Falls back to rendering children directly if CopilotKit is not installed.
 *
 * NOTE: CopilotKit is not currently in package.json. This is a forward-looking
 * wrapper that will activate once the dependency is installed. Until then it is
 * a transparent pass-through.
 */

import { type ReactNode } from 'react'

interface CopilotProviderProps {
  children: ReactNode
}

export function CopilotProvider({ children }: CopilotProviderProps): JSX.Element {
  // CopilotKit is not yet installed -- render children directly.
  // When @copilotkit/react-core is added to dependencies, update this
  // component to wrap children in <CopilotKit runtimeUrl="/api/copilotkit">.
  return <>{children}</>
}
