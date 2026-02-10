/**
 * Smoke test: Verify Electron app launches and login works.
 * Run this first to validate the E2E infrastructure.
 */
import { test, expect } from '../fixtures/electron-app'
import { loginAs, TEST_USER_1, navigateToNotes } from '../helpers/auth'

test.describe('Smoke Tests', () => {
  test('app launches and shows login page', async ({ window }) => {
    // The app should show the login page on first launch
    await window.waitForSelector('#email', { timeout: 30_000 })
    await window.waitForSelector('#password')

    // Verify login form elements exist
    await expect(window.locator('#email')).toBeVisible()
    await expect(window.locator('#password')).toBeVisible()
    await expect(window.locator('button[type="submit"]')).toBeVisible()
  })

  test('login succeeds with valid credentials', async ({ window }) => {
    await loginAs(window, TEST_USER_1)

    // Should be on dashboard after login
    await expect(window.locator('text=Dashboard')).toBeVisible()
  })

  test('can navigate to Notes page', async ({ window }) => {
    await loginAs(window, TEST_USER_1)
    await navigateToNotes(window)

    // Notes page should show the knowledge tree area
    await expect(window.locator('[role="tree"]')).toBeVisible()
  })
})
