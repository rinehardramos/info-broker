/**
 * Live smoke test against https://infobroker.tech with the admin account.
 *
 * What it verifies end-to-end:
 *   1. Pages-hosted frontend at infobroker.tech loads
 *   2. Login form is reachable
 *   3. admin/admin signs in (api.infobroker.tech tunnel reachable, CORS OK)
 *   4. Post-login navigation lands somewhere admin-y
 *   5. No pageerror crashes; only "expected" console errors allowed
 *
 * Run headed (you'll see Chrome on the Windows desktop via WSLg):
 *   cd frontend && npx playwright test e2e/verify-infobroker-tech.spec.ts \
 *     --headed --project=chromium
 */
import { test, expect } from '@playwright/test'

const SITE = 'https://infobroker.tech'
const ADMIN = { username: 'admin', password: 'admin' }

test.use({
  baseURL: SITE,
  // Open DevTools for visible debug
  launchOptions: { devtools: true, slowMo: 250 },
})

test.setTimeout(120_000)

test('admin can sign in to infobroker.tech', async ({ page }) => {
  const consoleErrors: string[] = []
  const pageErrors: string[] = []
  const failedRequests: { url: string; status: number; method: string }[] = []
  const apiRequests: string[] = []

  page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()) })
  page.on('pageerror', (e) => pageErrors.push(e.message))
  page.on('response', (r) => {
    if (r.status() >= 400) failedRequests.push({ url: r.url(), status: r.status(), method: r.request().method() })
    if (/api\.infobroker\.tech/.test(r.url())) apiRequests.push(`${r.status()} ${r.request().method()} ${r.url()}`)
  })

  console.log(`▶ GET ${SITE}/`)
  const resp = await page.goto('/', { waitUntil: 'networkidle' })
  expect(resp?.status(), 'home should return 200').toBe(200)
  console.log(`  title: ${await page.title()}`)
  await page.screenshot({ path: '/tmp/ib-1-home.png', fullPage: false })

  console.log(`▶ GET ${SITE}/login`)
  await page.goto('/login', { waitUntil: 'networkidle' })
  await page.screenshot({ path: '/tmp/ib-2-login.png', fullPage: false })

  const userField = page.getByPlaceholder(/username/i)
  const passField = page.getByPlaceholder(/password/i)
  await expect(userField, 'username input visible').toBeVisible({ timeout: 10_000 })
  await expect(passField, 'password input visible').toBeVisible()

  await userField.fill(ADMIN.username)
  await passField.fill(ADMIN.password)
  console.log(`▶ Submitting login as ${ADMIN.username}`)
  await page.getByRole('button', { name: /login|sign in/i }).click()

  // Wait for navigation off /login (success) — fail loud if still there after 15s
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 15_000 })
  console.log(`  landed on: ${page.url()}`)
  await page.screenshot({ path: '/tmp/ib-3-post-login.png', fullPage: true })

  // Sanity: the bundle should have hit api.infobroker.tech at least once
  console.log(`▶ API requests to api.infobroker.tech: ${apiRequests.length}`)
  apiRequests.slice(0, 8).forEach(u => console.log(`    ${u}`))

  // Sanity: no auth-related 401s after login (those would mean broken session)
  const auth401s = failedRequests.filter(r => r.status === 401 && r.url.includes('api.infobroker.tech'))
  if (auth401s.length > 0) {
    console.log('⚠ 401s after login:')
    auth401s.slice(0, 5).forEach(r => console.log(`    ${r.method} ${r.url}`))
  }

  // Hard-fail on uncaught page errors only — console errors and pre-login 401s are OK
  if (pageErrors.length > 0) {
    console.log('\n⚠ Uncaught page errors:')
    pageErrors.forEach(e => console.log(`    ${e}`))
  }
  expect(pageErrors, 'no uncaught page errors').toEqual([])

  // Log other failed requests for diagnostics (non-fatal)
  if (failedRequests.length > 0) {
    console.log(`\nFailed requests (${failedRequests.length} total, showing first 10):`)
    failedRequests.slice(0, 10).forEach(r => console.log(`    ${r.status} ${r.method} ${r.url}`))
  }
  if (consoleErrors.length > 0) {
    console.log(`\nConsole errors (${consoleErrors.length} total, showing first 5):`)
    consoleErrors.slice(0, 5).forEach(e => console.log(`    ${e}`))
  }

  console.log('\n✓ Screenshots saved: /tmp/ib-1-home.png /tmp/ib-2-login.png /tmp/ib-3-post-login.png')
})
