/**
 * Notes App - Search Tests (Scenarios #9.1-9.8)
 *
 * Validates search/filtering functionality in the application-scoped Notes tree,
 * including project-section-aware filtering.
 */
import { test, expect } from '../../fixtures/electron-app'
import { loginAs, TEST_USER_1, navigateToNotesAppTab } from '../../helpers/auth'
import {
  createDocViaUI,
  createFolderViaUI,
  createDocViaContextMenu,
  searchTree,
  clearSearch,
  expandFolder,
  expandProjectSection,
  getTreeItems,
  getTreeItem,
} from '../../helpers/knowledge-ops'
import { briefPause } from '../../helpers/wait'

const APP_NAME = 'E2E Test App'
const PROJECT_NAME = 'E2E Test Project'

test.describe('Notes App - Search', () => {
  test.beforeEach(async ({ window }) => {
    await loginAs(window, TEST_USER_1)
    await navigateToNotesAppTab(window, APP_NAME)
  })

  // ---------------------------------------------------------------------------
  // #9.1 Search filters tree
  // ---------------------------------------------------------------------------
  test('#9.1 search query filters tree to matching items only', async ({ window }) => {
    const ts = Date.now()
    const matchDoc = `SearchMatch-${ts}`
    const noMatchDoc = `NoMatch-${ts}`

    // Create two docs
    await createDocViaUI(window, matchDoc)
    await createDocViaUI(window, noMatchDoc)

    // Search for the matching doc
    await searchTree(window, 'SearchMatch')

    // Matching doc should be visible
    await expect(getTreeItem(window, matchDoc)).toBeVisible({ timeout: 5_000 })

    // Non-matching doc should be filtered out
    await expect(window.locator(`text="${noMatchDoc}"`).first()).not.toBeVisible({ timeout: 3_000 })

    // Clean up
    await clearSearch(window)
  })

  // ---------------------------------------------------------------------------
  // #9.2 Search auto-expands folders
  // ---------------------------------------------------------------------------
  test('#9.2 search auto-expands collapsed folders to show matches', async ({ window }) => {
    const ts = Date.now()
    const folderName = `SearchFolder-${ts}`
    const docName = `DeepSearchDoc-${ts}`

    // Create folder with a doc inside
    await createFolderViaUI(window, folderName)
    await createDocViaContextMenu(window, folderName, docName)

    // Make sure folder is collapsed
    // (it may be auto-expanded after creation, so we collapse it first)
    const folderItem = getTreeItem(window, folderName)
    const expanded = await folderItem.getAttribute('aria-expanded')
    if (expanded === 'true') {
      await folderItem.click()
      await briefPause(300)
    }

    // Search for the doc inside the folder
    await searchTree(window, 'DeepSearchDoc')

    // The folder should auto-expand and the doc should be visible
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })

    // Clean up
    await clearSearch(window)
  })

  // ---------------------------------------------------------------------------
  // #9.3 Search -- no results
  // ---------------------------------------------------------------------------
  test('#9.3 search with no matches shows "No results" message', async ({ window }) => {
    const nonsenseQuery = `zzz-nonexistent-${Date.now()}`

    await searchTree(window, nonsenseQuery)

    // Should show a "No results" or similar message
    await expect(
      window.locator('text=/No results|No documents found|Nothing found/i').first()
    ).toBeVisible({ timeout: 5_000 })

    // Clean up
    await clearSearch(window)
  })

  // ---------------------------------------------------------------------------
  // #9.4 Clear search
  // ---------------------------------------------------------------------------
  test('#9.4 clearing search restores the full tree', async ({ window }) => {
    const ts = Date.now()
    const doc1 = `ClearSearch1-${ts}`
    const doc2 = `ClearSearch2-${ts}`

    await createDocViaUI(window, doc1)
    await createDocViaUI(window, doc2)

    // Search for doc1 only
    await searchTree(window, 'ClearSearch1')
    await expect(getTreeItem(window, doc1)).toBeVisible({ timeout: 5_000 })
    await expect(window.locator(`text="${doc2}"`).first()).not.toBeVisible({ timeout: 3_000 })

    // Clear search
    await clearSearch(window)

    // Both docs should be visible again
    await expect(getTreeItem(window, doc1)).toBeVisible({ timeout: 5_000 })
    await expect(getTreeItem(window, doc2)).toBeVisible({ timeout: 5_000 })
  })

  // ---------------------------------------------------------------------------
  // #9.5 Search is case-insensitive
  // ---------------------------------------------------------------------------
  test('#9.5 search is case-insensitive', async ({ window }) => {
    const docName = `CaseSensitiveDoc-${Date.now()}`

    await createDocViaUI(window, docName)

    // Search with lowercase
    await searchTree(window, 'casesensitivedoc')

    // Should still find the doc
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })

    // Clean up
    await clearSearch(window)
  })

  // ---------------------------------------------------------------------------
  // #9.6 Search partial match
  // ---------------------------------------------------------------------------
  test('#9.6 search matches partial strings', async ({ window }) => {
    const docName = `ArchitectureNotes-${Date.now()}`

    await createDocViaUI(window, docName)

    // Search with partial string
    await searchTree(window, 'Architect')

    // Should find the doc
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })

    // Clean up
    await clearSearch(window)
  })

  // ---------------------------------------------------------------------------
  // #9.7 Search filters project sections (app-specific)
  // ---------------------------------------------------------------------------
  test('#9.7 search filters project sections by project name', async ({ window }) => {
    // Expand the project section to ensure it's loaded
    await expandProjectSection(window, PROJECT_NAME)
    await briefPause(500)

    // Search for the project name
    await searchTree(window, PROJECT_NAME)

    // The project section matching the query should be visible
    await expect(
      window.locator(`text="${PROJECT_NAME}"`).first()
    ).toBeVisible({ timeout: 5_000 })

    // Clean up
    await clearSearch(window)
  })

  // ---------------------------------------------------------------------------
  // #9.8 Search inside project sections (app-specific)
  // ---------------------------------------------------------------------------
  test('#9.8 search finds documents inside project sections', async ({ window }) => {
    const projDocName = `ProjSearchDoc-${Date.now()}`

    // Expand project section
    await expandProjectSection(window, PROJECT_NAME)

    // Create a doc inside the project
    await window.locator(`text="${PROJECT_NAME}"`).first().click({ button: 'right' })
    await window.click('text=New Document')

    await window.waitForSelector(
      'input[placeholder*="title"], input[placeholder*="name"], input[placeholder*="document"]',
      { timeout: 5_000 }
    )
    await window.fill(
      'input[placeholder*="title"], input[placeholder*="name"], input[placeholder*="document"]',
      projDocName
    )
    await window.click('button:has-text("Create")')
    await expect(window.locator(`text="${projDocName}"`).first()).toBeVisible({ timeout: 5_000 })

    // Clear any previous state
    await clearSearch(window)
    await briefPause(300)

    // Search for the project doc
    await searchTree(window, 'ProjSearchDoc')

    // The project section should be visible with the matching doc
    await expect(
      window.locator(`text="${projDocName}"`).first()
    ).toBeVisible({ timeout: 5_000 })

    // The project section header should also be visible (to provide context)
    await expect(
      window.locator(`text="${PROJECT_NAME}"`).first()
    ).toBeVisible({ timeout: 5_000 })

    // Clean up
    await clearSearch(window)
  })
})
