import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright configuration for PM Desktop Application E2E tests
 *
 * This configuration is set up to test the Electron desktop application
 * and the FastAPI backend API endpoints.
 *
 * @see https://playwright.dev/docs/test-configuration
 */

const API_BASE_URL = process.env.API_BASE_URL || 'http://localhost:8000';
const ELECTRON_APP_PATH = process.env.ELECTRON_APP_PATH || '../electron-app';

export default defineConfig({
  // Test directory containing all test files
  testDir: './e2e',

  // Run tests in files in parallel
  fullyParallel: true,

  // Fail the build on CI if you accidentally left test.only in the source code
  forbidOnly: !!process.env.CI,

  // Retry on CI only
  retries: process.env.CI ? 2 : 0,

  // Opt out of parallel tests on CI for stability
  workers: process.env.CI ? 1 : undefined,

  // Reporter to use
  reporter: [
    ['html', { open: 'never' }],
    ['list'],
    ['json', { outputFile: 'test-results/results.json' }]
  ],

  // Shared settings for all the projects below
  use: {
    // Base URL for API requests
    baseURL: API_BASE_URL,

    // Collect trace when retrying the failed test
    trace: 'on-first-retry',

    // Take screenshot on failure
    screenshot: 'only-on-failure',

    // Record video on failure
    video: 'on-first-retry',

    // Timeout for each action
    actionTimeout: 10000,

    // Navigation timeout
    navigationTimeout: 30000,
  },

  // Configure projects for different testing scenarios
  projects: [
    // API Tests - Run against the FastAPI backend
    {
      name: 'api',
      testMatch: '**/api/**/*.spec.ts',
      use: {
        baseURL: API_BASE_URL,
      },
    },

    // E2E Tests using Chromium (simulating web-view behavior)
    {
      name: 'chromium',
      testMatch: '**/e2e/**/*.spec.ts',
      use: {
        ...devices['Desktop Chrome'],
        baseURL: API_BASE_URL,
        viewport: { width: 1280, height: 720 },
      },
    },

    // Mobile viewport tests
    {
      name: 'mobile-chrome',
      testMatch: '**/e2e/**/*.spec.ts',
      testIgnore: '**/collaboration.spec.ts', // Skip collaboration tests on mobile
      use: {
        ...devices['Pixel 5'],
        baseURL: API_BASE_URL,
      },
    },
  ],

  // Timeout for each test
  timeout: 60000,

  // Timeout for expect() assertions
  expect: {
    timeout: 10000,
  },

  // Output directory for test artifacts
  outputDir: 'test-results',

  // Global setup file (for database seeding, etc.)
  // globalSetup: './global-setup.ts',

  // Global teardown file (for cleanup)
  // globalTeardown: './global-teardown.ts',

  // Configure web server to run before tests
  webServer: [
    // FastAPI Backend
    {
      command: 'cd ../fastapi-backend && uvicorn app.main:app --host 0.0.0.0 --port 8000',
      url: 'http://localhost:8000/health',
      reuseExistingServer: !process.env.CI,
      timeout: 120000,
      stdout: 'pipe',
      stderr: 'pipe',
    },
    // Electron app in development mode (for browser-based testing)
    // Uncomment when testing against the actual Electron app's web content
    // {
    //   command: 'cd ../electron-app && npm run dev',
    //   url: 'http://localhost:5173',
    //   reuseExistingServer: !process.env.CI,
    //   timeout: 120000,
    // },
  ],
});

/**
 * Custom fixture types for PM Desktop tests
 */
export interface PMTestFixtures {
  authenticatedPage: import('@playwright/test').Page;
  testUser: {
    email: string;
    password: string;
    displayName: string;
  };
}
