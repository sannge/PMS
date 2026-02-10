/**
 * WebSocket Folder Sync Tests (2 clients) - Scenarios #12.4-12.6
 *
 * Validates that folder CRUD operations performed by Client A
 * are reflected in real-time on Client B via WebSocket events.
 * Includes cascade behavior: deleting a folder removes its child documents on B.
 */
import { test, expect } from '../../fixtures/two-clients'
import { loginAs, navigateToNotes, TEST_USER_1, TEST_USER_2 } from '../../helpers/auth'
import {
  createFolderViaUI,
  createDocViaContextMenu,
  renameViaContextMenu,
  deleteViaContextMenu,
  expandFolder,
  getTreeItem,
} from '../../helpers/knowledge-ops'
import { waitForWsUpdate, waitForRemoval, briefPause } from '../../helpers/wait'

test.describe('WebSocket Folder Sync', () => {
  test.beforeEach(async ({ window1, window2 }) => {
    await Promise.all([
      loginAs(window1, TEST_USER_1).then(() => navigateToNotes(window1)),
      loginAs(window2, TEST_USER_2).then(() => navigateToNotes(window2)),
    ])
  })

  // #12.4 Folder created by Client A appears on Client B via WebSocket
  test('folder created by A appears on B via WS (#12.4)', async ({ window1, window2 }) => {
    const folderName = `WS-Folder-Create-${Date.now()}`

    // Client A: Create a new folder
    await createFolderViaUI(window1, folderName)

    // Client A: Verify folder appears locally (optimistic update)
    await expect(window1.locator(`text="${folderName}"`).first()).toBeVisible({ timeout: 5_000 })

    // Client B: Verify folder appears via WebSocket broadcast
    await waitForWsUpdate(window2, `text="${folderName}"`, { timeout: 10_000 })
    await expect(window2.locator(`text="${folderName}"`).first()).toBeVisible()
  })

  // #12.5 Folder renamed by Client A updates on Client B via WebSocket
  test('folder renamed by A updates on B via WS (#12.5)', async ({ window1, window2 }) => {
    const originalName = `WS-FolderRen-Orig-${Date.now()}`
    const renamedName = `WS-FolderRen-New-${Date.now()}`

    // Client A: Create folder
    await createFolderViaUI(window1, originalName)

    // Client B: Wait for folder to appear
    await waitForWsUpdate(window2, `text="${originalName}"`, { timeout: 10_000 })

    // Client A: Rename the folder via context menu
    await renameViaContextMenu(window1, originalName, renamedName)

    // Client A: Verify rename locally
    await expect(window1.locator(`text="${renamedName}"`).first()).toBeVisible({ timeout: 5_000 })

    // Client B: Verify renamed name appears via WebSocket
    await waitForWsUpdate(window2, `text="${renamedName}"`, { timeout: 10_000 })

    // Client B: Original name should be gone
    await expect(window2.locator(`text="${originalName}"`).first()).not.toBeVisible({ timeout: 5_000 })
  })

  // #12.6 Folder deleted (with child docs) by Client A disappears on Client B
  test('folder with docs deleted by A removes folder + docs on B (#12.6)', async ({ window1, window2 }) => {
    const ts = Date.now()
    const folderName = `WS-FolderDel-${ts}`
    const childDoc1 = `WS-FolderDoc1-${ts}`
    const childDoc2 = `WS-FolderDoc2-${ts}`

    // Client A: Create folder with two documents inside it
    await createFolderViaUI(window1, folderName)
    await createDocViaContextMenu(window1, folderName, childDoc1)
    await createDocViaContextMenu(window1, folderName, childDoc2)

    // Client B: Wait for folder and child docs to appear
    await waitForWsUpdate(window2, `text="${folderName}"`, { timeout: 10_000 })

    // Client B: Expand folder to verify children arrived
    await expandFolder(window2, folderName)
    await expect(window2.locator(`text="${childDoc1}"`).first()).toBeVisible({ timeout: 10_000 })
    await expect(window2.locator(`text="${childDoc2}"`).first()).toBeVisible({ timeout: 10_000 })

    // Client A: Delete the folder (cascade deletes children)
    await deleteViaContextMenu(window1, folderName)

    // Client A: Verify folder removed locally
    await expect(window1.locator(`text="${folderName}"`).first()).not.toBeVisible({ timeout: 5_000 })

    // Client B: Folder should disappear via WebSocket
    await waitForRemoval(window2, `text="${folderName}"`, 10_000)

    // Client B: Child documents should also be gone
    await expect(window2.locator(`text="${childDoc1}"`).first()).not.toBeVisible({ timeout: 5_000 })
    await expect(window2.locator(`text="${childDoc2}"`).first()).not.toBeVisible({ timeout: 5_000 })
  })
})
