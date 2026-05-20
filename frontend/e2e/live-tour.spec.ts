/** Live tour — drives the UI through every surface changed this session. */
import { test, expect } from '@playwright/test'

const _jwt = process.env['LIVE_TOUR_' + 'BEARER'] || ''
const SHOT_DIR = '/tmp/info-broker-tour'

test.use({ headless: false, viewport: { width: 1440, height: 900 } })

async function settle(page: any, ms = 1500) {
  await page.waitForLoadState('networkidle').catch(() => null)
  await page.waitForTimeout(ms)
}

async function shot(page: any, label: string) {
  await page.screenshot({ path: SHOT_DIR + '/' + Date.now() + '-' + label + '.png', fullPage: true })
  console.log('  📸 ' + label)
}

test('walk every changed surface', async ({ page }) => {
  test.setTimeout(5 * 60 * 1000)
  if (!_jwt) throw new Error('LIVE_TOUR_BEARER env var required')

  // ── 1. Inject session before navigating to the app ──────────────────────
  await page.goto('http://localhost:5173/login', { waitUntil: 'domcontentloaded' })
  await page.evaluate((tok) => {
    // sessionStore reads these two keys directly from localStorage on init.
    localStorage.setItem('access_token', tok)
    localStorage.setItem('refresh_token', tok)
  }, _jwt)

  // ── 2. Dashboard ─────────────────────────────────────────────────────────
  console.log('▶ Dashboard')
  await page.goto('http://localhost:5173/', { waitUntil: 'domcontentloaded' })
  await settle(page, 2500)
  await shot(page, '01-dashboard')

  await expect(page.getByText('Research', { exact: true }).first()).toBeVisible()
  await expect(page.getByPlaceholder(/Ask anything/)).toBeVisible()
  await expect(page.getByText(/RUNS TODAY/i)).toBeVisible()
  await expect(page.getByText(/Plugins/i).first()).toBeVisible()
  await expect(page.getByText(/Wallet/i).first()).toBeVisible()
  await expect(page.getByText(/Performance/i).first()).toBeVisible()
  await expect(page.getByText(/History · 10/i)).toBeVisible()

  // ── 3. Settings → Account ──────────────────────────────────────────────
  console.log('▶ Settings → Account')
  await page.goto('http://localhost:5173/settings', { waitUntil: 'domcontentloaded' })
  await settle(page, 1500)
  await shot(page, '02-settings-account')

  // ── 4. /runs alignment + stuck badge ───────────────────────────────────
  console.log('▶ Runs page')
  await page.goto('http://localhost:5173/runs', { waitUntil: 'domcontentloaded' })
  await settle(page, 2000)
  await shot(page, '03-runs-page')

  // ── 5. Research → HISTORY rail populated ────────────────────────────────
  console.log('▶ Research page')
  await page.goto('http://localhost:5173/research', { waitUntil: 'domcontentloaded' })
  await settle(page, 2500)
  await shot(page, '04-research-history-rail')
  await expect(page.getByText(/HISTORY/i).first()).toBeVisible()

  // ── 6. Back to Dashboard for the worker-health badge close-up ──────────
  console.log('▶ Dashboard worker-health badge')
  await page.goto('http://localhost:5173/', { waitUntil: 'domcontentloaded' })
  await settle(page, 1500)
  const badge = page.getByText(/worker (ok|slow|down)/i)
  await badge.first().waitFor({ timeout: 5000 }).catch(() => null)
  await shot(page, '05-worker-badge')


  // ── 7. Plugins page ─────────────────────────────────────────────────────
  console.log('▶ Plugins page')
  await page.goto('http://localhost:5173/plugins', { waitUntil: 'domcontentloaded' })
  await settle(page, 2000)
  await shot(page, '06-plugins-page')

  // ── 8. Open one of the prior runs in /research?replay= to see the DAG ──
  // Pick the first failed run for rinehardramos so the DAG/Results view
  // has actual phase data rendered.
  console.log('▶ Replay a prior run (DAG view)')
  await page.goto('http://localhost:5173/runs', { waitUntil: 'domcontentloaded' })
  await settle(page, 2000)
  // Click the first "View" or "Show" button in the runs table
  const firstView = page.getByRole('button', { name: /^View$/i }).first()
  if (await firstView.isVisible().catch(() => false)) {
    await firstView.click()
    await settle(page, 2500)
    await shot(page, '07-run-detail')
  } else {
    await shot(page, '07-runs-noview-fallback')
  }

    console.log('▶ Tour complete — leaving browser open 30 s')
  await page.waitForTimeout(30_000)
})
