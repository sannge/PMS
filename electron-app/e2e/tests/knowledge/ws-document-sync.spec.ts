/**
 * WebSocket Document Sync Tests (2 clients)
 *
 * Validates that document CRUD operations performed by Client A
 * are reflected in real-time on Client B via WebSocket events.
 */
import { test, expect } from '../../fixtures/two-clients'
import { loginAs, navigateToNotes, TEST_USER_1, TEST_USER_2 } from '../../helpers/auth'
import { waitForWsUpdate, waitForRemoval, briefPause } from '../../helpers/wait'

test.describe('WebSocket Document Sync', () => {
  // Setup: Both clients logged in and on Notes page
  test.beforeEach(async ({ window1, window2 }) => {
    await Promise.all([
      loginAs(window1, TEST_USER_1).then(() => navigateToNotes(window1)),
      loginAs(window2, TEST_USER_2).then(() => navigateToNotes(window2)),
    ])
  })

  test('document created by Client A appears on Client B via WS', async ({ window1, window2 }) => {
    const docTitle = `WS-Test-Doc-${Date.now()}`

    // Client A: Create a new document
    await window1.click('button:has-text("New")')
    await window1.fill('input[placeholder*="title"], input[placeholder*="name"]', docTitle)
    await window1.click('button:has-text("Create")')

    // Client A: Verify doc appears locally (optimistic update)
    await expect(window1.locator(`text="${docTitle}"`)).toBeVisible({ timeout: 5_000 })

    // Client B: Verify doc appears via WebSocket
    await waitForWsUpdate(window2, `text="${docTitle}"`, { timeout: 10_000 })
    await expect(window2.locator(`text="${docTitle}"`)).toBeVisible()
  })

  test('document deleted by Client A disappears on Client B via WS', async ({ window1, window2 }) => {
    const docTitle = `WS-Delete-Test-${Date.now()}`

    // Client A: Create a document first
    await window1.click('button:has-text("New")')
    await window1.fill('input[placeholder*="title"], input[placeholder*="name"]', docTitle)
    await window1.click('button:has-text("Create")')
    await expect(window1.locator(`text="${docTitle}"`)).toBeVisible({ timeout: 5_000 })

    // Client B: Wait for doc to appear
    await waitForWsUpdate(window2, `text="${docTitle}"`)

    // Client A: Delete the document via context menu
    await window1.locator(`text="${docTitle}"`).click({ button: 'right' })
    await window1.click('text=Delete')
    // Confirm deletion dialog
    await window1.click('button:has-text("Delete")')

    // Client A: Verify doc removed locally (optimistic)
    await waitForRemoval(window1, `text="${docTitle}"`)

    // Client B: Verify doc removed via WebSocket
    await waitForRemoval(window2, `text="${docTitle}"`, 10_000)
  })

  test('document renamed by Client A updates on Client B via WS', async ({ window1, window2 }) => {
    const originalTitle = `WS-Rename-Original-${Date.now()}`
    const renamedTitle = `WS-Rename-Updated-${Date.now()}`

    // Client A: Create document
    await window1.click('button:has-text("New")')
    await window1.fill('input[placeholder*="title"], input[placeholder*="name"]', originalTitle)
    await window1.click('button:has-text("Create")')
    await expect(window1.locator(`text="${originalTitle}"`)).toBeVisible({ timeout: 5_000 })

    // Client B: Wait for it
    await waitForWsUpdate(window2, `text="${originalTitle}"`)

    // Client A: Rename via context menu
    await window1.locator(`text="${originalTitle}"`).click({ button: 'right' })
    await window1.click('text=Rename')
    await window1.locator('input[type="text"]').last().fill(renamedTitle)
    await window1.keyboard.press('Enter')

    // Client A: Verify rename locally
    await expect(window1.locator(`text="${renamedTitle}"`)).toBeVisible({ timeout: 5_000 })

    // Client B: Verify rename via WebSocket
    await waitForWsUpdate(window2, `text="${renamedTitle}"`, { timeout: 10_000 })
  })
})
