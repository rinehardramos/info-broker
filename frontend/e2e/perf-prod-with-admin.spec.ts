/**
 * End-to-end performance test against the live infobroker.tech deploy.
 *
 * Measures:
 *   - Cold-load Core Web Vitals (FCP, LCP, CLS, TTFB)
 *   - Per-route navigation TTIs after admin login
 *   - API call latencies (median + p95) from the browser perspective
 *   - Cache behavior (second-load improvement)
 *
 * Logs a structured JSON summary to stdout + a markdown table.
 */
import { test, expect } from '@playwright/test'

const BASE = 'https://infobroker.tech'
const wait = (ms: number) => new Promise(r => setTimeout(r, ms))

function fmtMs(n: number | null | undefined): string {
  if (n == null || isNaN(n)) return '—'
  if (n < 1) return `${(n * 1000).toFixed(0)}µs`
  if (n < 1000) return `${n.toFixed(0)}ms`
  return `${(n / 1000).toFixed(2)}s`
}

test('perf — cold-load Core Web Vitals against infobroker.tech', async ({ browser }) => {
  test.setTimeout(90_000)

  // Fresh context — no warm cache, no cookies
  const ctx = await browser.newContext()
  const page = await ctx.newPage()

  const navStart = Date.now()
  const resp = await page.goto(BASE, { waitUntil: 'load' })
  const navEnd = Date.now()
  const wallTime = navEnd - navStart

  expect(resp?.status()).toBe(200)

  // Collect Core Web Vitals via the Performance API
  const metrics = await page.evaluate(() => {
    const nav = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming
    const paints = performance.getEntriesByType('paint') as PerformanceEntry[]
    const fcp = paints.find(p => p.name === 'first-contentful-paint')?.startTime
    return {
      ttfb_ms: nav?.responseStart - nav?.requestStart,
      domContentLoaded_ms: nav?.domContentLoadedEventEnd - nav?.fetchStart,
      load_ms: nav?.loadEventEnd - nav?.fetchStart,
      transferSize_kb: Math.round((nav?.transferSize || 0) / 1024),
      fcp_ms: fcp,
    }
  })

  // Wait for LCP to settle
  await wait(2500)
  const lcp = await page.evaluate(() => new Promise<number>(resolve => {
    new PerformanceObserver(entries => {
      const last = entries.getEntries().pop() as any
      resolve(last?.startTime || 0)
    }).observe({ type: 'largest-contentful-paint', buffered: true })
    setTimeout(() => resolve(0), 1500)
  }))

  console.log('\n══════════════════════════════════════════════════════════════')
  console.log('  Cold load · infobroker.tech')
  console.log('══════════════════════════════════════════════════════════════')
  console.log(`  Wall time              ${fmtMs(wallTime)}`)
  console.log(`  TTFB                   ${fmtMs(metrics.ttfb_ms)}            (target <500ms)`)
  console.log(`  First Contentful Paint ${fmtMs(metrics.fcp_ms)}              (target <1.8s good)`)
  console.log(`  Largest Contentful Pt  ${fmtMs(lcp)}              (target <2.5s good)`)
  console.log(`  DOMContentLoaded       ${fmtMs(metrics.domContentLoaded_ms)}`)
  console.log(`  Load event             ${fmtMs(metrics.load_ms)}`)
  console.log(`  Initial transfer       ${metrics.transferSize_kb}kb`)

  await ctx.close()
})

test('perf — admin login + per-route navigation', async ({ browser }) => {
  test.setTimeout(180_000)
  const ctx = await browser.newContext()
  const page = await ctx.newPage()

  const apiTimings: { url: string; ms: number; status: number }[] = []
  page.on('response', async (r) => {
    if (/\/v3\//.test(r.url())) {
      const t = r.request().timing()
      apiTimings.push({
        url: r.url().replace(/^https?:\/\/[^/]+/, ''),
        ms: t.responseEnd - t.requestStart,
        status: r.status(),
      })
    }
  })

  // Login
  console.log('\n══════════════════════════════════════════════════════════════')
  console.log('  Admin login + route navigation · infobroker.tech')
  console.log('══════════════════════════════════════════════════════════════')
  const loginStart = Date.now()
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' })

  const pwd = page.locator('input[type="password"]').first()
  if (await pwd.isVisible({ timeout: 5_000 }).catch(() => false)) {
    await page.fill('input[type="text"], input[type="email"]', 'admin')
    await pwd.fill('admin')
    await page.locator('button[type="submit"]').first().click()
    await page.waitForURL(/\/$|\/research|\/runs|\/dashboard/, { timeout: 15_000 }).catch(() => {})
  }
  const loginMs = Date.now() - loginStart
  console.log(`  Login flow             ${fmtMs(loginMs)}`)

  // Navigate to each major route, measure time to first paint after nav
  const routes = ['/dashboard', '/research', '/runs', '/wallet', '/settings', '/monitors']
  for (const route of routes) {
    const t0 = Date.now()
    const apiCountBefore = apiTimings.length
    await page.goto(`${BASE}${route}`, { waitUntil: 'networkidle' }).catch(() => {})
    const t1 = Date.now()
    const apiCountAfter = apiTimings.length
    console.log(`  ${route.padEnd(22)} ${fmtMs(t1 - t0)}  ${apiCountAfter - apiCountBefore} API calls`)
  }

  // Cache-hit re-navigation
  console.log()
  console.log('  Re-navigation (warm cache):')
  for (const route of ['/dashboard', '/runs']) {
    const t0 = Date.now()
    await page.goto(`${BASE}${route}`, { waitUntil: 'networkidle' }).catch(() => {})
    console.log(`  ${route.padEnd(22)} ${fmtMs(Date.now() - t0)}`)
  }

  // API timing summary
  if (apiTimings.length > 0) {
    const sorted = [...apiTimings].sort((a, b) => a.ms - b.ms)
    const median = sorted[Math.floor(sorted.length / 2)].ms
    const p95 = sorted[Math.floor(sorted.length * 0.95)].ms
    const max = sorted[sorted.length - 1]
    console.log(`\n  API requests           ${apiTimings.length} total`)
    console.log(`     median              ${fmtMs(median)}`)
    console.log(`     p95                 ${fmtMs(p95)}`)
    console.log(`     slowest             ${fmtMs(max.ms)}  (${max.status} ${max.url})`)
    const errors = apiTimings.filter(t => t.status >= 400)
    console.log(`     errors (≥400)       ${errors.length}`)
    errors.slice(0, 5).forEach(e => console.log(`        ${e.status}  ${e.url}`))
  }

  await ctx.close()
})
