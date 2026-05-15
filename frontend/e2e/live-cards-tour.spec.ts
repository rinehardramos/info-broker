/**
 * Live-cards tour — visually verify a completed engine_v2 run renders cards.
 *
 * Uses the run from /tmp/final_run.txt (most-recent live run with harvested
 * findings) — navigates to /research?replay=<id> in headed Chrome and
 * inspects what renders.
 */
import { test, Page } from '@playwright/test'
import { readFileSync } from 'node:fs'

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

const pause = (p: Page, ms = 2500) => p.waitForTimeout(ms)

test('live-cards tour — replay a completed engine_v2 run with findings', async ({ page }) => {
  test.setTimeout(180_000)

  await login(page)

  // Navigate to /runs and click the most-recent succeeded/terminated run
  await page.goto(`${BASE}/runs`)
  await pause(page, 3000)

  const firstViewBtn = page.getByRole('button', { name: /^view$/i }).first()
  if (!(await firstViewBtn.isVisible({ timeout: 5000 }).catch(() => false))) {
    test.skip(true, 'No runs visible')
    return
  }
  await firstViewBtn.click()
  console.log('  ▶ Opened most-recent run')
  await pause(page, 5000)

  const body = await page.locator('body').innerText()
  const cards = await page.locator('[data-slot="node-result-card"]').count()
  console.log(`  ▶ Cards rendered: ${cards}`)
  console.log(`  ▶ Body shows:`, {
    phaseProgress: /signal_extraction|broaden|red_team|rank_verify/i.test(body),
    cards: cards > 0,
    candidateComparison: /candidate|confidence/i.test(body),
    achMatrix: /ach|matrix/i.test(body),
    sourceClass: /live_search|🌐|prior_research|📚/i.test(body),
  })

  // If there are cards, click the first one to open the modal
  if (cards > 0) {
    const firstCard = page.locator('[data-slot="node-result-card"]').first()
    await firstCard.scrollIntoViewIfNeeded()
    await firstCard.click()
    await pause(page, 4000)
    const modalText = await page.locator('[role="dialog"]').first().innerText().catch(() => '')
    console.log(`  ▶ Modal opened with tabs:`, {
      formatted: /formatted/i.test(modalText),
      input: /\binput\b/i.test(modalText),
      hypothesis: /hypothesis/i.test(modalText),
      sources: /sources/i.test(modalText),
      timing: /timing/i.test(modalText),
      raw: /raw/i.test(modalText),
      grading: /grade|A.+B.+C.+D/i.test(modalText),
    })
    await pause(page, 4000)
    await page.keyboard.press('Escape')
  }

  console.log('  ▶ ✓ done')
  await pause(page, 2000)
})
