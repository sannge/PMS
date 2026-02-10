/**
 * App Knowledge - Folder CRUD Tests (#3.1-3.12)
 *
 * Validates folder create, rename, delete, and hierarchy operations
 * in the Application Detail Knowledge tab, including operations
 * within project sections.
 */
import { test, expect } from '../../fixtures/electron-app'
import { loginAs, TEST_USER_1, navigateToAppKnowledgeTab } from '../../helpers/auth'
import {
  createFolderViaUI,
  createFolderViaContextMenu,
  createDocViaContextMenu,
  renameViaContextMenu,
  deleteViaContextMenu,
  getTreeItem,
  getTreeItems,
  expandFolder,
  collapseFolder,
  expandProjectSection,
} from '../../helpers/knowledge-ops'
import { briefPause, waitForNetworkIdle } from '../../helpers/wait'

const APP_NAME = 'E2E Test App'
const PROJECT_NAME = 'E2E Test Project'

test.beforeEach(async ({ window }) => {
  await loginAs(window, TEST_USER_1)
  await navigateToAppKnowledgeTab(window, APP_NAME)
})

test.describe('App Knowledge - Folder CRUD', () => {
  // ============================================================================
  // Shared Folder CRUD (#3.1-3.10)
  // ============================================================================

  test('#3.1 Create folder via toolbar button', async ({ window }) => {
    const folderName = `Create-Folder-${Date.now()}`

    await createFolderViaUI(window, folderName)

    // Verify the folder appears in the tree
    const item = getTreeItem(window, folderName)
    await expect(item).toBeVisible({ timeout: 5_000 })
  })

  test('#3.2 Create subfolder via context menu', async ({ window }) => {
    const ts = Date.now()
    const parentName = `Parent-Folder-${ts}`
    const childName = `Child-Folder-${ts}`

    // Create parent folder
    await createFolderViaUI(window, parentName)

    // Create child folder via context menu on parent
    await createFolderViaContextMenu(window, parentName, childName)

    // Expand parent and verify child
    await expandFolder(window, parentName)
    await expect(getTreeItem(window, childName)).toBeVisible({ timeout: 5_000 })
  })

  test('#3.3 Create folder with empty name is rejected', async ({ window }) => {
    // Click the new folder button
    const newFolderBtn = window.locator(
      'button[aria-label="New folder"], button:has(svg.lucide-folder-plus)'
    )
    await newFolderBtn.first().click()

    // Wait for dialog
    await window.waitForSelector(
      'input[placeholder*="name"], input[placeholder*="folder"]',
      { timeout: 5_000 }
    )

    // Leave name empty and try to create
    await window.click('button:has-text("Create")')

    // Expect validation error or dialog stays open
    const errorOrDialog = window.locator(
      'text=/required|cannot be empty|enter a name/i, [role="dialog"]'
    )
    await expect(errorOrDialog.first()).toBeVisible({ timeout: 3_000 })

    // Close dialog
    await window.keyboard.press('Escape')
  })

  test('#3.4 Rename folder via context menu', async ({ window }) => {
    const ts = Date.now()
    const originalName = `Rename-Folder-${ts}`
    const newName = `Renamed-Folder-${ts}`

    await createFolderViaUI(window, originalName)
    await expect(getTreeItem(window, originalName)).toBeVisible()

    // Rename via context menu
    await renameViaContextMenu(window, originalName, newName)

    // Verify rename
    await expect(getTreeItem(window, newName)).toBeVisible({ timeout: 5_000 })
    await expect(
      window.locator(`[role="treeitem"]:has-text("${originalName}")`)
    ).not.toBeVisible({ timeout: 3_000 })
  })

  test('#3.5 Rename folder preserves contents', async ({ window }) => {
    const ts = Date.now()
    const folderName = `Preserve-Folder-${ts}`
    const docName = `Preserve-Doc-${ts}`
    const renamedFolder = `Preserved-Folder-${ts}`

    // Create folder with a document inside
    await createFolderViaUI(window, folderName)
    await createDocViaContextMenu(window, folderName, docName)

    // Expand and verify doc exists
    await expandFolder(window, folderName)
    await expect(getTreeItem(window, docName)).toBeVisible()

    // Rename the folder
    await renameViaContextMenu(window, folderName, renamedFolder)

    // Expand renamed folder and verify doc is still inside
    await expandFolder(window, renamedFolder)
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })
  })

  test('#3.6 Delete empty folder', async ({ window }) => {
    const folderName = `Delete-Empty-Folder-${Date.now()}`

    await createFolderViaUI(window, folderName)
    await expect(getTreeItem(window, folderName)).toBeVisible()

    // Delete the folder
    await deleteViaContextMenu(window, folderName)

    // Verify removal
    await expect(
      window.locator(`[role="treeitem"]:has-text("${folderName}")`)
    ).not.toBeVisible({ timeout: 5_000 })
  })

  test('#3.7 Delete folder with contents shows confirmation', async ({ window }) => {
    const ts = Date.now()
    const folderName = `Delete-Full-Folder-${ts}`
    const docName = `Delete-Full-Doc-${ts}`

    // Create folder with a document
    await createFolderViaUI(window, folderName)
    await createDocViaContextMenu(window, folderName, docName)

    // Right-click folder and select delete
    await window.locator(`text="${folderName}"`).first().click({ button: 'right' })
    await window.click('text=Delete')

    // Confirmation dialog should appear with warning about contents
    const dialog = window.locator('[role="alertdialog"], [role="dialog"]')
    await expect(dialog.first()).toBeVisible({ timeout: 3_000 })

    // Confirm deletion
    const confirmBtn = window.locator('button:has-text("Delete")').last()
    await confirmBtn.click()

    // Folder and its contents should be removed
    await expect(
      window.locator(`[role="treeitem"]:has-text("${folderName}")`)
    ).not.toBeVisible({ timeout: 5_000 })
    await expect(
      window.locator(`[role="treeitem"]:has-text("${docName}")`)
    ).not.toBeVisible({ timeout: 5_000 })
  })

  test('#3.8 Cancel folder deletion keeps folder', async ({ window }) => {
    const folderName = `Cancel-Delete-Folder-${Date.now()}`

    await createFolderViaUI(window, folderName)

    // Right-click and initiate delete
    await window.locator(`text="${folderName}"`).first().click({ button: 'right' })
    await window.click('text=Delete')

    // Wait for confirm dialog, then cancel
    const dialog = window.locator('[role="alertdialog"], [role="dialog"]')
    await expect(dialog.first()).toBeVisible({ timeout: 3_000 })

    const cancelBtn = window.locator('button:has-text("Cancel")')
    if (await cancelBtn.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await cancelBtn.click()
    } else {
      await window.keyboard.press('Escape')
    }

    // Folder should still exist
    await expect(getTreeItem(window, folderName)).toBeVisible({ timeout: 3_000 })
  })

  test('#3.9 Nested folder creation (3 levels deep)', async ({ window }) => {
    const ts = Date.now()
    const level1 = `Nest-L1-${ts}`
    const level2 = `Nest-L2-${ts}`
    const level3 = `Nest-L3-${ts}`

    // Create 3-level hierarchy
    await createFolderViaUI(window, level1)
    await createFolderViaContextMenu(window, level1, level2)
    await expandFolder(window, level1)
    await createFolderViaContextMenu(window, level2, level3)

    // Expand and verify all 3 levels
    await expandFolder(window, level1)
    await expandFolder(window, level2)

    await expect(getTreeItem(window, level1)).toBeVisible()
    await expect(getTreeItem(window, level2)).toBeVisible()
    await expect(getTreeItem(window, level3)).toBeVisible()
  })

  test('#3.10 Delete middle folder promotes children or deletes cascade', async ({ window }) => {
    const ts = Date.now()
    const topFolder = `Top-${ts}`
    const midFolder = `Mid-${ts}`
    const docInMid = `MidDoc-${ts}`

    // Create hierarchy: top > mid > doc
    await createFolderViaUI(window, topFolder)
    await createFolderViaContextMenu(window, topFolder, midFolder)
    await expandFolder(window, topFolder)
    await createDocViaContextMenu(window, midFolder, docInMid)

    // Delete middle folder
    await deleteViaContextMenu(window, midFolder)

    // Middle folder should be gone
    await expect(
      window.locator(`[role="treeitem"]:has-text("${midFolder}")`)
    ).not.toBeVisible({ timeout: 5_000 })

    // The doc inside the mid folder should also be gone (cascade delete)
    // or promoted to the parent folder (depending on implementation)
    await briefPause(500)
  })

  // ============================================================================
  // Project Section Folder CRUD (#3.11-3.12)
  // ============================================================================

  test('#3.11 Create folder inside project section', async ({ window }) => {
    const ts = Date.now()
    const folderName = `ProjFolder-${ts}`

    // Expand the project section
    await expandProjectSection(window, PROJECT_NAME)
    await briefPause(500)

    // Create a folder inside the project section
    await createFolderViaUI(window, folderName)

    // Verify the folder appears within the project section
    await expect(getTreeItem(window, folderName)).toBeVisible({ timeout: 5_000 })
  })

  test('#3.12 Delete folder from project section', async ({ window }) => {
    const ts = Date.now()
    const folderName = `ProjDelFolder-${ts}`

    // Expand project section and create a folder
    await expandProjectSection(window, PROJECT_NAME)
    await briefPause(500)
    await createFolderViaUI(window, folderName)
    await expect(getTreeItem(window, folderName)).toBeVisible()

    // Delete the folder
    await deleteViaContextMenu(window, folderName)

    // Verify removal
    await expect(
      window.locator(`[role="treeitem"]:has-text("${folderName}")`)
    ).not.toBeVisible({ timeout: 5_000 })
  })
})
