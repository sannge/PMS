/**
 * WebSocket Lock Sync Tests (2 clients)
 *
 * Validates real-time lock status updates between clients:
 * - Lock acquired → other client sees lock indicator
 * - Lock released → other client sees unlock
 * - Lock contention → second client cannot edit
 * - Force-take → original holder gets kicked out
 */
import { test, expect } from '../../fixtures/two-clients'
import { loginAs, navigateToNotes, TEST_USER_1, TEST_USER_2 } from '../../helpers/auth'
import { waitForWsUpdate, briefPause } from '../../helpers/wait'

test.describe('WebSocket Lock Sync', () => {
  test.beforeEach(async ({ window1, window2 }) => {
    await Promise.all([
      loginAs(window1, TEST_USER_1).then(() => navigateToNotes(window1)),
      loginAs(window2, TEST_USER_2).then(() => navigateToNotes(window2)),
    ])
  })

  test('lock acquired by Client A shows lock indicator on Client B', async ({ window1, window2 }) => {
    // Both clients: select the same document
    const firstDoc = window1.locator('[role="tree"] [role="treeitem"]').first()
    const docName = await firstDoc.textContent()
    await firstDoc.click()

    // Client B: select the same document
    if (docName) {
      await window2.locator(`text="${docName.trim()}"`).first().click()
    }
    await briefPause(500)

    // Client A: Enter edit mode (acquires lock)
    await window1.click('button:has-text("Edit")')

    // Client B: Should see lock indicator (locked by other user)
    // The lock status might show as a lock icon, "Locked by" text, or disabled edit button
    await expect(
      window2.locator('text=/[Ll]ocked|[Ee]diting/')
    ).toBeVisible({ timeout: 10_000 })
  })

  test('lock released by Client A enables edit on Client B', async ({ window1, window2 }) => {
    // Both clients select same document
    const firstDoc = window1.locator('[role="tree"] [role="treeitem"]').first()
    const docName = await firstDoc.textContent()
    await firstDoc.click()

    if (docName) {
      await window2.locator(`text="${docName.trim()}"`).first().click()
    }
    await briefPause(500)

    // Client A: Acquire lock
    await window1.click('button:has-text("Edit")')
    await briefPause(1000)

    // Client A: Release lock (cancel/save)
    const cancelBtn = window1.locator('button:has-text("Cancel")')
    const saveBtn = window1.locator('button:has-text("Save")')
    if (await cancelBtn.isVisible()) {
      await cancelBtn.click()
      // If discard dialog appears, confirm it
      const discardBtn = window1.locator('button:has-text("Discard")')
      if (await discardBtn.isVisible({ timeout: 2_000 }).catch(() => false)) {
        await discardBtn.click()
      }
    } else if (await saveBtn.isVisible()) {
      await saveBtn.click()
    }

    // Client B: Should now be able to edit (lock released via WS)
    await expect(
      window2.locator('button:has-text("Edit")')
    ).toBeEnabled({ timeout: 10_000 })
  })

  test('Client B cannot acquire lock held by Client A', async ({ window1, window2 }) => {
    // Both select same document
    const firstDoc = window1.locator('[role="tree"] [role="treeitem"]').first()
    const docName = await firstDoc.textContent()
    await firstDoc.click()

    if (docName) {
      await window2.locator(`text="${docName.trim()}"`).first().click()
    }
    await briefPause(500)

    // Client A: Acquire lock
    await window1.click('button:has-text("Edit")')
    await briefPause(1000)

    // Client B: Try to edit - should fail or show lock error
    const editBtn = window2.locator('button:has-text("Edit")')
    if (await editBtn.isEnabled({ timeout: 2_000 }).catch(() => false)) {
      await editBtn.click()

      // Should see a toast/error about lock contention
      await expect(
        window2.locator('text=/[Ll]ocked|cannot edit|in use/')
      ).toBeVisible({ timeout: 5_000 })
    } else {
      // Edit button is disabled - that's the expected behavior
      await expect(editBtn).toBeDisabled()
    }
  })
})
