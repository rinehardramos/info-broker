/**
 * Test: Pipeline-layer confirmation gate for identification queries
 * Run: cd frontend && npx playwright test e2e/confirm-gate.spec.ts --headed --project=chromium
 */
import { test, expect } from '@playwright/test'

const BASE = 'http://localhost:5173'
const wait = (ms: number) => new Promise(r => setTimeout(r, ms))

test.use({
  baseURL: BASE,
  viewport: { width: 1400, height: 900 },
  headless: false,
})

test.setTimeout(300_000)

async function login(page: any) {
  await page.goto(`${BASE}/`)
  await wait(1000)
  const loginVisible = await page.locator('input[type="password"]').isVisible().catch(() => false)
  if (loginVisible) {
    await page.fill('input[placeholder*="user" i], input[type="text"]', 'admin')
    await page.fill('input[type="password"]', 'admin')
    await page.locator('button[type="submit"], button:has-text("Login"), button:has-text("Sign in")').click()
    await wait(3000)
  }
}

test('confirmation gate: brain result held until user confirms', async ({ page }) => {
  const errors: string[] = []
  page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()) })

  await login(page)
  await page.screenshot({ path: '/tmp/cg-01-main.png' })

  // Submit spiderman query
  const textarea = page.locator('textarea').first()
  await expect(textarea).toBeVisible({ timeout: 5000 })
  await wait(2000)
  await textarea.fill('new series with girl in spiderman where man has a shotgun')
  await page.keyboard.press('Enter')
  console.log('Query submitted')

  // Answer PreFlight
  await page.waitForSelector('text=Where did you see or hear', { timeout: 15000 })
  console.log('PreFlight appeared')
  await page.screenshot({ path: '/tmp/cg-02-preflight.png' })

  const youtube = page.locator('button:has-text("YouTube"), [role="button"]:has-text("YouTube")').first()
  if (await youtube.isVisible()) await youtube.click()
  else {
    const inp = page.locator('input[placeholder*="answer"], input[placeholder*="type"]').first()
    if (await inp.isVisible()) { await inp.fill('YouTube'); await page.locator('button:has-text("Send")').click() }
  }
  await wait(2000)

  const adBtn = page.locator('button:has-text("An ad"), [role="button"]:has-text("ad")').first()
  if (await adBtn.isVisible()) await adBtn.click()
  console.log('Answered: YouTube → An ad')

  // Wait for brain to complete and confirmation card to appear (up to 4 min)
  console.log('Waiting for confirmation card (up to 4 min)...')
  const confirmCard = page.locator('text=RESULT FOUND — PLEASE CONFIRM').first()

  let confirmed = false
  for (let i = 0; i < 48; i++) {
    await wait(5000)
    const visible = await confirmCard.isVisible().catch(() => false)
    if (visible) {
      confirmed = true
      console.log(`Confirmation card appeared after ~${(i + 1) * 5}s`)
      break
    }
    if (i % 6 === 5) {
      await page.screenshot({ path: `/tmp/cg-wait-${i}.png` })
      console.log(`Still waiting... ${(i + 1) * 5}s elapsed`)
    }
  }

  await page.screenshot({ path: '/tmp/cg-03-confirm-card.png' })

  if (confirmed) {
    // Verify the card content
    const yesBtn    = await page.locator('button:has-text("Yes, that\'s it")').first().isVisible().catch(() => false)
    const noBtn     = await page.locator('button:has-text("No, try another")').first().isVisible().catch(() => false)
    const unsureBtn = await page.locator('button:has-text("Not sure")').first().isVisible().catch(() => false)
    console.log('Yes button:', yesBtn, '| No button:', noBtn, '| Not sure button:', unsureBtn)

    expect(yesBtn, 'Yes button should be visible').toBe(true)
    expect(noBtn, 'No button should be visible').toBe(true)

    // Click "No, try another" to test rejection flow
    if (noBtn) {
      await page.locator('button:has-text("No, try another")').first().click()
      console.log('Clicked "No, try another"')
      await wait(3000)
      await page.screenshot({ path: '/tmp/cg-04-after-rejection.png' })

      // Brain should re-run with rejected candidates
      const liveRunning = await page.locator('text=researching').first().isVisible().catch(() => false)
      console.log('Brain re-running after rejection:', liveRunning)
    }
  } else {
    console.log('Confirmation card did not appear in 4 min — brain may still be running')
    await page.screenshot({ path: '/tmp/cg-03-no-card.png' })
  }

  if (errors.length) console.log('Console errors:', errors.slice(0, 3))

  expect(confirmed, 'Confirmation card should appear before result is delivered').toBe(true)
})
