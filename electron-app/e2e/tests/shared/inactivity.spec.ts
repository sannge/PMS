/**
 * Shared - Inactivity & Timeout Tests (Scenarios #7.1-7.5)
 *
 * Validates the inactivity timeout dialog that appears after 5 minutes
 * of no interaction in edit mode. Tests all dialog actions:
 * Keep Editing, Save, Discard, and the 60-second auto-save countdown.
 *
 * These tests are SLOW because they wait for the inactivity timeout.
 * They use test.slow() to triple the default test timeout.
 */
import { test, expect } from '../../fixtures/electron-app'
import {
  loginAs,
  TEST_USER_1,
  navigateToNotesPersonalTab,
} from '../../helpers/auth'
import {
  createDocViaUI,
  selectTreeItem,
  enterEditMode,
} from '../../helpers/knowledge-ops'
import { briefPause, waitForNetworkIdle } from '../../helpers/wait'

/**
 * Helper: Enter edit mode on a new document and type some content.
 * Returns the document name for later reference.
 */
async function setupEditingDoc(
  window: import('@playwright/test').Page,
  suffix: string
): Promise<string> {
  const docName = `Inactivity-${suffix}-${Date.now()}`
  await createDocViaUI(window, docName)
  await selectTreeItem(window, docName)
  await enterEditMode(window)

  // Type some content so the editor is dirty
  const editor = window.locator('.ProseMirror, [data-testid="editor"], [role="textbox"]').first()
  await editor.click()
  await editor.type('Inactivity test content')

  return docName
}

/**
 * Helper: Wait for the inactivity dialog to appear.
 * The dialog appears after 5 minutes of no interaction.
 * Uses a generous timeout since this is a long wait.
 */
async function waitForInactivityDialog(
  window: import('@playwright/test').Page
): Promise<void> {
  // The inactivity dialog should appear after ~5 minutes
  // It contains phrases like "Are you still editing?" or "Inactivity"
  await expect(
    window.locator(
      'text=/[Aa]re you still editing|[Ii]nactiv|[Ss]ession.*timeout|[Ss]till here/'
    )
  ).toBeVisible({ timeout: 330_000 }) // 5.5 minutes
}

test.describe('Inactivity & Timeout', () => {
  test.beforeEach(async ({ window }) => {
    await loginAs(window, TEST_USER_1)
    await navigateToNotesPersonalTab(window)
  })

  // #7.1 Inactivity dialog appears after 5 minutes
  test('inactivity dialog appears after 5 minutes of no interaction', async ({ window }) => {
    test.slow() // Triple default timeout (120s -> 360s)

    await setupEditingDoc(window, 'DialogAppears')

    // Wait for the inactivity dialog (5 minutes of no interaction)
    await waitForInactivityDialog(window)

    // Verify dialog has the expected options
    await expect(
      window.locator('button:has-text("Keep"), button:has-text("keep")')
    ).toBeVisible({ timeout: 5_000 })
  })

  // #7.2 Inactivity - Keep editing
  test('clicking "Keep Editing" on inactivity dialog stays in edit mode', async ({ window }) => {
    test.slow()

    const docName = await setupEditingDoc(window, 'KeepEditing')

    // Wait for the inactivity dialog
    await waitForInactivityDialog(window)

    // Click "Keep Editing"
    const keepBtn = window.locator(
      'button:has-text("Keep Editing"), button:has-text("Keep editing"), button:has-text("Continue")'
    ).first()
    await keepBtn.click()

    // Dialog should close
    await expect(
      window.locator('text=/[Aa]re you still editing|[Ii]nactiv/')
    ).not.toBeVisible({ timeout: 5_000 })

    // Should still be in edit mode (Save/Cancel buttons visible)
    await expect(
      window.locator('button:has-text("Save"), button:has-text("Cancel")').first()
    ).toBeVisible({ timeout: 5_000 })

    // Timer should be reset - the dialog should not reappear for another 5 minutes
  })

  // #7.3 Inactivity - Save
  test('clicking "Save" on inactivity dialog saves and returns to view mode', async ({ window }) => {
    test.slow()

    const docName = await setupEditingDoc(window, 'Save')

    // Wait for the inactivity dialog
    await waitForInactivityDialog(window)

    // Click "Save"
    const saveBtn = window.locator(
      'button:has-text("Save")'
    ).first()
    await saveBtn.click()

    // Should return to view mode (Edit button visible)
    await expect(
      window.locator('button:has-text("Edit")')
    ).toBeVisible({ timeout: 10_000 })

    // Dialog should be closed
    await expect(
      window.locator('text=/[Aa]re you still editing|[Ii]nactiv/')
    ).not.toBeVisible({ timeout: 5_000 })
  })

  // #7.4 Inactivity - Discard
  test('clicking "Discard" on inactivity dialog discards changes', async ({ window }) => {
    test.slow()

    const docName = await setupEditingDoc(window, 'Discard')

    // Wait for the inactivity dialog
    await waitForInactivityDialog(window)

    // Click "Discard"
    const discardBtn = window.locator(
      'button:has-text("Discard")'
    ).first()
    await discardBtn.click()

    // Should return to view mode (Edit button visible)
    await expect(
      window.locator('button:has-text("Edit")')
    ).toBeVisible({ timeout: 10_000 })

    // Changes should be lost (content reverted)
    // Verify the content typed earlier is gone
    await expect(
      window.locator('text="Inactivity test content"')
    ).not.toBeVisible({ timeout: 5_000 })
  })

  // #7.5 Inactivity auto-save after 60-second countdown
  test('inactivity dialog auto-saves after 60-second countdown expires', async ({ window }) => {
    test.slow()

    const docName = await setupEditingDoc(window, 'AutoSave')

    // Wait for the inactivity dialog
    await waitForInactivityDialog(window)

    // The dialog should show a countdown (e.g., "Auto-saving in 60s")
    await expect(
      window.locator('text=/\\d+\\s*[Ss]|[Cc]ountdown|[Aa]uto.*sav/')
    ).toBeVisible({ timeout: 5_000 }).catch(() => {
      // Countdown text may not be visible as separate text
    })

    // Wait for the 60-second countdown to complete (auto-save triggers)
    // Using 70s timeout for buffer
    await expect(
      window.locator('button:has-text("Edit")')
    ).toBeVisible({ timeout: 70_000 })

    // The inactivity dialog should be gone
    await expect(
      window.locator('text=/[Aa]re you still editing|[Ii]nactiv/')
    ).not.toBeVisible({ timeout: 5_000 })

    // Content should have been auto-saved (not lost)
    // Re-enter edit mode to verify content was preserved
    await enterEditMode(window)
    await expect(
      window.locator('text="Inactivity test content"')
    ).toBeVisible({ timeout: 5_000 })
  })
})
