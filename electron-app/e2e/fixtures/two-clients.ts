/**
 * Playwright fixture that launches TWO Electron app instances.
 * Used for collaborative tests (WebSocket sync, lock contention, real-time updates).
 *
 * Each client gets its own isolated user-data directory.
 * Both clients share the same backend (FastAPI + Redis + Postgres).
 */
import { test as base, _electron as electron, ElectronApplication, Page } from '@playwright/test'
import path from 'path'
import fs from 'fs/promises'

export type TwoClientFixtures = {
  app1: ElectronApplication
  app2: ElectronApplication
  window1: Page
  window2: Page
}

async function launchElectron(label: string, testInfo: { workerIndex: number; testId: string }) {
  const userDataDir = path.join(
    __dirname, '..', '..', 'tmp-e2e-data',
    `worker-${testInfo.workerIndex}-${label}-${testInfo.testId}`
  )
  await fs.mkdir(userDataDir, { recursive: true })

  const app = await electron.launch({
    args: ['.'],
    cwd: path.join(__dirname, '../..'),
    env: {
      ...process.env,
      ELECTRON_USER_DATA_DIR: userDataDir,
      NODE_ENV: 'test',
    },
    timeout: 60_000,
  })

  return { app, userDataDir }
}

async function cleanup(app: ElectronApplication, dir: string) {
  await app.close().catch(() => {})
  await fs.rm(dir, { recursive: true, force: true }).catch(() => {})
}

export const test = base.extend<TwoClientFixtures>({
  app1: async ({}, use, testInfo) => {
    const { app, userDataDir } = await launchElectron('client1', testInfo)
    await use(app)
    await cleanup(app, userDataDir)
  },

  app2: async ({}, use, testInfo) => {
    const { app, userDataDir } = await launchElectron('client2', testInfo)
    await use(app)
    await cleanup(app, userDataDir)
  },

  window1: async ({ app1 }, use) => {
    const page = await app1.firstWindow()
    await page.waitForLoadState('domcontentloaded')
    await use(page)
  },

  window2: async ({ app2 }, use) => {
    const page = await app2.firstWindow()
    await page.waitForLoadState('domcontentloaded')
    await use(page)
  },
})

export { expect } from '@playwright/test'
