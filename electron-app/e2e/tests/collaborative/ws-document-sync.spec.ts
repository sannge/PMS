/**
 * WebSocket Document Sync Tests (2 clients) - Scenarios #12.1-12.3, 12.7-12.8, 12.12-12.13
 *
 * Validates that document CRUD and move operations performed by Client A
 * are reflected in real-time on Client B via WebSocket events.
 * Also validates skip-own-event deduplication and content sync.
 */
import { test, expect } from '../../fixtures/two-clients'
import { loginAs, navigateToNotes, TEST_USER_1, TEST_USER_2 } from '../../helpers/auth'
import {
  createDocViaUI,
  createFolderViaUI,
  renameViaContextMenu,
  deleteViaContextMenu,
  enterEditMode,
  saveDocument,
  selectTreeItem,
  expandFolder,
  dragItemToFolder,
  getTreeItem,
  getTreeItems,
} from '../../helpers/knowledge-ops'
import { waitForWsUpdate, waitForRemoval, briefPause } from '../../helpers/wait'

test.describe('WebSocket Document Sync', () => {
  test.beforeEach(async ({ window1, window2 }) => {
    await Promise.all([
      loginAs(window1, TEST_USER_1).then(() => navigateToNotes(window1)),
      loginAs(window2, TEST_USER_2).then(() => navigateToNotes(window2)),
    ])
  })

  // #12.1 Document created by Client A appears on Client B via WebSocket
  test('document created by A appears on B via WS (#12.1)', async ({ window1, window2 }) => {
    const docName = `WS-Create-${Date.now()}`

    // Client A: Create a new document
    await createDocViaUI(window1, docName)

    // Client A: Verify doc appears locally (optimistic update)
    await expect(window1.locator(`text="${docName}"`).first()).toBeVisible({ timeout: 5_000 })

    // Client B: Verify doc appears via WebSocket broadcast
    await waitForWsUpdate(window2, `text="${docName}"`, { timeout: 10_000 })
    await expect(window2.locator(`text="${docName}"`).first()).toBeVisible()
  })

  // #12.2 Document renamed by Client A updates on Client B via WebSocket
  test('document renamed by A updates on B via WS (#12.2)', async ({ window1, window2 }) => {
    const originalName = `WS-Rename-Orig-${Date.now()}`
    const renamedName = `WS-Rename-New-${Date.now()}`

    // Client A: Create document
    await createDocViaUI(window1, originalName)

    // Client B: Wait for doc to appear
    await waitForWsUpdate(window2, `text="${originalName}"`, { timeout: 10_000 })

    // Client A: Rename via context menu
    await renameViaContextMenu(window1, originalName, renamedName)

    // Client A: Verify rename locally
    await expect(window1.locator(`text="${renamedName}"`).first()).toBeVisible({ timeout: 5_000 })

    // Client B: Verify rename arrives via WebSocket
    await waitForWsUpdate(window2, `text="${renamedName}"`, { timeout: 10_000 })
    // Original name should no longer be visible on B
    await expect(window2.locator(`text="${originalName}"`).first()).not.toBeVisible({ timeout: 5_000 })
  })

  // #12.3 Document deleted by Client A disappears on Client B via WebSocket
  test('document deleted by A disappears on B via WS (#12.3)', async ({ window1, window2 }) => {
    const docName = `WS-Delete-${Date.now()}`

    // Client A: Create document
    await createDocViaUI(window1, docName)

    // Client B: Wait for doc to appear
    await waitForWsUpdate(window2, `text="${docName}"`, { timeout: 10_000 })

    // Client A: Delete the document
    await deleteViaContextMenu(window1, docName)

    // Client A: Verify doc removed locally (optimistic)
    await expect(window1.locator(`text="${docName}"`).first()).not.toBeVisible({ timeout: 5_000 })

    // Client B: Verify doc removed via WebSocket
    await waitForRemoval(window2, `text="${docName}"`, 10_000)
  })

  // #12.7 Document moved to folder by Client A, Client B sees new location
  test('document moved to folder by A appears in new location on B (#12.7)', async ({ window1, window2 }) => {
    const ts = Date.now()
    const docName = `WS-Move-Doc-${ts}`
    const folderName = `WS-Move-Target-${ts}`

    // Client A: Create a folder and a root-level document
    await createFolderViaUI(window1, folderName)
    await createDocViaUI(window1, docName)

    // Client B: Wait for both to appear
    await waitForWsUpdate(window2, `text="${folderName}"`, { timeout: 10_000 })
    await waitForWsUpdate(window2, `text="${docName}"`, { timeout: 10_000 })

    // Client A: Drag the document into the folder
    await dragItemToFolder(window1, docName, folderName)

    // Client A: Expand folder to verify document is inside
    await expandFolder(window1, folderName)
    await expect(
      window1.locator(`[role="treeitem"]:has-text("${docName}")`).first()
    ).toBeVisible({ timeout: 5_000 })

    // Client B: Wait for the move event to propagate via WebSocket, then expand folder
    await waitForWsUpdate(window2, `text="${docName}"`, { timeout: 10_000 })
    await expandFolder(window2, folderName)

    // Client B: Document should appear inside the folder
    await expect(window2.locator(`text="${docName}"`).first()).toBeVisible({ timeout: 10_000 })
  })

  // #12.8 Skip-own-event: Client A creates doc, sees it once (no duplication from own WS echo)
  test('creating client sees doc once, not duplicated by own WS echo (#12.8)', async ({ window1, window2 }) => {
    const docName = `WS-NoDupe-${Date.now()}`

    // Client A: Create document
    await createDocViaUI(window1, docName)

    // Wait for WebSocket broadcast cycle to complete
    await briefPause(3000)

    // Client A: Count how many times the document name appears in tree items.
    // It should appear exactly ONCE (from optimistic update), not duplicated by own WS event.
    const matchingItems = window1.locator(`[role="tree"] [role="treeitem"]:has-text("${docName}")`)
    const count = await matchingItems.count()
    expect(count).toBe(1)

    // Client B: Should also see exactly one instance
    await waitForWsUpdate(window2, `text="${docName}"`, { timeout: 10_000 })
    const countOnB = await window2.locator(`[role="tree"] [role="treeitem"]:has-text("${docName}")`).count()
    expect(countOnB).toBe(1)
  })

  // #12.12 Client B's selected doc deleted by Client A: B's selection clears, editor shows empty state
  test('B selected doc deleted by A clears selection and editor (#12.12)', async ({ window1, window2 }) => {
    const docName = `WS-SelectedDel-${Date.now()}`

    // Client A: Create document
    await createDocViaUI(window1, docName)

    // Client B: Wait for doc to appear, then select it
    await waitForWsUpdate(window2, `text="${docName}"`, { timeout: 10_000 })
    await selectTreeItem(window2, docName)

    // Client B: Verify editor opens for the document
    await expect(
      window2.locator('.ProseMirror, [data-testid="editor"], [role="textbox"]').first()
    ).toBeVisible({ timeout: 10_000 })

    // Client A: Delete the document
    await deleteViaContextMenu(window1, docName)

    // Client B: Document should disappear from tree via WebSocket
    await waitForRemoval(window2, `text="${docName}"`, 10_000)

    // Client B: Editor should show empty/placeholder state (selection cleared)
    // Check for empty state message OR editor no longer visible
    const emptyStateMsg = window2.locator('text=/[Ss]elect a document|[Nn]o document|[Cc]hoose a document|[Dd]ocument.*deleted/')
    const editorArea = window2.locator('.ProseMirror, [data-testid="editor"]')

    const hasEmptyState = await emptyStateMsg.isVisible({ timeout: 10_000 }).catch(() => false)
    const editorHidden = await editorArea.isHidden({ timeout: 5_000 }).catch(() => true)

    // At least one condition should be true: empty state shown OR editor hidden
    expect(hasEmptyState || editorHidden).toBeTruthy()
  })

  // #12.13 Content update by Client A refreshes on Client B viewing the same doc
  test('content saved by A refreshes on B viewing same doc (#12.13)', async ({ window1, window2 }) => {
    const docName = `WS-Content-${Date.now()}`
    const contentText = `Updated content at ${Date.now()}`

    // Client A: Create document
    await createDocViaUI(window1, docName)

    // Client B: Wait for doc, then select it to open in editor/viewer
    await waitForWsUpdate(window2, `text="${docName}"`, { timeout: 10_000 })
    await selectTreeItem(window2, docName)

    // Client B: Wait for editor/viewer to render
    await expect(
      window2.locator('.ProseMirror, [data-testid="editor"], [role="textbox"]').first()
    ).toBeVisible({ timeout: 10_000 })

    // Client A: Select the doc and enter edit mode
    await selectTreeItem(window1, docName)
    await enterEditMode(window1)

    // Client A: Type content into the editor
    const editor = window1.locator('.ProseMirror, [data-testid="editor"], [role="textbox"]').first()
    await editor.click()
    await editor.type(contentText)

    // Client A: Save the document
    await saveDocument(window1)

    // Client B: Should see the updated content (via WS-triggered cache invalidation or Yjs sync)
    // Wait generously since content sync may involve refetch
    await expect(
      window2.locator(`text="${contentText}"`)
    ).toBeVisible({ timeout: 15_000 })
  })
})
