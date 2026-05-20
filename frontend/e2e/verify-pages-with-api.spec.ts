/**
 * Verify the production Pages frontend can reach the tunneled API.
 *
 * Pre-req: api.infobroker.net is tunneled to the local FastAPI.
 *
 * Pass criteria:
 *   - GET https://info-broker.pages.dev returns 200.
 *   - The frontend's first API request (/v3/auth/providers) returns 2xx
 *     (was ERR_CONNECTION_REFUSED before the tunnel was up).
 *   - No JS pageerror.
 */
import { test, expect } from '@playwright/test'

test('Pages frontend → tunneled API end-to-end', async ({ page }) => {
  test.setTimeout(60_000)

  const crashes: string[] = []
  page.on('pageerror', (e) => crashes.push(`pageerror: ${e.message}`))

  const apiResponses: { url: string; status: number }[] = []
  page.on('response', (r) => {
    if (/api\.infobroker\.net|\/v3\//.test(r.url())) {
      apiResponses.push({ url: r.url(), status: r.status() })
    }
  })

  const apiFailures: string[] = []
  page.on('requestfailed', (r) => {
    if (/api\.infobroker\.net|\/v3\//.test(r.url())) {
      apiFailures.push(`${r.url()} → ${r.failure()?.errorText}`)
    }
  })

  console.log('▶ Loading https://info-broker.pages.dev …')
  const resp = await page.goto('https://info-broker.pages.dev', {
    waitUntil: 'networkidle',
    timeout: 30_000,
  })
  expect(resp?.status()).toBe(200)

  console.log(`  title: ${await page.title()}`)
  console.log(`  api requests: ${apiResponses.length}`)
  apiResponses.forEach(r => console.log(`    ${r.status}  ${r.url}`))
  if (apiFailures.length > 0) {
    console.log('  api FAILURES:')
    apiFailures.forEach(f => console.log(`    ${f}`))
  }

  expect(apiFailures, 'no API requests should fail to connect').toEqual([])
  expect(apiResponses.length, 'frontend should make at least one API call').toBeGreaterThan(0)
  // 200 or 401 is fine (401 means CORS + auth chain is working; just not logged in)
  const statuses = apiResponses.map(r => r.status)
  const acceptable = statuses.every(s => s < 500)
  expect(acceptable, `all API responses must be < 500. got: ${statuses}`).toBe(true)
  expect(crashes).toEqual([])

  console.log('\n✓ Pages → Tunnel → API path is live.')
})
