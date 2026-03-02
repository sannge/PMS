/**
 * AI Navigation Bridge
 *
 * Module-level bridge between the AI sidebar and screen-based navigation.
 * Since the app uses state-based routing (not react-router), the AI sidebar
 * can't directly navigate to a document in the Notes screen. This module
 * provides a decoupled way to:
 * 1. Store a pending navigation target (document + highlight params)
 * 2. Request a screen switch (e.g., to 'notes')
 * 3. Let the target screen consume the pending navigation on mount
 */

import type { NavigationTarget } from '@/components/ai/types'

// ---------------------------------------------------------------------------
// Pending navigation target
// ---------------------------------------------------------------------------

type NavigationListener = (target: NavigationTarget) => void

let _pendingTarget: NavigationTarget | null = null
const _listeners = new Set<NavigationListener>()

export function setPendingAiNavigation(target: NavigationTarget): void {
  _pendingTarget = target
  _listeners.forEach((fn) => fn(target))
}

export function consumePendingAiNavigation(): NavigationTarget | null {
  const target = _pendingTarget
  _pendingTarget = null
  return target
}

export function subscribePendingAiNavigation(
  listener: NavigationListener,
): () => void {
  _listeners.add(listener)
  return () => {
    _listeners.delete(listener)
  }
}

// ---------------------------------------------------------------------------
// Screen switcher bridge
// ---------------------------------------------------------------------------

type ScreenSwitcher = (screen: string) => void

let _screenSwitcher: ScreenSwitcher | null = null

export function setScreenSwitcher(fn: ScreenSwitcher): void {
  _screenSwitcher = fn
}

export function clearScreenSwitcher(): void {
  _screenSwitcher = null
}

export function requestScreenSwitch(screen: string): void {
  _screenSwitcher?.(screen)
}

// ---------------------------------------------------------------------------
// Full reset (call on logout / user switch)
// ---------------------------------------------------------------------------

export function resetAiNavigation(): void {
  _pendingTarget = null
  _listeners.clear()
  _screenSwitcher = null
}
