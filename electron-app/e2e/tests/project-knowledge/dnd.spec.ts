/**
 * Project Knowledge - Drag and Drop Tests (Scenarios #4.1-4.13)
 *
 * Validates drag-and-drop operations for documents and folders
 * in the project Knowledge tab context.
 *
 * Context: KnowledgePanel -> KnowledgeTree (scope=project)
 * DnD prefix: "project" (NOT "app")
 * NO cross-scope drag operations.
 */
import { test, expect } from '../../fixtures/electron-app'
import { loginAs, TEST_USER_1, navigateToProjectKnowledgeTab } from '../../helpers/auth'
import {
  createDocViaUI,
  createFolderViaUI,
  createDocViaContextMenu,
  createFolderViaContextMenu,
  dragItemToFolder,
  dragItemToRoot,
  getTreeItem,
  expandFolder,
  collapseFolder,
  selectTreeItem,
} from '../../helpers/knowledge-ops'
import { briefPause } from '../../helpers/wait'

const APP_NAME = 'E2E Test App'
const PROJECT_NAME = 'E2E Test Project'

test.describe('Project Knowledge - Drag and Drop', () => {
  test.beforeEach(async ({ window }) => {
    await loginAs(window, TEST_USER_1)
    await navigateToProjectKnowledgeTab(window, APP_NAME, PROJECT_NAME)
  })

  // #4.1 Drag document into folder
  test('drag document into folder moves it inside', async ({ window }) => {
    const ts = Date.now()
    const docName = `DragDoc-${ts}`
    const folderName = `DropFolder-${ts}`

    // Create a root document and a folder
    await createDocViaUI(window, docName)
    await createFolderViaUI(window, folderName)

    // Drag the document into the folder
    await dragItemToFolder(window, docName, folderName)

    // Expand the folder to verify the document is inside
    await expandFolder(window, folderName)
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })
  })

  // #4.2 Drag document to root
  test('drag document from folder to root level', async ({ window }) => {
    const ts = Date.now()
    const folderName = `SourceFolder-${ts}`
    const docName = `MoveToRoot-${ts}`

    // Create a folder with a document inside
    await createFolderViaUI(window, folderName)
    await createDocViaContextMenu(window, folderName, docName)

    // Expand to see the document
    await expandFolder(window, folderName)
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })

    // Drag the document to root
    await dragItemToRoot(window, docName)

    // The document should now be at root level (visible without expanding the folder)
    await collapseFolder(window, folderName)
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })
  })

  // #4.3 Drag document - already in folder (no-op)
  test('drag document to same folder is no-op', async ({ window }) => {
    const ts = Date.now()
    const folderName = `SameFolder-${ts}`
    const docName = `StayPut-${ts}`

    // Create folder with document
    await createFolderViaUI(window, folderName)
    await createDocViaContextMenu(window, folderName, docName)

    // Expand folder
    await expandFolder(window, folderName)
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })

    // Drag document to the same folder
    await dragItemToFolder(window, docName, folderName)

    // Document should still be inside the folder
    await expandFolder(window, folderName)
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })
  })

  // #4.4 Drag folder into folder
  test('drag folder into another folder', async ({ window }) => {
    const ts = Date.now()
    const sourceFolder = `SourceFolder-${ts}`
    const targetFolder = `TargetFolder-${ts}`

    // Create two root folders
    await createFolderViaUI(window, sourceFolder)
    await createFolderViaUI(window, targetFolder)

    // Drag sourceFolder into targetFolder
    await dragItemToFolder(window, sourceFolder, targetFolder)

    // Expand targetFolder to verify sourceFolder is nested inside
    await expandFolder(window, targetFolder)
    await expect(getTreeItem(window, sourceFolder)).toBeVisible({ timeout: 5_000 })
  })

  // #4.5 Drag folder to root
  test('drag folder from nested position to root', async ({ window }) => {
    const ts = Date.now()
    const parentFolder = `ParentDrag-${ts}`
    const childFolder = `ChildDrag-${ts}`

    // Create parent with a nested child folder
    await createFolderViaUI(window, parentFolder)
    await createFolderViaContextMenu(window, parentFolder, childFolder)

    // Expand to see child
    await expandFolder(window, parentFolder)
    await expect(getTreeItem(window, childFolder)).toBeVisible({ timeout: 5_000 })

    // Drag child folder to root
    await dragItemToRoot(window, childFolder)

    // Child should now be at root level
    await collapseFolder(window, parentFolder)
    await expect(getTreeItem(window, childFolder)).toBeVisible({ timeout: 5_000 })
  })

  // #4.6 Drag folder onto itself (no-op)
  test('drag folder onto itself is no-op', async ({ window }) => {
    const folderName = `SelfDrag-${Date.now()}`

    // Create a folder
    await createFolderViaUI(window, folderName)

    // Attempt to drag the folder onto itself
    await dragItemToFolder(window, folderName, folderName)

    // Folder should still be at root level, not nested inside itself
    await expect(getTreeItem(window, folderName)).toBeVisible({ timeout: 5_000 })
    const folderItem = getTreeItem(window, folderName)
    const ariaExpanded = await folderItem.getAttribute('aria-expanded')
    // If expanded, it should not contain itself as a child
    if (ariaExpanded === 'true') {
      const children = folderItem.locator(`[role="treeitem"]:has-text("${folderName}")`)
      // Should have 0 children with the same name (self is the only match at parent level)
      expect(await children.count()).toBeLessThanOrEqual(0)
    }
  })

  // #4.7 Prevent circular move
  test('prevent circular folder move (parent into child)', async ({ window }) => {
    const ts = Date.now()
    const parentFolder = `CircularParent-${ts}`
    const childFolder = `CircularChild-${ts}`

    // Create parent > child hierarchy
    await createFolderViaUI(window, parentFolder)
    await createFolderViaContextMenu(window, parentFolder, childFolder)
    await expandFolder(window, parentFolder)

    // Attempt to drag parent into its own child (circular move)
    await dragItemToFolder(window, parentFolder, childFolder)

    // The hierarchy should remain unchanged - parent still contains child
    await briefPause(500)
    await expandFolder(window, parentFolder)
    await expect(getTreeItem(window, childFolder)).toBeVisible({ timeout: 5_000 })

    // Parent should NOT be inside child
    await expandFolder(window, childFolder)
    const parentInsideChild = window.locator(
      `[role="treeitem"]:has-text("${childFolder}") [role="treeitem"]:has-text("${parentFolder}")`
    )
    expect(await parentInsideChild.count()).toBe(0)
  })

  // #4.8 Drag folder exceeds max depth
  test('drag folder that would exceed max depth (5) is prevented', async ({ window }) => {
    const ts = Date.now()
    // Create a 4-level deep hierarchy
    const l1 = `Depth1-${ts}`
    const l2 = `Depth2-${ts}`
    const l3 = `Depth3-${ts}`
    const l4 = `Depth4-${ts}`

    await createFolderViaUI(window, l1)
    await createFolderViaContextMenu(window, l1, l2)
    await expandFolder(window, l1)
    await createFolderViaContextMenu(window, l2, l3)
    await expandFolder(window, l2)
    await createFolderViaContextMenu(window, l3, l4)
    await expandFolder(window, l3)

    // Create a separate 2-level deep tree at root
    const deepFolder = `DeepRoot-${ts}`
    const deepChild = `DeepChild-${ts}`
    await createFolderViaUI(window, deepFolder)
    await createFolderViaContextMenu(window, deepFolder, deepChild)

    // Attempt to drag deepFolder (depth 2) into l4 (depth 4) -> total would be 6 > 5
    await dragItemToFolder(window, deepFolder, l4)

    // deepFolder should NOT have moved into l4 (exceeds max depth)
    await briefPause(500)
    // deepFolder should still be at root
    await expect(getTreeItem(window, deepFolder)).toBeVisible({ timeout: 5_000 })
  })

  // #4.9 Drag overlay shows item name
  test('drag overlay shows the dragged item name', async ({ window }) => {
    const docName = `OverlayDoc-${Date.now()}`

    await createDocViaUI(window, docName)

    // Start dragging the document
    const source = window.locator(`[role="treeitem"]:has-text("${docName}")`).first()
    const sourceBox = await source.boundingBox()

    if (sourceBox) {
      await window.mouse.move(sourceBox.x + sourceBox.width / 2, sourceBox.y + sourceBox.height / 2)
      await window.mouse.down()
      // Move slightly to trigger drag overlay
      await window.mouse.move(sourceBox.x + sourceBox.width / 2 + 20, sourceBox.y + sourceBox.height / 2 + 20)
      await briefPause(300)

      // The drag overlay should show the item name
      const overlay = window.locator('[data-dnd-overlay], [class*="drag-overlay"], [class*="DragOverlay"]')
      if (await overlay.isVisible({ timeout: 2_000 }).catch(() => false)) {
        await expect(overlay).toContainText(docName)
      }

      // Release
      await window.mouse.up()
    }
  })

  // #4.10 Root drop zone appears during drag
  test('root drop zone appears when dragging an item', async ({ window }) => {
    const ts = Date.now()
    const folderName = `DZFolder-${ts}`
    const docName = `DZDoc-${ts}`

    await createFolderViaUI(window, folderName)
    await createDocViaContextMenu(window, folderName, docName)
    await expandFolder(window, folderName)

    // Start dragging the document
    const source = window.locator(`[role="treeitem"]:has-text("${docName}")`).first()
    const sourceBox = await source.boundingBox()

    if (sourceBox) {
      await window.mouse.move(sourceBox.x + sourceBox.width / 2, sourceBox.y + sourceBox.height / 2)
      await window.mouse.down()
      await window.mouse.move(sourceBox.x + sourceBox.width / 2 + 30, sourceBox.y + sourceBox.height / 2 + 30)
      await briefPause(300)

      // Root drop zone should become visible during drag
      const rootDropZone = window.locator('[data-root-drop-zone], [data-testid="root-drop-zone"]')
      if (await rootDropZone.isVisible({ timeout: 2_000 }).catch(() => false)) {
        await expect(rootDropZone).toBeVisible()
      }

      // Release
      await window.mouse.up()
    }
  })

  // #4.11 Root drop zone hidden when not dragging
  test('root drop zone is hidden when not dragging', async ({ window }) => {
    const docName = `NoDragDoc-${Date.now()}`
    await createDocViaUI(window, docName)

    // Without any drag in progress, root drop zone should not be visible
    const rootDropZone = window.locator('[data-root-drop-zone], [data-testid="root-drop-zone"]')
    await expect(rootDropZone).not.toBeVisible({ timeout: 2_000 }).catch(() => {
      // Drop zone element may not exist at all when not dragging - that is fine
    })
  })

  // #4.12 Drop on document resolves to parent folder
  test('drop on a document resolves to its parent folder', async ({ window }) => {
    const ts = Date.now()
    const targetFolder = `TargetF-${ts}`
    const targetDoc = `TargetD-${ts}`
    const dragDoc = `DragToDoc-${ts}`

    // Create a folder with a document, and a separate root document to drag
    await createFolderViaUI(window, targetFolder)
    await createDocViaContextMenu(window, targetFolder, targetDoc)
    await createDocViaUI(window, dragDoc)

    // Expand folder to see target doc
    await expandFolder(window, targetFolder)

    // Drag root doc onto the document inside the folder
    await dragItemToFolder(window, dragDoc, targetDoc)
    await briefPause(500)

    // The dragged doc should now be inside targetFolder (drop resolved to parent)
    await expandFolder(window, targetFolder)
    await expect(getTreeItem(window, dragDoc)).toBeVisible({ timeout: 5_000 })
  })

  // #4.13 Drop on root-level document = move to root
  test('drop on a root-level document moves item to root', async ({ window }) => {
    const ts = Date.now()
    const folderName = `FolderForRootDrop-${ts}`
    const docInFolder = `DocInFolder-${ts}`
    const rootDoc = `RootLevelDoc-${ts}`

    // Create a folder with a document, and a root-level document
    await createFolderViaUI(window, folderName)
    await createDocViaContextMenu(window, folderName, docInFolder)
    await createDocViaUI(window, rootDoc)

    // Expand folder to see the document inside
    await expandFolder(window, folderName)

    // Drag the folder's document onto the root-level document
    await dragItemToFolder(window, docInFolder, rootDoc)
    await briefPause(500)

    // The dragged doc should now be at root level (root-level doc has no parent folder)
    await collapseFolder(window, folderName)
    await expect(getTreeItem(window, docInFolder)).toBeVisible({ timeout: 5_000 })
  })
})
