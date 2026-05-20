import { test, type Page } from '@playwright/test'

const BASE = 'http://localhost:5173'
const wait = (ms: number) => new Promise(r => setTimeout(r, ms))

async function login(page: Page) {
  await page.goto(`${BASE}/login`)
  await wait(1000)
  const pw = page.locator('input[type="password"]').first()
  if (await pw.isVisible({ timeout: 2000 }).catch(() => false)) {
    await page.fill('input[type="text"], input[type="email"]', 'admin')
    await pw.fill('admin')
    await page.locator('button[type="submit"]').first().click()
    await page.waitForURL(/\/$|\/research|\/runs|\/dashboard/, { timeout: 8_000 })
  }
}

test('mode picker — fetch /v3/modes and select', async ({ page }) => {
  test.setTimeout(60_000)
  page.on('pageerror', (e) => console.log(`pageerror: ${e.message}`))

  console.log('\n── ModePicker demo ──')
  await login(page)
  await page.goto(`${BASE}/research`)
  await wait(3000)

  // Mode label should be visible
  const modeLabel = page.locator('text=/^Mode$/i').first()
  console.log('Mode label visible:', await modeLabel.isVisible({ timeout: 5000 }).catch(() => false))

  // Each launch Mode should render as a button
  for (const label of ['General research', 'KYC / Enhanced Due Diligence', 'Competitive intelligence', 'Lead generation']) {
    const btn = page.locator(`button:has-text("${label}")`).first()
    const ok = await btn.isVisible({ timeout: 2000 }).catch(() => false)
    console.log(`  ${ok ? '✓' : '✗'}  ${label}`)
  }

  // Click KYC
  const kyc = page.locator('button:has-text("KYC / Enhanced Due Diligence")').first()
  if (await kyc.isVisible({ timeout: 2000 }).catch(() => false)) {
    await kyc.click()
    await wait(500)
    console.log('Clicked KYC mode — selection should persist.')
  }

  await wait(5000)
})

test('mode picker — selection persists across reloads', async ({ page }) => {
  test.setTimeout(60_000)
  await login(page)
  await page.goto(`${BASE}/research`)
  await wait(2500)

  // Select competitive intel
  await page.locator('button:has-text("Competitive intelligence")').first().click()
  await wait(400)

  // Hard reload
  await page.reload()
  await wait(3000)

  // Competitive intel should still be the active pill (accent border)
  // Verify the persisted value via JS evaluation of localStorage
  const stored = await page.evaluate(() => localStorage.getItem('info-broker.mode'))
  console.log('persisted store:', stored)
  if (stored && JSON.parse(stored).state.modeId === 'competitive_intel') {
    console.log('✓ selection persisted')
  } else {
    console.log('✗ persistence failed:', stored)
  }
  await wait(2000)
})
