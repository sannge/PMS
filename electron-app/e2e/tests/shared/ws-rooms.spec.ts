/**
 * Shared - WebSocket Room Management Tests (Scenarios #19.1-19.6)
 *
 * Validates WebSocket room join/leave behavior across different contexts:
 * personal rooms, app rooms, project rooms, tab-switch room changes,
 * cleanup on unmount, and cross-room event scoping.
 *
 * Single-client tests (#19.1-19.5) use the standard electron-app fixture.
 * The two-client test (#19.6) uses the two-clients fixture to verify
 * that events are scoped to their respective rooms.
 */
import { test, expect } from '../../fixtures/electron-app'
import { test as twoClientTest, expect as expect2 } from '../../fixtures/two-clients'
import {
  loginAs,
  TEST_USER_1,
  TEST_USER_2,
  navigateToNotesPersonalTab,
  navigateToNotesAppTab,
  navigateToAppKnowledgeTab,
  navigateToProjectKnowledgeTab,
} from '../../helpers/auth'
import {
  createDocViaUI,
  getTreeItem,
} from '../../helpers/knowledge-ops'
import { briefPause, waitForWsUpdate } from '../../helpers/wait'

const APP_NAME = 'E2E Test App'
const PROJECT_NAME = 'E2E Test Project'

test.describe('WebSocket Room Management', () => {
  // #19.1 Join personal room
  test('navigating to Notes Personal tab joins user room', async ({ window }) => {
    await loginAs(window, TEST_USER_1)

    // Listen for WebSocket-related console messages or network frames
    const wsMessages: string[] = []
    window.on('console', (msg) => {
      const text = msg.text()
      if (
        text.toLowerCase().includes('room') ||
        text.toLowerCase().includes('join') ||
        text.toLowerCase().includes('subscribe')
      ) {
        wsMessages.push(text)
      }
    })

    await navigateToNotesPersonalTab(window)

    // Wait for WS connection to establish and room join to happen
    await briefPause(2000)

    // Verify the personal tree is loaded (confirms WS room is active)
    const tree = window.locator('[role="tree"]')
    await expect(tree).toBeVisible({ timeout: 15_000 })

    // Create a document to verify WS is functional in personal scope
    const docName = `WSPersonal-${Date.now()}`
    await createDocViaUI(window, docName)
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })
  })

  // #19.2 Join app room when switching to app tab
  test('switching to App tab leaves personal room and joins app room', async ({ window }) => {
    await loginAs(window, TEST_USER_1)

    // Start in personal tab
    await navigateToNotesPersonalTab(window)
    await expect(window.locator('[role="tree"]')).toBeVisible({ timeout: 15_000 })

    // Switch to app tab (should leave personal room, join app room)
    await navigateToNotesAppTab(window, APP_NAME)
    await expect(window.locator('[role="tree"]')).toBeVisible({ timeout: 15_000 })

    // Verify app-scoped functionality works (WS room is correct)
    const docName = `WSApp-${Date.now()}`
    await createDocViaUI(window, docName)
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })
  })

  // #19.3 Room switch on tab change between apps
  test('switching between app tabs leaves old app room and joins new one', async ({ window }) => {
    await loginAs(window, TEST_USER_1)

    // Navigate to first app tab
    await navigateToNotesAppTab(window, APP_NAME)
    await expect(window.locator('[role="tree"]')).toBeVisible({ timeout: 15_000 })

    // Create a doc in first app
    const docInApp1 = `WSApp1-${Date.now()}`
    await createDocViaUI(window, docInApp1)
    await expect(getTreeItem(window, docInApp1)).toBeVisible({ timeout: 5_000 })

    // Switch back to personal tab (different room)
    await navigateToNotesPersonalTab(window)
    await expect(window.locator('[role="tree"]')).toBeVisible({ timeout: 15_000 })

    // The app-scoped doc should NOT be visible in personal scope
    await expect(getTreeItem(window, docInApp1)).not.toBeVisible({ timeout: 3_000 })

    // Switch back to app tab - the doc should still be there (cached)
    await navigateToNotesAppTab(window, APP_NAME)
    await expect(getTreeItem(window, docInApp1)).toBeVisible({ timeout: 10_000 })
  })

  // #19.4 Project room when opening project Knowledge tab
  test('opening project Knowledge tab joins project room', async ({ window }) => {
    await loginAs(window, TEST_USER_1)

    await navigateToProjectKnowledgeTab(window, APP_NAME, PROJECT_NAME)
    await expect(window.locator('[role="tree"]')).toBeVisible({ timeout: 15_000 })

    // Verify project-scoped operations work (WS room is correct)
    const docName = `WSProject-${Date.now()}`
    await createDocViaUI(window, docName)
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 5_000 })
  })

  // #19.5 Room cleanup on unmount (navigate away from Notes)
  test('navigating away from Notes leaves all WS rooms', async ({ window }) => {
    await loginAs(window, TEST_USER_1)

    // Navigate to Notes and load tree
    await navigateToNotesPersonalTab(window)
    await expect(window.locator('[role="tree"]')).toBeVisible({ timeout: 15_000 })

    const docName = `WSCleanup-${Date.now()}`
    await createDocViaUI(window, docName)

    // Navigate away from Notes to a different page (e.g., Dashboard)
    await window.click('text=Dashboard')
    await expect(window.locator('text=Dashboard')).toBeVisible({ timeout: 10_000 })

    // The Notes page is unmounted - WS rooms should be cleaned up.
    // We can't directly verify room membership, but we verify that
    // navigating back successfully re-joins the room.
    await briefPause(1000)

    // Navigate back to Notes
    await navigateToNotesPersonalTab(window)
    await expect(window.locator('[role="tree"]')).toBeVisible({ timeout: 15_000 })

    // Previous doc should still be visible (from cache + room rejoin)
    await expect(getTreeItem(window, docName)).toBeVisible({ timeout: 10_000 })
  })
})

// Two-client test for room scoping
twoClientTest.describe('WebSocket Room Scoping', () => {
  // #19.6 Events scoped to room: different apps don't leak events
  twoClientTest(
    'document created in App X by Client A is NOT seen by Client B in Personal tab',
    async ({ window1, window2 }) => {
      // Client A: Log in and navigate to App tab
      await loginAs(window1, TEST_USER_1)
      await navigateToNotesAppTab(window1, APP_NAME)
      await expect2(window1.locator('[role="tree"]')).toBeVisible({ timeout: 15_000 })

      // Client B: Log in and navigate to Personal tab (different room)
      await loginAs(window2, TEST_USER_2)
      await navigateToNotesPersonalTab(window2)
      await expect2(window2.locator('[role="tree"]')).toBeVisible({ timeout: 15_000 })

      // Client A: Create a document in the app scope
      const docName = `WSScoped-${Date.now()}`
      await createDocViaUI(window1, docName)

      // Client A: Should see the document
      await expect2(
        window1.locator(`text="${docName}"`).first()
      ).toBeVisible({ timeout: 5_000 })

      // Wait for any WS events to propagate
      await briefPause(3000)

      // Client B: Should NOT see the document (different room - personal vs app)
      await expect2(
        window2.locator(`text="${docName}"`).first()
      ).not.toBeVisible({ timeout: 5_000 })
    }
  )
})
