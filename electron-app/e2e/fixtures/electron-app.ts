/**
 * Playwright fixture that launches ONE Electron app instance.
 * Used for single-client tests (CRUD, DnD, caching, search, navigation).
 */
import { test as base, _electron as electron, ElectronApplication, Page } from '@playwright/test'
import path from 'path'
import fs from 'fs/promises'

export type ElectronFixtures = {
  electronApp: ElectronApplication
  window: Page
}

export const test = base.extend<ElectronFixtures>({
  electronApp: async ({}, use, testInfo) => {
    const userDataDir = path.join(
      __dirname, '..', '..', 'tmp-e2e-data',
      `worker-${testInfo.workerIndex}-${testInfo.testId}`
    )
    await fs.mkdir(userDataDir, { recursive: true })

    const app = await electron.launch({
      args: ['.'],
      cwd: path.join(__dirname, '../..'), // electron-app root
      env: {
        ...process.env,
        ELECTRON_USER_DATA_DIR: userDataDir,
        NODE_ENV: 'test',
      },
      timeout: 60_000,
    })

    await use(app)

    await app.close().catch(() => {})
    await fs.rm(userDataDir, { recursive: true, force: true }).catch(() => {})
  },

  window: async ({ electronApp }, use) => {
    const page = await electronApp.firstWindow()
    await page.waitForLoadState('domcontentloaded')
    await use(page)
  },
})

export { expect } from '@playwright/test'
