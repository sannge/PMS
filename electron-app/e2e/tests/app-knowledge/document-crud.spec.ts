/**
 * App Knowledge - Document CRUD Tests (#2.1-2.14)
 *
 * Validates document create, read, update, and delete operations
 * in the Application Detail Knowledge tab, including operations
 * within project sections.
 */
import { test, expect } from '../../fixtures/electron-app'
import { loginAs, TEST_USER_1, navigateToAppKnowledgeTab } from '../../helpers/auth'
import {
  createDocViaUI,
  createFolderViaUI,
  createDocViaContextMenu,
  renameViaContextMenu,
  deleteViaContextMenu,
  selectTreeItem,
  getTreeItem,
  getTreeItems,
  expandFolder,
  expandProjectSection,
} from '../../helpers/knowledge-ops'
import { waitForNetworkIdle, briefPause } from '../../helpers/wait'

const APP_NAME = 'E2E Test App'
const PROJECT_NAME = 'E2E Test Project'

test.beforeEach(async ({ window }) => {
  await loginAs(window, TEST_USER_1)
  await navigateToAppKnowledgeTab(window, APP_NAME)
})

test.describe('App Knowledge - Document CRUD', () => {
  // ============================================================================
  // Shared Document CRUD (#2.1-2.11)
  // ============================================================================

  test('#2.1 Create document via toolbar button', async ({ window }) => {
    const docName = `Create-Doc-${Date.now()}`

    await createDocViaUI(window, docName)

    // Verify the document appears in the tree
    const item = getTreeItem(window, docName)
    await expect(item).toBeVisible({ timeout: 5_000 })
  })

  test('#2.2 Create document via context menu on folder', async ({ window }) => {
    const ts = Date.now()
    const folderName = `CtxFolder-${ts}`
    const docName = `CtxDoc-${ts}`

    // Create a folder first
    await createFolderViaUI(window, folderName)

    // Create a document inside the folder via context menu
    await createDocViaContextMenu(window, folderName, docName)

    // Expand folder and verify doc is inside
    await expandFolder(window, folderName)
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })
  })

  test('#2.3 Create document — cancel dialog', async ({ window }) => {
    // Click the new document button
    const newDocBtn = window.locator(
      'button[aria-label="New document"], button:has(svg.lucide-file-plus)'
    )
    await newDocBtn.first().click()

    // Wait for dialog
    await window.waitForSelector(
      'input[placeholder*="title"], input[placeholder*="name"], input[placeholder*="document"]',
      { timeout: 5_000 }
    )

    // Fill in a name but then cancel
    const docName = `Cancelled-Doc-${Date.now()}`
    await window.fill(
      'input[placeholder*="title"], input[placeholder*="name"], input[placeholder*="document"]',
      docName
    )

    // Cancel the dialog
    await window.keyboard.press('Escape')

    // Verify dialog closed and doc was NOT created
    await briefPause(500)
    const items = window.locator(`[role="treeitem"]:has-text("${docName}")`)
    const count = await items.count()
    expect(count).toBe(0)
  })

  test('#2.4 Create document — empty name rejected', async ({ window }) => {
    // Click the new document button
    const newDocBtn = window.locator(
      'button[aria-label="New document"], button:has(svg.lucide-file-plus)'
    )
    await newDocBtn.first().click()

    // Wait for dialog
    await window.waitForSelector(
      'input[placeholder*="title"], input[placeholder*="name"], input[placeholder*="document"]',
      { timeout: 5_000 }
    )

    // Leave the name empty and try to submit
    await window.click('button:has-text("Create")')

    // Expect an error message or the dialog to remain open
    const errorOrDialog = window.locator(
      'text=/required|cannot be empty|enter a name/i, [role="dialog"]'
    )
    await expect(errorOrDialog.first()).toBeVisible({ timeout: 3_000 })

    // Close dialog
    await window.keyboard.press('Escape')
  })

  test('#2.5 Select document shows content in editor', async ({ window }) => {
    const docName = `View-Doc-${Date.now()}`

    await createDocViaUI(window, docName)
    await selectTreeItem(window, docName)

    // The editor panel should show the document title or content area
    const editor = window.locator(
      '[data-editor], [class*="ProseMirror"], [class*="tiptap"], [contenteditable]'
    )
    await expect(editor.first()).toBeVisible({ timeout: 10_000 })
  })

  test('#2.6 Rename document via context menu', async ({ window }) => {
    const ts = Date.now()
    const originalName = `Rename-Original-${ts}`
    const newName = `Rename-Updated-${ts}`

    await createDocViaUI(window, originalName)
    await expect(getTreeItem(window, originalName)).toBeVisible()

    // Rename via context menu
    await renameViaContextMenu(window, originalName, newName)

    // Verify old name gone, new name present
    await expect(getTreeItem(window, newName)).toBeVisible({ timeout: 5_000 })
    await expect(
      window.locator(`[role="treeitem"]:has-text("${originalName}")`)
    ).not.toBeVisible({ timeout: 3_000 })
  })

  test('#2.7 Rename document to empty name is rejected', async ({ window }) => {
    const docName = `Rename-Empty-${Date.now()}`

    await createDocViaUI(window, docName)

    // Open context menu and click rename
    await window.locator(`text="${docName}"`).first().click({ button: 'right' })
    await window.click('text=Rename')

    // Try to set an empty name
    const renameInput = window.locator('[role="tree"] input[type="text"]').last()
    await renameInput.waitFor({ state: 'visible', timeout: 3_000 })
    await renameInput.fill('')
    await window.keyboard.press('Enter')

    // Expect the rename to be rejected — original name should persist
    await briefPause(500)
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })
  })

  test('#2.8 Delete document via context menu', async ({ window }) => {
    const docName = `Delete-Doc-${Date.now()}`

    await createDocViaUI(window, docName)
    await expect(getTreeItem(window, docName)).toBeVisible()

    // Delete via context menu
    await deleteViaContextMenu(window, docName)

    // Verify the document is removed from the tree
    await expect(
      window.locator(`[role="treeitem"]:has-text("${docName}")`)
    ).not.toBeVisible({ timeout: 5_000 })
  })

  test('#2.9 Delete document shows confirmation dialog', async ({ window }) => {
    const docName = `Delete-Confirm-${Date.now()}`

    await createDocViaUI(window, docName)

    // Right-click and delete
    await window.locator(`text="${docName}"`).first().click({ button: 'right' })
    await window.click('text=Delete')

    // Confirm dialog should appear
    const dialog = window.locator('[role="alertdialog"], [role="dialog"]')
    await expect(dialog.first()).toBeVisible({ timeout: 3_000 })

    // Dialog should have a confirm/delete button
    const confirmBtn = window.locator('button:has-text("Delete")').last()
    await expect(confirmBtn).toBeVisible()

    // Cancel the deletion
    const cancelBtn = window.locator('button:has-text("Cancel")')
    if (await cancelBtn.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await cancelBtn.click()
    } else {
      await window.keyboard.press('Escape')
    }

    // Document should still be present
    await expect(getTreeItem(window, docName)).toBeVisible()
  })

  test('#2.10 Delete last document returns to empty state', async ({ window }) => {
    // This test creates a doc, then deletes it, checking if empty state returns
    const docName = `Last-Doc-${Date.now()}`

    await createDocViaUI(window, docName)
    await expect(getTreeItem(window, docName)).toBeVisible()

    await deleteViaContextMenu(window, docName)

    // Check if tree is now empty
    const treeItems = getTreeItems(window)
    const count = await treeItems.count()

    if (count === 0) {
      // Empty state should reappear
      const emptyState = window.locator(
        'text=/No documents yet|No documents|Get started/'
      )
      await expect(emptyState.first()).toBeVisible({ timeout: 5_000 })
    }
  })

  test('#2.11 Newly created document is auto-selected', async ({ window }) => {
    const docName = `AutoSelect-Doc-${Date.now()}`

    await createDocViaUI(window, docName)

    // The newly created doc should be selected (aria-selected or highlighted)
    const item = getTreeItem(window, docName)
    await expect(item).toBeVisible({ timeout: 5_000 })

    // Check if selected
    const isSelected = await item.getAttribute('aria-selected')
    const hasSelectedClass = await item.evaluate(el =>
      el.classList.contains('selected') ||
      el.getAttribute('data-selected') === 'true' ||
      el.getAttribute('aria-selected') === 'true'
    )

    expect(isSelected === 'true' || hasSelectedClass).toBe(true)
  })

  // ============================================================================
  // Project Section Document CRUD (#2.12-2.14)
  // ============================================================================

  test('#2.12 Create document inside project section', async ({ window }) => {
    const ts = Date.now()
    const docName = `Proj-Doc-${ts}`

    // Expand the project section
    await expandProjectSection(window, PROJECT_NAME)
    await briefPause(500)

    // Create a document inside the project section
    await createDocViaUI(window, docName)

    // Verify the document appears within the project section
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })
  })

  test('#2.13 Rename document in project section', async ({ window }) => {
    const ts = Date.now()
    const originalName = `ProjRename-Orig-${ts}`
    const newName = `ProjRename-New-${ts}`

    // Expand project section and create a doc
    await expandProjectSection(window, PROJECT_NAME)
    await briefPause(500)
    await createDocViaUI(window, originalName)
    await expect(getTreeItem(window, originalName)).toBeVisible()

    // Rename the document
    await renameViaContextMenu(window, originalName, newName)

    // Verify rename
    await expect(getTreeItem(window, newName)).toBeVisible({ timeout: 5_000 })
    await expect(
      window.locator(`[role="treeitem"]:has-text("${originalName}")`)
    ).not.toBeVisible({ timeout: 3_000 })
  })

  test('#2.14 Delete document from project section', async ({ window }) => {
    const ts = Date.now()
    const docName = `ProjDelete-Doc-${ts}`

    // Expand project section and create a doc
    await expandProjectSection(window, PROJECT_NAME)
    await briefPause(500)
    await createDocViaUI(window, docName)
    await expect(getTreeItem(window, docName)).toBeVisible()

    // Delete the document
    await deleteViaContextMenu(window, docName)

    // Verify removal
    await expect(
      window.locator(`[role="treeitem"]:has-text("${docName}")`)
    ).not.toBeVisible({ timeout: 5_000 })
  })
})
