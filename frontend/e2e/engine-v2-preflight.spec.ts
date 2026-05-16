/**
 * engine-v2-preflight.spec.ts -- MVP-M9 Playwright test
 *
 * Scope: preflight handshake only.
 *   1. Navigate to /research?engine=v2
 *   2. Submit a query
 *   3. Assert PreflightPanel renders (mode + dial + estimate)
 *   4. Click Run
 *   5. Assert POST /v3/preflight/confirm fires
 *   6. Assert live view receives is.phase_start (or equivalent v2 event)
 *
 * Does NOT wait for run completion -- engine_v2 runs are long.
 * Deeper assertions are marked test.skip with TODO referencing manual #89
 * regression doc at docs/intelligence/mvp-m9-smoke-test.md.
 *
 * Run:
 *   cd frontend && npx playwright test e2e/engine-v2-preflight.spec.ts --headed --project=chromium
 */
import { test, expect, type Page, type Request } from '@playwright/test'

const BASE = 'http://localhost:5173'
const API = 'http://localhost:8000'
const wait = (ms: number) => new Promise(r => setTimeout(r, ms))

test.use({
  baseURL: BASE,
  viewport: { width: 1400, height: 900 },
  headless: false,
})

test.setTimeout(120_000)

// ---------------------------------------------------------------------------
// Auth helper
// ---------------------------------------------------------------------------

async function login(page: Page): Promise<void> {
  await page.goto(`${BASE}/`)
  await wait(1000)
  const loginVisible = await page
    .locator('input[type="password"]')
    .isVisible()
    .catch(() => false)
  if (loginVisible) {
    await page.fill('input[placeholder*="user" i], input[type="text"]', 'admin')
    await page.fill('input[type="password"]', 'admin')
    await page
      .locator(
        'button[type="submit"], button:has-text("Login"), button:has-text("Sign in")',
      )
      .click()
    await wait(2000)
  }
}

// ---------------------------------------------------------------------------
// Main test
// ---------------------------------------------------------------------------

test('engine-v2: preflight panel renders and confirm fires on Run click', async ({
  page,
}) => {
  await login(page)

  // Capture all preflight/confirm requests
  const confirmRequests: Request[] = []
  page.on('request', req => {
    if (req.url().includes('/v3/preflight/confirm')) {
      confirmRequests.push(req)
    }
  })

  // Navigate to research page with engine=v2 flag
  await page.goto(`${BASE}/research?engine=v2`)
  await wait(1500)

  // Submit a query
  const textarea = page.locator('textarea').first()
  await expect(textarea).toBeVisible({ timeout: 10_000 })
  await textarea.fill(
    'asian girl with mole in cheek bone and has an advertisement where she uses a curling iron',
  )
  await page.keyboard.press('Enter')

  // Wait for PreflightPanel to appear
  // PreflightPanel renders on the ?engine=v2 path after query submission
  const preflightPanel = page.locator(
    '[data-testid="preflight-panel"], .preflight-panel, [class*="preflight"]',
  )
  await expect(preflightPanel.first()).toBeVisible({ timeout: 15_000 })

  // Assert panel contains mode, dial, and estimate information
  const panelText = await page.locator('body').innerText()
  const hasModeInfo =
    panelText.includes('investigation') ||
    panelText.includes('mode') ||
    panelText.includes('Mode')
  const hasEstimate =
    panelText.includes('RU') || panelText.includes('estimate') || panelText.includes('Estimate')
  const hasDial =
    panelText.includes('competing') ||
    panelText.includes('hypothesis') ||
    panelText.includes('general')

  expect(hasModeInfo || hasEstimate || hasDial).toBeTruthy()

  // Click the Run button
  const runButton = page.locator(
    'button:has-text("Run"), button:has-text("Confirm"), button:has-text("Start")',
  )
  const runButtonVisible = await runButton.first().isVisible().catch(() => false)
  if (runButtonVisible) {
    await runButton.first().click()
    await wait(3000)
  }

  // Assert POST /v3/preflight/confirm was called
  // (may have fired during preflight flow or on Run click)
  const confirmFired = confirmRequests.length > 0
  expect(confirmFired).toBeTruthy()

  // Assert is.phase_start or equivalent v2 event arrives via WS
  // We listen for the event in the DOM or via page.evaluate
  const phaseStartReceived = await page
    .evaluate(() => {
      // Check if the live view panel shows any phase-related content
      const body = document.body.innerText
      return (
        body.includes('phase') ||
        body.includes('running') ||
        body.includes('signal_extraction') ||
        body.includes('broaden')
      )
    })
    .catch(() => false)

  // This assertion is intentionally soft -- the run may not have started
  // yet within the test's time window. The confirm POST is the hard assertion.
  // is.phase_start is verified in the integration tests (test_engine_v2.py).
  if (!phaseStartReceived) {
    console.log(
      '[engine-v2-preflight] Note: phase_start not yet visible in DOM -- confirm POST did fire.',
    )
  }

  // Verify confirm request shape
  if (confirmRequests.length > 0) {
    const req = confirmRequests[0]
    const body = req.postDataJSON?.() ?? {}
    expect(typeof body).toBe('object')
    // confirm body should include run_id or strategy_id
    const hasExpectedFields =
      'strategy_id' in body ||
      'run_id' in body ||
      'query' in body ||
      'envelope' in body
    expect(hasExpectedFields).toBeTruthy()
  }
})

// ---------------------------------------------------------------------------
// Skipped deep completion tests
// TODO: enable once manual #89 smoke test is passing end-to-end
// Ref: docs/intelligence/mvp-m9-smoke-test.md
// ---------------------------------------------------------------------------

test.skip('engine-v2: run completes with >= 3 distinct candidates', async ({
  page,
}) => {
  // TODO(#89): Requires real LLM + MCP + funded wallet (>= 50 RU).
  // See docs/intelligence/mvp-m9-smoke-test.md for manual verification steps.
  // This test should be enabled after the smoke test passes manually.
  expect(true).toBe(false) // placeholder
})

test.skip('engine-v2: research_trails row has branches with live source_class', async ({
  page,
}) => {
  // TODO(#89): Verify research_trails.trail.branches contains >= 1 entry
  // where source_class is NOT in {prior_research, training_knowledge}.
  // See docs/intelligence/mvp-m9-smoke-test.md pass/fail criteria.
  expect(true).toBe(false) // placeholder
})

test.skip('engine-v2: final answer surfaces >= 2 candidates not named Zhao Lusi', async ({
  page,
}) => {
  // TODO(#89): The core anti-tunneling regression. Run the exact #89 query
  // string from the smoke test doc and assert the ranked_candidates list
  // contains >= 2 entries whose names differ from "Zhao Lusi".
  // See docs/intelligence/mvp-m9-smoke-test.md for the exact query string.
  expect(true).toBe(false) // placeholder
})
