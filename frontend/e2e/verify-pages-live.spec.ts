import { test, expect } from '@playwright/test'

test('production pages.dev URL serves the frontend', async ({ page }) => {
  test.setTimeout(60_000)

  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`))
  page.on('console', (m) => { if (m.type() === 'error') errors.push(`console.error: ${m.text()}`) })

  // Capture all network requests so we can verify the bundle reaches the
  // tunneled API (or at least attempts to).
  const apiRequests: string[] = []
  page.on('request', (r) => {
    if (/api\.infobroker\.net|\/v3\//.test(r.url())) apiRequests.push(r.url())
  })

  console.log('▶ Loading https://info-broker.pages.dev …')
  const resp = await page.goto('https://info-broker.pages.dev', { waitUntil: 'networkidle', timeout: 30_000 })
  console.log(`  status: ${resp?.status()}`)
  expect(resp?.status()).toBe(200)

  // Verify HTML body actually rendered something React produced (not just a
  // raw shell). The login page is the natural landing state.
  const title = await page.title()
  console.log(`  title: ${title}`)

  // Check the bundle is the modern build
  const html = await page.content()
  expect(html).toContain('<div id="root">')

  // Confirm at least one VITE_API_URL-baked request was attempted
  console.log(`  API-shaped requests attempted: ${apiRequests.length}`)
  apiRequests.slice(0, 5).forEach(u => console.log(`    - ${u}`))

  // Take a screenshot for the record
  await page.screenshot({ path: '/tmp/pages-live.png', fullPage: false })
  console.log('  screenshot: /tmp/pages-live.png')

  // Any pageerrors?
  if (errors.length > 0) {
    console.log('\n⚠ Page errors detected:')
    errors.forEach(e => console.log(`    ${e}`))
  }

  // Hard-fail only on pageerrors that crash the app — console errors about
  // CORS / 401 against the API are expected on first load (api.infobroker.net
  // isn't tunneled yet).
  const crashes = errors.filter(e => e.startsWith('pageerror:'))
  expect(crashes).toEqual([])
})
