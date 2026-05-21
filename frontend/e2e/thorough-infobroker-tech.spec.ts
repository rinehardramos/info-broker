/**
 * Thorough e2e sweep of https://infobroker.tech as admin/admin.
 *
 * For every route we:
 *   - Navigate, wait for networkidle
 *   - Screenshot (full page)
 *   - Capture: uncaught page errors, console errors, 4xx/5xx network responses
 *   - Move on (no expects per-route — we want maximum coverage, not early exit)
 *
 * Output a structured JSON report at /tmp/ib-thorough-report.json so the
 * follow-up step (filing GitHub tickets) can iterate it deterministically.
 *
 * Run:
 *   cd frontend && npx playwright test e2e/thorough-infobroker-tech.spec.ts \
 *     --headed --project=chromium --reporter=line
 */
import { test, expect } from '@playwright/test'
import { writeFileSync, mkdirSync } from 'fs'

const SITE = 'https://infobroker.tech'
const API = 'https://api.infobroker.tech'
const ADMIN = { username: 'admin', password: 'admin' }

// Each entry: [path, descriptive_name, admin_only?]
const ROUTES: Array<[string, string, boolean]> = [
  ['/', 'Dashboard (root)', false],
  ['/dashboard', 'Dashboard', false],
  ['/research', 'Research', false],
  ['/runs', 'Runs', false],
  ['/monitors', 'Monitors', false],
  ['/wallet', 'Wallet', false],
  ['/linkedin', 'LinkedIn', false],
  ['/plugins', 'Plugins', false],
  ['/pipelines', 'Pipelines', false],
  ['/settings', 'Settings', false],
  ['/knowledge', 'KnowledgeGraph', false],
  ['/performance', 'Performance', false],
  ['/admin/processes', 'AdminProcesses', true],
  ['/admin/users', 'AdminUsers', true],
]

type Bug = {
  route: string
  page_name: string
  type: 'pageerror' | 'console_error' | 'http_error' | 'navigation_failed'
  detail: string
  evidence?: string
}

test.use({
  baseURL: SITE,
  launchOptions: { devtools: true, slowMo: 200 },
})

test.setTimeout(15 * 60 * 1000)

test('thorough sweep of infobroker.tech as admin', async ({ page }) => {
  mkdirSync('/tmp/ib-sweep', { recursive: true })
  const bugs: Bug[] = []

  // ── Login first ──────────────────────────────────────────────────────────
  console.log(`\n▶ Login as ${ADMIN.username}`)
  await page.goto('/login', { waitUntil: 'networkidle' })
  await page.getByPlaceholder(/username/i).fill(ADMIN.username)
  await page.getByPlaceholder(/password/i).fill(ADMIN.password)
  await page.getByRole('button', { name: /login|sign in/i }).click()
  try {
    await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 15_000 })
    console.log(`  ✓ landed on ${page.url()}`)
  } catch {
    bugs.push({
      route: '/login',
      page_name: 'Login',
      type: 'navigation_failed',
      detail: `Did not navigate off /login within 15s. Final URL: ${page.url()}`,
    })
    // Cannot continue without auth
    writeFileSync('/tmp/ib-thorough-report.json', JSON.stringify({ bugs, fatal: 'login' }, null, 2))
    throw new Error('Login failed — cannot proceed with authenticated sweep')
  }

  // ── Route sweep ──────────────────────────────────────────────────────────
  for (const [path, name, adminOnly] of ROUTES) {
    console.log(`\n▶ ${name}  (${path}${adminOnly ? ', admin-only' : ''})`)

    // Per-route listeners (reset each route so we can attribute correctly)
    const consoleErrs: string[] = []
    const pageErrs: string[] = []
    const httpErrs: Array<{ method: string; url: string; status: number }> = []

    const onConsole = (m: any) => { if (m.type() === 'error') consoleErrs.push(m.text()) }
    const onPageErr = (e: any) => pageErrs.push(e.message)
    const onResp = (r: any) => {
      const u = r.url()
      // Only track our own API errors; ignore third-party (Google GSI, etc.)
      if (r.status() >= 400 && (u.includes(API) || u.includes('localhost'))) {
        httpErrs.push({ method: r.request().method(), url: u, status: r.status() })
      }
    }
    page.on('console', onConsole)
    page.on('pageerror', onPageErr)
    page.on('response', onResp)

    try {
      const resp = await page.goto(path, { waitUntil: 'networkidle', timeout: 30_000 })
      const status = resp?.status() ?? 0
      console.log(`  HTTP ${status}, URL: ${page.url()}`)
      if (status >= 400) {
        bugs.push({ route: path, page_name: name, type: 'http_error', detail: `Page returned ${status}` })
      }
      // Give the page another 2s for late-firing XHR/WebSocket
      await page.waitForTimeout(2000)
      const slug = name.replace(/[^a-zA-Z0-9]/g, '-')
      const screenshotPath = `/tmp/ib-sweep/${slug}.png`
      await page.screenshot({ path: screenshotPath, fullPage: true })
    } catch (e: any) {
      bugs.push({
        route: path,
        page_name: name,
        type: 'navigation_failed',
        detail: e.message?.split('\n')[0] ?? String(e),
      })
    }

    // Record findings for this route
    for (const e of pageErrs) {
      bugs.push({ route: path, page_name: name, type: 'pageerror', detail: e })
    }
    for (const e of consoleErrs) {
      // Skip noise we know is environmental, not a bug
      if (/GSI_LOGGER|google\.com\/gsi|Provider's accounts list is empty|Not signed in with the identity provider|FedCM/.test(e)) continue
      if (e.includes('Failed to load resource: the server responded with a status of 403') && consoleErrs.some(x => x.includes('GSI_LOGGER'))) continue
      bugs.push({ route: path, page_name: name, type: 'console_error', detail: e })
    }
    for (const h of httpErrs) {
      // Skip "expected" pre-login 401s (we're post-login here, so these matter)
      bugs.push({
        route: path,
        page_name: name,
        type: 'http_error',
        detail: `${h.status} ${h.method} ${h.url}`,
      })
    }

    console.log(`  bugs collected on this route: ${pageErrs.length} pageerror, ${consoleErrs.length} console, ${httpErrs.length} http`)

    page.off('console', onConsole)
    page.off('pageerror', onPageErr)
    page.off('response', onResp)
  }

  // ── Final report ────────────────────────────────────────────────────────
  console.log(`\n══════════════════════════════════════════════`)
  console.log(`SWEEP COMPLETE — ${bugs.length} findings`)
  console.log(`══════════════════════════════════════════════`)

  // Dedupe — same (route, type, first-100-chars-of-detail) is one bug
  const seen = new Set<string>()
  const uniqueBugs: Bug[] = []
  for (const b of bugs) {
    const key = `${b.route}|${b.type}|${b.detail.slice(0, 100)}`
    if (!seen.has(key)) { seen.add(key); uniqueBugs.push(b) }
  }
  console.log(`Distinct (route+type+detail): ${uniqueBugs.length}`)

  writeFileSync('/tmp/ib-thorough-report.json', JSON.stringify({
    site: SITE,
    api: API,
    user: ADMIN.username,
    timestamp: new Date().toISOString(),
    routes_checked: ROUTES.length,
    bugs_total: bugs.length,
    bugs_distinct: uniqueBugs.length,
    bugs: uniqueBugs,
  }, null, 2))
  console.log(`Report: /tmp/ib-thorough-report.json`)
  console.log(`Screenshots: /tmp/ib-sweep/*.png`)

  // Non-fatal — we want full report, not first-failure exit
  expect(true).toBe(true)
})
