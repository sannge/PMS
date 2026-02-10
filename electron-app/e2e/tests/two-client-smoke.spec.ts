/**
 * Two-Client Smoke Test: Verify two Electron instances can run simultaneously.
 * Both clients log in as different users and navigate to the Notes page.
 * This validates the foundational 2-client E2E setup.
 */
import { test, expect } from '../fixtures/two-clients'
import { loginAs, navigateToNotes, TEST_USER_1, TEST_USER_2 } from '../helpers/auth'

test.describe('Two-Client Infrastructure', () => {
  test('both Electron apps launch independently', async ({ window1, window2 }) => {
    // Both windows should show login page
    await window1.waitForSelector('#email', { timeout: 30_000 })
    await window2.waitForSelector('#email', { timeout: 30_000 })

    await expect(window1.locator('#email')).toBeVisible()
    await expect(window2.locator('#email')).toBeVisible()
  })

  test('both clients can log in as different users', async ({ window1, window2 }) => {
    // Login both clients in parallel
    await Promise.all([
      loginAs(window1, TEST_USER_1),
      loginAs(window2, TEST_USER_2),
    ])

    // Both should see dashboard
    await expect(window1.locator('text=Dashboard')).toBeVisible()
    await expect(window2.locator('text=Dashboard')).toBeVisible()
  })

  test('both clients can navigate to Notes page', async ({ window1, window2 }) => {
    // Login both
    await Promise.all([
      loginAs(window1, TEST_USER_1),
      loginAs(window2, TEST_USER_2),
    ])

    // Navigate both to Notes
    await Promise.all([
      navigateToNotes(window1),
      navigateToNotes(window2),
    ])

    // Both should see the knowledge tree
    await expect(window1.locator('[role="tree"]')).toBeVisible()
    await expect(window2.locator('[role="tree"]')).toBeVisible()
  })
})
