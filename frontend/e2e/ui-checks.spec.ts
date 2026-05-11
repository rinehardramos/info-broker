/**
 * UI checks: textarea size, no Goal button, history items restore chat
 */
import { test, expect } from '@playwright/test'

const BASE = 'http://localhost:5173'
const wait = (ms: number) => new Promise(r => setTimeout(r, ms))

test.use({ baseURL: BASE, viewport: { width: 1400, height: 900 }, headless: false })
test.setTimeout(60_000)

async function login(page: any) {
  await page.goto(`${BASE}/`)
  await wait(1000)
  if (await page.locator('input[type="password"]').isVisible().catch(() => false)) {
    await page.fill('input[placeholder*="user" i], input[type="text"]', 'admin')
    await page.fill('input[type="password"]', 'admin')
    await page.locator('button[type="submit"], button:has-text("Sign in")').click()
    await wait(3000)
  }
}

test('textarea is larger and Goal button is gone', async ({ page }) => {
  await login(page)
  await page.screenshot({ path: '/tmp/ui-01-main.png' })

  const textarea = page.locator('textarea').first()
  await expect(textarea).toBeVisible({ timeout: 5000 })

  const box = await textarea.boundingBox()
  console.log('Textarea bounding box:', box)
  expect(box!.height, 'Textarea should be taller than 60px (rows=4)').toBeGreaterThan(60)

  const goalBtn = await page.locator('button:has-text("Goal")').isVisible().catch(() => false)
  console.log('Goal button visible:', goalBtn)
  expect(goalBtn, 'Goal button should be removed from below textarea').toBe(false)

  await page.screenshot({ path: '/tmp/ui-02-textarea.png' })
})

test('history items restore chat messages', async ({ page }) => {
  await login(page)

  // Find a history item and click it
  const historyItem = page.locator('text=HISTORY').locator('..').locator('button').first()
  const historyVisible = await historyItem.isVisible().catch(() => false)

  if (!historyVisible) {
    console.log('No history items found — skipping restore test')
    return
  }

  const historyText = await historyItem.textContent()
  console.log('Clicking history item:', historyText?.trim().slice(0, 50))

  await historyItem.click()
  await wait(2000)
  await page.screenshot({ path: '/tmp/ui-03-history-restored.png' })

  // Chat should have messages after restoring
  const messages = await page.locator('.flex.justify-end, .flex.justify-start').count()
  console.log('Messages in chat after restore:', messages)

  // At minimum: the session ID should be set (no "Ask anything" placeholder)
  const placeholder = await page.locator('text=Ask anything').isVisible().catch(() => false)
  console.log('Placeholder still showing:', placeholder)

  expect(messages > 0 || !placeholder, 'History restore should populate chat').toBe(true)
})
