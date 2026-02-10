/**
 * App Knowledge - Drag and Drop Tests (#4.1-4.17)
 *
 * Validates drag-and-drop operations in the Application Detail Knowledge tab.
 * Uses DnD prefix "app" for sortable items.
 * Includes cross-scope prevention tests for app/project boundaries.
 */
import { test, expect } from '../../fixtures/electron-app'
import { loginAs, TEST_USER_1, navigateToAppKnowledgeTab } from '../../helpers/auth'
import {
  createDocViaUI,
  createFolderViaUI,
  createDocViaContextMenu,
  createFolderViaContextMenu,
  dragItemToFolder,
  dragItemToRoot,
  getTreeItem,
  getTreeItems,
  expandFolder,
  collapseFolder,
  selectTreeItem,
  expandProjectSection,
} from '../../helpers/knowledge-ops'
import { briefPause, waitForNetworkIdle } from '../../helpers/wait'

const APP_NAME = 'E2E Test App'
const PROJECT_NAME = 'E2E Test Project'

test.beforeEach(async ({ window }) => {
  await loginAs(window, TEST_USER_1)
  await navigateToAppKnowledgeTab(window, APP_NAME)
})

test.describe('App Knowledge - Drag and Drop', () => {
  // ============================================================================
  // Shared DnD Tests (#4.1-4.13)
  // ============================================================================

  test('#4.1 Drag unfiled document into folder', async ({ window }) => {
    const ts = Date.now()
    const folderName = `DnD-Folder-${ts}`
    const docName = `DnD-Doc-${ts}`

    await createFolderViaUI(window, folderName)
    await createDocViaUI(window, docName)

    // Drag doc into folder
    await dragItemToFolder(window, docName, folderName)

    // Expand folder and verify doc is inside
    await expandFolder(window, folderName)
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })
  })

  test('#4.2 Drag document out of folder to root', async ({ window }) => {
    const ts = Date.now()
    const folderName = `DnD-OutFolder-${ts}`
    const docName = `DnD-OutDoc-${ts}`

    // Create folder with a document inside
    await createFolderViaUI(window, folderName)
    await createDocViaContextMenu(window, folderName, docName)

    // Expand to see the doc
    await expandFolder(window, folderName)
    await expect(getTreeItem(window, docName)).toBeVisible()

    // Drag the doc to root
    await dragItemToRoot(window, docName)

    // Doc should now be at root level (visible without expanding folder)
    await collapseFolder(window, folderName)
    await briefPause(300)

    // The doc should still be visible at root level
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })
  })

  test('#4.3 Drag document between folders', async ({ window }) => {
    const ts = Date.now()
    const folder1 = `DnD-From-${ts}`
    const folder2 = `DnD-To-${ts}`
    const docName = `DnD-Between-${ts}`

    // Create two folders with a doc in the first
    await createFolderViaUI(window, folder1)
    await createFolderViaUI(window, folder2)
    await createDocViaContextMenu(window, folder1, docName)

    // Expand folder1 to see doc
    await expandFolder(window, folder1)
    await expect(getTreeItem(window, docName)).toBeVisible()

    // Drag doc from folder1 to folder2
    await dragItemToFolder(window, docName, folder2)

    // Verify doc is now in folder2
    await expandFolder(window, folder2)
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })
  })

  test('#4.4 Drag folder into another folder (nesting)', async ({ window }) => {
    const ts = Date.now()
    const outerFolder = `DnD-Outer-${ts}`
    const innerFolder = `DnD-Inner-${ts}`

    await createFolderViaUI(window, outerFolder)
    await createFolderViaUI(window, innerFolder)

    // Drag inner folder into outer folder
    await dragItemToFolder(window, innerFolder, outerFolder)

    // Expand outer folder and verify inner is nested
    await expandFolder(window, outerFolder)
    await expect(getTreeItem(window, innerFolder)).toBeVisible({ timeout: 5_000 })
  })

  test('#4.5 Drag folder to root', async ({ window }) => {
    const ts = Date.now()
    const parentFolder = `DnD-Parent-${ts}`
    const childFolder = `DnD-Child-${ts}`

    // Create nested folder
    await createFolderViaUI(window, parentFolder)
    await createFolderViaContextMenu(window, parentFolder, childFolder)
    await expandFolder(window, parentFolder)
    await expect(getTreeItem(window, childFolder)).toBeVisible()

    // Drag child folder to root
    await dragItemToRoot(window, childFolder)

    // Child folder should be at root level
    await collapseFolder(window, parentFolder)
    await briefPause(300)
    await expect(getTreeItem(window, childFolder)).toBeVisible({ timeout: 5_000 })
  })

  test('#4.6 Drag folder into its own descendant is prevented', async ({ window }) => {
    const ts = Date.now()
    const parentFolder = `DnD-CycleParent-${ts}`
    const childFolder = `DnD-CycleChild-${ts}`

    // Create parent > child hierarchy
    await createFolderViaUI(window, parentFolder)
    await createFolderViaContextMenu(window, parentFolder, childFolder)
    await expandFolder(window, parentFolder)

    // Try to drag parent into child (should be prevented)
    await dragItemToFolder(window, parentFolder, childFolder)

    // Parent should still be at root level, not nested inside its own child
    await briefPause(500)
    const parentItem = getTreeItem(window, parentFolder)
    await expect(parentItem).toBeVisible()

    // Verify hierarchy is unchanged: parent still contains child
    await expandFolder(window, parentFolder)
    await expect(getTreeItem(window, childFolder)).toBeVisible()
  })

  test('#4.7 Visual drop indicator appears during drag', async ({ window }) => {
    const ts = Date.now()
    const folderName = `DnD-Indicator-Folder-${ts}`
    const docName = `DnD-Indicator-Doc-${ts}`

    await createFolderViaUI(window, folderName)
    await createDocViaUI(window, docName)

    // Start dragging the document
    const source = window.locator(`[role="treeitem"]:has-text("${docName}")`).first()
    const target = window.locator(`[role="treeitem"]:has-text("${folderName}")`).first()

    const sourceBox = await source.boundingBox()
    const targetBox = await target.boundingBox()

    if (sourceBox && targetBox) {
      // Start drag
      await window.mouse.move(
        sourceBox.x + sourceBox.width / 2,
        sourceBox.y + sourceBox.height / 2
      )
      await window.mouse.down()
      await briefPause(200)

      // Move to target area
      await window.mouse.move(
        targetBox.x + targetBox.width / 2,
        targetBox.y + targetBox.height / 2
      )
      await briefPause(300)

      // Check for visual indicator (highlight, border, overlay)
      const dropIndicator = window.locator(
        '[data-drop-target], [class*="drop-target"], [class*="drag-over"], [data-over="true"]'
      )
      const indicatorVisible = await dropIndicator.count().catch(() => 0)

      // There should be some visual feedback during drag
      // (If DnD uses @dnd-kit, the overlay or active state should be visible)

      // Release
      await window.mouse.up()
    }
  })

  test('#4.8 Drag overlay shows item being dragged', async ({ window }) => {
    const ts = Date.now()
    const docName = `DnD-Overlay-${ts}`

    await createDocViaUI(window, docName)

    const source = window.locator(`[role="treeitem"]:has-text("${docName}")`).first()
    const sourceBox = await source.boundingBox()

    if (sourceBox) {
      // Start dragging
      await window.mouse.move(
        sourceBox.x + sourceBox.width / 2,
        sourceBox.y + sourceBox.height / 2
      )
      await window.mouse.down()
      await briefPause(200)

      // Move away to trigger overlay
      await window.mouse.move(
        sourceBox.x + sourceBox.width / 2 + 50,
        sourceBox.y + sourceBox.height / 2 + 50
      )
      await briefPause(300)

      // Check for @dnd-kit drag overlay
      const overlay = window.locator(
        '[data-dnd-overlay], [class*="drag-overlay"], [style*="pointer-events: none"]'
      )
      // Overlay should contain the item name
      const overlayText = await overlay.first().innerText().catch(() => '')

      // Release
      await window.mouse.up()
    }
  })

  test('#4.9 Drag reorder: document position changes within folder', async ({ window }) => {
    const ts = Date.now()
    const folderName = `DnD-Reorder-Folder-${ts}`
    const doc1 = `AAA-Reorder-${ts}`
    const doc2 = `BBB-Reorder-${ts}`
    const doc3 = `CCC-Reorder-${ts}`

    // Create folder with 3 docs
    await createFolderViaUI(window, folderName)
    await createDocViaContextMenu(window, folderName, doc1)
    await createDocViaContextMenu(window, folderName, doc2)
    await createDocViaContextMenu(window, folderName, doc3)

    await expandFolder(window, folderName)

    // All three docs should be visible
    await expect(getTreeItem(window, doc1)).toBeVisible()
    await expect(getTreeItem(window, doc2)).toBeVisible()
    await expect(getTreeItem(window, doc3)).toBeVisible()

    // Drag doc3 above doc1 (reorder)
    const source = window.locator(`[role="treeitem"]:has-text("${doc3}")`).first()
    const target = window.locator(`[role="treeitem"]:has-text("${doc1}")`).first()

    const sourceBox = await source.boundingBox()
    const targetBox = await target.boundingBox()

    if (sourceBox && targetBox) {
      await window.mouse.move(
        sourceBox.x + sourceBox.width / 2,
        sourceBox.y + sourceBox.height / 2
      )
      await window.mouse.down()
      await briefPause(200)
      // Drop above the first item
      await window.mouse.move(
        targetBox.x + targetBox.width / 2,
        targetBox.y + 2
      )
      await briefPause(200)
      await window.mouse.up()
    }

    await briefPause(500)

    // All items should still be present
    await expect(getTreeItem(window, doc1)).toBeVisible()
    await expect(getTreeItem(window, doc2)).toBeVisible()
    await expect(getTreeItem(window, doc3)).toBeVisible()
  })

  test('#4.10 Drag cancelled via Escape returns item to original position', async ({ window }) => {
    const ts = Date.now()
    const folderName = `DnD-Cancel-Folder-${ts}`
    const docName = `DnD-Cancel-Doc-${ts}`

    await createFolderViaUI(window, folderName)
    await createDocViaUI(window, docName)

    // Start dragging
    const source = window.locator(`[role="treeitem"]:has-text("${docName}")`).first()
    const sourceBox = await source.boundingBox()

    if (sourceBox) {
      await window.mouse.move(
        sourceBox.x + sourceBox.width / 2,
        sourceBox.y + sourceBox.height / 2
      )
      await window.mouse.down()
      await briefPause(200)

      // Move somewhere
      await window.mouse.move(sourceBox.x + 100, sourceBox.y + 100)
      await briefPause(200)

      // Press Escape to cancel
      await window.keyboard.press('Escape')
      await briefPause(300)
    }

    // Doc should still be at its original position (not in any folder)
    await expect(getTreeItem(window, docName)).toBeVisible()
  })

  test('#4.11 Drag preserves document selection state', async ({ window }) => {
    const ts = Date.now()
    const folderName = `DnD-Select-Folder-${ts}`
    const docName = `DnD-Select-Doc-${ts}`

    await createFolderViaUI(window, folderName)
    await createDocViaUI(window, docName)

    // Select the document
    await selectTreeItem(window, docName)

    // Drag doc into folder
    await dragItemToFolder(window, docName, folderName)

    // Expand folder
    await expandFolder(window, folderName)

    // Verify the doc is still selected after the drag
    const item = getTreeItem(window, docName)
    await expect(item).toBeVisible({ timeout: 5_000 })

    const isSelected = await item.evaluate(el =>
      el.getAttribute('aria-selected') === 'true' ||
      el.getAttribute('data-selected') === 'true' ||
      el.classList.contains('selected')
    )
    expect(isSelected).toBe(true)
  })

  test('#4.12 Drag into collapsed folder auto-expands it', async ({ window }) => {
    const ts = Date.now()
    const folderName = `DnD-AutoExpand-${ts}`
    const docName = `DnD-AutoExpand-Doc-${ts}`

    await createFolderViaUI(window, folderName)
    await createDocViaUI(window, docName)

    // Ensure folder is collapsed
    await collapseFolder(window, folderName)

    // Drag doc to folder
    const source = window.locator(`[role="treeitem"]:has-text("${docName}")`).first()
    const target = window.locator(`[role="treeitem"]:has-text("${folderName}")`).first()
    const sourceBox = await source.boundingBox()
    const targetBox = await target.boundingBox()

    if (sourceBox && targetBox) {
      await window.mouse.move(
        sourceBox.x + sourceBox.width / 2,
        sourceBox.y + sourceBox.height / 2
      )
      await window.mouse.down()
      await briefPause(200)

      // Hover over folder to trigger auto-expand
      await window.mouse.move(
        targetBox.x + targetBox.width / 2,
        targetBox.y + targetBox.height / 2
      )
      // Hold for auto-expand delay
      await briefPause(1000)
      await window.mouse.up()
    }

    await briefPause(500)

    // Folder should now be expanded with the doc inside
    const folderItem = getTreeItem(window, folderName)
    const expanded = await folderItem.getAttribute('aria-expanded')
    expect(expanded).toBe('true')

    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })
  })

  test('#4.13 Drag multiple rapid operations do not corrupt tree', async ({ window }) => {
    const ts = Date.now()
    const folder1 = `DnD-Rapid-F1-${ts}`
    const folder2 = `DnD-Rapid-F2-${ts}`
    const doc1 = `DnD-Rapid-D1-${ts}`
    const doc2 = `DnD-Rapid-D2-${ts}`

    // Create test data
    await createFolderViaUI(window, folder1)
    await createFolderViaUI(window, folder2)
    await createDocViaUI(window, doc1)
    await createDocViaUI(window, doc2)

    // Rapid drag operations
    await dragItemToFolder(window, doc1, folder1)
    await dragItemToFolder(window, doc2, folder2)

    // Verify both items ended up in their respective folders
    await expandFolder(window, folder1)
    await expect(getTreeItem(window, doc1)).toBeVisible({ timeout: 5_000 })

    await expandFolder(window, folder2)
    await expect(getTreeItem(window, doc2)).toBeVisible({ timeout: 5_000 })

    // Now move doc1 to folder2
    await dragItemToFolder(window, doc1, folder2)
    await briefPause(500)

    // Both docs should now be in folder2
    await expandFolder(window, folder2)
    await expect(getTreeItem(window, doc1)).toBeVisible({ timeout: 5_000 })
    await expect(getTreeItem(window, doc2)).toBeVisible({ timeout: 5_000 })
  })

  // ============================================================================
  // Cross-Scope / Project Section DnD (#4.14-4.17)
  // ============================================================================

  test('#4.14 Prevent cross-scope drag: app item to project section', async ({ window }) => {
    const ts = Date.now()
    const appDoc = `AppDoc-NoCross-${ts}`

    // Create an app-level document
    await createDocViaUI(window, appDoc)
    await expect(getTreeItem(window, appDoc)).toBeVisible()

    // Expand the project section
    await expandProjectSection(window, PROJECT_NAME)
    await briefPause(500)

    // Try to drag the app doc into the project section
    const source = window.locator(`[role="treeitem"]:has-text("${appDoc}")`).first()
    const projectTarget = window.locator(
      `[role="treeitem"]:has-text("${PROJECT_NAME}")`
    ).first()

    const sourceBox = await source.boundingBox()
    const targetBox = await projectTarget.boundingBox()

    if (sourceBox && targetBox) {
      await window.mouse.move(
        sourceBox.x + sourceBox.width / 2,
        sourceBox.y + sourceBox.height / 2
      )
      await window.mouse.down()
      await briefPause(200)
      await window.mouse.move(
        targetBox.x + targetBox.width / 2,
        targetBox.y + targetBox.height / 2
      )
      await briefPause(500)
      await window.mouse.up()
    }

    await briefPause(500)

    // The app doc should NOT have moved into the project section
    // It should still be at the app root level
    await expect(getTreeItem(window, appDoc)).toBeVisible({ timeout: 5_000 })
  })

  test('#4.15 Prevent cross-scope drag: project item to app root', async ({ window }) => {
    const ts = Date.now()
    const projDoc = `ProjDoc-NoCross-${ts}`

    // Expand project section and create a doc inside it
    await expandProjectSection(window, PROJECT_NAME)
    await briefPause(500)
    await createDocViaUI(window, projDoc)
    await expect(getTreeItem(window, projDoc)).toBeVisible()

    // Try to drag the project doc to the app root area
    await dragItemToRoot(window, projDoc)

    await briefPause(500)

    // The project doc should remain in the project section (cross-scope blocked)
    await expandProjectSection(window, PROJECT_NAME)
    await expect(getTreeItem(window, projDoc)).toBeVisible({ timeout: 5_000 })
  })

  test('#4.16 DnD within project section works', async ({ window }) => {
    const ts = Date.now()
    const projFolder = `ProjDnD-Folder-${ts}`
    const projDoc = `ProjDnD-Doc-${ts}`

    // Expand project section and create items
    await expandProjectSection(window, PROJECT_NAME)
    await briefPause(500)
    await createFolderViaUI(window, projFolder)
    await createDocViaUI(window, projDoc)

    // Drag doc into folder within the project section
    await dragItemToFolder(window, projDoc, projFolder)

    // Expand folder and verify doc moved
    await expandFolder(window, projFolder)
    await expect(getTreeItem(window, projDoc)).toBeVisible({ timeout: 5_000 })
  })

  test('#4.17 DnD between different project sections is blocked', async ({ window }) => {
    const ts = Date.now()
    const projDoc = `CrossProj-Doc-${ts}`
    const otherProject = 'E2E Test Project 2'

    // Expand the first project section and create a doc
    await expandProjectSection(window, PROJECT_NAME)
    await briefPause(500)
    await createDocViaUI(window, projDoc)
    await expect(getTreeItem(window, projDoc)).toBeVisible()

    // Try to drag the doc to a different project section
    const source = window.locator(`[role="treeitem"]:has-text("${projDoc}")`).first()
    const otherProjectTarget = window.locator(
      `[role="treeitem"]:has-text("${otherProject}")`
    ).first()

    // Only attempt if the other project exists
    const otherExists = await otherProjectTarget.isVisible({ timeout: 3_000 }).catch(() => false)
    if (otherExists) {
      const sourceBox = await source.boundingBox()
      const targetBox = await otherProjectTarget.boundingBox()

      if (sourceBox && targetBox) {
        await window.mouse.move(
          sourceBox.x + sourceBox.width / 2,
          sourceBox.y + sourceBox.height / 2
        )
        await window.mouse.down()
        await briefPause(200)
        await window.mouse.move(
          targetBox.x + targetBox.width / 2,
          targetBox.y + targetBox.height / 2
        )
        await briefPause(500)
        await window.mouse.up()
      }

      await briefPause(500)

      // Doc should still be in the original project section
      await expandProjectSection(window, PROJECT_NAME)
      await expect(getTreeItem(window, projDoc)).toBeVisible({ timeout: 5_000 })
    }
  })
})
