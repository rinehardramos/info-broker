/**
 * Debug test — open the app in Chrome and inspect current UI state.
 * Run: cd frontend && npx playwright test e2e/debug-ui.spec.ts --headed --project=chromium
 */
import { test, expect } from '@playwright/test'

const BASE = 'http://localhost:5173'
const wait = (ms: number) => new Promise(r => setTimeout(r, ms))

test.use({
  baseURL: BASE,
  viewport: { width: 1400, height: 900 },
  headless: false,
})

test.setTimeout(300_000) // 5 min

test('debug: inspect current UI', async ({ page }) => {
  // ── 1. Login ──────────────────────────────────────────────────────────
  await page.goto(`${BASE}/`)
  await wait(1000)

  // Check if login form is visible
  const loginVisible = await page.locator('input[type="password"]').isVisible().catch(() => false)
  if (loginVisible) {
    await page.fill('input[placeholder*="user" i], input[type="text"]', 'admin').catch(() => {})
    await page.fill('input[type="password"]', 'admin').catch(() => {})
    await page.locator('button[type="submit"], button:has-text("Login"), button:has-text("Sign in")').click().catch(() => {})
    await wait(2000)
  }

  // ── 2. Screenshot the main UI ─────────────────────────────────────────
  await page.screenshot({ path: '/tmp/debug-01-main.png', fullPage: false })
  console.log('Screenshot 1: main UI saved to /tmp/debug-01-main.png')

  // ── 3. Check IS toggle ────────────────────────────────────────────────
  const isSwitch = page.locator('text=IS').first()
  const isSwitchVisible = await isSwitch.isVisible().catch(() => false)
  console.log('IS switch visible:', isSwitchVisible)

  // ── 4. Check LiveStream columns ────────────────────────────────────────
  const liveText = await page.locator('text=LIVE').isVisible().catch(() => false)
  const historyText = await page.locator('text=HISTORY').isVisible().catch(() => false)
  const reviewText = await page.locator('text=REVIEW').isVisible().catch(() => false)
  console.log('LIVE visible:', liveText, '| HISTORY visible:', historyText, '| REVIEW visible:', reviewText)

  // ── 5. Check New Session button ────────────────────────────────────────
  const newSessionBtn = await page.locator('text=New Session').isVisible().catch(() => false)
  console.log('New Session button visible:', newSessionBtn)

  // ── 6. Check Agent column header ───────────────────────────────────────
  const agentHeader = await page.locator('text=Agent').first().isVisible().catch(() => false)
  const goalChip = await page.locator('text=Goal').isVisible().catch(() => false)
  console.log('Agent header visible:', agentHeader, '| Goal chip visible:', goalChip)

  // ── 7. Check icon rail size ────────────────────────────────────────────
  const settingsIcon = await page.locator('text=⚙').first().boundingBox().catch(() => null)
  console.log('Settings icon bounding box:', settingsIcon)

  // ── 8. Type a query and check PreFlight clarification ─────────────────
  const textarea = page.locator('textarea').first()
  if (await textarea.isVisible().catch(() => false)) {
    await textarea.fill('new series with girl in spiderman where man has a shotgun')
    await page.screenshot({ path: '/tmp/debug-02-query-typed.png' })
    console.log('Screenshot 2: query typed')

    // Submit
    await page.keyboard.press('Enter')
    await wait(5000)

    await page.screenshot({ path: '/tmp/debug-03-after-submit.png' })
    console.log('Screenshot 3: after submit')

    // Check for clarification question
    const clarifyVisible = await page.locator('text=Where did you see').isVisible().catch(() => false)
    const optionsVisible = await page.locator('text=YouTube').isVisible().catch(() => false)
    console.log('Clarification "Where did you see" visible:', clarifyVisible)
    console.log('YouTube option chip visible:', optionsVisible)
  }

  // ── 9. Check console errors ────────────────────────────────────────────
  const errors: string[] = []
  page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()) })
  await wait(2000)
  if (errors.length) console.log('Console errors:', errors)

  // Keep browser open for manual inspection
  console.log('\n=== Browser is open for inspection. Press Ctrl+C when done. ===')
  await wait(120_000) // Keep open 2 minutes
})
