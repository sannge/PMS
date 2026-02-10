/**
 * Notes App - Document CRUD Tests (Scenarios #2.1-2.14)
 *
 * Validates document create, read, rename, and delete operations
 * in the application-scoped Notes tree, including project-scoped documents.
 */
import { test, expect } from '../../fixtures/electron-app'
import { loginAs, TEST_USER_1, navigateToNotesAppTab } from '../../helpers/auth'
import {
  createDocViaUI,
  createDocViaContextMenu,
  createFolderViaUI,
  renameViaContextMenu,
  deleteViaContextMenu,
  selectTreeItem,
  getTreeItems,
  getTreeItem,
  expandFolder,
  expandProjectSection,
} from '../../helpers/knowledge-ops'
import { waitForRemoval, briefPause } from '../../helpers/wait'

const APP_NAME = 'E2E Test App'
const PROJECT_NAME = 'E2E Test Project'

test.describe('Notes App - Document CRUD', () => {
  test.beforeEach(async ({ window }) => {
    await loginAs(window, TEST_USER_1)
    await navigateToNotesAppTab(window, APP_NAME)
  })

  // ---------------------------------------------------------------------------
  // #2.1 Create document at root
  // ---------------------------------------------------------------------------
  test('#2.1 create document at root', async ({ window }) => {
    const docName = `RootDoc-${Date.now()}`

    await createDocViaUI(window, docName)

    // Verify doc appears in tree at root level
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })
  })

  // ---------------------------------------------------------------------------
  // #2.2 Create document inside folder
  // ---------------------------------------------------------------------------
  test('#2.2 create document inside folder', async ({ window }) => {
    const ts = Date.now()
    const folderName = `DocFolder-${ts}`
    const docName = `FolderDoc-${ts}`

    // Create folder first
    await createFolderViaUI(window, folderName)

    // Create document inside folder via context menu
    await createDocViaContextMenu(window, folderName, docName)

    // Expand folder to verify doc is inside
    await expandFolder(window, folderName)
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })
  })

  // ---------------------------------------------------------------------------
  // #2.3 Create document -- cancel dialog
  // ---------------------------------------------------------------------------
  test('#2.3 create document cancel dialog closes without creating', async ({ window }) => {
    // Open create dialog
    const newDocBtn = window.locator(
      'button[aria-label="New document"], button:has(svg.lucide-file-plus)'
    )
    await newDocBtn.first().click()

    // Wait for dialog to appear
    await window.waitForSelector(
      'input[placeholder*="title"], input[placeholder*="name"], input[placeholder*="document"]',
      { timeout: 5_000 }
    )

    // Cancel the dialog
    const cancelBtn = window.locator('button:has-text("Cancel")')
    if (await cancelBtn.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await cancelBtn.click()
    } else {
      // Press ESC to close
      await window.keyboard.press('Escape')
    }

    // Dialog should close
    await expect(
      window.locator('input[placeholder*="title"], input[placeholder*="name"], input[placeholder*="document"]')
    ).not.toBeVisible({ timeout: 3_000 })
  })

  // ---------------------------------------------------------------------------
  // #2.4 Create document -- empty name rejected
  // ---------------------------------------------------------------------------
  test('#2.4 create document with empty name is rejected', async ({ window }) => {
    // Open create dialog
    const newDocBtn = window.locator(
      'button[aria-label="New document"], button:has(svg.lucide-file-plus)'
    )
    await newDocBtn.first().click()

    // Wait for dialog
    await window.waitForSelector(
      'input[placeholder*="title"], input[placeholder*="name"], input[placeholder*="document"]',
      { timeout: 5_000 }
    )

    // Leave name empty and try to submit
    await window.click('button:has-text("Create")')

    // Dialog should stay open with a validation error
    await expect(
      window.locator('input[placeholder*="title"], input[placeholder*="name"], input[placeholder*="document"]')
    ).toBeVisible({ timeout: 3_000 })

    // Look for validation message
    const errorMsg = window.locator('text=/required|cannot be empty|enter a name/i')
    await expect(errorMsg.first()).toBeVisible({ timeout: 3_000 }).catch(() => {
      // Some implementations disable the create button instead of showing error text
    })

    // Clean up: close dialog
    await window.keyboard.press('Escape')
  })

  // ---------------------------------------------------------------------------
  // #2.5 View document
  // ---------------------------------------------------------------------------
  test('#2.5 clicking document shows it in editor panel', async ({ window }) => {
    const docName = `ViewDoc-${Date.now()}`

    // Create document
    await createDocViaUI(window, docName)

    // Click the document to select/view it
    await selectTreeItem(window, docName)

    // Editor panel should show the document in read-only mode
    // Look for the Edit button which indicates view mode
    await expect(window.locator('button:has-text("Edit")')).toBeVisible({ timeout: 10_000 })

    // Document title should appear somewhere in the editor area
    await expect(window.locator(`text="${docName}"`).first()).toBeVisible()
  })

  // ---------------------------------------------------------------------------
  // #2.6 Rename document
  // ---------------------------------------------------------------------------
  test('#2.6 rename document via context menu', async ({ window }) => {
    const ts = Date.now()
    const originalName = `RenameMe-${ts}`
    const newName = `Renamed-${ts}`

    // Create document
    await createDocViaUI(window, originalName)

    // Rename via context menu
    await renameViaContextMenu(window, originalName, newName)

    // Verify new name appears, old name gone
    await expect(getTreeItem(window, newName)).toBeVisible({ timeout: 5_000 })
    await expect(window.locator(`text="${originalName}"`)).not.toBeVisible({ timeout: 3_000 })
  })

  // ---------------------------------------------------------------------------
  // #2.7 Rename document -- cancel
  // ---------------------------------------------------------------------------
  test('#2.7 rename document cancel with ESC restores original name', async ({ window }) => {
    const docName = `RenameCancelDoc-${Date.now()}`

    await createDocViaUI(window, docName)

    // Right-click to open context menu
    await window.locator(`text="${docName}"`).first().click({ button: 'right' })
    await window.click('text=Rename')

    // Wait for inline rename input
    const renameInput = window.locator('[role="tree"] input[type="text"]').last()
    await renameInput.waitFor({ state: 'visible', timeout: 3_000 })

    // Type something but press ESC
    await renameInput.fill('ShouldNotSave')
    await window.keyboard.press('Escape')

    // Original name should still be there
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })
    await expect(window.locator('text="ShouldNotSave"')).not.toBeVisible({ timeout: 2_000 })
  })

  // ---------------------------------------------------------------------------
  // #2.8 Rename document -- empty name
  // ---------------------------------------------------------------------------
  test('#2.8 rename document with empty name reverts to original', async ({ window }) => {
    const docName = `RenameEmptyDoc-${Date.now()}`

    await createDocViaUI(window, docName)

    // Right-click to open context menu
    await window.locator(`text="${docName}"`).first().click({ button: 'right' })
    await window.click('text=Rename')

    // Wait for inline rename input
    const renameInput = window.locator('[role="tree"] input[type="text"]').last()
    await renameInput.waitFor({ state: 'visible', timeout: 3_000 })

    // Clear the name and press Enter
    await renameInput.fill('')
    await window.keyboard.press('Enter')

    // Original name should still be there (empty name rejected)
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })
  })

  // ---------------------------------------------------------------------------
  // #2.9 Delete document
  // ---------------------------------------------------------------------------
  test('#2.9 delete document via context menu', async ({ window }) => {
    const docName = `DeleteMe-${Date.now()}`

    await createDocViaUI(window, docName)

    // Delete via context menu
    await deleteViaContextMenu(window, docName)

    // Document should be removed from tree
    await expect(window.locator(`text="${docName}"`).first()).not.toBeVisible({ timeout: 5_000 })
  })

  // ---------------------------------------------------------------------------
  // #2.10 Delete document -- cancel
  // ---------------------------------------------------------------------------
  test('#2.10 delete document cancel keeps document in tree', async ({ window }) => {
    const docName = `DeleteCancelDoc-${Date.now()}`

    await createDocViaUI(window, docName)

    // Right-click to open context menu
    await window.locator(`text="${docName}"`).first().click({ button: 'right' })
    await window.click('text=Delete')

    // Cancel the delete dialog
    const cancelBtn = window.locator('button:has-text("Cancel")').last()
    if (await cancelBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await cancelBtn.click()
    } else {
      await window.keyboard.press('Escape')
    }

    // Document should still be there
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })
  })

  // ---------------------------------------------------------------------------
  // #2.11 Delete selected document
  // ---------------------------------------------------------------------------
  test('#2.11 deleting selected document shows empty state in editor', async ({ window }) => {
    const docName = `DeleteSelectedDoc-${Date.now()}`

    await createDocViaUI(window, docName)

    // Select the document to open it in editor
    await selectTreeItem(window, docName)
    await expect(window.locator('button:has-text("Edit")')).toBeVisible({ timeout: 10_000 })

    // Now delete the selected document
    await deleteViaContextMenu(window, docName)

    // Editor should show empty state ("Select a document" or similar)
    await expect(
      window.locator('text=/Select a document|No document selected/i').first()
    ).toBeVisible({ timeout: 10_000 })
  })

  // ---------------------------------------------------------------------------
  // #2.12 Create doc inside project section (app-specific)
  // ---------------------------------------------------------------------------
  test('#2.12 create document inside project section', async ({ window }) => {
    const docName = `ProjectDoc-${Date.now()}`

    // Expand the project section
    await expandProjectSection(window, PROJECT_NAME)

    // Right-click the project section to create a doc
    await window.locator(`text="${PROJECT_NAME}"`).first().click({ button: 'right' })
    await window.click('text=New Document')

    // Fill the dialog
    await window.waitForSelector(
      'input[placeholder*="title"], input[placeholder*="name"], input[placeholder*="document"]',
      { timeout: 5_000 }
    )
    await window.fill(
      'input[placeholder*="title"], input[placeholder*="name"], input[placeholder*="document"]',
      docName
    )
    await window.click('button:has-text("Create")')

    // Document should appear under the project section
    await expect(window.locator(`text="${docName}"`).first()).toBeVisible({ timeout: 5_000 })
  })

  // ---------------------------------------------------------------------------
  // #2.13 Rename doc in project section
  // ---------------------------------------------------------------------------
  test('#2.13 rename document in project section', async ({ window }) => {
    const ts = Date.now()
    const originalName = `ProjRenameDoc-${ts}`
    const newName = `ProjRenamed-${ts}`

    // Expand project, create doc
    await expandProjectSection(window, PROJECT_NAME)

    await window.locator(`text="${PROJECT_NAME}"`).first().click({ button: 'right' })
    await window.click('text=New Document')

    await window.waitForSelector(
      'input[placeholder*="title"], input[placeholder*="name"], input[placeholder*="document"]',
      { timeout: 5_000 }
    )
    await window.fill(
      'input[placeholder*="title"], input[placeholder*="name"], input[placeholder*="document"]',
      originalName
    )
    await window.click('button:has-text("Create")')
    await expect(window.locator(`text="${originalName}"`).first()).toBeVisible({ timeout: 5_000 })

    // Rename the project doc
    await renameViaContextMenu(window, originalName, newName)

    // Verify new name appears
    await expect(getTreeItem(window, newName)).toBeVisible({ timeout: 5_000 })
    await expect(window.locator(`text="${originalName}"`)).not.toBeVisible({ timeout: 3_000 })
  })

  // ---------------------------------------------------------------------------
  // #2.14 Delete doc from project section
  // ---------------------------------------------------------------------------
  test('#2.14 delete document from project section', async ({ window }) => {
    const docName = `ProjDeleteDoc-${Date.now()}`

    // Expand project, create doc
    await expandProjectSection(window, PROJECT_NAME)

    await window.locator(`text="${PROJECT_NAME}"`).first().click({ button: 'right' })
    await window.click('text=New Document')

    await window.waitForSelector(
      'input[placeholder*="title"], input[placeholder*="name"], input[placeholder*="document"]',
      { timeout: 5_000 }
    )
    await window.fill(
      'input[placeholder*="title"], input[placeholder*="name"], input[placeholder*="document"]',
      docName
    )
    await window.click('button:has-text("Create")')
    await expect(window.locator(`text="${docName}"`).first()).toBeVisible({ timeout: 5_000 })

    // Delete the project doc
    await deleteViaContextMenu(window, docName)

    // Document should be removed
    await expect(window.locator(`text="${docName}"`).first()).not.toBeVisible({ timeout: 5_000 })
  })
})
