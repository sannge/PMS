/**
 * Authentication and navigation helpers for E2E tests.
 * Logs in a user via the app's login form and navigates to different contexts.
 */
import { Page, expect } from '@playwright/test'

export interface TestUser {
  email: string
  password: string
}

/**
 * Test users - these must exist in the backend database.
 * Create them via backend seed script or API before running E2E tests.
 */
export const TEST_USER_1: TestUser = {
  email: 'samngestep@gmail.com',
  password: '9ol.(OL>',
}

export const TEST_USER_2: TestUser = {
  email: 'samngestep2@gmail.com',
  password: 'Test123!',
}

/**
 * Log in via the login form UI.
 * The login page uses input id="email" and id="password".
 */
export async function loginAs(page: Page, user: TestUser): Promise<void> {
  // Wait for login form to appear
  await page.waitForSelector('#email', { timeout: 30_000 })

  // Fill login form
  await page.fill('#email', user.email)
  await page.fill('#password', user.password)

  // Submit - find the submit button (contains "Sign In" text)
  await page.click('button[type="submit"]')

  // Wait for dashboard to load (login success indicator)
  // The dashboard renders a sidebar with navigation items
  await page.waitForSelector('text=Dashboard', { timeout: 30_000 })
}

/**
 * Wait for knowledge tree OR empty state to appear.
 * The tree component returns early with an empty state when there are no items,
 * so [role="tree"] is only rendered when there are folders/documents.
 */
async function waitForTreeOrEmptyState(page: Page): Promise<void> {
  await page.locator('[role="tree"], :text("No documents yet"), :text("Create your first document")')
    .first()
    .waitFor({ state: 'visible', timeout: 15_000 })
}

/**
 * Navigate to the Notes page via sidebar.
 */
export async function navigateToNotes(page: Page): Promise<void> {
  // Click "Notes" in the sidebar navigation
  await page.click('text=Notes')

  // Wait for either the tree or empty state
  await waitForTreeOrEmptyState(page)
}

/**
 * Login and navigate to Notes page in one call.
 */
export async function loginAndGoToNotes(page: Page, user: TestUser): Promise<void> {
  await loginAs(page, user)
  await navigateToNotes(page)
}

// ============================================================================
// Context Navigation Helpers
// ============================================================================

/**
 * Navigate to Notes page → Personal (My Notes) tab.
 * Assumes user is already logged in.
 */
export async function navigateToNotesPersonalTab(page: Page): Promise<void> {
  await navigateToNotes(page)
  // Click "My Notes" tab if not already active
  const personalTab = page.locator('button:has-text("My Notes")')
  if (await personalTab.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await personalTab.click()
  }
  // Wait for tree or empty state in personal scope
  await waitForTreeOrEmptyState(page)
}

/**
 * Navigate to Notes page → specific App tab.
 * Assumes user is already logged in.
 */
export async function navigateToNotesAppTab(page: Page, appName: string): Promise<void> {
  await navigateToNotes(page)
  // Click the app tab in the tab bar
  const appTab = page.locator(`button:has-text("${appName}")`)
  // App might be in overflow dropdown
  if (await appTab.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await appTab.click()
  } else {
    // Check overflow "More Apps" dropdown
    const moreBtn = page.locator('button:has-text("More")')
    if (await moreBtn.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await moreBtn.click()
      await page.locator(`text="${appName}"`).click()
    }
  }
  await waitForTreeOrEmptyState(page)
}

/**
 * Navigate to Application Detail → Knowledge tab.
 * Sidebar → Applications → click app → Knowledge tab.
 * Assumes user is already logged in.
 */
export async function navigateToAppKnowledgeTab(page: Page, appName: string): Promise<void> {
  // Navigate to Applications page via sidebar
  await page.click('text=Applications')
  await page.waitForSelector('text=Applications', { timeout: 15_000 })

  // Click the specific application
  await page.locator(`text="${appName}"`).first().click()
  await page.waitForTimeout(1000)

  // Click the Knowledge tab
  const knowledgeTab = page.locator('button:has-text("Knowledge")')
  await knowledgeTab.click()

  // Wait for KnowledgePanel tree or empty state
  await waitForTreeOrEmptyState(page)
}

/**
 * Navigate to Project Detail → Knowledge tab.
 * Sidebar → Applications → click app → click project → Knowledge tab.
 * Assumes user is already logged in.
 */
export async function navigateToProjectKnowledgeTab(
  page: Page,
  appName: string,
  projectName: string
): Promise<void> {
  // Navigate to Applications → App detail
  await page.click('text=Applications')
  await page.waitForSelector('text=Applications', { timeout: 15_000 })

  await page.locator(`text="${appName}"`).first().click()
  await page.waitForTimeout(1000)

  // Click the project from the projects list
  await page.locator(`text="${projectName}"`).first().click()
  await page.waitForTimeout(1000)

  // Click the Knowledge tab
  const knowledgeTab = page.locator('button:has-text("Knowledge")')
  await knowledgeTab.click()

  // Wait for KnowledgePanel tree or empty state
  await waitForTreeOrEmptyState(page)
}
