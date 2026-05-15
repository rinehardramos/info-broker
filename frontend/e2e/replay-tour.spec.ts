/**
 * Replay tour — verifies the past-run replay path visually.
 *
 * Flow:
 *  1. Login → /runs
 *  2. Find a succeeded run → click "View"
 *  3. Lands on /research?replay=<id>; replayRunIntoStore() fires
 *  4. Confirm replay endpoint was called
 *  5. Inspect what the UI renders: PhaseProgress, CandidateComparison,
 *     ACH matrix, source class badges — depending on what the trail had
 */
import { test, expect, Page } from '@playwright/test'

const BASE = 'http://localhost:5173'

async function login(page: Page) {
  await page.goto(`${BASE}/login`)
  const loginVisible = await page.locator('input[type="password"]').first().isVisible({ timeout: 2000 }).catch(() => false)
  if (loginVisible) {
    await page.fill('input[type="text"], input[type="email"]', 'admin')
    await page.fill('input[type="password"]', 'admin')
    await page.locator('button[type="submit"]').first().click()
    await page.waitForURL(/\/$|\/research|\/jobs/, { timeout: 8_000 })
  }
}

const pause = (p: Page, ms = 2000) => p.waitForTimeout(ms)
const announce = async (p: Page, msg: string) => { console.log(`  ▶ ${msg}`) }

test('replay tour — past run rehydrates from research_trails', async ({ page }) => {
  test.setTimeout(120_000)

  await announce(page, 'STEP 1 — Login')
  await login(page)
  await pause(page, 1000)

  // Capture replay API call
  const replayRequests: string[] = []
  page.on('request', req => {
    if (req.url().includes('/replay')) replayRequests.push(req.url())
  })
  const replayResponses: { url: string; status: number; bodyPreview?: string }[] = []
  page.on('response', async resp => {
    if (resp.url().includes('/replay')) {
      const status = resp.status()
      let bodyPreview: string | undefined
      try {
        const body = await resp.text()
        bodyPreview = body.slice(0, 200)
      } catch { /* ignore */ }
      replayResponses.push({ url: resp.url(), status, bodyPreview })
    }
  })

  await announce(page, 'STEP 2 — Navigate to /runs')
  await page.goto(`${BASE}/runs`)
  await pause(page, 3000)

  await announce(page, 'STEP 3 — Click "View" on first run')
  const viewBtn = page.getByRole('button', { name: /^view$/i }).first()
  if (await viewBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
    await viewBtn.scrollIntoViewIfNeeded()
    await viewBtn.click()
    console.log('       View clicked')
    await pause(page, 4000)
  } else {
    console.log('       No View button visible — runs list may be empty')
  }

  await announce(page, 'STEP 4 — Confirm replay fired')
  console.log(`       replay requests: ${replayRequests.length}`)
  for (const r of replayRequests) console.log(`         ${r}`)
  for (const r of replayResponses) console.log(`         status=${r.status}: ${r.bodyPreview?.slice(0, 120)}`)
  expect(replayRequests.length).toBeGreaterThan(0)

  await announce(page, 'STEP 5 — Inspect rendered UI (depends on what trail had)')
  await pause(page, 2000)
  const body = await page.locator('body').innerText()
  console.log('       UI elements detected:', {
    phaseProgress: /signal_extraction|broaden|red_team|rank_verify/i.test(body),
    candidateComparison: /candidate|confidence|signal/i.test(body),
    achMatrix: /ach|matrix/i.test(body),
    sourceClass: /live_search|prior_research|🌐|📚/i.test(body),
  })
  await pause(page, 3000)

  await announce(page, '✓ replay tour complete')
})
