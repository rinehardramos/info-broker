import { test } from '@playwright/test'

const BASE = 'http://localhost:5173'
const wait = (ms: number) => new Promise<void>(r => setTimeout(r, ms))

test.use({ headless: false, viewport: { width: 1440, height: 900 } })
test.setTimeout(60_000)

test('diagnose UI errors', async ({ page }) => {
  const consoleErrors: string[] = []
  const networkErrors: string[] = []

  page.on('console', msg => {
    if (msg.type() === 'error') consoleErrors.push(msg.text())
  })
  page.on('response', res => {
    if (res.status() >= 400) networkErrors.push(`${res.status()} ${res.url()}`)
  })

  await page.goto(BASE)
  await wait(2500)
  await page.screenshot({ path: '/tmp/e2e-01-landing.png' })

  const errorOverlay = await page.evaluate(() => {
    const ov = document.querySelector('vite-error-overlay')
    if (!ov) return null
    const root = (ov as any).shadowRoot
    return root?.querySelector('.message-body')?.textContent
      ?? root?.querySelector('pre')?.textContent
      ?? 'overlay present'
  }).catch(() => null)
  console.log('VITE OVERLAY:', errorOverlay ?? 'none')

  const hasPassword = await page.locator('input[type="password"]').isVisible().catch(() => false)
  if (hasPassword) {
    await page.locator('input[type="text"]').first().fill('admin')
    await page.locator('input[type="password"]').fill('admin')
    await page.locator('button[type="submit"]').click()
    await wait(3000)
  }
  await page.screenshot({ path: '/tmp/e2e-02-logged-in.png' })

  const bgColor = await page.evaluate(() => getComputedStyle(document.body).backgroundColor)
  console.log('Body bg:', bgColor)

  await page.goto(`${BASE}/dashboard`)
  await wait(2000)
  await page.screenshot({ path: '/tmp/e2e-03-dashboard.png' })

  const dashOverlay = await page.evaluate(() => {
    const ov = document.querySelector('vite-error-overlay')
    if (!ov) return null
    const root = (ov as any).shadowRoot
    return root?.querySelector('.message-body')?.textContent ?? 'overlay present'
  }).catch(() => null)
  console.log('DASHBOARD OVERLAY:', dashOverlay ?? 'none')

  console.log('CONSOLE ERRORS:')
  if (!consoleErrors.length) console.log(' none')
  consoleErrors.forEach(e => console.log(' -', e))

  console.log('NETWORK ERRORS:')
  const netFiltered = networkErrors.filter(e => !e.includes('favicon'))
  if (!netFiltered.length) console.log(' none')
  netFiltered.slice(0, 20).forEach(e => console.log(' -', e))
})
