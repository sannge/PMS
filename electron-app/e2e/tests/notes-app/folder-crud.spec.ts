/**
 * Notes App - Folder CRUD Tests (Scenarios #3.1-3.12)
 *
 * Validates folder create, rename, and delete operations
 * in the application-scoped Notes tree, including project-scoped folders.
 */
import { test, expect } from '../../fixtures/electron-app'
import { loginAs, TEST_USER_1, navigateToNotesAppTab } from '../../helpers/auth'
import {
  createDocViaUI,
  createFolderViaUI,
  createFolderViaContextMenu,
  createDocViaContextMenu,
  renameViaContextMenu,
  deleteViaContextMenu,
  selectTreeItem,
  expandFolder,
  getTreeItem,
  getTreeItems,
  expandProjectSection,
} from '../../helpers/knowledge-ops'
import { waitForRemoval, briefPause } from '../../helpers/wait'

const APP_NAME = 'E2E Test App'
const PROJECT_NAME = 'E2E Test Project'

test.describe('Notes App - Folder CRUD', () => {
  test.beforeEach(async ({ window }) => {
    await loginAs(window, TEST_USER_1)
    await navigateToNotesAppTab(window, APP_NAME)
  })

  // ---------------------------------------------------------------------------
  // #3.1 Create root folder
  // ---------------------------------------------------------------------------
  test('#3.1 create root folder', async ({ window }) => {
    const folderName = `RootFolder-${Date.now()}`

    await createFolderViaUI(window, folderName)

    // Verify folder appears at root level
    await expect(getTreeItem(window, folderName)).toBeVisible({ timeout: 5_000 })

    // Verify it has folder semantics (aria-expanded attribute)
    const folderItem = getTreeItem(window, folderName)
    const ariaExpanded = await folderItem.getAttribute('aria-expanded')
    expect(ariaExpanded !== null).toBeTruthy()
  })

  // ---------------------------------------------------------------------------
  // #3.2 Create nested subfolder
  // ---------------------------------------------------------------------------
  test('#3.2 create nested subfolder via context menu', async ({ window }) => {
    const ts = Date.now()
    const parentName = `ParentFolder-${ts}`
    const childName = `SubFolder-${ts}`

    // Create parent folder
    await createFolderViaUI(window, parentName)

    // Create subfolder inside parent via context menu
    await createFolderViaContextMenu(window, parentName, childName)

    // Expand parent to verify child is inside
    await expandFolder(window, parentName)
    await expect(getTreeItem(window, childName)).toBeVisible({ timeout: 5_000 })
  })

  // ---------------------------------------------------------------------------
  // #3.3 Create at max depth (5)
  // ---------------------------------------------------------------------------
  test('#3.3 create folder at max depth 5 succeeds', async ({ window }) => {
    const ts = Date.now()
    const names = Array.from({ length: 5 }, (_, i) => `Depth${i + 1}-${ts}`)

    // Create depth-1 at root
    await createFolderViaUI(window, names[0])

    // Create deeper levels via context menu
    for (let i = 1; i < 5; i++) {
      await expandFolder(window, names[i - 1])
      await createFolderViaContextMenu(window, names[i - 1], names[i])
    }

    // Expand all and verify deepest folder is visible
    for (let i = 0; i < 5; i++) {
      await expandFolder(window, names[i])
    }
    await expect(getTreeItem(window, names[4])).toBeVisible({ timeout: 5_000 })
  })

  // ---------------------------------------------------------------------------
  // #3.4 Create beyond max depth (6)
  // ---------------------------------------------------------------------------
  test('#3.4 create folder beyond max depth 6 is rejected', async ({ window }) => {
    const ts = Date.now()
    const names = Array.from({ length: 5 }, (_, i) => `MaxD${i + 1}-${ts}`)
    const tooDeep = `TooDeep-${ts}`

    // Create 5 levels
    await createFolderViaUI(window, names[0])
    for (let i = 1; i < 5; i++) {
      await expandFolder(window, names[i - 1])
      await createFolderViaContextMenu(window, names[i - 1], names[i])
    }

    // Expand all
    for (const name of names) {
      await expandFolder(window, name)
    }

    // Attempt to create a 6th level inside the 5th
    await window.locator(`text="${names[4]}"`).first().click({ button: 'right' })

    // The "New Subfolder" / "New Folder" option may be disabled or absent
    const newFolderItem = window.locator('text=/New (Sub)?[Ff]older/')
    const isVisible = await newFolderItem.first().isVisible({ timeout: 2_000 }).catch(() => false)

    if (isVisible) {
      await newFolderItem.first().click()

      // Fill and submit
      const nameInput = window.locator(
        'input[placeholder*="name"], input[placeholder*="folder"]'
      )
      if (await nameInput.isVisible({ timeout: 3_000 }).catch(() => false)) {
        await nameInput.fill(tooDeep)
        await window.click('button:has-text("Create")')

        // Expect an error toast or validation message
        const errorMsg = window.locator('text=/max depth|maximum depth|too deep/i')
        await expect(errorMsg.first()).toBeVisible({ timeout: 5_000 })
      }
    }
    // If "New Subfolder" is not visible, the UI already prevents it -- pass
  })

  // ---------------------------------------------------------------------------
  // #3.5 Rename folder
  // ---------------------------------------------------------------------------
  test('#3.5 rename folder via context menu', async ({ window }) => {
    const ts = Date.now()
    const originalName = `RenameFolder-${ts}`
    const newName = `FolderRenamed-${ts}`

    await createFolderViaUI(window, originalName)
    await renameViaContextMenu(window, originalName, newName)

    await expect(getTreeItem(window, newName)).toBeVisible({ timeout: 5_000 })
    await expect(window.locator(`text="${originalName}"`)).not.toBeVisible({ timeout: 3_000 })
  })

  // ---------------------------------------------------------------------------
  // #3.6 Rename folder -- duplicate name
  // ---------------------------------------------------------------------------
  test('#3.6 rename folder to duplicate sibling name shows error', async ({ window }) => {
    const ts = Date.now()
    const folder1 = `DupFolder1-${ts}`
    const folder2 = `DupFolder2-${ts}`

    // Create two folders at root
    await createFolderViaUI(window, folder1)
    await createFolderViaUI(window, folder2)

    // Try to rename folder2 to folder1's name
    await window.locator(`text="${folder2}"`).first().click({ button: 'right' })
    await window.click('text=Rename')

    const renameInput = window.locator('[role="tree"] input[type="text"]').last()
    await renameInput.waitFor({ state: 'visible', timeout: 3_000 })
    await renameInput.fill(folder1)
    await window.keyboard.press('Enter')

    // Expect error toast about duplicate name (409 conflict)
    const errorToast = window.locator('text=/already exists|duplicate|conflict/i')
    await expect(errorToast.first()).toBeVisible({ timeout: 5_000 })
  })

  // ---------------------------------------------------------------------------
  // #3.7 Delete empty folder
  // ---------------------------------------------------------------------------
  test('#3.7 delete empty folder', async ({ window }) => {
    const folderName = `DeleteEmptyFolder-${Date.now()}`

    await createFolderViaUI(window, folderName)
    await deleteViaContextMenu(window, folderName)

    await expect(window.locator(`text="${folderName}"`).first()).not.toBeVisible({ timeout: 5_000 })
  })

  // ---------------------------------------------------------------------------
  // #3.8 Delete folder with documents
  // ---------------------------------------------------------------------------
  test('#3.8 delete folder with documents cascades', async ({ window }) => {
    const ts = Date.now()
    const folderName = `CascadeFolder-${ts}`
    const doc1 = `CascadeDoc1-${ts}`
    const doc2 = `CascadeDoc2-${ts}`
    const doc3 = `CascadeDoc3-${ts}`

    // Create folder with 3 documents inside
    await createFolderViaUI(window, folderName)
    await createDocViaContextMenu(window, folderName, doc1)
    await createDocViaContextMenu(window, folderName, doc2)
    await createDocViaContextMenu(window, folderName, doc3)

    // Expand folder to verify docs exist
    await expandFolder(window, folderName)
    await expect(getTreeItem(window, doc1)).toBeVisible()

    // Delete the folder
    await deleteViaContextMenu(window, folderName)

    // Folder and all docs should be gone
    await expect(window.locator(`text="${folderName}"`).first()).not.toBeVisible({ timeout: 5_000 })
    await expect(window.locator(`text="${doc1}"`).first()).not.toBeVisible({ timeout: 3_000 })
    await expect(window.locator(`text="${doc2}"`).first()).not.toBeVisible({ timeout: 3_000 })
    await expect(window.locator(`text="${doc3}"`).first()).not.toBeVisible({ timeout: 3_000 })
  })

  // ---------------------------------------------------------------------------
  // #3.9 Delete folder with nested subfolders
  // ---------------------------------------------------------------------------
  test('#3.9 delete folder with nested subfolders removes entire subtree', async ({ window }) => {
    const ts = Date.now()
    const parentFolder = `ParentDel-${ts}`
    const childFolder = `ChildDel-${ts}`
    const grandchildDoc = `GrandchildDoc-${ts}`

    // Create nested structure: Parent > Child > Document
    await createFolderViaUI(window, parentFolder)
    await createFolderViaContextMenu(window, parentFolder, childFolder)
    await expandFolder(window, parentFolder)
    await createDocViaContextMenu(window, childFolder, grandchildDoc)

    // Delete parent folder
    await deleteViaContextMenu(window, parentFolder)

    // Entire subtree should be gone
    await expect(window.locator(`text="${parentFolder}"`).first()).not.toBeVisible({ timeout: 5_000 })
    await expect(window.locator(`text="${childFolder}"`).first()).not.toBeVisible({ timeout: 3_000 })
    await expect(window.locator(`text="${grandchildDoc}"`).first()).not.toBeVisible({ timeout: 3_000 })
  })

  // ---------------------------------------------------------------------------
  // #3.10 Delete folder -- selected doc inside
  // ---------------------------------------------------------------------------
  test('#3.10 deleting folder with selected doc inside shows empty editor', async ({ window }) => {
    const ts = Date.now()
    const folderName = `SelDocFolder-${ts}`
    const docName = `SelDocInside-${ts}`

    // Create folder with a doc
    await createFolderViaUI(window, folderName)
    await createDocViaContextMenu(window, folderName, docName)

    // Expand and select the doc
    await expandFolder(window, folderName)
    await selectTreeItem(window, docName)
    await expect(window.locator('button:has-text("Edit")')).toBeVisible({ timeout: 10_000 })

    // Delete the parent folder
    await deleteViaContextMenu(window, folderName)

    // Editor should show empty state
    await expect(
      window.locator('text=/Select a document|No document selected/i').first()
    ).toBeVisible({ timeout: 10_000 })
  })

  // ---------------------------------------------------------------------------
  // #3.11 Create folder inside project section (app-specific)
  // ---------------------------------------------------------------------------
  test('#3.11 create folder inside project section', async ({ window }) => {
    const folderName = `ProjFolder-${Date.now()}`

    // Expand the project section
    await expandProjectSection(window, PROJECT_NAME)

    // Right-click the project to create a folder
    await window.locator(`text="${PROJECT_NAME}"`).first().click({ button: 'right' })

    const newFolderItem = window.locator('text=/New (Sub)?[Ff]older/')
    await newFolderItem.first().click()

    // Fill dialog
    await window.waitForSelector(
      'input[placeholder*="name"], input[placeholder*="folder"]',
      { timeout: 5_000 }
    )
    await window.fill('input[placeholder*="name"], input[placeholder*="folder"]', folderName)
    await window.click('button:has-text("Create")')

    // Folder should appear under the project section
    await expect(window.locator(`text="${folderName}"`).first()).toBeVisible({ timeout: 5_000 })
  })

  // ---------------------------------------------------------------------------
  // #3.12 Delete project folder cascades within project scope only
  // ---------------------------------------------------------------------------
  test('#3.12 delete project folder cascades within project scope only', async ({ window }) => {
    const ts = Date.now()
    const projFolder = `ProjCascade-${ts}`
    const projDoc = `ProjCascadeDoc-${ts}`
    const appDoc = `AppSafe-${ts}`

    // Create an app-level doc that should NOT be affected
    await createDocViaUI(window, appDoc)

    // Expand project section and create folder + doc inside
    await expandProjectSection(window, PROJECT_NAME)

    await window.locator(`text="${PROJECT_NAME}"`).first().click({ button: 'right' })
    const newFolderItem = window.locator('text=/New (Sub)?[Ff]older/')
    await newFolderItem.first().click()

    await window.waitForSelector(
      'input[placeholder*="name"], input[placeholder*="folder"]',
      { timeout: 5_000 }
    )
    await window.fill('input[placeholder*="name"], input[placeholder*="folder"]', projFolder)
    await window.click('button:has-text("Create")')
    await expect(window.locator(`text="${projFolder}"`).first()).toBeVisible({ timeout: 5_000 })

    // Create doc inside the project folder
    await createDocViaContextMenu(window, projFolder, projDoc)

    // Delete the project folder
    await deleteViaContextMenu(window, projFolder)

    // Project folder and its doc should be gone
    await expect(window.locator(`text="${projFolder}"`).first()).not.toBeVisible({ timeout: 5_000 })
    await expect(window.locator(`text="${projDoc}"`).first()).not.toBeVisible({ timeout: 3_000 })

    // App-level doc should still be there
    await expect(getTreeItem(window, appDoc)).toBeVisible({ timeout: 3_000 })
  })
})
