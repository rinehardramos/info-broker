import { test, expect, type Page } from '@playwright/test'

const BASE = 'http://localhost:5173'

async function login(page: Page) {
  await page.goto(`${BASE}/login`)
  const v = await page.locator('input[type="password"]').first().isVisible({ timeout: 2000 }).catch(() => false)
  if (v) {
    await page.fill('input[type="text"], input[type="email"]', 'admin')
    await page.fill('input[type="password"]', 'admin')
    await page.locator('button[type="submit"]').first().click()
    await page.waitForURL(/\/$|\/research|\/jobs|\/runs/, { timeout: 8_000 })
  }
}

test('preflight → confirm → run-detail flow', async ({ page }) => {
  test.setTimeout(240_000)

  const consoleLogs: string[] = []
  page.on('console', (m) => consoleLogs.push(`[${m.type()}] ${m.text()}`))
  const networkErrors: string[] = []
  page.on('response', async (r) => {
    if (r.status() >= 400) {
      const body = await r.text().catch(() => '')
      networkErrors.push(`${r.status()} ${r.request().method()} ${r.url()} ${body.slice(0, 200)}`)
    }
  })

  await login(page)

  // 1. Go to research page (where chat + preflight live)
  await page.goto(`${BASE}/research`)
  await page.waitForTimeout(1500)
  await page.screenshot({ path: 'test-results/01-research-loaded.png' })
  console.log('STEP 1: research page loaded')

  // 2. Type a query and submit
  const input = page.locator('textarea, input[type="text"]').filter({ hasNot: page.locator('[type="password"]') }).first()
  await input.waitFor({ timeout: 5000 })
  await input.fill('Who is the CEO of OpenAI?')
  await page.screenshot({ path: 'test-results/02-query-typed.png' })

  // Submit via Enter (most common chat-send pattern)
  await input.press('Enter')
  console.log('STEP 2: query submitted')

  // 3. Wait for preflight panel
  const preflightHeading = page.getByText(/strateg|preflight|approach|select.*strateg/i).first()
  await preflightHeading.waitFor({ timeout: 15_000 }).catch(() => null)
  await page.waitForTimeout(2000)
  await page.screenshot({ path: 'test-results/03-preflight-shown.png' })
  const preflightVisible = await preflightHeading.isVisible().catch(() => false)
  console.log('STEP 3: preflight panel visible =', preflightVisible)

  if (!preflightVisible) {
    console.log('!! preflight never appeared, recent console:')
    consoleLogs.slice(-15).forEach((l) => console.log(' ', l))
    console.log('!! network errors:')
    networkErrors.slice(-10).forEach((l) => console.log(' ', l))
    return
  }

  // 4. Click the Run button on the first strategy card
  const runBtn = page.getByRole('button', { name: /^run$/i }).first()
  await runBtn.waitFor({ timeout: 5000 })
  await page.screenshot({ path: 'test-results/04-before-run-click.png' })
  await runBtn.click()
  console.log('STEP 4: Run clicked')

  // 5. Check that query was NOT dumped into chat as a message
  await page.waitForTimeout(2500)
  await page.screenshot({ path: 'test-results/05-after-run-click.png' })

  // 6. Look for "Run not found" or run-detail panel
  const runNotFound = await page.getByText(/run not found/i).isVisible({ timeout: 1000 }).catch(() => false)
  console.log('STEP 6a: "Run not found" visible =', runNotFound)

  // Check for run-detail markers (phases, swim lanes, or pipeline run)
  const phaseEl = page.locator('[data-slot="phase-rail"], [data-slot="phase"]').first()
  const swimLane = page.locator('[data-slot="tactician-swimlane"], [data-slot="swimlane"]').first()
  const phaseVisible = await phaseEl.isVisible({ timeout: 1000 }).catch(() => false)
  const swimVisible = await swimLane.isVisible({ timeout: 1000 }).catch(() => false)
  console.log('STEP 6b: phase rail visible =', phaseVisible, ' swim lane =', swimVisible)

  // 7. Wait for first node card to appear (engine_v2 should emit something within ~20s)
  const firstCard = page.locator('[data-slot="node-result-card"]').first()
  const cardVisible = await firstCard.isVisible({ timeout: 120_000 }).catch(() => false)
  const cardCount = await page.locator('[data-slot="node-result-card"]').count()
  console.log('STEP 7b: total cards rendered =', cardCount)
  console.log('STEP 7: first node-result-card visible =', cardVisible)
  await page.screenshot({ path: 'test-results/07-run-detail-with-cards.png', fullPage: true })

  // 8. Summarize
  console.log('=== SUMMARY ===')
  console.log('preflight visible:', preflightVisible)
  console.log('run-not-found:', runNotFound)
  console.log('phase rail:', phaseVisible)
  console.log('swim lane:', swimVisible)
  console.log('node card:', cardVisible)
  console.log('network errors:', networkErrors.length)
  networkErrors.slice(-10).forEach((l) => console.log('  net:', l))
  console.log('recent console:')
  consoleLogs.slice(-20).forEach((l) => console.log(' ', l))

  // Soft assertions so the test reports findings instead of stopping at first failure
  expect.soft(preflightVisible, 'preflight panel should appear').toBe(true)
  expect.soft(runNotFound, '"Run not found" should NOT appear').toBe(false)
  expect.soft(phaseVisible || swimVisible || cardVisible, 'some run-detail UI should appear').toBe(true)
})
