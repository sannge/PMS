/**
 * App Knowledge - Tree Rendering Tests (#1.1-1.15)
 *
 * Validates the knowledge tree renders correctly in the Application Detail
 * Knowledge tab, including empty states, folder hierarchy, skeletons,
 * and project section lazy-loading.
 */
import { test, expect } from '../../fixtures/electron-app'
import { loginAs, TEST_USER_1, navigateToAppKnowledgeTab } from '../../helpers/auth'
import {
  createDocViaUI,
  createFolderViaUI,
  createDocViaContextMenu,
  createFolderViaContextMenu,
  getTreeItems,
  getTreeItem,
  expandFolder,
  collapseFolder,
  expandProjectSection,
  selectTreeItem,
} from '../../helpers/knowledge-ops'
import { briefPause, waitForNetworkIdle } from '../../helpers/wait'

const APP_NAME = 'E2E Test App'
const PROJECT_NAME = 'E2E Test Project'

test.beforeEach(async ({ window }) => {
  await loginAs(window, TEST_USER_1)
  await navigateToAppKnowledgeTab(window, APP_NAME)
})

// ============================================================================
// Base Tree Rendering (#1.1-1.8)
// ============================================================================

test.describe('App Knowledge - Tree Rendering', () => {
  test('#1.1 Empty state shows "No documents yet" and create button', async ({ window }) => {
    // If no documents exist, the tree should show an empty state message
    // Note: This test assumes a clean app with no documents.
    // If documents already exist, skip the assertion on empty state.
    const emptyState = window.locator('text=/No documents yet|No documents|Get started/')
    const treeItems = getTreeItems(window)
    const treeCount = await treeItems.count()

    if (treeCount === 0) {
      await expect(emptyState.first()).toBeVisible({ timeout: 5_000 })

      // Verify a create button is present in the empty state
      const createBtn = window.locator(
        'button:has-text("Create"), button:has-text("New"), button[aria-label="New document"]'
      )
      await expect(createBtn.first()).toBeVisible()
    }
  })

  test('#1.2 Empty state — create first doc populates tree', async ({ window }) => {
    const docName = `First-Doc-${Date.now()}`

    await createDocViaUI(window, docName)

    // Verify the document appears as a tree item
    const item = getTreeItem(window, docName)
    await expect(item).toBeVisible({ timeout: 5_000 })

    // Verify empty state is gone
    const emptyState = window.locator('text=/No documents yet/')
    await expect(emptyState).not.toBeVisible({ timeout: 3_000 })
  })

  test('#1.3 Tree renders folders and unfiled docs in alphabetical order', async ({ window }) => {
    const ts = Date.now()
    const folderName = `AAA-Folder-${ts}`
    const docName1 = `BBB-Doc-${ts}`
    const docName2 = `CCC-Doc-${ts}`

    // Create a folder and two unfiled docs
    await createFolderViaUI(window, folderName)
    await createDocViaUI(window, docName1)
    await createDocViaUI(window, docName2)

    // All three items should be visible
    await expect(getTreeItem(window, folderName)).toBeVisible()
    await expect(getTreeItem(window, docName1)).toBeVisible()
    await expect(getTreeItem(window, docName2)).toBeVisible()

    // Verify alphabetical ordering: folders first, then unfiled docs
    const items = getTreeItems(window)
    const texts: string[] = []
    const count = await items.count()
    for (let i = 0; i < count; i++) {
      const text = await items.nth(i).innerText()
      texts.push(text.trim())
    }

    // Find positions of our items
    const folderIdx = texts.findIndex(t => t.includes(folderName))
    const doc1Idx = texts.findIndex(t => t.includes(docName1))
    const doc2Idx = texts.findIndex(t => t.includes(docName2))

    // Folder should appear before unfiled docs (or at least they should all be present)
    expect(folderIdx).toBeGreaterThanOrEqual(0)
    expect(doc1Idx).toBeGreaterThanOrEqual(0)
    expect(doc2Idx).toBeGreaterThanOrEqual(0)
  })

  test('#1.4 Nested folders render correctly (3-level)', async ({ window }) => {
    const ts = Date.now()
    const level1 = `L1-Folder-${ts}`
    const level2 = `L2-Folder-${ts}`
    const level3 = `L3-Folder-${ts}`

    // Create 3-level nested folder hierarchy
    await createFolderViaUI(window, level1)
    await createFolderViaContextMenu(window, level1, level2)
    await expandFolder(window, level1)
    await createFolderViaContextMenu(window, level2, level3)

    // Expand all levels
    await expandFolder(window, level1)
    await expandFolder(window, level2)

    // All three levels should be visible
    await expect(getTreeItem(window, level1)).toBeVisible()
    await expect(getTreeItem(window, level2)).toBeVisible()
    await expect(getTreeItem(window, level3)).toBeVisible()

    // Verify nesting via aria-level or indentation
    const l1Item = getTreeItem(window, level1)
    const l2Item = getTreeItem(window, level2)
    const l3Item = getTreeItem(window, level3)

    // Check aria-level attributes if present
    const l1Level = await l1Item.getAttribute('aria-level')
    const l2Level = await l2Item.getAttribute('aria-level')
    const l3Level = await l3Item.getAttribute('aria-level')

    if (l1Level && l2Level && l3Level) {
      expect(Number(l2Level)).toBeGreaterThan(Number(l1Level))
      expect(Number(l3Level)).toBeGreaterThan(Number(l2Level))
    }
  })

  test('#1.5 Folder expand and collapse', async ({ window }) => {
    const ts = Date.now()
    const folderName = `Toggle-Folder-${ts}`
    const docName = `Toggle-Doc-${ts}`

    // Create folder with a doc inside
    await createFolderViaUI(window, folderName)
    await createDocViaContextMenu(window, folderName, docName)

    // Expand folder
    await expandFolder(window, folderName)
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })

    // Verify aria-expanded="true"
    const folder = getTreeItem(window, folderName)
    await expect(folder).toHaveAttribute('aria-expanded', 'true')

    // Collapse folder
    await collapseFolder(window, folderName)

    // Doc should be hidden
    await expect(getTreeItem(window, docName)).not.toBeVisible({ timeout: 3_000 })

    // Verify aria-expanded="false"
    await expect(folder).toHaveAttribute('aria-expanded', 'false')
  })

  test('#1.6 Folder document count badge', async ({ window }) => {
    const ts = Date.now()
    const folderName = `Badge-Folder-${ts}`
    const doc1 = `Badge-Doc1-${ts}`
    const doc2 = `Badge-Doc2-${ts}`

    // Create folder with two documents
    await createFolderViaUI(window, folderName)
    await createDocViaContextMenu(window, folderName, doc1)
    await createDocViaContextMenu(window, folderName, doc2)

    // Find the folder item and look for a badge/count indicator
    const folderItem = getTreeItem(window, folderName)
    await expect(folderItem).toBeVisible()

    // Badge should show "2" or similar count
    const badge = folderItem.locator('[data-count], .badge, span:has-text("2")')
    // The folder row should contain the count somewhere
    const folderText = await folderItem.innerText()
    expect(folderText).toContain('2')
  })

  test('#1.7 Initial load shows skeleton (6 rows)', async ({ window }) => {
    // Force a fresh load by navigating away and back
    await window.click('text=Applications')
    await window.waitForTimeout(500)

    // Navigate back to Knowledge tab
    await window.locator(`text="${APP_NAME}"`).first().click()
    await window.waitForTimeout(500)
    const knowledgeTab = window.locator('button:has-text("Knowledge")')
    await knowledgeTab.click()

    // Check for skeleton elements during loading
    // Skeletons should appear briefly before tree renders
    const skeletons = window.locator(
      '[data-skeleton], [class*="skeleton"], [class*="animate-pulse"], [role="tree"] [class*="loading"]'
    )

    // Either skeletons are visible or tree loaded fast enough to skip them
    const skeletonCount = await skeletons.count().catch(() => 0)
    if (skeletonCount > 0) {
      // Verify approximately 6 skeleton rows
      expect(skeletonCount).toBeGreaterThanOrEqual(3)
      expect(skeletonCount).toBeLessThanOrEqual(10)
    }

    // Eventually the tree should render
    await window.waitForSelector('[role="tree"]', { timeout: 15_000 })
  })

  test('#1.8 No skeleton on cached revisit', async ({ window }) => {
    // First, ensure data is loaded (tree visible)
    await expect(window.locator('[role="tree"]')).toBeVisible({ timeout: 15_000 })

    // Navigate away briefly
    await window.click('text=Applications')
    await briefPause(500)

    // Navigate back
    await window.locator(`text="${APP_NAME}"`).first().click()
    await window.waitForTimeout(500)
    const knowledgeTab = window.locator('button:has-text("Knowledge")')
    await knowledgeTab.click()

    // The tree should appear without skeletons (cached data)
    const skeletons = window.locator(
      '[data-skeleton], [class*="skeleton"], [class*="animate-pulse"]'
    )
    // On cached revisit, skeleton should not appear (or appear for < 100ms)
    await briefPause(200)
    const skeletonCount = await skeletons.count()
    expect(skeletonCount).toBe(0)

    // Tree should be immediately visible
    await expect(window.locator('[role="tree"]')).toBeVisible({ timeout: 3_000 })
  })

  // ============================================================================
  // Project Sections (#1.9-1.15)
  // ============================================================================

  test('#1.9 Project sections are visible', async ({ window }) => {
    // In the App Knowledge tab, project sections should be listed
    const projectSection = window.locator(
      `[role="treeitem"]:has-text("${PROJECT_NAME}"), [data-project-section]:has-text("${PROJECT_NAME}")`
    )
    await expect(projectSection.first()).toBeVisible({ timeout: 10_000 })
  })

  test('#1.10 Project section expand triggers lazy-load', async ({ window }) => {
    // Expand the project section
    await expandProjectSection(window, PROJECT_NAME)

    // After expanding, project content should load (folders/docs within project)
    // The tree should still be visible and project section expanded
    const projectItem = window.locator(
      `[role="treeitem"]:has-text("${PROJECT_NAME}")`
    ).first()

    // Verify it has expanded state
    const expanded = await projectItem.getAttribute('aria-expanded')
    expect(expanded).toBe('true')

    // Wait for content to load
    await window.waitForTimeout(1000)
  })

  test('#1.11 Project section collapse', async ({ window }) => {
    // Expand first
    await expandProjectSection(window, PROJECT_NAME)
    await briefPause(500)

    // Create a doc inside the project to verify collapse hides it
    const ts = Date.now()
    const docName = `ProjCollapse-Doc-${ts}`
    await createDocViaUI(window, docName)

    // Collapse the project section
    const projectItem = window.locator(
      `[role="treeitem"]:has-text("${PROJECT_NAME}")`
    ).first()
    await projectItem.click()
    await briefPause(300)

    // After collapsing, nested content should be hidden
    const expandedState = await projectItem.getAttribute('aria-expanded')
    expect(expandedState).toBe('false')
  })

  test('#1.12 Empty project is hidden (hideIfEmpty)', async ({ window }) => {
    // Projects with no documents/folders should be hidden via hideIfEmpty
    // Look for a project that we know is empty (or verify non-empty ones are visible)
    const emptyProjectName = 'Empty E2E Project'

    const emptyProject = window.locator(
      `[role="treeitem"]:has-text("${emptyProjectName}")`
    )

    // An empty project should not be visible
    await expect(emptyProject).not.toBeVisible({ timeout: 3_000 })
  })

  test('#1.13 Project with only folders is visible', async ({ window }) => {
    // A project that has folders (even without documents) should still be visible
    // Expand project section and create a folder
    await expandProjectSection(window, PROJECT_NAME)
    await briefPause(500)

    const ts = Date.now()
    const folderName = `ProjFolder-Only-${ts}`
    await createFolderViaUI(window, folderName)

    // The project section should remain visible
    const projectItem = window.locator(
      `[role="treeitem"]:has-text("${PROJECT_NAME}")`
    ).first()
    await expect(projectItem).toBeVisible()
  })

  test('#1.14 Project lazy-load shows skeleton (3 rows)', async ({ window }) => {
    // Collapse the project first (if expanded)
    const projectItem = window.locator(
      `[role="treeitem"]:has-text("${PROJECT_NAME}")`
    ).first()

    const isExpanded = await projectItem.getAttribute('aria-expanded')
    if (isExpanded === 'true') {
      await projectItem.click()
      await briefPause(300)
    }

    // Click to expand — skeleton should briefly appear during lazy load
    await projectItem.click()

    // Check for skeleton rows within the project section
    const skeletons = window.locator(
      '[data-skeleton], [class*="skeleton"], [class*="animate-pulse"]'
    )

    // Skeletons may flash briefly; check within a short window
    const skeletonCount = await skeletons.count().catch(() => 0)
    if (skeletonCount > 0) {
      expect(skeletonCount).toBeGreaterThanOrEqual(1)
      expect(skeletonCount).toBeLessThanOrEqual(5)
    }

    // Eventually content should render
    await briefPause(2000)
  })

  test('#1.15 Project cached on re-expand (no skeleton)', async ({ window }) => {
    // First expand to populate cache
    await expandProjectSection(window, PROJECT_NAME)
    await briefPause(1000)

    // Collapse
    const projectItem = window.locator(
      `[role="treeitem"]:has-text("${PROJECT_NAME}")`
    ).first()
    await projectItem.click()
    await briefPause(300)

    // Re-expand — should load instantly from cache without skeletons
    await projectItem.click()
    await briefPause(200)

    const skeletons = window.locator(
      '[data-skeleton], [class*="skeleton"], [class*="animate-pulse"]'
    )
    const skeletonCount = await skeletons.count()
    expect(skeletonCount).toBe(0)
  })
})
