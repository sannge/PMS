import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  timeout: 120_000,
  expect: { timeout: 15_000 },
  retries: 0,
  workers: 1, // Sequential - Electron instances are heavy
  reporter: [
    ['list'],
    ['html', { outputFolder: '../test-results/html', open: 'never' }],
  ],
  outputDir: '../test-results/artifacts',
  use: {
    trace: 'on-first-retry',
    video: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
})
