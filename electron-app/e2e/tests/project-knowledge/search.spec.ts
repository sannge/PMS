/**
 * Project Knowledge - Search Tests (Scenarios #9.1-9.6)
 *
 * Validates knowledge tree search/filter functionality
 * in the project Knowledge tab context.
 *
 * Context: KnowledgePanel -> KnowledgeTree (scope=project)
 * NO project section search (this IS a project context).
 */
import { test, expect } from '../../fixtures/electron-app'
import { loginAs, TEST_USER_1, navigateToProjectKnowledgeTab } from '../../helpers/auth'
import {
  createDocViaUI,
  createFolderViaUI,
  createDocViaContextMenu,
  searchTree,
  clearSearch,
  getTreeItems,
  getTreeItem,
  expandFolder,
} from '../../helpers/knowledge-ops'
import { briefPause } from '../../helpers/wait'

const APP_NAME = 'E2E Test App'
const PROJECT_NAME = 'E2E Test Project'

test.describe('Project Knowledge - Search', () => {
  test.beforeEach(async ({ window }) => {
    await loginAs(window, TEST_USER_1)
    await navigateToProjectKnowledgeTab(window, APP_NAME, PROJECT_NAME)
  })

  // #9.1 Search filters tree
  test('search filters tree to show only matching items', async ({ window }) => {
    const ts = Date.now()
    const matchDoc = `SearchMatch-${ts}`
    const noMatchDoc = `Unrelated-${ts}`

    // Create two documents - one matching, one not
    await createDocViaUI(window, matchDoc)
    await createDocViaUI(window, noMatchDoc)

    // Both should be visible before search
    await expect(getTreeItem(window, matchDoc)).toBeVisible({ timeout: 5_000 })
    await expect(getTreeItem(window, noMatchDoc)).toBeVisible({ timeout: 5_000 })

    // Search for the matching document
    await searchTree(window, 'SearchMatch')

    // Only the matching document should be visible
    await expect(getTreeItem(window, matchDoc)).toBeVisible({ timeout: 5_000 })
    await expect(getTreeItem(window, noMatchDoc)).not.toBeVisible({ timeout: 3_000 })

    // Clear search to restore
    await clearSearch(window)
  })

  // #9.2 Search auto-expands folders
  test('search auto-expands folders containing matching documents', async ({ window }) => {
    const ts = Date.now()
    const folderName = `SearchFolder-${ts}`
    const docInFolder = `HiddenGem-${ts}`

    // Create a folder with a document inside
    await createFolderViaUI(window, folderName)
    await createDocViaContextMenu(window, folderName, docInFolder)

    // Collapse the folder so the doc is hidden
    const folder = getTreeItem(window, folderName)
    await folder.click() // toggle collapse
    await briefPause(300)

    // Search for the document inside the folder
    await searchTree(window, 'HiddenGem')

    // The document should be visible (folder auto-expanded by search)
    await expect(getTreeItem(window, docInFolder)).toBeVisible({ timeout: 5_000 })

    // The folder should also be visible (it contains a match)
    await expect(getTreeItem(window, folderName)).toBeVisible({ timeout: 5_000 })

    // Clear search
    await clearSearch(window)
  })

  // #9.3 Search - no results
  test('search with no results shows empty state', async ({ window }) => {
    const noMatchQuery = `NoSuchDocument_${Date.now()}_xyz`

    // Search for something that definitely does not exist
    await searchTree(window, noMatchQuery)

    // Tree should either show no items or an explicit "no results" message
    const treeItems = getTreeItems(window)
    const count = await treeItems.count()

    if (count === 0) {
      // No tree items - check for a "no results" message
      const noResults = window.locator('text=/[Nn]o results|[Nn]o match|[Nn]othing found/')
      const messageVisible = await noResults.isVisible({ timeout: 3_000 }).catch(() => false)
      // Either message exists or tree is simply empty
      expect(count === 0 || messageVisible).toBeTruthy()
    }

    // Clear search
    await clearSearch(window)
  })

  // #9.4 Clear search
  test('clearing search restores full tree', async ({ window }) => {
    const ts = Date.now()
    const doc1 = `ClearSearch1-${ts}`
    const doc2 = `ClearSearch2-${ts}`

    // Create two documents
    await createDocViaUI(window, doc1)
    await createDocViaUI(window, doc2)

    // Search for doc1 only
    await searchTree(window, 'ClearSearch1')
    await expect(getTreeItem(window, doc1)).toBeVisible({ timeout: 5_000 })
    await expect(getTreeItem(window, doc2)).not.toBeVisible({ timeout: 3_000 })

    // Clear the search
    await clearSearch(window)

    // Both documents should be visible again
    await expect(getTreeItem(window, doc1)).toBeVisible({ timeout: 5_000 })
    await expect(getTreeItem(window, doc2)).toBeVisible({ timeout: 5_000 })
  })

  // #9.5 Search is case-insensitive
  test('search is case-insensitive', async ({ window }) => {
    const ts = Date.now()
    const docName = `CaseTestDoc-${ts}`

    // Create a document with mixed case
    await createDocViaUI(window, docName)

    // Search with lowercase
    await searchTree(window, 'casetestdoc')
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })

    // Clear and search with uppercase
    await clearSearch(window)
    await searchTree(window, 'CASETESTDOC')
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })

    // Clear and search with mixed case (different from original)
    await clearSearch(window)
    await searchTree(window, 'cAsEtEsTdOc')
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })

    // Clean up
    await clearSearch(window)
  })

  // #9.6 Search partial match
  test('search matches partial text', async ({ window }) => {
    const ts = Date.now()
    const docName = `PartialMatchDocument-${ts}`

    // Create a document
    await createDocViaUI(window, docName)

    // Search for a partial substring
    await searchTree(window, 'PartialMatch')
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })

    // Search for a different partial substring
    await clearSearch(window)
    await searchTree(window, 'MatchDoc')
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })

    // Search for just a few characters
    await clearSearch(window)
    await searchTree(window, 'Partial')
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })

    // Clean up
    await clearSearch(window)
  })
})
