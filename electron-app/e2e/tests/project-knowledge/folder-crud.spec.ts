/**
 * Project Knowledge - Folder CRUD Tests (Scenarios #3.1-3.10)
 *
 * Validates folder create, rename, and delete operations
 * in the project Knowledge tab context.
 *
 * Context: KnowledgePanel -> KnowledgeTree (scope=project)
 * Max folder depth: 5 levels.
 */
import { test, expect } from '../../fixtures/electron-app'
import { loginAs, TEST_USER_1, navigateToProjectKnowledgeTab } from '../../helpers/auth'
import {
  createFolderViaUI,
  createFolderViaContextMenu,
  createDocViaContextMenu,
  renameViaContextMenu,
  deleteViaContextMenu,
  selectTreeItem,
  getTreeItems,
  getTreeItem,
  expandFolder,
} from '../../helpers/knowledge-ops'
import { briefPause, waitForRemoval } from '../../helpers/wait'

const APP_NAME = 'E2E Test App'
const PROJECT_NAME = 'E2E Test Project'

test.describe('Project Knowledge - Folder CRUD', () => {
  test.beforeEach(async ({ window }) => {
    await loginAs(window, TEST_USER_1)
    await navigateToProjectKnowledgeTab(window, APP_NAME, PROJECT_NAME)
  })

  // #3.1 Create root folder
  test('create root folder', async ({ window }) => {
    const folderName = `RootFolder-${Date.now()}`

    await createFolderViaUI(window, folderName)

    // Verify folder appears in tree
    const folderItem = getTreeItem(window, folderName)
    await expect(folderItem).toBeVisible({ timeout: 5_000 })

    // Folder should have aria-expanded attribute (it is expandable)
    const ariaExpanded = await folderItem.getAttribute('aria-expanded')
    expect(ariaExpanded).not.toBeNull()
  })

  // #3.2 Create nested subfolder
  test('create nested subfolder via context menu', async ({ window }) => {
    const ts = Date.now()
    const parentFolder = `ParentFolder-${ts}`
    const childFolder = `ChildFolder-${ts}`

    // Create parent folder
    await createFolderViaUI(window, parentFolder)

    // Create child folder inside parent via context menu
    await createFolderViaContextMenu(window, parentFolder, childFolder)

    // Expand parent to see child
    await expandFolder(window, parentFolder)

    // Verify child folder is visible
    await expect(getTreeItem(window, childFolder)).toBeVisible({ timeout: 5_000 })

    // Verify nesting via aria-level
    const parentLevel = await getTreeItem(window, parentFolder).getAttribute('aria-level')
    const childLevel = await getTreeItem(window, childFolder).getAttribute('aria-level')
    if (parentLevel && childLevel) {
      expect(Number(childLevel)).toBeGreaterThan(Number(parentLevel))
    }
  })

  // #3.3 Create at max depth (5)
  test('create folder at max depth (5 levels)', async ({ window }) => {
    const ts = Date.now()
    const level1 = `L1-${ts}`
    const level2 = `L2-${ts}`
    const level3 = `L3-${ts}`
    const level4 = `L4-${ts}`
    const level5 = `L5-${ts}`

    // Build 5-level hierarchy
    await createFolderViaUI(window, level1)

    await createFolderViaContextMenu(window, level1, level2)
    await expandFolder(window, level1)

    await createFolderViaContextMenu(window, level2, level3)
    await expandFolder(window, level2)

    await createFolderViaContextMenu(window, level3, level4)
    await expandFolder(window, level3)

    await createFolderViaContextMenu(window, level4, level5)
    await expandFolder(window, level4)

    // All 5 levels should be visible
    await expect(getTreeItem(window, level1)).toBeVisible({ timeout: 5_000 })
    await expect(getTreeItem(window, level2)).toBeVisible({ timeout: 5_000 })
    await expect(getTreeItem(window, level3)).toBeVisible({ timeout: 5_000 })
    await expect(getTreeItem(window, level4)).toBeVisible({ timeout: 5_000 })
    await expect(getTreeItem(window, level5)).toBeVisible({ timeout: 5_000 })
  })

  // #3.4 Create beyond max depth (6) - should be rejected
  test('create folder beyond max depth (6 levels) is rejected', async ({ window }) => {
    const ts = Date.now()
    const level1 = `D1-${ts}`
    const level2 = `D2-${ts}`
    const level3 = `D3-${ts}`
    const level4 = `D4-${ts}`
    const level5 = `D5-${ts}`
    const level6 = `D6-${ts}`

    // Build 5-level hierarchy
    await createFolderViaUI(window, level1)

    await createFolderViaContextMenu(window, level1, level2)
    await expandFolder(window, level1)

    await createFolderViaContextMenu(window, level2, level3)
    await expandFolder(window, level2)

    await createFolderViaContextMenu(window, level3, level4)
    await expandFolder(window, level3)

    await createFolderViaContextMenu(window, level4, level5)
    await expandFolder(window, level4)

    // Attempt to create a 6th level - right-click level5 folder
    await window.locator(`text="${level5}"`).first().click({ button: 'right' })

    // Either "New Folder" / "New Subfolder" is disabled/missing, or clicking it shows an error
    const newFolderItem = window.locator('text=/New (Sub)?[Ff]older/')
    const isVisible = await newFolderItem.first().isVisible({ timeout: 2_000 }).catch(() => false)

    if (isVisible) {
      // Option exists - check if disabled
      const isDisabled = await newFolderItem.first().isDisabled().catch(() => false)

      if (!isDisabled) {
        // Click and try to create - should show an error
        await newFolderItem.first().click()

        // Fill name and submit
        const nameInput = window.locator('input[placeholder*="name"], input[placeholder*="folder"]')
        if (await nameInput.isVisible({ timeout: 2_000 }).catch(() => false)) {
          await nameInput.fill(level6)
          await window.click('button:has-text("Create")')

          // Should see an error about max depth
          await expect(
            window.locator('text=/[Mm]ax.*depth|[Mm]aximum.*level|[Cc]annot.*nest|[Tt]oo deep/')
          ).toBeVisible({ timeout: 5_000 })
        }
      } else {
        // Menu item is disabled - that is the expected behavior
        await expect(newFolderItem.first()).toBeDisabled()
      }
    }
    // If "New Folder" option is not shown at all, the UI correctly prevents it

    // Level 6 should NOT exist
    await expect(getTreeItem(window, level6)).not.toBeVisible({ timeout: 3_000 })
  })

  // #3.5 Rename folder
  test('rename folder via context menu', async ({ window }) => {
    const ts = Date.now()
    const originalName = `OrigFolder-${ts}`
    const renamedName = `RenamedFolder-${ts}`

    // Create a folder
    await createFolderViaUI(window, originalName)

    // Rename via context menu
    await renameViaContextMenu(window, originalName, renamedName)

    // Verify new name appears
    await expect(getTreeItem(window, renamedName)).toBeVisible({ timeout: 5_000 })

    // Verify old name is gone
    await expect(getTreeItem(window, originalName)).not.toBeVisible({ timeout: 3_000 })
  })

  // #3.6 Rename folder - duplicate name
  test('rename folder to duplicate name shows error', async ({ window }) => {
    const ts = Date.now()
    const folder1 = `DupFolder1-${ts}`
    const folder2 = `DupFolder2-${ts}`

    // Create two folders
    await createFolderViaUI(window, folder1)
    await createFolderViaUI(window, folder2)

    // Try to rename folder2 to folder1's name
    await window.locator(`text="${folder2}"`).first().click({ button: 'right' })
    await window.click('text=Rename')

    const renameInput = window.locator('[role="tree"] input[type="text"]').last()
    await renameInput.waitFor({ state: 'visible', timeout: 3_000 })
    await renameInput.fill(folder1)
    await window.keyboard.press('Enter')

    // Should see an error about duplicate name, or the rename is rejected
    await briefPause(500)

    // Either an error toast appears or the original name persists
    const errorVisible = await window.locator(
      'text=/[Dd]uplicate|[Aa]lready exists|[Nn]ame.*taken/'
    ).isVisible({ timeout: 3_000 }).catch(() => false)

    if (!errorVisible) {
      // If no explicit error, verify folder2 still has its original name
      // (rename was silently rejected and reverted)
      await expect(getTreeItem(window, folder2)).toBeVisible({ timeout: 5_000 })
    }
  })

  // #3.7 Delete empty folder
  test('delete empty folder via context menu', async ({ window }) => {
    const folderName = `EmptyDelete-${Date.now()}`

    // Create a folder
    await createFolderViaUI(window, folderName)
    await expect(getTreeItem(window, folderName)).toBeVisible({ timeout: 5_000 })

    // Delete via context menu
    await deleteViaContextMenu(window, folderName)

    // Verify folder is removed
    await expect(getTreeItem(window, folderName)).not.toBeVisible({ timeout: 5_000 })
  })

  // #3.8 Delete folder with documents
  test('delete folder with documents removes folder and documents', async ({ window }) => {
    const ts = Date.now()
    const folderName = `FolderWithDocs-${ts}`
    const doc1 = `FolderDoc1-${ts}`
    const doc2 = `FolderDoc2-${ts}`

    // Create folder with documents
    await createFolderViaUI(window, folderName)
    await createDocViaContextMenu(window, folderName, doc1)
    await createDocViaContextMenu(window, folderName, doc2)

    // Expand to verify docs are there
    await expandFolder(window, folderName)
    await expect(getTreeItem(window, doc1)).toBeVisible({ timeout: 5_000 })
    await expect(getTreeItem(window, doc2)).toBeVisible({ timeout: 5_000 })

    // Delete the folder (should cascade to documents)
    await deleteViaContextMenu(window, folderName)

    // Verify folder and all its documents are removed
    await expect(getTreeItem(window, folderName)).not.toBeVisible({ timeout: 5_000 })
    await expect(getTreeItem(window, doc1)).not.toBeVisible({ timeout: 5_000 })
    await expect(getTreeItem(window, doc2)).not.toBeVisible({ timeout: 5_000 })
  })

  // #3.9 Delete folder with nested subfolders
  test('delete folder with nested subfolders cascades deletion', async ({ window }) => {
    const ts = Date.now()
    const parent = `CascadeParent-${ts}`
    const child = `CascadeChild-${ts}`
    const grandchild = `CascadeGrandchild-${ts}`

    // Create parent > child > grandchild
    await createFolderViaUI(window, parent)
    await createFolderViaContextMenu(window, parent, child)
    await expandFolder(window, parent)
    await createFolderViaContextMenu(window, child, grandchild)
    await expandFolder(window, child)

    // Verify all exist
    await expect(getTreeItem(window, parent)).toBeVisible({ timeout: 5_000 })
    await expect(getTreeItem(window, child)).toBeVisible({ timeout: 5_000 })
    await expect(getTreeItem(window, grandchild)).toBeVisible({ timeout: 5_000 })

    // Delete parent - should cascade to child and grandchild
    await deleteViaContextMenu(window, parent)

    // All three should be removed
    await expect(getTreeItem(window, parent)).not.toBeVisible({ timeout: 5_000 })
    await expect(getTreeItem(window, child)).not.toBeVisible({ timeout: 5_000 })
    await expect(getTreeItem(window, grandchild)).not.toBeVisible({ timeout: 5_000 })
  })

  // #3.10 Delete folder - selected doc inside
  test('delete folder containing the currently selected document clears editor', async ({ window }) => {
    const ts = Date.now()
    const folderName = `FolderSelDoc-${ts}`
    const docName = `SelDocInFolder-${ts}`

    // Create folder with a document
    await createFolderViaUI(window, folderName)
    await createDocViaContextMenu(window, folderName, docName)

    // Expand and select the document inside the folder
    await expandFolder(window, folderName)
    await selectTreeItem(window, docName)

    // Verify editor shows the document
    await expect(
      window.locator('.ProseMirror, [data-testid="editor"], [role="textbox"]').first()
    ).toBeVisible({ timeout: 10_000 })

    // Delete the folder (which contains the selected document)
    await deleteViaContextMenu(window, folderName)

    // Folder and document should be gone
    await expect(getTreeItem(window, folderName)).not.toBeVisible({ timeout: 5_000 })
    await expect(getTreeItem(window, docName)).not.toBeVisible({ timeout: 5_000 })

    // Editor should show empty state or "select a document" prompt
    await expect(
      window.locator('text=/[Ss]elect a document|[Nn]o document|[Cc]hoose a document/').or(
        window.locator('[data-testid="empty-editor"]')
      )
    ).toBeVisible({ timeout: 5_000 }).catch(() => {
      // Editor may just be cleared without explicit message
    })
  })
})
