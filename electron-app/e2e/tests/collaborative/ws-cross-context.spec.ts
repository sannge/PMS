/**
 * WebSocket Cross-Context Sync Tests (2 clients) - Scenarios #12.14-12.17
 *
 * Validates that knowledge tree changes sync across DIFFERENT contexts:
 * - Notes page (App tab) <-> Application Detail (Knowledge tab)
 * - Notes page (App tab, project section) <-> Project Detail (Knowledge tab)
 * - App Detail KB <-> Project Detail KB
 * - Project Detail KB <-> Notes App tab
 *
 * Each test has the two clients viewing the SAME application/project data
 * from different pages/tabs in the UI.
 */
import { test, expect } from '../../fixtures/two-clients'
import {
  loginAs,
  navigateToNotesAppTab,
  navigateToAppKnowledgeTab,
  navigateToProjectKnowledgeTab,
  TEST_USER_1,
  TEST_USER_2,
} from '../../helpers/auth'
import {
  createDocViaUI,
  createFolderViaUI,
  deleteViaContextMenu,
  renameViaContextMenu,
  selectTreeItem,
} from '../../helpers/knowledge-ops'
import { waitForWsUpdate, waitForRemoval, briefPause } from '../../helpers/wait'

/**
 * Shared application and project names for cross-context tests.
 *
 * PREREQUISITES:
 * - These entities must exist in the backend database before running these tests
 * - Both TEST_USER_1 and TEST_USER_2 must be members of the application
 * - Both TEST_USER_1 and TEST_USER_2 must be members of the project
 * - The application must have at least one project (PROJECT_NAME)
 *
 * Setup via backend seed script or API calls before E2E test run.
 */
const APP_NAME = 'E2E Test App'
const PROJECT_NAME = 'E2E Test Project'

