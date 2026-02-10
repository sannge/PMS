/**
 * App Knowledge - Search Tests (#9.1-9.8)
 *
 * Validates search functionality in the Application Detail Knowledge tab.
 * Includes shared search scenarios (#9.1-9.6) and app-specific scenarios
 * that test filtering within project sections (#9.7-9.8).
 */
import { test, expect } from '../../fixtures/electron-app'
import { loginAs, TEST_USER_1, navigateToAppKnowledgeTab } from '../../helpers/auth'
import {
  createDocViaUI,
  createFolderViaUI,
  createDocViaContextMenu,
  searchTree,
  clearSearch,
  getTreeItems,
  getTreeItem,
  expandFolder,
  expandProjectSection,
  selectTreeItem,
  enterEditMode,
  saveDocument,
} from '../../helpers/knowledge-ops'
import { briefPause, waitForNetworkIdle } from '../../helpers/wait'

const APP_NAME = 'E2E Test App'
const PROJECT_NAME = 'E2E Test Project'

test.beforeEach(async ({ window }) => {
  await loginAs(window, TEST_USER_1)
  await navigateToAppKnowledgeTab(window, APP_NAME)
})

test.describe('App Knowledge - Search', () => {
  // ============================================================================
  // Shared Search Tests (#9.1-9.6)
  // ============================================================================

  test('#9.1 Search input is visible', async ({ window }) => {
    // The search input should be visible in the tree panel
    const searchInput = window.locator(
      'input[placeholder*="Search"], input[placeholder*="search"], input[type="search"]'
    ).first()
    await expect(searchInput).toBeVisible({ timeout: 5_000 })
  })

  test('#9.2 Search filters tree items by name', async ({ window }) => {
    const ts = Date.now()
    const matchDoc = `SearchMatch-${ts}`
    const noMatchDoc = `Unrelated-${ts}`

    // Create two documents
    await createDocViaUI(window, matchDoc)
    await createDocViaUI(window, noMatchDoc)

    // Both should be visible initially
    await expect(getTreeItem(window, matchDoc)).toBeVisible()
    await expect(getTreeItem(window, noMatchDoc)).toBeVisible()

    // Search for the matching document
    await searchTree(window, 'SearchMatch')

    // Only the matching doc should be visible
    await expect(getTreeItem(window, matchDoc)).toBeVisible({ timeout: 5_000 })
    await expect(
      window.locator(`[role="treeitem"]:has-text("${noMatchDoc}")`)
    ).not.toBeVisible({ timeout: 3_000 })

    // Clear search to restore tree
    await clearSearch(window)
  })

  test('#9.3 Search with no results shows empty state', async ({ window }) => {
    // Search for something that definitely does not exist
    await searchTree(window, `nonexistent-query-${Date.now()}`)

    // Should show no results message
    const noResults = window.locator(
      'text=/No results|No documents found|No matches|Nothing found/i'
    )
    await expect(noResults.first()).toBeVisible({ timeout: 5_000 })

    // Clear search
    await clearSearch(window)
  })

  test('#9.4 Clear search restores full tree', async ({ window }) => {
    const ts = Date.now()
    const doc1 = `Restore-Doc1-${ts}`
    const doc2 = `Restore-Doc2-${ts}`

    // Create two documents
    await createDocViaUI(window, doc1)
    await createDocViaUI(window, doc2)

    // Search to filter
    await searchTree(window, doc1)
    await expect(getTreeItem(window, doc1)).toBeVisible()
    await expect(
      window.locator(`[role="treeitem"]:has-text("${doc2}")`)
    ).not.toBeVisible({ timeout: 3_000 })

    // Clear search
    await clearSearch(window)

    // Both documents should be visible again
    await expect(getTreeItem(window, doc1)).toBeVisible({ timeout: 5_000 })
    await expect(getTreeItem(window, doc2)).toBeVisible({ timeout: 5_000 })
  })

  test('#9.5 Search matches folder names', async ({ window }) => {
    const ts = Date.now()
    const folderName = `SearchFolder-${ts}`
    const otherDoc = `OtherDoc-${ts}`

    // Create a folder and an unrelated document
    await createFolderViaUI(window, folderName)
    await createDocViaUI(window, otherDoc)

    // Search by folder name
    await searchTree(window, 'SearchFolder')

    // Folder should be visible, unrelated doc should be hidden
    await expect(getTreeItem(window, folderName)).toBeVisible({ timeout: 5_000 })
    await expect(
      window.locator(`[role="treeitem"]:has-text("${otherDoc}")`)
    ).not.toBeVisible({ timeout: 3_000 })

    await clearSearch(window)
  })

  test('#9.6 Search is case-insensitive', async ({ window }) => {
    const ts = Date.now()
    const docName = `CaseTest-${ts}`

    await createDocViaUI(window, docName)

    // Search with lowercase
    await searchTree(window, 'casetest')

    // Document should still be found (case-insensitive match)
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })

    // Search with uppercase
    await clearSearch(window)
    await searchTree(window, 'CASETEST')

    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })

    await clearSearch(window)
  })

  // ============================================================================
  // App-Specific: Project Section Search (#9.7-9.8)
  // ============================================================================

  test('#9.7 Search filters project sections (hides non-matching project items)', async ({ window }) => {
    const ts = Date.now()
    const appDoc = `AppSearch-${ts}`
    const projDoc = `ProjSearch-${ts}`

    // Create an app-level document
    await createDocViaUI(window, appDoc)

    // Expand project section and create a project-level document
    await expandProjectSection(window, PROJECT_NAME)
    await briefPause(500)
    await createDocViaUI(window, projDoc)

    // Clear and search for the app-level doc only
    await clearSearch(window)
    await searchTree(window, 'AppSearch')

    // App doc should be visible
    await expect(getTreeItem(window, appDoc)).toBeVisible({ timeout: 5_000 })

    // Project doc should NOT be visible (filtered out)
    await expect(
      window.locator(`[role="treeitem"]:has-text("${projDoc}")`)
    ).not.toBeVisible({ timeout: 3_000 })

    await clearSearch(window)
  })

  test('#9.8 Search inside project sections finds project documents', async ({ window }) => {
    const ts = Date.now()
    const appDoc = `AppOnly-${ts}`
    const projDoc = `ProjOnly-${ts}`

    // Create an app-level document
    await createDocViaUI(window, appDoc)

    // Expand project section and create a project-level document
    await expandProjectSection(window, PROJECT_NAME)
    await briefPause(500)
    await createDocViaUI(window, projDoc)

    // Search for the project-level doc
    await clearSearch(window)
    await searchTree(window, 'ProjOnly')

    // Project doc should be visible (search spans project sections)
    await expect(getTreeItem(window, projDoc)).toBeVisible({ timeout: 5_000 })

    // App doc should NOT be visible (filtered out)
    await expect(
      window.locator(`[role="treeitem"]:has-text("${appDoc}")`)
    ).not.toBeVisible({ timeout: 3_000 })

    await clearSearch(window)
  })
})
