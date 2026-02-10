/**
 * Reusable knowledge tree operations for E2E tests.
 * These helpers encapsulate common UI interactions with the knowledge tree.
 */
import { Page, expect, Locator } from '@playwright/test'
import { briefPause } from './wait'

// ============================================================================
// Document Operations
// ============================================================================

/**
 * Create a document via the UI create button.
 * Clicks the FilePlus button (new document), fills the dialog, and submits.
 */
export async function createDocViaUI(
  page: Page,
  name: string,
  opts?: { folderId?: string }
): Promise<void> {
  // Click the new document button (FilePlus icon button)
  const newDocBtn = page.locator('button[title="New document"], button[aria-label="New document"], button:has(svg.lucide-file-plus)')
  await newDocBtn.first().click()

  // Fill the document name in the dialog (input has id="name")
  await page.waitForSelector('[role="dialog"] #name', { timeout: 5_000 })
  await page.fill('[role="dialog"] #name', name)

  // Submit the create form
  await page.click('button:has-text("Create")')

  // Wait for the doc to appear in tree
  await expect(page.locator(`text="${name}"`).first()).toBeVisible({ timeout: 5_000 })
}

/**
 * Create a folder via the UI create button.
 * Clicks the FolderPlus button, fills the dialog, and submits.
 */
export async function createFolderViaUI(
  page: Page,
  name: string
): Promise<void> {
  // Click the new folder button (FolderPlus icon button)
  const newFolderBtn = page.locator('button[title="New folder"], button[aria-label="New folder"], button:has(svg.lucide-folder-plus)')
  await newFolderBtn.first().click()

  // Fill the folder name in the dialog (input has id="name")
  await page.waitForSelector('[role="dialog"] #name', { timeout: 5_000 })
  await page.fill('[role="dialog"] #name', name)

  // Submit
  await page.click('button:has-text("Create")')

  // Wait for the folder to appear in tree
  await expect(page.locator(`text="${name}"`).first()).toBeVisible({ timeout: 5_000 })
}

/**
 * Create a document inside a folder via the context menu.
 * Right-clicks the folder → New Document → fills name → submits.
 */
export async function createDocViaContextMenu(
  page: Page,
  folderName: string,
  docName: string
): Promise<void> {
  await page.locator(`text="${folderName}"`).first().click({ button: 'right' })
  await page.click('text=New Document')

  await page.waitForSelector('[role="dialog"] #name', { timeout: 5_000 })
  await page.fill('[role="dialog"] #name', docName)
  await page.click('button:has-text("Create")')

  await expect(page.locator(`text="${docName}"`).first()).toBeVisible({ timeout: 5_000 })
}

/**
 * Create a subfolder inside a parent folder via the context menu.
 * Right-clicks the parent → New Folder / New Subfolder → fills name → submits.
 */
export async function createFolderViaContextMenu(
  page: Page,
  parentName: string,
  folderName: string
): Promise<void> {
  await page.locator(`text="${parentName}"`).first().click({ button: 'right' })
  // Menu item may say "New Folder" or "New Subfolder"
  const newFolderItem = page.locator('text=/New (Sub)?[Ff]older/')
  await newFolderItem.first().click()

  await page.waitForSelector('[role="dialog"] #name', { timeout: 5_000 })
  await page.fill('[role="dialog"] #name', folderName)
  await page.click('button:has-text("Create")')

  await expect(page.locator(`text="${folderName}"`).first()).toBeVisible({ timeout: 5_000 })
}

// ============================================================================
// Rename / Delete via Context Menu
// ============================================================================

/**
 * Rename an item (folder or document) via the context menu.
 * Right-clicks → Rename → clears + types new name → Enter.
 */
export async function renameViaContextMenu(
  page: Page,
  itemName: string,
  newName: string
): Promise<void> {
  await page.locator(`text="${itemName}"`).first().click({ button: 'right' })
  await page.click('text=Rename')

  // Wait for inline rename input to appear, fill new name
  const renameInput = page.locator('[role="tree"] input[type="text"]').last()
  await renameInput.waitFor({ state: 'visible', timeout: 3_000 })
  await renameInput.fill(newName)
  await page.keyboard.press('Enter')

  // Wait for the new name to appear
  await expect(page.locator(`text="${newName}"`).first()).toBeVisible({ timeout: 5_000 })
}

/**
 * Delete an item via the context menu.
 * Right-clicks → Delete → confirms the delete dialog.
 */
export async function deleteViaContextMenu(
  page: Page,
  itemName: string
): Promise<void> {
  await page.locator(`text="${itemName}"`).first().click({ button: 'right' })
  await page.click('text=Delete')

  // Confirm deletion dialog
  const confirmBtn = page.locator('button:has-text("Delete")').last()
  if (await confirmBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await confirmBtn.click()
  }

  // Wait for item to disappear
  await expect(page.locator(`text="${itemName}"`).first()).not.toBeVisible({ timeout: 5_000 })
}

// ============================================================================
// Edit Mode Operations
// ============================================================================

/**
 * Enter edit mode on the currently selected document.
 * Clicks the "Edit" button → waits for editor to become editable.
 */
