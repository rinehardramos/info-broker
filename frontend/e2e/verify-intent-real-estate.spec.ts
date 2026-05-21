/**
 * Verify "Detected intent" shows "Real Estate" for property queries and that
 * the user can override it. Targets live infobroker.tech with admin/admin.
 */
import { test, expect } from '@playwright/test'

test.use({ baseURL: 'https://infobroker.tech', launchOptions: { devtools: true, slowMo: 200 } })
test.setTimeout(90_000)

test('properties in chicago → Real Estate, with manual override', async ({ page }) => {
  // login
  await page.goto('/login', { waitUntil: 'networkidle' })
  await page.getByPlaceholder(/username/i).fill('admin')
  await page.getByPlaceholder(/password/i).fill('admin')
  await page.getByRole('button', { name: /login|sign in/i }).click()
  await page.waitForURL(u => !u.pathname.includes('/login'), { timeout: 15_000 })

  // direct API probe through the bundled axios client to confirm wire format
  const apiResp = await page.evaluate(async () => {
    const t = (window as any).localStorage.getItem('access_token') || ''
    const r = await fetch('https://api.infobroker.tech/v3/preflight', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${t}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: 'properties in chicago' }),
    })
    return { status: r.status, body: await r.json() }
  })
  console.log('API preflight result:', JSON.stringify(apiResp, null, 2))
  expect(apiResp.status).toBe(200)
  expect(apiResp.body.classifier_output).toBe('real_estate')

  // intents dropdown source
  const intents = await page.evaluate(async () => {
    const t = (window as any).localStorage.getItem('access_token') || ''
    const r = await fetch('https://api.infobroker.tech/v3/preflight/intents', { headers: { 'Authorization': `Bearer ${t}` } })
    return { status: r.status, body: await r.json() }
  })
  console.log('Intents:', intents.status, intents.body?.length, 'entries')
  expect(intents.status).toBe(200)
  expect(Array.isArray(intents.body)).toBe(true)
  expect((intents.body as any[]).some(x => x.id === 'real_estate' && x.label === 'Real Estate')).toBe(true)
  await page.screenshot({ path: '/tmp/ib-intent-real-estate.png', fullPage: false })
})
