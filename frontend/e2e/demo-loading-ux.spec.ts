import { test, type Page } from '@playwright/test'

const BASE = 'http://localhost:5173'
const wait = (ms: number) => new Promise(r => setTimeout(r, ms))

async function login(page: Page) {
  await page.goto(`${BASE}/login`)
  await wait(1200)
  const pw = page.locator('input[type="password"]').first()
  if (await pw.isVisible({ timeout: 2000 }).catch(() => false)) {
    await page.fill('input[type="text"], input[type="email"]', 'admin')
    await pw.fill('admin')
    await page.locator('button[type="submit"]').first().click()
    await page.waitForURL(/\/$|\/research|\/runs|\/dashboard/, { timeout: 8_000 })
  }
}

async function caption(page: Page, text: string) {
  console.log(`\n▶ ${text}`)
  await wait(2500)
}

test('demo loading UX rollout — phases 1-5', async ({ page, context }) => {
  test.setTimeout(180_000)
  page.on('pageerror', (e) => console.log(`pageerror: ${e.message}`))

  console.log('\n════════════════════════════════════════════════════════════')
  console.log('  Loading-UX Demo · Phases 1–5')
  console.log('════════════════════════════════════════════════════════════')

  // ── login ──
  await login(page)

  // ── 1. Dashboard — first load with cleared cache ──
  await caption(page, '1. Dashboard — clearing cache so skeletons are visible')
  await context.clearCookies()
  await page.evaluate(() => { try { sessionStorage.clear() } catch {} })
  await page.goto(`${BASE}/dashboard`)
  await caption(page, '   ↳ 4 widget skeletons should flash before data lands (G cost, H open Qs, B entity, History)')
  await wait(3000)

  // ── 2. Entity knowledge — type a query and watch skeleton ──
  await caption(page, '2. B widget — type an entity name to see search skeleton')
  const entityInput = page.locator('input[placeholder*="company"]').first()
  if (await entityInput.isVisible({ timeout: 3000 }).catch(() => false)) {
    await entityInput.fill('test entity')
    await page.locator('button:has-text("Look up")').first().click()
    await wait(3500)
  }

  // ── 3. Research preflight — submit a query, see cost-estimate skeleton ──
  await caption(page, '3. Research preflight — submit a query to see cost-estimate skeleton')
  await page.goto(`${BASE}/research`)
  await wait(2000)
  // Find the chat input (multiple possible selectors based on AgentChat layout)
  const chatInput = page.locator('textarea, input[placeholder*="research" i], input[placeholder*="ask" i]').first()
  if (await chatInput.isVisible({ timeout: 5000 }).catch(() => false)) {
    await chatInput.fill('Quick test query — show me preflight estimate skeleton')
    await chatInput.press('Enter')
    await caption(page, '   ↳ EstimateBreakdownSkeleton renders, then real estimate appears')
    await wait(4000)
  }

  // ── 4. LiveStream rail — already showing all states ──
  await caption(page, '4. LiveStream right rail — Live / History / Review sections')
  await wait(2500)

  // ── 5. Open a previous run from dashboard, see drawer skeletons ──
  await caption(page, '5. Run drawer — opening a run to see Findings skeleton')
  await page.goto(`${BASE}/dashboard`)
  await wait(2000)
  // Click first row in history
  const firstRow = page.locator('tbody tr, [role="row"]').first()
  if (await firstRow.isVisible({ timeout: 3000 }).catch(() => false)) {
    await firstRow.click()
    await caption(page, '   ↳ Title skeleton + finding-card skeletons before run data lands')
    await wait(3500)
    // Click through tabs
    for (const tab of ['Summary', 'Raw JSON']) {
      const t = page.locator(`button:has-text("${tab}")`).first()
      if (await t.isVisible({ timeout: 1500 }).catch(() => false)) {
        await t.click()
        await caption(page, `   ↳ ${tab} tab — skeleton matching tab content shape`)
        await wait(2000)
      }
    }
    // Close drawer
    await page.keyboard.press('Escape')
    await wait(800)
  }

  // ── 6. Settings — account section skeleton ──
  await caption(page, '6. Settings → Account — form skeleton on cold load')
  await page.goto(`${BASE}/settings`)
  await wait(3500)

  // ── 7. Monitors page ──
  await caption(page, '7. Monitors page — list skeleton')
  await page.goto(`${BASE}/monitors`)
  await wait(3000)

  // ── 8. Wallet page (TransactionHistory skeleton) ──
  await caption(page, '8. Wallet → Transaction history — table skeleton')
  await page.goto(`${BASE}/wallet`)
  await wait(3500)

  // ── 9. Error state demo ──
  await caption(page, '9. Error state — intercepting /v3/* to force InlineError + Retry')
  await page.route('**/v3/runs/metrics**', route => route.abort('failed'))
  await page.route('**/v3/users/cost/aggregate**', route => route.abort('failed'))
  await page.route('**/v3/users/open-questions/digest**', route => route.abort('failed'))
  await page.goto(`${BASE}/dashboard`)
  await caption(page, '   ↳ Widgets should show InlineError with Retry buttons')
  await wait(5000)
  await page.unroute('**/v3/runs/metrics**')
  await page.unroute('**/v3/users/cost/aggregate**')
  await page.unroute('**/v3/users/open-questions/digest**')

  // ── 10. Recovery via Retry ──
  await caption(page, '10. Hit a Retry button to recover')
  const retryBtn = page.locator('button:has-text("Retry")').first()
  if (await retryBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
    await retryBtn.click()
    await wait(3000)
  }

  console.log('\n════════════════════════════════════════════════════════════')
  console.log('  Demo complete. Press Ctrl+C in the terminal when done.')
  console.log('════════════════════════════════════════════════════════════\n')

  // Keep the browser open for visual inspection
  await wait(20_000)
})
