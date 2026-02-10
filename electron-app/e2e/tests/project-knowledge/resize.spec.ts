/**
 * Project Knowledge - Resizable Panel Tests (Scenarios #20.1-20.3)
 *
 * Validates the resizable tree panel behavior in the project Knowledge tab:
 * drag to resize, minimum (200px), and maximum (500px) bounds.
 *
 * Context: KnowledgePanel -> KnowledgeTree (scope=project)
 * The tree panel has a resize handle between 200-500px width.
 */
import { test, expect } from '../../fixtures/electron-app'
import { loginAs, TEST_USER_1, navigateToProjectKnowledgeTab } from '../../helpers/auth'
import { briefPause } from '../../helpers/wait'

const APP_NAME = 'E2E Test App'
const PROJECT_NAME = 'E2E Test Project'

/** Locate the resize handle for the tree panel. */
async function getResizeHandle(window: import('@playwright/test').Page) {
  return window.locator('[class*="cursor-col-resize"], [data-resize-handle]').first()
}

/** Get the current width of the tree panel. */
async function getTreePanelWidth(window: import('@playwright/test').Page): Promise<number> {
  // The tree panel is the container holding [role="tree"] or the panel before the resize handle
  const treePanel = window.locator(
    '[data-testid="tree-panel"], [data-panel="tree"], [role="tree"]'
  ).first()

  // Try getting the closest resizable panel container
  const panelContainer = window.locator(
    '[data-testid="tree-panel"], [data-panel="tree"]'
  ).first()

  const box = await panelContainer.boundingBox().catch(() => null)
  if (box) {
    return box.width
  }

  // Fallback: get the tree's parent container width
  const treeBox = await treePanel.boundingBox()
  return treeBox?.width ?? 0
}

test.describe('Project Knowledge - Resizable Panel', () => {
  test.beforeEach(async ({ window }) => {
    await loginAs(window, TEST_USER_1)
    await navigateToProjectKnowledgeTab(window, APP_NAME, PROJECT_NAME)
  })

  // #20.1 Resize tree panel wider: Drag handle right -> up to 500px max
  test('resize tree panel wider by dragging handle right', async ({ window }) => {
    const handle = await getResizeHandle(window)
    await expect(handle).toBeVisible({ timeout: 10_000 })

    const initialWidth = await getTreePanelWidth(window)

    // Get handle position
    const box = await handle.boundingBox()
    if (box) {
      // Drag handle 100px to the right
      await window.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
      await window.mouse.down()
      await window.mouse.move(box.x + box.width / 2 + 100, box.y + box.height / 2, { steps: 10 })
      await window.mouse.up()
    }

    await briefPause(300)

    const newWidth = await getTreePanelWidth(window)

    // Panel should have gotten wider (or stayed at max if already near 500px)
    if (initialWidth < 500) {
      expect(newWidth).toBeGreaterThan(initialWidth)
    }

    // Should not exceed 500px max
    expect(newWidth).toBeLessThanOrEqual(510) // Allow small tolerance for rounding
  })

  // #20.2 Resize tree panel narrower: Drag handle left -> down to 200px min
  test('resize tree panel narrower by dragging handle left', async ({ window }) => {
    const handle = await getResizeHandle(window)
    await expect(handle).toBeVisible({ timeout: 10_000 })

    const initialWidth = await getTreePanelWidth(window)

    // Get handle position
    const box = await handle.boundingBox()
    if (box) {
      // Drag handle 200px to the left (aggressive shrink)
      await window.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
      await window.mouse.down()
      await window.mouse.move(box.x + box.width / 2 - 200, box.y + box.height / 2, { steps: 10 })
      await window.mouse.up()
    }

    await briefPause(300)

    const newWidth = await getTreePanelWidth(window)

    // Panel should have gotten narrower (or stayed at min if already near 200px)
    if (initialWidth > 200) {
      expect(newWidth).toBeLessThan(initialWidth)
    }

    // Should not go below 200px min
    expect(newWidth).toBeGreaterThanOrEqual(190) // Allow small tolerance for rounding
  })

  // #20.3 Resize doesn't exceed bounds: Clamped at 200px/500px
  test('resize is clamped between 200px minimum and 500px maximum', async ({ window }) => {
    const handle = await getResizeHandle(window)
    await expect(handle).toBeVisible({ timeout: 10_000 })

    // Test upper bound: drag handle far to the right (600px)
    let box = await handle.boundingBox()
    if (box) {
      await window.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
      await window.mouse.down()
      await window.mouse.move(box.x + box.width / 2 + 600, box.y + box.height / 2, { steps: 15 })
      await window.mouse.up()
    }

    await briefPause(300)
    const maxWidth = await getTreePanelWidth(window)

    // Should be clamped at or near 500px
    expect(maxWidth).toBeLessThanOrEqual(510) // Allow small tolerance
    expect(maxWidth).toBeGreaterThanOrEqual(450) // Should be near 500, not far below

    // Test lower bound: drag handle far to the left (600px)
    box = await handle.boundingBox()
    if (box) {
      await window.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
      await window.mouse.down()
      await window.mouse.move(box.x + box.width / 2 - 600, box.y + box.height / 2, { steps: 15 })
      await window.mouse.up()
    }

    await briefPause(300)
    const minWidth = await getTreePanelWidth(window)

    // Should be clamped at or near 200px
    expect(minWidth).toBeGreaterThanOrEqual(190) // Allow small tolerance
    expect(minWidth).toBeLessThanOrEqual(250) // Should be near 200, not far above
  })
})