export async function enterEditMode(page: Page): Promise<void> {
  await page.click('button:has-text("Edit")')
  // Wait for Save/Cancel buttons to confirm edit mode
  await expect(
    page.locator('button:has-text("Save"), button:has-text("Cancel")').first()
  ).toBeVisible({ timeout: 10_000 })
}

/**
 * Save the current document (click "Save" button).
 */
export async function saveDocument(page: Page): Promise<void> {
  await page.click('button:has-text("Save")')
  // Wait for return to view mode (Edit button reappears)
  await expect(page.locator('button:has-text("Edit")')).toBeVisible({ timeout: 10_000 })
}

/**
 * Cancel editing (click "Cancel" button).
 * If there are unsaved changes, handles the discard dialog.
 */
export async function cancelEdit(page: Page, hasChanges = false): Promise<void> {
  await page.click('button:has-text("Cancel")')

  if (hasChanges) {
    // Discard dialog should appear
    const discardBtn = page.locator('button:has-text("Discard")')
    if (await discardBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await discardBtn.click()
    }
  }

  // Wait for return to view mode
  await expect(page.locator('button:has-text("Edit")')).toBeVisible({ timeout: 10_000 })
}

// ============================================================================
// Drag and Drop Operations
// ============================================================================

/**
 * Drag an item (document or folder) to a target folder.
 * Uses Playwright's drag-and-drop API.
 */
export async function dragItemToFolder(
  page: Page,
  itemName: string,
  folderName: string
): Promise<void> {
  const source = page.locator(`[role="treeitem"]:has-text("${itemName}")`).first()
  const target = page.locator(`[role="treeitem"]:has-text("${folderName}")`).first()

  await source.dragTo(target)
  await briefPause(500)
}

/**
 * Drag an item to the root drop zone (unfiled).
 */
export async function dragItemToRoot(
  page: Page,
  itemName: string
): Promise<void> {
  const source = page.locator(`[role="treeitem"]:has-text("${itemName}")`).first()
  // Root drop zone appears during drag - target the tree root area
  const rootZone = page.locator('[data-root-drop-zone], [role="tree"]').first()

  // Start the drag to activate the root drop zone
  const sourceBox = await source.boundingBox()
  const rootBox = await rootZone.boundingBox()
  if (sourceBox && rootBox) {
    await page.mouse.move(sourceBox.x + sourceBox.width / 2, sourceBox.y + sourceBox.height / 2)
    await page.mouse.down()
    await briefPause(200)
    // Move to bottom of tree area (root drop zone)
    await page.mouse.move(rootBox.x + rootBox.width / 2, rootBox.y + rootBox.height - 10)
    await briefPause(200)
    await page.mouse.up()
  }
  await briefPause(500)
}

// ============================================================================
// Search Operations
// ============================================================================

/**
 * Type a search query into the knowledge tree search bar.
 */
export async function searchTree(page: Page, query: string): Promise<void> {
  const searchInput = page.locator('input[placeholder*="Search"], input[placeholder*="search"], input[type="search"]').first()
  await searchInput.fill(query)
  // Wait for filter to apply
  await briefPause(300)
}

/**
 * Clear the search bar to restore the full tree.
 */
export async function clearSearch(page: Page): Promise<void> {
  const searchInput = page.locator('input[placeholder*="Search"], input[placeholder*="search"], input[type="search"]').first()
  await searchInput.fill('')
  await briefPause(300)
}

// ============================================================================
// Tree Inspection Helpers
// ============================================================================

/**
 * Get all tree items currently visible.
 */
export function getTreeItems(page: Page): Locator {
  return page.locator('[role="tree"] [role="treeitem"]')
}

/**
 * Get a specific tree item by name.
 */
export function getTreeItem(page: Page, name: string): Locator {
  return page.locator(`[role="treeitem"]:has-text("${name}")`).first()
}

/**
 * Click a tree item to select it.
 */
export async function selectTreeItem(page: Page, name: string): Promise<void> {
  await page.locator(`[role="treeitem"]:has-text("${name}")`).first().click()
  await briefPause(300)
}

/**
 * Expand a folder in the tree by clicking its chevron.
 */
export async function expandFolder(page: Page, folderName: string): Promise<void> {
  const folder = page.locator(`[role="treeitem"]:has-text("${folderName}")`).first()
  // Check if already expanded
  const isExpanded = await folder.getAttribute('aria-expanded')
  if (isExpanded !== 'true') {
    await folder.click()
    await briefPause(300)
  }
}

/**
 * Collapse a folder in the tree.
 */
export async function collapseFolder(page: Page, folderName: string): Promise<void> {
  const folder = page.locator(`[role="treeitem"]:has-text("${folderName}")`).first()
  const isExpanded = await folder.getAttribute('aria-expanded')
  if (isExpanded === 'true') {
    await folder.click()
    await briefPause(300)
  }
}

/**
 * Expand a project section in the tree.
 */
export async function expandProjectSection(page: Page, projectName: string): Promise<void> {
  const projectRow = page.locator(`text="${projectName}"`).first()
  await projectRow.click()
  await briefPause(500)
}