test.describe('WebSocket Cross-Context Sync', () => {
  // No shared beforeEach - each test navigates to different contexts

  // #12.14 Notes App tab <-> App Detail Knowledge tab
  test('Notes App tab <-> App Detail KB tab sync (#12.14)', async ({ window1, window2 }) => {
    // Client A: Login and navigate to Notes page -> App tab
    // Client B: Login and navigate to Application Detail -> Knowledge tab
    await Promise.all([
      loginAs(window1, TEST_USER_1).then(() => navigateToNotesAppTab(window1, APP_NAME)),
      loginAs(window2, TEST_USER_2).then(() => navigateToAppKnowledgeTab(window2, APP_NAME)),
    ])

    const ts = Date.now()

    // --- Test 1: Create on Notes App tab, see on App KB tab ---
    const docFromNotes = `Cross-NotesToKB-${ts}`
    await createDocViaUI(window1, docFromNotes)

    // Client B (App KB): Should see the new doc
    await waitForWsUpdate(window2, `text="${docFromNotes}"`, { timeout: 10_000 })
    await expect(window2.locator(`text="${docFromNotes}"`).first()).toBeVisible()

    // --- Test 2: Create on App KB tab, see on Notes App tab ---
    const docFromKB = `Cross-KBToNotes-${ts}`
    await createDocViaUI(window2, docFromKB)

    // Client A (Notes App tab): Should see the new doc
    await waitForWsUpdate(window1, `text="${docFromKB}"`, { timeout: 10_000 })
    await expect(window1.locator(`text="${docFromKB}"`).first()).toBeVisible()

    // --- Test 3: Rename on A, see update on B ---
    const renamedDoc = `Cross-Renamed-${ts}`
    await renameViaContextMenu(window1, docFromNotes, renamedDoc)

    // Client B: Should see the renamed document
    await waitForWsUpdate(window2, `text="${renamedDoc}"`, { timeout: 10_000 })
    // Original name should be gone
    await expect(window2.locator(`text="${docFromNotes}"`).first()).not.toBeVisible({ timeout: 5_000 })

    // --- Test 4: Delete on B, disappears on A ---
    await deleteViaContextMenu(window2, docFromKB)

    // Client A: Should see it disappear
    await waitForRemoval(window1, `text="${docFromKB}"`, 10_000)
  })

  // #12.15 Notes App tab (project section) <-> Project Detail Knowledge tab
  test('Notes App tab (project) <-> Project Detail KB sync (#12.15)', async ({ window1, window2 }) => {
    // Client A: Login -> Notes page -> App tab (will see project section)
    // Client B: Login -> Project Detail -> Knowledge tab
    await Promise.all([
      loginAs(window1, TEST_USER_1).then(() => navigateToNotesAppTab(window1, APP_NAME)),
      loginAs(window2, TEST_USER_2).then(() =>
        navigateToProjectKnowledgeTab(window2, APP_NAME, PROJECT_NAME)
      ),
    ])

    const ts = Date.now()

    // --- Test 1: Create doc on Notes App tab (in project scope), see on Project KB ---
    // In the Notes App tab, the project section should be visible.
    // Click/expand the project section to scope the creation.
    const projectSection = window1.locator(`text="${PROJECT_NAME}"`)
    if (await projectSection.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await projectSection.first().click()
      await briefPause(500)
    }

    const docFromNotes = `CrossProj-NotesToPKB-${ts}`
    await createDocViaUI(window1, docFromNotes)

    // Client B (Project KB): Should see the new doc
    await waitForWsUpdate(window2, `text="${docFromNotes}"`, { timeout: 10_000 })
    await expect(window2.locator(`text="${docFromNotes}"`).first()).toBeVisible()

    // --- Test 2: Create doc on Project KB tab, see on Notes App tab ---
    const docFromPKB = `CrossProj-PKBToNotes-${ts}`
    await createDocViaUI(window2, docFromPKB)

    // Client A (Notes App tab): Should see the new doc in project section
    await waitForWsUpdate(window1, `text="${docFromPKB}"`, { timeout: 10_000 })
    await expect(window1.locator(`text="${docFromPKB}"`).first()).toBeVisible()

    // --- Test 3: Delete on B, disappears on A ---
    await deleteViaContextMenu(window2, docFromPKB)
    await waitForRemoval(window1, `text="${docFromPKB}"`, 10_000)
  })

  // #12.16 App Detail KB -> Project Detail KB (project-scoped doc created in App KB)
  test('App Detail KB -> Project Detail KB sync (#12.16)', async ({ window1, window2 }) => {
    // Client A: App Detail -> Knowledge tab
    // Client B: Project Detail -> Knowledge tab
    await Promise.all([
      loginAs(window1, TEST_USER_1).then(() => navigateToAppKnowledgeTab(window1, APP_NAME)),
      loginAs(window2, TEST_USER_2).then(() =>
        navigateToProjectKnowledgeTab(window2, APP_NAME, PROJECT_NAME)
      ),
    ])

    const ts = Date.now()

    // Client A: In App KB, navigate to the project section and create a project-scoped doc
    const projectSection = window1.locator(`text="${PROJECT_NAME}"`)
    if (await projectSection.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await projectSection.first().click()
      await briefPause(500)
    }

    const docName = `CrossAppToProj-${ts}`
    await createDocViaUI(window1, docName)

    // Client B (Project KB): Should see the new project-scoped doc
    await waitForWsUpdate(window2, `text="${docName}"`, { timeout: 10_000 })
    await expect(window2.locator(`text="${docName}"`).first()).toBeVisible()

    // Also test folder creation syncs across
    const folderName = `CrossAppToProj-Folder-${ts}`
    await createFolderViaUI(window1, folderName)

    // Client B: Should see the folder
    await waitForWsUpdate(window2, `text="${folderName}"`, { timeout: 10_000 })
    await expect(window2.locator(`text="${folderName}"`).first()).toBeVisible()
  })

  // #12.17 Project Detail KB -> Notes App tab (doc created in Project KB appears in Notes)
  test('Project Detail KB -> Notes App tab sync (#12.17)', async ({ window1, window2 }) => {
    // Client A: Project Detail -> Knowledge tab
    // Client B: Notes page -> App tab
    await Promise.all([
      loginAs(window1, TEST_USER_1).then(() =>
        navigateToProjectKnowledgeTab(window1, APP_NAME, PROJECT_NAME)
      ),
      loginAs(window2, TEST_USER_2).then(() => navigateToNotesAppTab(window2, APP_NAME)),
    ])

    const ts = Date.now()

    // Client A: Create a doc in Project KB
    const docName = `CrossProjToNotes-${ts}`
    await createDocViaUI(window1, docName)

    // Client A: Verify doc appears locally in Project KB
    await expect(window1.locator(`text="${docName}"`).first()).toBeVisible({ timeout: 5_000 })

    // Client B (Notes App tab): Should see the doc appear under the project section
    await waitForWsUpdate(window2, `text="${docName}"`, { timeout: 10_000 })
    await expect(window2.locator(`text="${docName}"`).first()).toBeVisible()

    // Also verify rename syncs across Project KB -> Notes
    const renamedDoc = `CrossProjRenamed-${ts}`
    await renameViaContextMenu(window1, docName, renamedDoc)

    // Client B: Should see the renamed name
    await waitForWsUpdate(window2, `text="${renamedDoc}"`, { timeout: 10_000 })
    await expect(window2.locator(`text="${docName}"`).first()).not.toBeVisible({ timeout: 5_000 })

    // Also verify delete syncs
    await deleteViaContextMenu(window1, renamedDoc)
    await waitForRemoval(window2, `text="${renamedDoc}"`, 10_000)
  })
})
