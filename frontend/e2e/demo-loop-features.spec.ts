/**
 * DEMO RECORDING — end-to-end tour of all loop substrate features.
 *
 * Captures a Playwright video showing every major capability surface:
 *   1. Investigation Templates picker on the Dashboard
 *   2. Plugins page with correct category tags
 *   3. Run Drawer — Turns tab with:
 *        · Loop banner (complete/partial counts)
 *        · Cost banner (per-phase RU)
 *        · PIR coverage (entity, resolved/total, gaps)
 *        · Decay banner (when applicable)
 *        · Synthesis panel
 *        · ACH evidence-matrix grid (expanded)
 *        · Per-turn rows with source-class chips + ACH ranking
 *        · JSON expand on a turn row
 *   4. Findings tab
 *
 * Output: test-results/.../video.webm
 */
import { test, expect, Page } from '@playwright/test'

const BASE = 'http://localhost:5173'
const USER = 'testuser'
const PASS = 'TestUser2026!'
const wait = (ms: number) => new Promise<void>(r => setTimeout(r, ms))

test.use({
  headless: false,
  viewport: { width: 1440, height: 900 },
  video: 'on',           // always record this test
})
test.setTimeout(120_000)

async function login(page: Page) {
  await page.goto(`${BASE}/`)
  await wait(1500)
  const hasLogin = await page.locator('input[type="password"]').isVisible().catch(() => false)
  if (hasLogin) {
    await page.locator('input[type="text"]').first().fill(USER)
    await page.locator('input[type="password"]').fill(PASS)
    await page.locator('button[type="submit"]').click()
    await wait(3000)
  }
}

test('demo · loop substrate end-to-end tour', async ({ page }) => {
  await login(page)

  // ── Act 1: Dashboard with Templates picker ─────────────────────────────────
  await page.goto(`${BASE}/`)
  await wait(2000)
  await page.screenshot({ path: '/tmp/demo-01-dashboard.png', fullPage: false })

  const templatesBtn = page.locator('[data-testid="templates-toggle"]')
  if (await templatesBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
    await templatesBtn.click()
    await wait(1500)
    await page.screenshot({ path: '/tmp/demo-02-templates-open.png' })
    // Click the KYB-Company template to populate the input
    const kybTemplate = page.locator('[data-testid="template-kyb-company"]').first()
    if (await kybTemplate.isVisible({ timeout: 2000 }).catch(() => false)) {
      await kybTemplate.click()
      await wait(800)
      await page.screenshot({ path: '/tmp/demo-03-template-applied.png' })
      console.log('✓ Template picker visible and applies query')
    }
  }

  // ── Act 2: Plugins page — category tags ────────────────────────────────────
  await page.goto(`${BASE}/plugins`)
  await wait(2500)
  await page.screenshot({ path: '/tmp/demo-04-plugins.png', fullPage: true })

  // Scroll to "Lookups" section to show new section
  const lookupsHeading = page.locator('text=/^Lookups( \\(\\d+\\))?$/').first()
  if (await lookupsHeading.isVisible({ timeout: 3000 }).catch(() => false)) {
    await lookupsHeading.scrollIntoViewIfNeeded()
    await wait(1500)
    await page.screenshot({ path: '/tmp/demo-05-plugins-lookups.png' })
    console.log('✓ Lookups section rendered')
  }

  // ── Act 3: Runs page → click into a real loop run ──────────────────────────
  await page.goto(`${BASE}/runs`)
  await wait(2500)
  await page.screenshot({ path: '/tmp/demo-06-runs.png' })

  // Find first succeeded row's Show button
  const succeededRows = page.locator('tr', { hasText: /succeeded/i })
  const succeededCount = await succeededRows.count()
  expect(succeededCount).toBeGreaterThan(0)

  const showButtons = succeededRows.locator('button:has-text("Show")')
  await showButtons.first().click()
  await wait(3500)   // give snapshot endpoint time to settle
  await page.screenshot({ path: '/tmp/demo-07-drawer-findings.png' })

  // ── Act 4: Turns tab — every feature visible ───────────────────────────────
  const turnsTab = page.locator('button[role="tab"]:has-text("Turns")').first()
  await expect(turnsTab).toBeVisible({ timeout: 5000 })
  await turnsTab.click()
  await wait(1500)
  await page.screenshot({ path: '/tmp/demo-08-turns-tab.png', fullPage: false })
  console.log('✓ Turns tab opened')

  // Wait for the snapshot fetch to finish
  await wait(1500)

  // Expand the ACH matrix grid for the screencap
  const showMatrix = page.locator('button:has-text("Show matrix")').first()
  if (await showMatrix.isVisible({ timeout: 3000 }).catch(() => false)) {
    await showMatrix.click()
    await wait(1500)
    await page.screenshot({ path: '/tmp/demo-09-ach-matrix-expanded.png' })
    console.log('✓ ACH matrix expanded')
  }

  // Expand one turn's JSON
  const showJson = page.locator('button:has-text("Show JSON")').first()
  if (await showJson.isVisible({ timeout: 2000 }).catch(() => false)) {
    await showJson.click()
    await wait(1500)
    await page.screenshot({ path: '/tmp/demo-10-turn-json.png' })
    console.log('✓ Turn JSON expanded')
  }

  // ── Act 5: Summary tab ─────────────────────────────────────────────────────
  const summaryTab = page.locator('button[role="tab"]:has-text("Summary")').first()
  if (await summaryTab.isVisible({ timeout: 2000 }).catch(() => false)) {
    await summaryTab.click()
    await wait(1500)
    await page.screenshot({ path: '/tmp/demo-11-summary.png' })
  }

  // ── Act 6: Back to Findings tab to round out the tour ──────────────────────
  const findingsTab = page.locator('button[role="tab"]:has-text("Findings")').first()
  await findingsTab.click()
  await wait(1500)
  await page.screenshot({ path: '/tmp/demo-12-findings-final.png' })

  console.log('\n=== DEMO RECORDING COMPLETE ===')
})
