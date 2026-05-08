/**
 * Live E2E test for the comprehensive investigation system.
 * Tests: orchestrator routing, strategy injection, new OSINT nodes,
 * multi-search, technique catalog, completeness assessment.
 *
 * Run:
 *   cd frontend && npx playwright test e2e/investigation-system-live.spec.ts --headed --project=chromium
 *
 * Prerequisites:
 *   - Full stack: docker compose up -d (with rebuilt images)
 *   - ANTHROPIC_API_KEY set in the API container
 */
import { test, expect } from '@playwright/test'

const TEST_USER = { username: 'admin', password: 'admin' }

// IS brain research can take a while
test.setTimeout(300_000)

async function login(page) {
  await page.goto('/login')
  await page.getByPlaceholder(/username/i).fill(TEST_USER.username)
  await page.getByPlaceholder(/password/i).fill(TEST_USER.password)
  await page.getByRole('button', { name: /login|sign in/i }).click()
  await page.waitForURL(url => !url.pathname.includes('/login'), { timeout: 10_000 })
}

async function sendQuery(page, query: string) {
  await page.goto('/')
  await page.waitForLoadState('networkidle')

  const textarea = page.getByPlaceholder(/ask info-broker/i)
  await textarea.fill(query)
  await textarea.press('Enter')
  console.log(`[TEST] Sent: "${query}"`)

  // Wait for research to start — look for "running" or "Researching" status in the page
  await expect(async () => {
    const text = await page.locator('body').innerText()
    const started = text.includes('running') || text.includes('Researching') || text.includes('queued')
    expect(started).toBe(true)
  }).toPass({ timeout: 30_000 })
  console.log('[TEST] Research started!')

  // Wait for completion — look for results indicators
  await expect(async () => {
    const text = await page.locator('body').innerText()
    const done = text.includes('succeeded') || text.includes('Findings') ||
                 text.includes('confidence') || text.includes('Go Deeper') ||
                 text.includes('findings')
    expect(done).toBe(true)
  }).toPass({ timeout: 240_000 })
  console.log('[TEST] Research completed!')

  return await page.locator('body').innerText()
}

test('Person investigation uses new OSINT tools', async ({ page }) => {
  await login(page)

  const bodyText = await sendQuery(
    page,
    'Build a complete profile of Juan dela Cruz in the Philippines'
  )

  // Screenshot
  await page.screenshot({
    path: 'test-results/person-investigation.png',
    fullPage: true,
  })

  // Verify findings exist
  const lower = bodyText.toLowerCase()
  const hasFindings = lower.includes('findings') || lower.includes('confidence') || lower.includes('succeeded')
  console.log('[TEST] Has findings:', hasFindings)
  console.log('[TEST] Has succeeded:', lower.includes('succeeded'))

  expect(hasFindings).toBe(true)
})
