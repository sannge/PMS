/**
 * App Knowledge - Resizable Panel Tests (#20.1-20.3)
 *
 * Validates the resizable tree panel in the Application Detail Knowledge tab.
 * The tree panel has a resize handle on its right edge and is constrained
 * between 200px (min) and 500px (max) width.
 */
import { test, expect } from '../../fixtures/electron-app'
import { loginAs, TEST_USER_1, navigateToAppKnowledgeTab } from '../../helpers/auth'
import { briefPause } from '../../helpers/wait'

const APP_NAME = 'E2E Test App'
const PROJECT_NAME = 'E2E Test Project'

test.beforeEach(async ({ window }) => {
  await loginAs(window, TEST_USER_1)
  await navigateToAppKnowledgeTab(window, APP_NAME)
})

/**
 * Get the resize handle element.
 * The handle is at the right edge of the tree panel. It may be identified
 * by cursor-col-resize class, data-resize-handle attribute, or similar.
 */
async function getResizeHandle(window: import('@playwright/test').Page) {
  return window.locator(
    '[class*="cursor-col-resize"], [data-resize-handle], [data-panel-resize-handle-id], [role="separator"]'
  ).first()
}

/**
 * Get the tree panel element and its current width.
 */
async function getTreePanelWidth(window: import('@playwright/test').Page): Promise<number> {
  // The tree panel is the container that holds the tree and has a constrained width
  const treePanel = window.locator(
    '[data-panel], [data-tree-panel], [class*="knowledge-tree"], [class*="tree-panel"]'
  ).first()

  // Fallback: get the parent of [role="tree"] that has the resizable width
  const panel = await treePanel.isVisible({ timeout: 3_000 }).catch(() => false)
    ? treePanel
    : window.locator('[role="tree"]').first().locator('..')

  const box = await panel.boundingBox()
  return box ? box.width : 0
}

test.describe('App Knowledge - Resizable Panel', () => {
  test('#20.1 Resize tree panel wider: drag handle right increases width (up to 500px max)', async ({ window }) => {
    const handle = await getResizeHandle(window)
    await expect(handle).toBeVisible({ timeout: 5_000 })

    // Get initial panel width
    const initialWidth = await getTreePanelWidth(window)
    expect(initialWidth).toBeGreaterThan(0)

    // Get handle position
    const box = await handle.boundingBox()
    expect(box).not.toBeNull()

    if (box) {
      const startX = box.x + box.width / 2
      const startY = box.y + box.height / 2

      // Drag handle to the right by 100px
      await window.mouse.move(startX, startY)
      await window.mouse.down()
      await window.mouse.move(startX + 100, startY, { steps: 10 })
      await window.mouse.up()

      await briefPause(300)

      // Verify panel got wider
      const newWidth = await getTreePanelWidth(window)
      expect(newWidth).toBeGreaterThan(initialWidth)

      // Verify it does not exceed 500px max
      expect(newWidth).toBeLessThanOrEqual(510) // small tolerance for rounding
    }
  })

  test('#20.2 Resize tree panel narrower: drag handle left decreases width (down to 200px min)', async ({ window }) => {
    const handle = await getResizeHandle(window)
    await expect(handle).toBeVisible({ timeout: 5_000 })

    // Get initial panel width
    const initialWidth = await getTreePanelWidth(window)
    expect(initialWidth).toBeGreaterThan(0)

    // Get handle position
    const box = await handle.boundingBox()
    expect(box).not.toBeNull()

    if (box) {
      const startX = box.x + box.width / 2
      const startY = box.y + box.height / 2

      // Drag handle to the left by 100px
      await window.mouse.move(startX, startY)
      await window.mouse.down()
      await window.mouse.move(startX - 100, startY, { steps: 10 })
      await window.mouse.up()

      await briefPause(300)

      // Verify panel got narrower
      const newWidth = await getTreePanelWidth(window)
      expect(newWidth).toBeLessThan(initialWidth)

      // Verify it does not go below 200px min
      expect(newWidth).toBeGreaterThanOrEqual(190) // small tolerance for rounding
    }
  })

  test('#20.3 Resize does not exceed bounds: drag beyond min/max clamped at 200px/500px', async ({ window }) => {
    const handle = await getResizeHandle(window)
    await expect(handle).toBeVisible({ timeout: 5_000 })

    const box = await handle.boundingBox()
    expect(box).not.toBeNull()

    if (box) {
      const startX = box.x + box.width / 2
      const startY = box.y + box.height / 2

      // --- Test MAX bound (500px) ---

      // Drag handle far to the right (way beyond max)
      await window.mouse.move(startX, startY)
      await window.mouse.down()
      await window.mouse.move(startX + 500, startY, { steps: 15 })
      await window.mouse.up()

      await briefPause(300)

      const maxWidth = await getTreePanelWidth(window)
      // Width should be clamped at or near 500px
      expect(maxWidth).toBeLessThanOrEqual(510) // tolerance for borders/rounding
      expect(maxWidth).toBeGreaterThanOrEqual(450) // should be near max

      // --- Test MIN bound (200px) ---

      // Re-acquire handle position after resize
      const handleAfterMax = await getResizeHandle(window)
      const boxAfterMax = await handleAfterMax.boundingBox()

      if (boxAfterMax) {
        const newStartX = boxAfterMax.x + boxAfterMax.width / 2
        const newStartY = boxAfterMax.y + boxAfterMax.height / 2

        // Drag handle far to the left (way beyond min)
        await window.mouse.move(newStartX, newStartY)
        await window.mouse.down()
        await window.mouse.move(newStartX - 500, newStartY, { steps: 15 })
        await window.mouse.up()

        await briefPause(300)

        const minWidth = await getTreePanelWidth(window)
        // Width should be clamped at or near 200px
        expect(minWidth).toBeGreaterThanOrEqual(190) // tolerance for rounding
        expect(minWidth).toBeLessThanOrEqual(250) // should be near min
      }
    }
  })
})
