/**
 * Visual tour — runs in headed Chrome so the user can see each feature work.
 *
 * Pauses between steps with annotated console.log so it's clear what's being
 * demonstrated. Designed to be watched end-to-end (~90s total). Single test
 * function so the headed browser doesn't close between sections.
 */
import { expect, test, Page } from '@playwright/test'

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

async function announce(page: Page, msg: string) {
  console.log(`\n  ▶ ${msg}`)
  await page.evaluate((m: string) => console.log(`[TOUR] ${m}`), msg)
}

async function pause(page: Page, ms = 2500) {
  await page.waitForTimeout(ms)
}

test('visual tour — every feature, watch it work', async ({ page }) => {
  test.setTimeout(180_000)

  // -----------------------------------------------------------------------
  // 1. Login
  // -----------------------------------------------------------------------
  await announce(page, 'STEP 1/9 — Login as admin')
  await login(page)
  await pause(page, 1500)

  // -----------------------------------------------------------------------
  // 2. Navigate to /research, type the #89 query
  // -----------------------------------------------------------------------
  await announce(page, 'STEP 2/9 — Navigate to /research (no engine= URL hack)')
  await page.goto(`${BASE}/research`)
  await page.locator('textarea').first().waitFor({ timeout: 10_000 })
  await pause(page, 1500)

  await announce(page, 'STEP 3/9 — Type the #89 query and press Enter')
  const textarea = page.locator('textarea').first()
  await textarea.click()
  await textarea.fill('asian girl with mole in cheek bone using a curling iron in a youtube ad')
  await pause(page, 1500)
  await page.keyboard.press('Enter')

  // -----------------------------------------------------------------------
  // 3. Preflight panel renders with mode + dials + estimate + wallet
  // -----------------------------------------------------------------------
  await announce(page, 'STEP 4/9 — Preflight panel: 6 modes, 5 dials, estimate, wallet balance')
  const preflight = page.locator('[data-testid="preflight-panel"]')
  await expect(preflight).toBeVisible({ timeout: 10_000 })
  await pause(page, 3500)

  // Try expanding "Advanced" to reveal dials, if collapsed
  const advancedToggle = page.locator('button:has-text("Advanced"), summary:has-text("Advanced"), [data-testid="advanced-toggle"]').first()
  const hasAdvanced = await advancedToggle.isVisible({ timeout: 1000 }).catch(() => false)
  if (hasAdvanced) {
    await advancedToggle.click()
    await pause(page, 2000)
  }

  // -----------------------------------------------------------------------
  // 4. Try a different mode — click "Quick Lookup" pill
  // -----------------------------------------------------------------------
  await announce(page, 'STEP 5/9 — Click "Quick Lookup" mode to watch dials swap')
  const quickPill = page.getByText(/quick lookup/i).first()
  if (await quickPill.isVisible({ timeout: 1000 }).catch(() => false)) {
    await quickPill.click()
    await pause(page, 2500)
  }

  await announce(page, '       click back to Investigation mode')
  const investPill = page.getByText(/investigation/i).first()
  if (await investPill.isVisible({ timeout: 1000 }).catch(() => false)) {
    await investPill.click()
    await pause(page, 2500)
  }

  // -----------------------------------------------------------------------
  // 5. Cancel preflight (we won't actually run a real query in this tour)
  // -----------------------------------------------------------------------
  await announce(page, 'STEP 6/9 — Cancel preflight (skip the actual run)')
  const cancelBtn = page.locator('button:has-text("Cancel"), [data-testid="preflight-cancel"]').first()
  if (await cancelBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
    await cancelBtn.click()
    await pause(page, 1500)
  }

  // -----------------------------------------------------------------------
  // 6. Navigate to /wallet page
  // -----------------------------------------------------------------------
  await announce(page, 'STEP 7/9 — /wallet page: balance, floor config, burn chart, transactions')
  await page.goto(`${BASE}/wallet`)
  await pause(page, 4000)

  // Probe for key wallet UI elements
  const walletBody = await page.locator('body').innerText()
  const found = {
    balance: /balance|available/i.test(walletBody),
    floor: /floor/i.test(walletBody),
    topup: /top.?up/i.test(walletBody),
    history: /transaction|history|operation/i.test(walletBody),
    chart: /burn|forecast|projection|30.?day|days/i.test(walletBody),
  }
  console.log('       Wallet UI present:', found)
  await pause(page, 2000)

  // -----------------------------------------------------------------------
  // 7. /runs page — per-run cost breakdown
  // -----------------------------------------------------------------------
  await announce(page, 'STEP 8/9 — /runs page: per-run cost breakdown')
  await page.goto(`${BASE}/runs`)
  await pause(page, 4000)

  const runsBody = await page.locator('body').innerText()
  console.log('       Runs UI: has-cost-column:', /cost|ru/i.test(runsBody))
  await pause(page, 2000)

  // -----------------------------------------------------------------------
  // 8. Go back to /research and look at a completed run with grading row
  // -----------------------------------------------------------------------
  await announce(page, 'STEP 9/9 — Back to /research — look at any past run + grading')
  await page.goto(`${BASE}/research`)
  await pause(page, 2500)

  // Look for a History entry to click into
  const historyEntry = page.locator('[class*="history"], [data-testid="history-item"]').first()
  if (await historyEntry.isVisible({ timeout: 1000 }).catch(() => false)) {
    await historyEntry.click()
    await pause(page, 2500)
  }

  // Look for a node card to click (opens modal)
  const card = page.locator('[data-slot="node-result-card"]').first()
  if (await card.isVisible({ timeout: 2000 }).catch(() => false)) {
    await card.click()
    await pause(page, 4000)
    // Check the modal has the new tabs
    const modalBody = await page.locator('[role="dialog"], [class*="dialog"]').first().innerText().catch(() => '')
    console.log('       Modal tabs present:', {
      hypothesis: /hypothesis/i.test(modalBody),
      sources: /sources/i.test(modalBody),
      timing: /timing/i.test(modalBody),
      raw: /raw/i.test(modalBody),
      grading: /grade|A.+B.+C.+D/i.test(modalBody),
    })
    await pause(page, 3000)
    await page.keyboard.press('Escape')
  } else {
    console.log('       (no completed runs to inspect — preflight UI only)')
  }

  await announce(page, 'tour complete ✓')
  await pause(page, 2000)
})
