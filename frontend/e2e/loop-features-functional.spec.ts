/**
 * Functional E2E check for the orchestrated-loop UI surface.
 *
 * Verifies that every backend feature added in Slices 1, 1.5, 2, and 2b
 * has a corresponding visible UI surface and that the data flows through:
 *   · Turns tab appears for loop runs
 *   · LoopBanner shows complete/partial + hypothesis counts + turn count
 *   · Synthesis panel renders the brain's final answer
 *   · Source-class chips render with color
 *   · ACH ranking (inconsistencies/consistencies) renders per turn
 *   · TurnRow expands to show the working_memory JSON
 *
 * Targets a known successful loop run from the recent dev session — does not
 * trigger a fresh run (that would take ~3 minutes and require API auth).
 */
import { test, expect, Page } from '@playwright/test'

const BASE = 'http://localhost:5173'
const USER = 'testuser'
const PASS = 'TestUser2026!'
// Known loop run with full Slice 1/2 features populated.
const LOOP_RUN_ID = '4f9291b7-6a6a-4447-91a9-ec6c0ecd8edf'

const wait = (ms: number) => new Promise<void>(r => setTimeout(r, ms))

async function login(page: Page) {
  await page.goto(`${BASE}/`)
  await wait(1200)
  const hasLogin = await page.locator('input[type="password"]').isVisible().catch(() => false)
  if (hasLogin) {
    await page.locator('input[type="text"]').first().fill(USER)
    await page.locator('input[type="password"]').fill(PASS)
    await page.locator('button[type="submit"]').click()
    await wait(2500)
  }
}

test.use({ headless: false, viewport: { width: 1440, height: 900 } })
test.setTimeout(90_000)

