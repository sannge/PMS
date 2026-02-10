/**
 * Common wait helpers for E2E tests.
 */
import { Page, expect } from '@playwright/test'

/**
 * Wait for a WebSocket-propagated change to appear on a remote client.
 * Polls for a selector with a generous timeout since WS delivery
 * depends on backend broadcast + client cache invalidation.
 */
export async function waitForWsUpdate(
  page: Page,
  selector: string,
  options?: { timeout?: number; state?: 'visible' | 'attached' | 'hidden' | 'detached' }
): Promise<void> {
  await page.waitForSelector(selector, {
    timeout: options?.timeout ?? 10_000,
    state: options?.state ?? 'visible',
  })
}

/**
 * Wait for an element to disappear (e.g., after WS delete event).
 */
export async function waitForRemoval(
  page: Page,
  selector: string,
  timeout = 10_000
): Promise<void> {
  await page.waitForSelector(selector, { state: 'detached', timeout })
}

/**
 * Short delay for UI animations or optimistic update rendering.
 * Use sparingly - prefer waitForSelector when possible.
 */
export async function briefPause(ms = 500): Promise<void> {
  await new Promise(resolve => setTimeout(resolve, ms))
}

/**
 * Wait for network idle (no pending requests for 500ms).
 * Useful after mutations to wait for cache invalidation fetches.
 */
export async function waitForNetworkIdle(page: Page, timeout = 10_000): Promise<void> {
  await page.waitForLoadState('networkidle', { timeout })
}
