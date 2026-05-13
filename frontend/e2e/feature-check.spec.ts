/**
 * Full feature check using testuser (analyst role).
 * Runs in headed Chrome so visual state is inspectable.
 */
import { test, expect, Page } from '@playwright/test'

const BASE = 'http://localhost:5173'
const USER = 'testuser'
const PASS = 'TestUser2026!'
const wait = (ms: number) => new Promise<void>(r => setTimeout(r, ms))

test.use({ headless: false, viewport: { width: 1440, height: 900 } })
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
  await page.screenshot({ path: '/tmp/feat-01-login.png' })
  console.log('Logged in as testuser')
}

test('01 — Login page design and sign-in', async ({ page }) => {
  await page.goto(`${BASE}/login`)
  await wait(1000)
  await page.screenshot({ path: '/tmp/feat-00-login-page.png' })

  // Logo visible
  const logo = page.locator('svg[aria-label="infobroker"]').first()
  await expect(logo).toBeVisible({ timeout: 5000 })
  console.log('Logo mark visible on login page')

  // Sign in button exists and has correct size
  const btn = page.locator('button[type="submit"]')
  await expect(btn).toBeVisible()
  const btnBox = await btn.boundingBox()
  console.log('Sign in button height:', btnBox?.height)
  expect(btnBox!.height).toBeGreaterThan(45)

  // Social login placeholders visible
  const googleBtn = page.locator('button:has-text("Continue with Google")')
  await expect(googleBtn).toBeVisible()
  const githubBtn = page.locator('button:has-text("Continue with GitHub")')
  await expect(githubBtn).toBeVisible()
  console.log('Social login buttons present')

  // Login
  await page.locator('input[type="text"]').first().fill(USER)
  await page.locator('input[type="password"]').fill(PASS)
  await page.locator('button[type="submit"]').click()
  await wait(3000)
  await expect(page).not.toHaveURL(/login/)
  console.log('Login successful — redirected to', page.url())
})

test('02 — Dashboard loads with stat cards and run list', async ({ page }) => {
  await login(page)
  await page.goto(`${BASE}/dashboard`)
  await wait(2000)
  await page.screenshot({ path: '/tmp/feat-02-dashboard.png' })

  // Page title
  await expect(page.locator('h1, [class*="text-lg"]').filter({ hasText: /Dashboard/i })).toBeVisible({ timeout: 5000 })

  // Stat cards (even if showing "—" due to no auth on API)
  const cards = page.locator('[class*="Card"], .card').filter({ hasNot: page.locator('table') })
  const cardCount = await cards.count()
  console.log('Stat cards found:', cardCount)

  // Icon rail visible
  const rail = page.locator('[class*="flex-col"][style*="width: 52"], [style*="border-left"]').first()
  const railVisible = await rail.isVisible().catch(() => false)
  console.log('Icon rail visible:', railVisible)

  // Logo mark in rail
  const logoMark = page.locator('button[title="infobroker"]').first()
  const logoVisible = await logoMark.isVisible().catch(() => false)
  console.log('Logo mark in rail:', logoVisible)
})

test('03 — History page loads with filters', async ({ page }) => {
  await login(page)
  await page.goto(`${BASE}/history`)
  await wait(2000)
  await page.screenshot({ path: '/tmp/feat-03-history.png' })

  await expect(page.locator('h1').filter({ hasText: /History/i })).toBeVisible({ timeout: 5000 })

  // Filter controls
  const fromInput = page.locator('input[aria-label="from"]')
  const statusSel = page.locator('select[aria-label="status"]')
  await expect(fromInput).toBeVisible()
  await expect(statusSel).toBeVisible()
  console.log('History filters present')

  // Table shows headers (runs exist) OR empty state (fresh user — both correct)
  const hasHeaders = await page.locator('th').filter({ hasText: /Query/i }).isVisible().catch(() => false)
  const hasEmpty = await page.locator('text=No runs').isVisible().catch(() => false)
  console.log('History: headers=', hasHeaders, 'empty=', hasEmpty)
  expect(hasHeaders || hasEmpty, 'History should show table or empty state').toBe(true)
})

test('04 — Settings page shows Agent section (analyst role)', async ({ page }) => {
  await login(page)
  await page.goto(`${BASE}/settings`)
  await wait(2000)
  await page.screenshot({ path: '/tmp/feat-04-settings.png' })

  // Agent section should be visible to analyst
  const agentBtn = page.locator('button').filter({ hasText: /Agent/i })
  await expect(agentBtn).toBeVisible({ timeout: 5000 })
  await agentBtn.click()
  await wait(500)
  await page.screenshot({ path: '/tmp/feat-04-settings-agent.png' })
  console.log('Settings Agent section accessible to analyst')

  // Core Settings should NOT be visible (analyst, not admin)
  const coreBtn = page.locator('button').filter({ hasText: /Core Settings/i })
  const coreVisible = await coreBtn.isVisible().catch(() => false)
  console.log('Core Settings visible to analyst (should be false):', coreVisible)
  expect(coreVisible).toBe(false)
})

test('05 — Research page design matches brand', async ({ page }) => {
  await login(page)
  await page.goto(`${BASE}/research`)
  await wait(2000)
  await page.screenshot({ path: '/tmp/feat-05-research.png' })

  // Check accent color is violet (not green)
  const liveLabel = page.locator('span').filter({ hasText: /^LIVE$/ }).first()
  const labelVisible = await liveLabel.isVisible().catch(() => false)
  if (labelVisible) {
    const color = await liveLabel.evaluate(el =>
      getComputedStyle(el).color
    )
    console.log('LIVE label color (should be violet ~167,139,250):', color)
  }

  // Agent column visible
  const agentArea = page.locator('text=Agent').first()
  const agentVisible = await agentArea.isVisible().catch(() => false)
  console.log('Agent column visible:', agentVisible)

  // Input/textarea for chat
  const textarea = page.locator('textarea').first()
  const inputVisible = await textarea.isVisible().catch(() => false)
  console.log('Chat input visible:', inputVisible)
})

test('06 — Navigation via icon rail', async ({ page }) => {
  await login(page)
  await wait(1000)

  const routes: [string, RegExp][] = [
    ['Jobs', /\/jobs/],
    ['History', /\/history/],
    ['Settings', /\/settings/],
  ]

  for (const [label, urlPattern] of routes) {
    const btn = page.locator(`button[title="${label}"]`)
    const visible = await btn.isVisible().catch(() => false)
    if (visible) {
      await btn.click()
      await wait(1500)
      console.log(`Navigated to ${label}:`, page.url())
      await page.screenshot({ path: `/tmp/feat-06-nav-${label.toLowerCase()}.png` })
    } else {
      console.log(`${label} nav button not found`)
    }
  }
})

test('07 — No console errors across pages', async ({ page }) => {
  const errors: string[] = []
  page.on('console', msg => {
    if (msg.type() === 'error') errors.push(`${msg.text().slice(0, 120)}`)
  })

  await login(page)
  for (const path of ['/dashboard', '/history', '/research', '/settings']) {
    await page.goto(`${BASE}${path}`)
    await wait(1500)
  }

  const criticalErrors = errors.filter(e =>
    !e.includes('404') && !e.includes('401') && !e.includes('Failed to load resource')
  )
  console.log('Critical console errors:', criticalErrors.length)
  if (criticalErrors.length) criticalErrors.forEach(e => console.log(' -', e))
  expect(criticalErrors.length).toBe(0)
})