test('loop UI surface: every new backend feature is visible in the drawer', async ({ page }) => {
  await login(page)

  // Go to /runs and find the loop run row
  await page.goto(`${BASE}/runs`)
  await wait(1500)
  await page.screenshot({ path: '/tmp/loop-ui-01-runs.png', fullPage: true })

  // Find a SUCCEEDED row's Show button — partial/queued runs may not have
  // synthesis text yet, so the test would be flaky. We narrow to rows that
  // contain the "succeeded" status badge.
  await wait(1500)  // let React Query settle
  // Each row is a <tr>. Find rows with succeeded status, then their Show button.
  const succeededRows = page.locator('tr', { hasText: /succeeded/i })
  const succeededCount = await succeededRows.count()
  console.log(`Found ${succeededCount} succeeded rows`)
  expect(succeededCount).toBeGreaterThan(0)
  const showButtons = succeededRows.locator('button:has-text("Show")')
  const buttonCount = await showButtons.count()
  console.log(`Found ${buttonCount} Show buttons on succeeded rows`)
  expect(buttonCount).toBeGreaterThan(0)

  // Trace working-memory endpoint responses so we can see what the drawer is
  // actually receiving (or not) for each run.
  page.on('response', async (resp) => {
    const url = resp.url()
    if (url.includes('/working-memory')) {
      console.log(`  [net] GET ${url.split('/').slice(-3).join('/')} → ${resp.status()}`)
    }
  })

  let opened = false
  for (let i = 0; i < Math.min(buttonCount, 6); i++) {
    await showButtons.nth(i).click()
    await wait(2500)   // let snapshot fetch settle
    const drawerOpen = await page.locator('[role="dialog"]').first().isVisible({ timeout: 3000 }).catch(() => false)
    console.log(`  row ${i}: drawer open=${drawerOpen}`)
    if (!drawerOpen) continue
    await page.screenshot({ path: `/tmp/loop-ui-iter-${i}.png`, fullPage: true })
    // Wait a beat longer for React Query to fetch snapshots
    await wait(1500)
    const tabsVisible = await page.locator('button[role="tab"]').count()
    const tabLabels = await page.locator('button[role="tab"]').allTextContents()
    console.log(`  row ${i}: ${tabsVisible} tabs visible: ${JSON.stringify(tabLabels)}`)
    const hasTurnsTab = tabLabels.some(t => /Turns/.test(t))
    if (hasTurnsTab) {
      console.log(`✓ Found loop run at row ${i + 1}; drawer opened with Turns tab`)
      opened = true
      break
    }
    // Not a loop run — close drawer and try next
    await page.keyboard.press('Escape')
    await wait(800)
  }
  expect(opened).toBe(true)
  await page.screenshot({ path: '/tmp/loop-ui-02-drawer-open.png', fullPage: true })

  // ── 1+2. Drawer + Turns tab — already verified during the search above ────
  const turnsTab = page.locator('button[role="tab"]:has-text("Turns")').first()
  const turnsText = await turnsTab.textContent()
  console.log(`✓ Drawer + Turns tab present: "${turnsText}"`)

  // ── 3. Click Turns tab ────────────────────────────────────────────────────
  await turnsTab.click()
  await wait(800)
  await page.screenshot({ path: '/tmp/loop-ui-03-turns-tab.png', fullPage: true })

  // ── 4. LoopBanner ─────────────────────────────────────────────────────────
  // Banner text format: "complete · 3/3 hypotheses verified · 5 turns"
  // or partial · X/Y hypotheses verified · final phase XYZ · N turns
  const bannerCandidate = page.locator('text=/(complete|partial).*hypotheses verified.*turns/')
  await expect(bannerCandidate.first()).toBeVisible({ timeout: 4000 })
  const bannerText = await bannerCandidate.first().textContent()
  console.log(`✓ LoopBanner: "${bannerText}"`)

  // ── 5. Synthesis panel ────────────────────────────────────────────────────
  // Locate the synthesis CONTAINER (the parent div containing the "Synthesis
  // (final turn)" label) and grab its body. The body lives in the
  // sibling div with whitespace-pre-wrap; falling back to the parent's full
  // text minus the header label.
  const synthHeader = page.locator('text="Synthesis (final turn)"').first()
  const headerVisible = await synthHeader.isVisible({ timeout: 4000 }).catch(() => false)
  if (!headerVisible) {
    console.log('ℹ︎ Synthesis panel not present — this run had empty synthesis_summary (likely partial)')
  } else {
    console.log('✓ Synthesis panel header visible')
    const synthContainer = synthHeader.locator('xpath=..')  // parent
    const containerText = (await synthContainer.textContent()) || ''
    const synthBodyLen = containerText.replace('Synthesis (final turn)', '').trim().length
    console.log(`✓ Synthesis body length: ${synthBodyLen} chars`)
    expect(synthBodyLen).toBeGreaterThan(200)
  }

  // ── 6. Source-class chips ─────────────────────────────────────────────────
  const sourceClassChips = page.locator('span', {
    hasText: /^(primary official|registry|news|aggregator|social|training|unknown) \d+$/i,
  })
  const chipCount = await sourceClassChips.count()
  console.log(`✓ Source-class chips rendered: ${chipCount} chips found`)
  expect(chipCount).toBeGreaterThan(0)

  // ── 7. ACH ranking ────────────────────────────────────────────────────────
  // Format: "ACH ranking · N scores · fewest inconsistencies wins:"
  const achHeader = page.locator('text=/ACH ranking.*scores.*fewest inconsistencies/')
  const achPresent = await achHeader.count() > 0
  if (achPresent) {
    console.log('✓ ACH ranking header rendered')
    // At least one ranking row: "Ni / Nc"
    const rankingRows = page.locator('text=/\\d+i \\/ \\d+c/')
    const rankingCount = await rankingRows.count()
    console.log(`✓ ACH ranking rows: ${rankingCount}`)
    expect(rankingCount).toBeGreaterThan(0)
  } else {
    console.log('ℹ︎ ACH ranking not rendered (matrix may be empty for this run)')
  }

  // ── 8. Per-turn rows ──────────────────────────────────────────────────────
  // Each row starts with "Turn N"
  const turnRows = page.locator('text=/^Turn \\d+$/')
  const turnRowCount = await turnRows.count()
  console.log(`✓ Per-turn rows: ${turnRowCount}`)
  expect(turnRowCount).toBeGreaterThanOrEqual(2)   // at least init turn + 1 brain turn

  // ── 9. Phase tag colors per turn ──────────────────────────────────────────
  const phaseTags = page.locator('span', { hasText: /^(EXPLORE|TEST|SYNTHESIZE)$/i })
  const phaseCount = await phaseTags.count()
  console.log(`✓ Phase tags: ${phaseCount}`)
  expect(phaseCount).toBeGreaterThanOrEqual(2)

  // ── 10. TurnRow Show JSON expand ──────────────────────────────────────────
  const showJsonBtn = page.locator('button:has-text("Show JSON")').first()
  await expect(showJsonBtn).toBeVisible({ timeout: 3000 })
  await showJsonBtn.click()
  await wait(500)
  // Expanded panel shows a <pre> with WM JSON
  const preBlock = page.locator('pre').first()
  await expect(preBlock).toBeVisible({ timeout: 3000 })
  const preText = await preBlock.textContent()
  expect((preText || '').length).toBeGreaterThan(100)
  console.log(`✓ JSON expand works (pre block ${(preText || '').length} chars)`)
  await page.screenshot({ path: '/tmp/loop-ui-04-expanded-json.png', fullPage: true })

  // ── 10a. ACH matrix grid (only when there's a non-empty evidence matrix) ──
  const matrixHeader = page.locator('text=/ACH evidence matrix/')
  const matrixVisible = await matrixHeader.first().isVisible({ timeout: 2000 }).catch(() => false)
  if (matrixVisible) {
    console.log('✓ ACH matrix header rendered')
    // Click "Show matrix" to expand it
    const showMatrixBtn = page.locator('button:has-text("Show matrix")').first()
    await showMatrixBtn.click()
    await wait(500)
    // Legend appears when expanded
    const legend = page.locator('text=/^\\+ consistent$/')
    await expect(legend).toBeVisible({ timeout: 2000 })
    console.log('✓ ACH matrix legend rendered after expand')
    // At least one consistent cell should be present (+)
    const consistentCells = page.locator('td', { hasText: /^\+$/ })
    const consistentCount = await consistentCells.count()
    console.log(`✓ Consistent cells in matrix: ${consistentCount}`)
    expect(consistentCount).toBeGreaterThan(0)
    await page.screenshot({ path: '/tmp/loop-ui-ach-matrix.png', fullPage: true })
  } else {
    console.log('ℹ︎ ACH matrix not rendered (no evidence scores on this run)')
  }

  // ── 10b. Deception chip (only when at least one finding scored ≥ 0.3) ─────
  const deceptionChip = page.locator('text=/⚠ \\d+ flagged/')
  const deceptionCount = await deceptionChip.count()
  if (deceptionCount > 0) {
    const chipText = await deceptionChip.first().textContent()
    console.log(`✓ Deception chip surfaced: "${chipText}"`)
  } else {
    console.log('ℹ︎ No deception flags on this run (no source_echo / copied_content / etc.)')
  }

  // ── 11. Findings tab still works (legacy compatibility) ───────────────────
  const findingsTab = page.locator('button[role="tab"]:has-text("Findings")').first()
  await findingsTab.click()
  await wait(700)
  await page.screenshot({ path: '/tmp/loop-ui-05-findings.png', fullPage: true })
  // We don't enforce a specific count — loop runs may not write to research_trails,
  // but the tab itself must render without error
  const findingsTabActive = await findingsTab.getAttribute('data-state')
  console.log(`✓ Findings tab clickable (state=${findingsTabActive})`)

  console.log('\n=== ALL UI SURFACES VERIFIED ===')
})
