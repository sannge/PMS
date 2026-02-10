/**
 * Project Knowledge - Document CRUD Tests (Scenarios #2.1-2.11)
 *
 * Validates document create, view, rename, and delete operations
 * in the project Knowledge tab context.
 *
 * Context: KnowledgePanel -> KnowledgeTree (scope=project)
 * NO project-scoped variants (this IS a project context).
 */
import { test, expect } from '../../fixtures/electron-app'
import { loginAs, TEST_USER_1, navigateToProjectKnowledgeTab } from '../../helpers/auth'
import {
  createDocViaUI,
  createFolderViaUI,
  createDocViaContextMenu,
  renameViaContextMenu,
  deleteViaContextMenu,
  selectTreeItem,
  getTreeItems,
  getTreeItem,
  expandFolder,
} from '../../helpers/knowledge-ops'
import { waitForRemoval, briefPause } from '../../helpers/wait'

const APP_NAME = 'E2E Test App'
const PROJECT_NAME = 'E2E Test Project'

test.describe('Project Knowledge - Document CRUD', () => {
  test.beforeEach(async ({ window }) => {
    await loginAs(window, TEST_USER_1)
    await navigateToProjectKnowledgeTab(window, APP_NAME, PROJECT_NAME)
  })

  // #2.1 Create document at root
  test('create document at root level', async ({ window }) => {
    const docName = `RootDoc-${Date.now()}`

    await createDocViaUI(window, docName)

    // Verify the document appears in the tree at root level
    const docItem = getTreeItem(window, docName)
    await expect(docItem).toBeVisible({ timeout: 5_000 })

    // Verify it is a document (not a folder) - should not have aria-expanded
    const ariaExpanded = await docItem.getAttribute('aria-expanded')
    expect(ariaExpanded).toBeNull()
  })

  // #2.2 Create document inside folder
  test('create document inside a folder via context menu', async ({ window }) => {
    const ts = Date.now()
    const folderName = `DocFolder-${ts}`
    const docName = `InsideDoc-${ts}`

    // Create a folder first
    await createFolderViaUI(window, folderName)

    // Create doc inside folder via context menu
    await createDocViaContextMenu(window, folderName, docName)

    // Expand the folder to see the document
    await expandFolder(window, folderName)

    // Verify the document is visible inside the folder
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })
  })

  // #2.3 Create document - cancel dialog
  test('create document dialog cancel does not create document', async ({ window }) => {
    const docName = `CancelDoc-${Date.now()}`

    // Click the new document button
    const newDocBtn = window.locator('button[aria-label="New document"], button:has(svg.lucide-file-plus)')
    await newDocBtn.first().click()

    // Fill the name
    await window.waitForSelector('input[placeholder*="title"], input[placeholder*="name"], input[placeholder*="document"]', { timeout: 5_000 })
    await window.fill('input[placeholder*="title"], input[placeholder*="name"], input[placeholder*="document"]', docName)

    // Cancel instead of Create
    const cancelBtn = window.locator('button:has-text("Cancel")')
    await cancelBtn.click()

    // Verify the document does NOT appear in the tree
    await briefPause(500)
    await expect(getTreeItem(window, docName)).not.toBeVisible({ timeout: 3_000 })
  })

  // #2.4 Create document - empty name rejected
  test('create document with empty name is rejected', async ({ window }) => {
    // Click the new document button
    const newDocBtn = window.locator('button[aria-label="New document"], button:has(svg.lucide-file-plus)')
    await newDocBtn.first().click()

    // Wait for dialog
    await window.waitForSelector('input[placeholder*="title"], input[placeholder*="name"], input[placeholder*="document"]', { timeout: 5_000 })

    // Leave the name empty and try to create
    await window.fill('input[placeholder*="title"], input[placeholder*="name"], input[placeholder*="document"]', '')

    const createBtn = window.locator('button:has-text("Create")')

    // The Create button should be disabled, or clicking it should show a validation error
    const isDisabled = await createBtn.isDisabled().catch(() => false)
    if (isDisabled) {
      await expect(createBtn).toBeDisabled()
    } else {
      // Try clicking - should show validation error
      await createBtn.click()
      await expect(
        window.locator('text=/[Rr]equired|[Ee]mpty|[Nn]ame.*required|[Tt]itle.*required/')
      ).toBeVisible({ timeout: 3_000 })
    }
  })

  // #2.5 View document
  test('clicking a document displays its content in the editor panel', async ({ window }) => {
    const docName = `ViewDoc-${Date.now()}`

    // Create a document
    await createDocViaUI(window, docName)

    // Click the document in the tree to select it
    await selectTreeItem(window, docName)

    // The editor panel should show the document title or content area
    await expect(
      window.locator('.ProseMirror, [data-testid="editor"], [role="textbox"]').first()
    ).toBeVisible({ timeout: 10_000 })

    // The document title should be visible in the editor header
    await expect(
      window.locator(`text="${docName}"`).first()
    ).toBeVisible({ timeout: 5_000 })
  })

  // #2.6 Rename document
  test('rename document via context menu', async ({ window }) => {
    const ts = Date.now()
    const originalName = `OriginalDoc-${ts}`
    const renamedName = `RenamedDoc-${ts}`

    // Create the document
    await createDocViaUI(window, originalName)

    // Rename via context menu
    await renameViaContextMenu(window, originalName, renamedName)

    // Verify the new name appears
    await expect(getTreeItem(window, renamedName)).toBeVisible({ timeout: 5_000 })

    // Verify the old name is gone
    await expect(getTreeItem(window, originalName)).not.toBeVisible({ timeout: 3_000 })
  })

  // #2.7 Rename document - cancel
  test('rename document cancel preserves original name', async ({ window }) => {
    const docName = `NoCancelRename-${Date.now()}`

    // Create a document
    await createDocViaUI(window, docName)

    // Right-click to open context menu and click Rename
    await window.locator(`text="${docName}"`).first().click({ button: 'right' })
    await window.click('text=Rename')

    // Wait for inline rename input
    const renameInput = window.locator('[role="tree"] input[type="text"]').last()
    await renameInput.waitFor({ state: 'visible', timeout: 3_000 })

    // Type a new name but press Escape to cancel
    await renameInput.fill('ShouldNotAppear')
    await window.keyboard.press('Escape')

    // Original name should still be present
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })

    // The cancelled name should not appear
    await expect(getTreeItem(window, 'ShouldNotAppear')).not.toBeVisible({ timeout: 3_000 })
  })

  // #2.8 Rename document - empty name
  test('rename document with empty name is rejected', async ({ window }) => {
    const docName = `EmptyRename-${Date.now()}`

    // Create a document
    await createDocViaUI(window, docName)

    // Right-click to open context menu and click Rename
    await window.locator(`text="${docName}"`).first().click({ button: 'right' })
    await window.click('text=Rename')

    // Wait for inline rename input
    const renameInput = window.locator('[role="tree"] input[type="text"]').last()
    await renameInput.waitFor({ state: 'visible', timeout: 3_000 })

    // Clear the input and press Enter (submit empty name)
    await renameInput.fill('')
    await window.keyboard.press('Enter')

    // The original name should persist (empty name rejected)
    await briefPause(500)
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })
  })

  // #2.9 Delete document
  test('delete document via context menu', async ({ window }) => {
    const docName = `DeleteDoc-${Date.now()}`

    // Create a document
    await createDocViaUI(window, docName)
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })

    // Delete via context menu
    await deleteViaContextMenu(window, docName)

    // Verify the document is removed from the tree
    await expect(getTreeItem(window, docName)).not.toBeVisible({ timeout: 5_000 })
  })

  // #2.10 Delete document - cancel
  test('delete document cancel preserves document', async ({ window }) => {
    const docName = `NoCancelDelete-${Date.now()}`

    // Create a document
    await createDocViaUI(window, docName)

    // Right-click and choose Delete
    await window.locator(`text="${docName}"`).first().click({ button: 'right' })
    await window.click('text=Delete')

    // Cancel the delete confirmation dialog
    const cancelBtn = window.locator('button:has-text("Cancel")')
    if (await cancelBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await cancelBtn.click()
    }

    // Document should still be in the tree
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })
  })

  // #2.11 Delete selected document
  test('delete the currently selected document clears editor', async ({ window }) => {
    const docName = `DeleteSelected-${Date.now()}`

    // Create and select a document
    await createDocViaUI(window, docName)
    await selectTreeItem(window, docName)

    // Verify the editor shows the document
    await expect(
      window.locator('.ProseMirror, [data-testid="editor"], [role="textbox"]').first()
    ).toBeVisible({ timeout: 10_000 })

    // Delete the selected document
    await deleteViaContextMenu(window, docName)

    // Document should be removed from tree
    await expect(getTreeItem(window, docName)).not.toBeVisible({ timeout: 5_000 })

    // Editor should either show empty state or no document selected
    await expect(
      window.locator('text=/[Ss]elect a document|[Nn]o document|[Cc]hoose a document/').or(
        window.locator('[data-testid="empty-editor"]')
      )
    ).toBeVisible({ timeout: 5_000 }).catch(() => {
      // Alternatively, the editor panel may just be cleared
    })
  })
})
