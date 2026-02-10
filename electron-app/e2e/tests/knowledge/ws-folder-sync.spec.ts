/**
 * WebSocket Folder Sync Tests (2 clients)
 *
 * Validates that folder CRUD operations performed by Client A
 * are reflected in real-time on Client B via WebSocket events.
 */
import { test, expect } from '../../fixtures/two-clients'
import { loginAs, navigateToNotes, TEST_USER_1, TEST_USER_2 } from '../../helpers/auth'
import { waitForWsUpdate, waitForRemoval } from '../../helpers/wait'

test.describe('WebSocket Folder Sync', () => {
  test.beforeEach(async ({ window1, window2 }) => {
    await Promise.all([
      loginAs(window1, TEST_USER_1).then(() => navigateToNotes(window1)),
      loginAs(window2, TEST_USER_2).then(() => navigateToNotes(window2)),
    ])
  })

  test('folder created by Client A appears on Client B via WS', async ({ window1, window2 }) => {
    const folderName = `WS-Folder-${Date.now()}`

    // Client A: Create folder
    await window1.click('button:has-text("New")')
    // Switch to folder creation if dialog has a toggle
    const folderOption = window1.locator('text=Folder')
    if (await folderOption.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await folderOption.click()
    }
    await window1.fill('input[placeholder*="name"], input[placeholder*="title"]', folderName)
    await window1.click('button:has-text("Create")')

    // Client A: Verify folder appears locally
    await expect(window1.locator(`text="${folderName}"`)).toBeVisible({ timeout: 5_000 })

    // Client B: Verify folder appears via WebSocket
    await waitForWsUpdate(window2, `text="${folderName}"`, { timeout: 10_000 })
  })

  test('folder deleted by Client A disappears on Client B via WS', async ({ window1, window2 }) => {
    const folderName = `WS-FolderDel-${Date.now()}`

    // Client A: Create folder
    await window1.click('button:has-text("New")')
    const folderOption = window1.locator('text=Folder')
    if (await folderOption.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await folderOption.click()
    }
    await window1.fill('input[placeholder*="name"], input[placeholder*="title"]', folderName)
    await window1.click('button:has-text("Create")')
    await expect(window1.locator(`text="${folderName}"`)).toBeVisible({ timeout: 5_000 })

    // Client B: Wait for folder to appear
    await waitForWsUpdate(window2, `text="${folderName}"`)

    // Client A: Delete folder via context menu
    await window1.locator(`text="${folderName}"`).click({ button: 'right' })
    await window1.click('text=Delete')
    await window1.click('button:has-text("Delete")')

    // Client A: Verify removed locally
    await waitForRemoval(window1, `text="${folderName}"`)

    // Client B: Verify removed via WebSocket
    await waitForRemoval(window2, `text="${folderName}"`, 10_000)
  })

  test('folder renamed by Client A updates on Client B via WS', async ({ window1, window2 }) => {
    const originalName = `WS-FolderRen-Original-${Date.now()}`
    const renamedName = `WS-FolderRen-Updated-${Date.now()}`

    // Client A: Create folder
    await window1.click('button:has-text("New")')
    const folderOption = window1.locator('text=Folder')
    if (await folderOption.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await folderOption.click()
    }
    await window1.fill('input[placeholder*="name"], input[placeholder*="title"]', originalName)
    await window1.click('button:has-text("Create")')
    await expect(window1.locator(`text="${originalName}"`)).toBeVisible({ timeout: 5_000 })

    // Client B: Wait for it
    await waitForWsUpdate(window2, `text="${originalName}"`)

    // Client A: Rename via context menu
    await window1.locator(`text="${originalName}"`).click({ button: 'right' })
    await window1.click('text=Rename')
    await window1.locator('input[type="text"]').last().fill(renamedName)
    await window1.keyboard.press('Enter')

    // Client A: Verify rename locally
    await expect(window1.locator(`text="${renamedName}"`)).toBeVisible({ timeout: 5_000 })

    // Client B: Verify rename via WebSocket
    await waitForWsUpdate(window2, `text="${renamedName}"`, { timeout: 10_000 })
  })
})
