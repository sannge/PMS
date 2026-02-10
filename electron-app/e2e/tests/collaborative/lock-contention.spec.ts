/**
 * Lock Contention & Lifecycle Tests (2 clients) - Scenarios #6.8-6.11
 *
 * Validates lock lifecycle edge cases:
 * - Heartbeat keeps lock alive within TTL
 * - Lock released on page navigation
 * - Lock released on tab switch within Notes
 * - Lock released on document switch (with discard/save dialog)
 */
import { test, expect } from '../../fixtures/two-clients'
import { loginAs, navigateToNotes, TEST_USER_1, TEST_USER_2 } from '../../helpers/auth'
import {
  createDocViaUI,
  enterEditMode,
  saveDocument,
  cancelEdit,
  selectTreeItem,
  getTreeItem,
} from '../../helpers/knowledge-ops'
import { waitForWsUpdate, waitForRemoval, briefPause } from '../../helpers/wait'

test.describe('Lock Contention & Lifecycle', () => {
  test.beforeEach(async ({ window1, window2 }) => {
    await Promise.all([
      loginAs(window1, TEST_USER_1).then(() => navigateToNotes(window1)),
      loginAs(window2, TEST_USER_2).then(() => navigateToNotes(window2)),
    ])
  })

  // #6.8 Heartbeat keeps lock alive: Enter edit, wait 2 min (within 5 min TTL), lock still held
  test('heartbeat keeps lock alive within TTL (#6.8)', async ({ window1, window2 }) => {
    test.slow() // Triple the default timeout for this long-wait test

    const docName = `Heartbeat-Lock-${Date.now()}`

    // Create a shared document
    await createDocViaUI(window1, docName)
    await waitForWsUpdate(window2, `text="${docName}"`, { timeout: 10_000 })

    // Client A: Select and enter edit mode (acquires lock)
    await selectTreeItem(window1, docName)
    await enterEditMode(window1)

    // Confirm A is in edit mode
    await expect(
      window1.locator('button:has-text("Save"), button:has-text("Cancel")').first()
    ).toBeVisible({ timeout: 5_000 })

    // Wait 2 minutes (120 seconds) - well within the 5-minute TTL.
    // The heartbeat mechanism should keep the lock alive.
    await briefPause(120_000)

    // Client A: Should still be in edit mode (lock not expired)
    await expect(
      window1.locator('button:has-text("Save"), button:has-text("Cancel")').first()
    ).toBeVisible({ timeout: 5_000 })

    // Client B: Select the same doc - should still see it as locked by A
    await selectTreeItem(window2, docName)
    await expect(
      window2.locator('text=/[Ll]ocked/')
    ).toBeVisible({ timeout: 10_000 })

    // Client B: Edit button should still be disabled or show lock contention
    const editBtn = window2.locator('button:has-text("Edit")')
    if (await editBtn.isEnabled({ timeout: 3_000 }).catch(() => false)) {
      // If enabled, clicking should show lock error
      await editBtn.click()
      await expect(
        window2.locator('text=/[Ll]ocked|cannot edit|in use/')
      ).toBeVisible({ timeout: 5_000 })
    } else {
      await expect(editBtn).toBeDisabled()
    }

    // Clean up: Client A saves and releases lock
    await saveDocument(window1)
  })

  // #6.9 Lock released on navigation: Edit doc in Notes -> navigate to Tasks -> lock released
  test('lock released when navigating away from Notes page (#6.9)', async ({ window1, window2 }) => {
    const docName = `Nav-Release-${Date.now()}`

    // Create a shared document
    await createDocViaUI(window1, docName)
    await waitForWsUpdate(window2, `text="${docName}"`, { timeout: 10_000 })

    // Client A: Select and enter edit mode (acquires lock)
    await selectTreeItem(window1, docName)
    await enterEditMode(window1)

    // Confirm lock is held - Client B should see lock indicator
    await selectTreeItem(window2, docName)
    await expect(
      window2.locator('text=/[Ll]ocked/')
    ).toBeVisible({ timeout: 10_000 })

    // Client A: Navigate away from Notes to a different page (e.g., Tasks or Dashboard)
    // This should trigger lock release via component unmount / beforeunload handler
    const dashboardLink = window1.locator('text=Dashboard, text=Home').first()
    await dashboardLink.click()
    // Wait for navigation to complete (Notes page unmounted)
    await briefPause(2000)

    // Handle any discard dialog that might appear
    const discardBtn = window1.locator('button:has-text("Discard")')
    if (await discardBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await discardBtn.click()
    }

    // Client B: Lock should be released - Edit button should become enabled
    await expect(
      window2.locator('button:has-text("Edit")')
    ).toBeEnabled({ timeout: 15_000 })

    // Client B: "Locked by" indicator should disappear
    await expect(
      window2.locator('text=/[Ll]ocked by/')
    ).not.toBeVisible({ timeout: 10_000 })
  })

  // #6.10 Lock released on tab switch: Edit in Personal -> switch to App tab -> lock released
  test('lock released when switching tabs within Notes page (#6.10)', async ({ window1, window2 }) => {
    const docName = `TabSwitch-Release-${Date.now()}`

    // Create a shared document (in the current tab context)
    await createDocViaUI(window1, docName)
    await waitForWsUpdate(window2, `text="${docName}"`, { timeout: 10_000 })

    // Client A: Select and enter edit mode (acquires lock)
    await selectTreeItem(window1, docName)
    await enterEditMode(window1)

    // Confirm lock is held - Client B should see lock indicator
    await selectTreeItem(window2, docName)
    await expect(
      window2.locator('text=/[Ll]ocked/')
    ).toBeVisible({ timeout: 10_000 })

    // Client A: Switch to a different tab within the Notes page
    // Look for any other available tab (Personal/My Notes or an App tab)
    const personalTab = window1.locator('button:has-text("My Notes"), button:has-text("Personal")').first()
    const appTabsInTabBar = window1.locator('button[role="tab"]')

    // Try to find a different tab to switch to
    let tabToClick = null
    if (await personalTab.isVisible({ timeout: 3_000 }).catch(() => false)) {
      tabToClick = personalTab
    } else {
      // Find first app tab in tab bar
      const tabCount = await appTabsInTabBar.count()
      if (tabCount > 0) {
        tabToClick = appTabsInTabBar.first()
      }
    }

    if (tabToClick) {
      await tabToClick.click()
    } else {
      // Fallback: navigate away from Notes entirely
      await window1.click('text=Dashboard, text=Home').catch(() => {})
    }

    // Handle discard dialog
    const discardBtn = window1.locator('button:has-text("Discard")')
    if (await discardBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await discardBtn.click()
    }

    // Wait for tab switch to complete
    await briefPause(2000)

    // Client B: Lock should be released - Edit button should become enabled
    await expect(
      window2.locator('button:has-text("Edit")')
    ).toBeEnabled({ timeout: 15_000 })

    // Client B: Lock indicator should disappear
    await expect(
      window2.locator('text=/[Ll]ocked by/')
    ).not.toBeVisible({ timeout: 10_000 })
  })

  // #6.11 Lock released on doc switch: Edit doc A -> click doc B -> discard/save dialog -> lock on A released
  test('lock released when switching to another document (#6.11)', async ({ window1, window2 }) => {
    const ts = Date.now()
    const docNameA = `DocSwitch-A-${ts}`
    const docNameB = `DocSwitch-B-${ts}`

    // Create two shared documents
    await createDocViaUI(window1, docNameA)
    await createDocViaUI(window1, docNameB)

    // Client B: Wait for both docs
    await waitForWsUpdate(window2, `text="${docNameA}"`, { timeout: 10_000 })
    await waitForWsUpdate(window2, `text="${docNameB}"`, { timeout: 10_000 })

    // Client A: Select doc A and enter edit mode (acquires lock on doc A)
    await selectTreeItem(window1, docNameA)
    await enterEditMode(window1)

    // Confirm lock is held - Client B should see lock indicator on doc A
    await selectTreeItem(window2, docNameA)
    await expect(
      window2.locator('text=/[Ll]ocked/')
    ).toBeVisible({ timeout: 10_000 })

    // Client A: Click doc B in the tree (switch away from doc A while editing)
    await window1.locator(`[role="treeitem"]:has-text("${docNameB}")`).first().click()

    // A discard/save dialog should appear since doc A is being edited
    const discardBtn = window1.locator('button:has-text("Discard")')
    const saveBtn = window1.locator('button:has-text("Save")')

    if (await discardBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
      // Choose "Discard" to abandon changes and switch documents
      await discardBtn.click()
    } else if (await saveBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
      // If only save is shown, save first
      await saveBtn.click()
    }

    // Wait for document switch to complete
    await briefPause(2000)

    // Client B: Lock on doc A should now be released
    await selectTreeItem(window2, docNameA)
    await expect(
      window2.locator('button:has-text("Edit")')
    ).toBeEnabled({ timeout: 15_000 })

    // Client B: "Locked by" indicator on doc A should be gone
    await expect(
      window2.locator('text=/[Ll]ocked by/')
    ).not.toBeVisible({ timeout: 10_000 })
  })
})
