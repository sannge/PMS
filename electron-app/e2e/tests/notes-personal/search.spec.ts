/**
 * Notes Personal - Search Tests (Scenarios #9.1-9.6)
 *
 * Validates the search/filter functionality in the personal (My Notes)
 * knowledge tree, including filtering, auto-expansion, empty results,
 * and case-insensitive/partial matching.
 */
import { test, expect } from '../../fixtures/electron-app'
import { loginAs, TEST_USER_1, navigateToNotesPersonalTab } from '../../helpers/auth'
import {
  createDocViaUI,
  createFolderViaUI,
  createDocViaContextMenu,
  searchTree,
  clearSearch,
  getTreeItems,
  getTreeItem,
  expandFolder,
  collapseFolder,
} from '../../helpers/knowledge-ops'
import { briefPause } from '../../helpers/wait'

test.describe('Notes Personal - Search', () => {
  test.beforeEach(async ({ window }) => {
    await loginAs(window, TEST_USER_1)
    await navigateToNotesPersonalTab(window)
  })

  // #9.1 Search filters tree
  test('search query filters tree to show only matching items', async ({ window }) => {
    const ts = Date.now()
    const matchingDoc = `SearchMatch-${ts}`
    const nonMatchingDoc = `Unrelated-${ts}`

    // Create two documents with different names
    await createDocViaUI(window, matchingDoc)
    await createDocViaUI(window, nonMatchingDoc)

    // Both should be visible initially
    await expect(getTreeItem(window, matchingDoc)).toBeVisible({ timeout: 5_000 })
    await expect(getTreeItem(window, nonMatchingDoc)).toBeVisible({ timeout: 5_000 })

    // Search for the matching document
    await searchTree(window, 'SearchMatch')

    // Only the matching document should be visible
    await expect(getTreeItem(window, matchingDoc)).toBeVisible({ timeout: 5_000 })

    // Non-matching document should be hidden
    await expect(getTreeItem(window, nonMatchingDoc)).not.toBeVisible({ timeout: 3_000 })

    // Clear search to restore
    await clearSearch(window)
  })

  // #9.2 Search auto-expands folders
  test('search auto-expands folders containing matching documents', async ({ window }) => {
    const ts = Date.now()
    const folderName = `SearchFolder-${ts}`
    const docInsideFolder = `DeepSearchDoc-${ts}`

    // Create a folder with a document inside
    await createFolderViaUI(window, folderName)
    await createDocViaContextMenu(window, folderName, docInsideFolder)

    // Collapse the folder so document is hidden
    await collapseFolder(window, folderName)
    await expect(getTreeItem(window, docInsideFolder)).not.toBeVisible({ timeout: 3_000 })

    // Search for the document inside the folder
    await searchTree(window, 'DeepSearchDoc')

    // The folder should auto-expand and the document should be visible
    await expect(getTreeItem(window, docInsideFolder)).toBeVisible({ timeout: 5_000 })

    // The folder should also be visible (as the parent)
    await expect(getTreeItem(window, folderName)).toBeVisible({ timeout: 5_000 })

    // Clear search
    await clearSearch(window)
  })

  // #9.3 Search - no results
  test('search for nonexistent term shows "No results" message', async ({ window }) => {
    const nonsenseQuery = `ZZZZZZZ-NoMatch-${Date.now()}`

    // Search for something that definitely does not exist
    await searchTree(window, nonsenseQuery)

    // Should show a "no results" message
    await expect(
      window.locator('text=/[Nn]o results|[Nn]o match|[Nn]othing found|[Nn]o documents/')
    ).toBeVisible({ timeout: 5_000 })

    // Tree items should be empty or hidden
    const treeItems = getTreeItems(window)
    const count = await treeItems.count()
    expect(count).toBe(0)

    // Clear search
    await clearSearch(window)
  })

  // #9.4 Clear search restores full tree
  test('clearing search input restores the full tree', async ({ window }) => {
    const ts = Date.now()
    const doc1 = `ClearSearch1-${ts}`
    const doc2 = `ClearSearch2-${ts}`

    // Create two documents
    await createDocViaUI(window, doc1)
    await createDocViaUI(window, doc2)

    // Get the initial count of tree items
    const initialItems = getTreeItems(window)
    const initialCount = await initialItems.count()

    // Search to filter down
    await searchTree(window, 'ClearSearch1')
    await briefPause(300)

    // Should have fewer items
    const filteredCount = await getTreeItems(window).count()
    expect(filteredCount).toBeLessThanOrEqual(initialCount)

    // Clear the search
    await clearSearch(window)

    // Full tree should be restored
    const restoredCount = await getTreeItems(window).count()
    expect(restoredCount).toBeGreaterThanOrEqual(initialCount)

    // Both documents should be visible again
    await expect(getTreeItem(window, doc1)).toBeVisible({ timeout: 5_000 })
    await expect(getTreeItem(window, doc2)).toBeVisible({ timeout: 5_000 })
  })

  // #9.5 Search is case-insensitive
  test('search is case-insensitive', async ({ window }) => {
    const ts = Date.now()
    const docName = `MyDocument-${ts}`

    // Create a document with mixed case
    await createDocViaUI(window, docName)

    // Search with lowercase
    await searchTree(window, 'mydocument')

    // The document should still be found
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })

    // Clear and try uppercase
    await clearSearch(window)
    await searchTree(window, 'MYDOCUMENT')

    // Should still find it
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })

    // Clear search
    await clearSearch(window)
  })

  // #9.6 Search partial match
  test('search with partial query matches documents', async ({ window }) => {
    const ts = Date.now()
    const docName = `ArchitectureNotes-${ts}`

    // Create a document with a longer name
    await createDocViaUI(window, docName)

    // Search with a partial prefix
    await searchTree(window, 'Arch')

    // The document should be found via partial match
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })

    // Clear and try a different partial
    await clearSearch(window)
    await searchTree(window, 'Notes')

    // Should still match the document
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })

    // Clear search
    await clearSearch(window)
  })
})
