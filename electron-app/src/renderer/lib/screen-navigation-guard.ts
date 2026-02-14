/**
 * Screen Navigation Guard
 *
 * Module-level singleton for blocking screen-level navigation (sidebar clicks)
 * when the user has unsaved edits. Only one guard can be active at a time
 * (only one document can be edited at a time).
 *
 * Usage:
 * - `useEditMode` registers a guard while in edit mode
 * - `DashboardPage` checks the guard in `handleNavigate`
 *
 * The guard receives a `proceed` callback so it can store it as a deferred
 * action and execute it after the user confirms discard.
 */

type ScreenGuard = (proceed: () => void) => boolean

let currentGuard: ScreenGuard | null = null

export function registerScreenGuard(guard: ScreenGuard): void {
  currentGuard = guard
}

export function unregisterScreenGuard(): void {
  currentGuard = null
}

/**
 * Check if screen navigation is allowed.
 * @param proceed - callback to execute the navigation (stored as deferred action if blocked)
 * @returns true if navigation is allowed, false if blocked (dialog shown)
 */
export function checkScreenGuard(proceed: () => void): boolean {
  if (!currentGuard) return true
  return currentGuard(proceed)
}
