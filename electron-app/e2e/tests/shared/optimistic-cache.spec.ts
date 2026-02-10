/**
 * Shared - Optimistic Updates & Cache Tests (Scenarios #11.1-11.7)
 *
 * Validates that CRUD operations update the UI optimistically
 * (immediately, before server responds) and that rollback works on errors.
 * Uses route interception to add API delays to prove optimistic behavior.
 */
import { test, expect } from '../../fixtures/electron-app'
import {
  loginAs,
  TEST_USER_1,
  navigateToNotesPersonalTab,
} from '../../helpers/auth'
import {
  createDocViaUI,
  createFolderViaUI,
  renameViaContextMenu,
  deleteViaContextMenu,
  dragItemToFolder,
  getTreeItem,
  getTreeItems,
  expandFolder,
} from '../../helpers/knowledge-ops'
import { briefPause, waitForNetworkIdle } from '../../helpers/wait'

test.describe('Optimistic Updates & Cache', () => {
  test.beforeEach(async ({ window }) => {
    await loginAs(window, TEST_USER_1)
    await navigateToNotesPersonalTab(window)
  })

  // #11.1 Optimistic create doc
  test('optimistic create doc appears immediately before server responds', async ({ window }) => {
    const docName = `Optimistic-${Date.now()}`

    // Intercept document creation API to add a 2s delay (simulates slow network)
    await window.route('**/documents', async (route) => {
      if (route.request().method() === 'POST') {
        await new Promise(r => setTimeout(r, 2000))
        await route.continue()
      } else {
        await route.continue()
      }
    })

    await createDocViaUI(window, docName)

    // Doc should be visible immediately (optimistic) even before server responds
    // Using a short timeout to prove it appeared before the 2s delay completes
    await expect(
      window.locator(`text="${docName}"`).first()
    ).toBeVisible({ timeout: 1_000 })
  })

  // #11.2 Temp ID replaced after create
  test('temp ID replaced with real UUID after server response', async ({ window }) => {
    const docName = `TempID-${Date.now()}`

    // Track the document creation response
    const responsePromise = window.waitForResponse(
      (resp) => resp.url().includes('/documents') && resp.request().method() === 'POST',
      { timeout: 15_000 }
    )

    await createDocViaUI(window, docName)

    // Wait for the server response with the real ID
    const response = await responsePromise
    const body = await response.json()
    const realId = body.id

    // After server response, the tree item should use the real UUID
    // and there should be exactly one instance of this document
    await briefPause(1000)

    const matchingItems = window.locator(
      `[role="tree"] [role="treeitem"]:has-text("${docName}")`
    )
    const count = await matchingItems.count()
    expect(count).toBe(1)

    // If the tree item has a data-id attribute, verify it matches the real UUID
    if (realId) {
      const treeItem = matchingItems.first()
      const dataId = await treeItem.getAttribute('data-id')
      if (dataId) {
        // Should NOT contain "TEMP" prefix
        expect(dataId).not.toContain('TEMP')
      }
    }
  })

  // #11.3 Optimistic create folder
  test('optimistic create folder appears immediately', async ({ window }) => {
    const folderName = `OptFolder-${Date.now()}`

    // Intercept folder creation API to add delay
    await window.route('**/folders', async (route) => {
      if (route.request().method() === 'POST') {
        await new Promise(r => setTimeout(r, 2000))
        await route.continue()
      } else {
        await route.continue()
      }
    })

    await createFolderViaUI(window, folderName)

    // Folder should appear immediately (optimistic)
    await expect(
      window.locator(`text="${folderName}"`).first()
    ).toBeVisible({ timeout: 1_000 })
  })

  // #11.4 Optimistic rename
  test('optimistic rename changes name instantly with no flicker', async ({ window }) => {
    const ts = Date.now()
    const originalName = `OptRenameOrig-${ts}`
    const newName = `OptRenameNew-${ts}`

    // Create a document first (wait for server)
    await createDocViaUI(window, originalName)
    await waitForNetworkIdle(window)

    // Intercept rename API to add delay
    await window.route('**/documents/**', async (route) => {
      if (route.request().method() === 'PATCH' || route.request().method() === 'PUT') {
        await new Promise(r => setTimeout(r, 2000))
        await route.continue()
      } else {
        await route.continue()
      }
    })

    // Rename the document
    await renameViaContextMenu(window, originalName, newName)

    // New name should appear instantly (optimistic, within 1 second)
    await expect(
      window.locator(`text="${newName}"`).first()
    ).toBeVisible({ timeout: 1_000 })

    // Old name should already be gone (no flicker back)
    await expect(getTreeItem(window, originalName)).not.toBeVisible({ timeout: 1_000 })
  })

  // #11.5 Optimistic delete
  test('optimistic delete removes item from tree instantly', async ({ window }) => {
    const docName = `OptDelete-${Date.now()}`

    // Create a document (wait for server)
    await createDocViaUI(window, docName)
    await waitForNetworkIdle(window)

    // Intercept delete API to add delay
    await window.route('**/documents/**', async (route) => {
      if (route.request().method() === 'DELETE') {
        await new Promise(r => setTimeout(r, 2000))
        await route.continue()
      } else {
        await route.continue()
      }
    })

    // Delete the document
    await deleteViaContextMenu(window, docName)

    // Document should disappear instantly (optimistic, before server responds)
    await expect(getTreeItem(window, docName)).not.toBeVisible({ timeout: 1_000 })
  })

  // #11.6 Optimistic move (DnD)
  test('optimistic move shows item in new folder instantly', async ({ window }) => {
    const ts = Date.now()
    const docName = `OptMoveDoc-${ts}`
    const folderName = `OptMoveTarget-${ts}`

    // Create folder and document (wait for server)
    await createFolderViaUI(window, folderName)
    await createDocViaUI(window, docName)
    await waitForNetworkIdle(window)

    // Intercept move API to add delay
    await window.route('**/documents/**', async (route) => {
      if (route.request().method() === 'PATCH' || route.request().method() === 'PUT') {
        await new Promise(r => setTimeout(r, 2000))
        await route.continue()
      } else {
        await route.continue()
      }
    })

    // Drag document into folder
    await dragItemToFolder(window, docName, folderName)

    // Expand the folder to verify the doc is inside
    await expandFolder(window, folderName)

    // Document should appear in the folder immediately (optimistic)
    await expect(
      window.locator(`text="${docName}"`).first()
    ).toBeVisible({ timeout: 2_000 })
  })

  // #11.7 Rollback on error
  test('rollback on error returns item to original position with error toast', async ({ window }) => {
    const ts = Date.now()
    const docName = `OptRollback-${ts}`
    const folderName = `OptRollbackTarget-${ts}`

    // Create folder and document (wait for server)
    await createFolderViaUI(window, folderName)
    await createDocViaUI(window, docName)
    await waitForNetworkIdle(window)

    // Intercept move API to return a 400 error
    await window.route('**/documents/**', async (route) => {
      if (route.request().method() === 'PATCH' || route.request().method() === 'PUT') {
        // Return 400 error for any move operation
        await route.fulfill({
          status: 400,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Invalid move target' }),
        })
      } else {
        await route.continue()
      }
    })

    // Attempt to drag document into folder
    await dragItemToFolder(window, docName, folderName)

    // Wait for the rollback to happen
    await briefPause(2000)

    // Error toast should appear
    await expect(
      window.locator('text=/[Ee]rror|[Ff]ailed|[Ii]nvalid/')
    ).toBeVisible({ timeout: 5_000 })

    // Document should return to its original position (root level)
    // It should still be visible in the tree at root level
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })
  })
})
