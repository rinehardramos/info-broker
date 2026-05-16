/**
 * Deeper visual tour — exercises features that need a completed past run:
 *   - History sidebar entry → opens completed run
 *   - Node card click → modal with Formatted / Input / Hypothesis / Sources / Timing / Raw tabs
 *   - Grading row in Sources tab (3.1)
 *   - Share button → ShareDialog (3.9)
 *   - Templates dropdown at top of fresh preflight (3.2)
 *   - Wallet/runs page visit
 *
 * Runs in headed Chrome so the user can watch each feature work.
 */
import { test, Page } from '@playwright/test'

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
}

const pause = (page: Page, ms = 2000) => page.waitForTimeout(ms)

test('deep visual tour — past run modal, grading, share, templates', async ({ page }) => {
  test.setTimeout(240_000)

  await announce(page, 'STEP 1 — Login')
  await login(page)
  await pause(page, 1500)

  // -----------------------------------------------------------------------
  // 2. /research — pick a succeeded run from the History sidebar
  // -----------------------------------------------------------------------
  await announce(page, 'STEP 2 — Open /research and click a succeeded past run from History')
  await page.goto(`${BASE}/research`)
  await pause(page, 2500)

  // History session items have data-testid="history-session-item"
  const historyEntries = page.locator('[data-testid="history-session-item"]')
  const entryCount = await historyEntries.count().catch(() => 0)
  console.log(`       Found ${entryCount} history-session-item buttons`)
  if (entryCount > 0) {
    const first = historyEntries.first()
    await first.scrollIntoViewIfNeeded()
    await first.click({ timeout: 5000 })
    console.log('       Clicked first history entry')
  } else {
    console.log('       No history entries to click')
  }
  await pause(page, 4000)

  // -----------------------------------------------------------------------
  // 3. Look at the live/completed run view — should show cards or candidate compare
  // -----------------------------------------------------------------------
  await announce(page, 'STEP 3 — Look for completed run UI (cards, CandidateComparison, ACH matrix)')
  await pause(page, 2500)

  const runViewText = await page.locator('body').innerText()
  console.log('       Run view shows:', {
    candidateComparison: /candidate|confidence|signal/i.test(runViewText),
    phaseProgress: /signal_extraction|broaden|red_team|rank_verify/i.test(runViewText),
    achMatrix: /ach matrix|primary subject|supporting/i.test(runViewText),
    sourceClass: /live_search|prior_research|🌐|📚/i.test(runViewText),
  })

  // -----------------------------------------------------------------------
  // 4. Click a node card to open the modal
  // -----------------------------------------------------------------------
  await announce(page, 'STEP 4 — Click a node card → modal with tabs')
  const card = page.locator('[data-slot="node-result-card"]').first()
  if (await card.isVisible({ timeout: 2000 }).catch(() => false)) {
    await card.scrollIntoViewIfNeeded()
    await card.click({ timeout: 5000 })
    await pause(page, 3500)
    const modalText = await page.locator('[role="dialog"]').first().innerText().catch(() => '')
    console.log('       Modal tabs detected:', {
      formatted: /formatted/i.test(modalText),
      input: /^input$|\binput\b/im.test(modalText),
      hypothesis: /hypothesis/i.test(modalText),
      sources: /sources/i.test(modalText),
      timing: /timing/i.test(modalText),
      raw: /raw output|raw/i.test(modalText),
      grading: /grade.*finding|A.+B.+C.+D|admiralty/i.test(modalText),
    })
    await pause(page, 4000)
    // Try clicking Hypothesis tab
    const hypothesisTab = page.getByRole('tab', { name: /hypothesis/i })
    if (await hypothesisTab.isVisible({ timeout: 1000 }).catch(() => false)) {
      await hypothesisTab.click()
      await pause(page, 2500)
      console.log('       Hypothesis tab clicked — visible')
    }
    // Try Sources tab to see grading row
    const sourcesTab = page.getByRole('tab', { name: /sources/i })
    if (await sourcesTab.isVisible({ timeout: 1000 }).catch(() => false)) {
      await sourcesTab.click()
      await pause(page, 2500)
      console.log('       Sources tab clicked — grading row should be visible')
    }
    await pause(page, 2000)
    await page.keyboard.press('Escape')
  } else {
    console.log('       No node card visible — run may not have rendered IS cards')
  }
  await pause(page, 1500)

  // -----------------------------------------------------------------------
  // 5. Find Share button somewhere on the run view
  // -----------------------------------------------------------------------
  await announce(page, 'STEP 5 — Share dialog')
  const shareBtn = page.locator('[data-testid="share-run-button"]').first()
  if (await shareBtn.isVisible({ timeout: 1500 }).catch(() => false)) {
    await shareBtn.click()
    await pause(page, 3500)
    const shareModal = await page.locator('[role="dialog"]').first().innerText().catch(() => '')
    console.log('       Share dialog content:', {
      ttlField: /ttl|days|expire/i.test(shareModal),
      shareButton: /create|share link/i.test(shareModal),
      revokeButton: /revoke/i.test(shareModal),
    })
    await pause(page, 2500)
    await page.keyboard.press('Escape')
  } else {
    console.log('       Share button not visible in this view')
  }
  await pause(page, 1500)

  // -----------------------------------------------------------------------
  // 6. Templates dropdown — fresh /research → type → preflight panel
  // -----------------------------------------------------------------------
  await announce(page, 'STEP 6 — Templates dropdown in preflight')
  await page.goto(`${BASE}/research`)
  await pause(page, 2000)
  await page.locator('textarea').first().fill('template demo query')
  await page.keyboard.press('Enter')
  await page.locator('[data-testid="preflight-panel"]').waitFor({ timeout: 10_000 })
  await pause(page, 3000)
  const panelText = await page.locator('[data-testid="preflight-panel"]').innerText()
  console.log('       Preflight has templates dropdown:', /template/i.test(panelText))
  await pause(page, 2500)

  // -----------------------------------------------------------------------
  // 7. Wallet page — full features
  // -----------------------------------------------------------------------
  await announce(page, 'STEP 7 — /wallet page features')
  await page.goto(`${BASE}/wallet`)
  await pause(page, 4000)
  const wallet = await page.locator('body').innerText()
  console.log('       Wallet sections present:', {
    balance: /balance|available/i.test(wallet),
    floor: /floor/i.test(wallet),
    buyMore: /buy more|top.?up/i.test(wallet),
    burnChart: /burn|forecast|projection|30.?day|days|chart/i.test(wallet),
    transactionHistory: /transaction|history|operation/i.test(wallet),
    templates: /template/i.test(wallet),
  })
  await pause(page, 2500)

  // -----------------------------------------------------------------------
  // 8. Runs page — per-run cost
  // -----------------------------------------------------------------------
  await announce(page, 'STEP 8 — /runs page')
  await page.goto(`${BASE}/runs`)
  await pause(page, 3000)
  const runsBody = await page.locator('body').innerText()
  console.log('       Runs sections:', {
    runList: /run|query|cost|ru/i.test(runsBody),
    costColumn: /cost|ru/i.test(runsBody),
  })
  // Click "Cost" button if present
  const costBtn = page.getByText(/^cost$/i).or(page.getByText(/breakdown/i)).first()
  if (await costBtn.isVisible({ timeout: 1500 }).catch(() => false)) {
    await costBtn.click()
    await pause(page, 3500)
    console.log('       Cost breakdown panel opened')
  }
  await pause(page, 2000)

  await announce(page, '✓ deep tour complete')
  await pause(page, 2000)
})
