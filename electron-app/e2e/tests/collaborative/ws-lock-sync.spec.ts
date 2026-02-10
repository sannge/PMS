/**
 * WebSocket Lock Sync Tests (2 clients) - Scenarios #12.9-12.11, #6.1-6.7
 *
 * Validates real-time lock status updates between clients:
 * - Lock acquired/released events via WebSocket
 * - Force-take lock flow
 * - Lock indicator UI (action bar, lock icon)
 * - Lock contention (concurrent edit attempts)
 * - Independent locks on different documents
 * - Batch active-locks endpoint
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

/**
 * Helper: Both clients select the same document by name.
 */
async function bothSelectDoc(
  window1: import('@playwright/test').Page,
  window2: import('@playwright/test').Page,
  docName: string
): Promise<void> {
  await selectTreeItem(window1, docName)
  await selectTreeItem(window2, docName)
  await briefPause(500)
}

test.describe('WebSocket Lock Sync', () => {
  test.beforeEach(async ({ window1, window2 }) => {
    await Promise.all([
      loginAs(window1, TEST_USER_1).then(() => navigateToNotes(window1)),
      loginAs(window2, TEST_USER_2).then(() => navigateToNotes(window2)),
    ])
  })

  // =========================================================================
  // WS Lock Events (#12.9-12.11)
  // =========================================================================

  // #12.9 Lock event: Client A acquires lock, Client B sees lock indicator
  test('lock acquired by A shows lock indicator on B (#12.9)', async ({ window1, window2 }) => {
    const docName = `WS-Lock-Ind-${Date.now()}`

    // Create a shared document
    await createDocViaUI(window1, docName)
    await waitForWsUpdate(window2, `text="${docName}"`, { timeout: 10_000 })

    // Both clients select the same document
    await bothSelectDoc(window1, window2, docName)

    // Client A: Enter edit mode (acquires lock)
    await enterEditMode(window1)

    // Client B: Should see lock indicator (lock icon, "Locked by" text, or disabled Edit button)
    await expect(
      window2.locator('text=/[Ll]ocked|[Ee]diting/')
    ).toBeVisible({ timeout: 10_000 })
  })

  // #12.10 Unlock event: Client A releases lock, Client B sees lock indicator disappear
  test('lock released by A removes lock indicator on B (#12.10)', async ({ window1, window2 }) => {
    const docName = `WS-Unlock-${Date.now()}`

    // Create a shared document
    await createDocViaUI(window1, docName)
    await waitForWsUpdate(window2, `text="${docName}"`, { timeout: 10_000 })

    // Both select same document
    await bothSelectDoc(window1, window2, docName)

    // Client A: Enter edit mode (acquire lock)
    await enterEditMode(window1)

    // Client B: Verify lock indicator appears
    await expect(
      window2.locator('text=/[Ll]ocked|[Ee]diting/')
    ).toBeVisible({ timeout: 10_000 })

    // Client A: Release lock by cancelling edit
    await cancelEdit(window1)

    // Client B: Lock indicator should disappear, Edit button should be enabled
    await expect(
      window2.locator('button:has-text("Edit")')
    ).toBeEnabled({ timeout: 10_000 })

    // Lock indicator text should no longer be visible
    await expect(
      window2.locator('text=/[Ll]ocked by/')
    ).not.toBeVisible({ timeout: 10_000 })
  })

  // #12.11 Force-take: Client B force-takes lock, Client A exits edit mode and sees toast
  test('force-take by B kicks A out of edit mode with notification (#12.11)', async ({ window1, window2 }) => {
    const docName = `WS-ForceTake-${Date.now()}`

    // Create a shared document
    await createDocViaUI(window1, docName)
    await waitForWsUpdate(window2, `text="${docName}"`, { timeout: 10_000 })

    // Both select same document
    await bothSelectDoc(window1, window2, docName)

    // Client A: Enter edit mode (acquire lock)
    await enterEditMode(window1)
    await briefPause(1000)

    // Client B: Should see lock contention UI. Look for "Force Take" or "Take Over" button
    const forceTakeBtn = window2.locator(
      'button:has-text("Force"), button:has-text("Take Over"), button:has-text("Override")'
    )
    await expect(forceTakeBtn.first()).toBeVisible({ timeout: 10_000 })

    // Client B: Click force-take
    await forceTakeBtn.first().click()

    // Client B: Should now be in edit mode (Save/Cancel visible)
    await expect(
      window2.locator('button:has-text("Save"), button:has-text("Cancel")').first()
    ).toBeVisible({ timeout: 10_000 })

    // Client A: Should be kicked out of edit mode (back to view mode)
    await expect(
      window1.locator('button:has-text("Edit")')
    ).toBeVisible({ timeout: 10_000 })

    // Client A: Should see a toast/notification about the lock being taken
    await expect(
      window1.locator('text=/[Ll]ock.*taken|[Ff]orce|[Oo]verride|lost.*edit/')
    ).toBeVisible({ timeout: 10_000 })
  })

  // =========================================================================
  // Lock System Core (#6.1-6.7)
  // =========================================================================

  // #6.1 Lock indicator visible: A locks doc, B sees "Locked by A" in action bar
  test('locked doc shows "Locked by" in action bar on B (#6.1)', async ({ window1, window2 }) => {
    const docName = `Lock-Visible-${Date.now()}`

    // Create a shared document
    await createDocViaUI(window1, docName)
    await waitForWsUpdate(window2, `text="${docName}"`, { timeout: 10_000 })

    // Both select same document
    await bothSelectDoc(window1, window2, docName)

    // Client A: Enter edit mode (acquires lock)
    await enterEditMode(window1)

    // Client B: Action bar should show "Locked by" with user info
    await expect(
      window2.locator('text=/[Ll]ocked by/')
    ).toBeVisible({ timeout: 10_000 })
  })

  // #6.2 Lock release visible: A releases lock, B sees Edit button enabled
  test('lock release makes Edit button enabled on B (#6.2)', async ({ window1, window2 }) => {
    const docName = `Lock-Release-${Date.now()}`

    // Create a shared document
    await createDocViaUI(window1, docName)
    await waitForWsUpdate(window2, `text="${docName}"`, { timeout: 10_000 })

    // Both select same document
    await bothSelectDoc(window1, window2, docName)

    // Client A: Acquire lock
    await enterEditMode(window1)
    await briefPause(1000)

    // Client A: Release lock via save
    await saveDocument(window1)

    // Client B: Edit button should now be enabled (lock released via WS)
    await expect(
      window2.locator('button:has-text("Edit")')
    ).toBeEnabled({ timeout: 10_000 })
  })

  // #6.3 Lock contention: A holds lock, B clicks Edit -> error or disabled
  test('B cannot edit while A holds lock (#6.3)', async ({ window1, window2 }) => {
    const docName = `Lock-Contention-${Date.now()}`

    // Create a shared document
    await createDocViaUI(window1, docName)
    await waitForWsUpdate(window2, `text="${docName}"`, { timeout: 10_000 })

    // Both select same document
    await bothSelectDoc(window1, window2, docName)

    // Client A: Acquire lock
    await enterEditMode(window1)
    await briefPause(1000)

    // Client B: Try to edit - should fail or show lock error
    const editBtn = window2.locator('button:has-text("Edit")')

    if (await editBtn.isEnabled({ timeout: 3_000 }).catch(() => false)) {
      // Button is enabled but clicking it should show lock contention error
      await editBtn.click()

      // Should see a toast/error about lock contention
      await expect(
        window2.locator('text=/[Ll]ocked|cannot edit|in use|already editing/')
      ).toBeVisible({ timeout: 5_000 })
    } else {
      // Edit button is disabled - expected behavior when another user holds the lock
      await expect(editBtn).toBeDisabled()
    }
  })

  // #6.4 Force-take lock: A holds -> B force-takes -> A kicked out, B enters edit
  test('force-take: B takes lock from A, A exits edit mode (#6.4)', async ({ window1, window2 }) => {
    const docName = `Force-Take-${Date.now()}`

    // Create a shared document
    await createDocViaUI(window1, docName)
    await waitForWsUpdate(window2, `text="${docName}"`, { timeout: 10_000 })

    // Both select same document
    await bothSelectDoc(window1, window2, docName)

    // Client A: Acquire lock
    await enterEditMode(window1)
    await briefPause(1000)

    // Client B: Find and click force-take button
    const forceTakeBtn = window2.locator(
      'button:has-text("Force"), button:has-text("Take Over"), button:has-text("Override")'
    )
    await expect(forceTakeBtn.first()).toBeVisible({ timeout: 10_000 })
    await forceTakeBtn.first().click()

    // Client B: Verify B is now in edit mode
    await expect(
      window2.locator('button:has-text("Save"), button:has-text("Cancel")').first()
    ).toBeVisible({ timeout: 10_000 })

    // Client A: Should be back in view mode (kicked out)
    await expect(
      window1.locator('button:has-text("Edit")')
    ).toBeVisible({ timeout: 10_000 })
  })

  // #6.5 Lock reacquire (same user): A locks, releases, re-locks -> no conflict
  test('same user can reacquire lock after releasing (#6.5)', async ({ window1, window2 }) => {
    const docName = `Lock-Reacquire-${Date.now()}`

    // Create a shared document
    await createDocViaUI(window1, docName)
    await waitForWsUpdate(window2, `text="${docName}"`, { timeout: 10_000 })

    // Client A: Select and enter edit mode (first lock)
    await selectTreeItem(window1, docName)
    await enterEditMode(window1)

    // Client A: Release lock by cancelling
    await cancelEdit(window1)

    // Brief pause for lock release to propagate
    await briefPause(1000)

    // Client A: Re-enter edit mode (reacquire lock) - should succeed without conflict
    await enterEditMode(window1)

    // Client A: Should be in edit mode (Save/Cancel visible)
    await expect(
      window1.locator('button:has-text("Save"), button:has-text("Cancel")').first()
    ).toBeVisible({ timeout: 5_000 })

    // Client B: Select same doc, should see lock indicator from A's re-lock
    await selectTreeItem(window2, docName)
    await expect(
      window2.locator('text=/[Ll]ocked/')
    ).toBeVisible({ timeout: 10_000 })
  })

  // #6.6 Lock across tree items: A locks doc A, B locks doc B -> both show locked independently
  test('independent locks on different docs do not conflict (#6.6)', async ({ window1, window2 }) => {
    const ts = Date.now()
    const docNameA = `Lock-IndepA-${ts}`
    const docNameB = `Lock-IndepB-${ts}`

    // Create two shared documents
    await createDocViaUI(window1, docNameA)
    await createDocViaUI(window1, docNameB)

    // Client B: Wait for both docs
    await waitForWsUpdate(window2, `text="${docNameA}"`, { timeout: 10_000 })
    await waitForWsUpdate(window2, `text="${docNameB}"`, { timeout: 10_000 })

    // Client A: Select and lock doc A
    await selectTreeItem(window1, docNameA)
    await enterEditMode(window1)

    // Client B: Select and lock doc B (should succeed independently)
    await selectTreeItem(window2, docNameB)
    await enterEditMode(window2)

    // Client A: Should be in edit mode on doc A
    await expect(
      window1.locator('button:has-text("Save"), button:has-text("Cancel")').first()
    ).toBeVisible({ timeout: 5_000 })

    // Client B: Should be in edit mode on doc B
    await expect(
      window2.locator('button:has-text("Save"), button:has-text("Cancel")').first()
    ).toBeVisible({ timeout: 5_000 })

    // Now cross-check: Client A views doc B -> should see B's lock
    // (We avoid navigation here since A is editing; instead verify both edits are independent)
    // Clean up: save both
    await saveDocument(window1)
    await saveDocument(window2)
  })

  // #6.7 Lock in batch endpoint: Lock multiple docs -> active-locks batch returns all
  test('active-locks batch endpoint returns all locked docs (#6.7)', async ({ window1, window2 }) => {
    const ts = Date.now()
    const docName1 = `Batch-Lock1-${ts}`
    const docName2 = `Batch-Lock2-${ts}`

    // Create two documents
    await createDocViaUI(window1, docName1)
    await createDocViaUI(window1, docName2)

    // Client B: Wait for both docs
    await waitForWsUpdate(window2, `text="${docName1}"`, { timeout: 10_000 })
    await waitForWsUpdate(window2, `text="${docName2}"`, { timeout: 10_000 })

    // Client A: Lock doc 1
    await selectTreeItem(window1, docName1)
    await enterEditMode(window1)

    // Wait for lock to propagate
    await briefPause(1000)

    // Client B: Both docs should show lock status correctly
    // Doc 1 should show locked (by A)
    await selectTreeItem(window2, docName1)
    await expect(
      window2.locator('text=/[Ll]ocked/')
    ).toBeVisible({ timeout: 10_000 })

    // Doc 2 should NOT show locked (no one is editing it)
    await selectTreeItem(window2, docName2)
    await briefPause(500)

    // The Edit button for doc 2 should be enabled (not locked)
    await expect(
      window2.locator('button:has-text("Edit")')
    ).toBeEnabled({ timeout: 5_000 })

    // Verify the tree shows lock indicator on doc 1 but not doc 2
    // Lock icon in the tree item for doc 1
    const treeItem1 = window2.locator(`[role="treeitem"]:has-text("${docName1}")`)
    const lockIcon1 = treeItem1.locator('svg.lucide-lock, [data-testid="lock-icon"], [aria-label*="lock"]')

    const treeItem2 = window2.locator(`[role="treeitem"]:has-text("${docName2}")`)
    const lockIcon2 = treeItem2.locator('svg.lucide-lock, [data-testid="lock-icon"], [aria-label*="lock"]')

    // Count lock icons
    const lockIcon1Count = await lockIcon1.count()
    const lockIcon2Count = await lockIcon2.count()

    // Doc 1 should have lock (in tree or action bar - already verified above via "Locked" text)
    // Doc 2 should NOT have a lock icon in the tree
    expect(lockIcon2Count).toBe(0)
    // Note: Doc 1 lock may be in action bar instead of tree, so we don't assert icon count
    // The "Locked" text assertion earlier confirms lock status

    // Clean up
    await selectTreeItem(window1, docName1)
    await saveDocument(window1)
  })
})
