import { defineConfig, devices } from '@playwright/test'

// `E2E_BASE_URL=https://infobroker.tech npx playwright test ...` flips the
// whole suite to PROD without per-test edits. Defaults preserved for local dev.
const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:5173'

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  retries: 0,
  use: {
    baseURL: BASE_URL,
    channel: 'chromium',
    headless: false,
    viewport: { width: 1400, height: 900 },
    // Keep browser open on failure so you can inspect state
    video: 'retain-on-failure',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  // Do not spin up a dev server — tests run against the already-running stack
  webServer: undefined,
})
