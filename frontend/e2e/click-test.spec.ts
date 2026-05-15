import { test, Page, expect } from '@playwright/test'

const BASE = 'http://localhost:5173'

async function login(page: Page) {
  await page.goto(`${BASE}/login`)
  const v = await page.locator('input[type="password"]').first().isVisible({ timeout: 2000 }).catch(() => false)
  if (v) {
    await page.fill('input[type="text"], input[type="email"]', 'admin')
    await page.fill('input[type="password"]', 'admin')
    await page.locator('button[type="submit"]').first().click()
    await page.waitForURL(/\/$|\/research|\/jobs/, { timeout: 8_000 })
  }
}

test('clicking a finding card opens the modal', async ({ page }) => {
  test.setTimeout(60_000)
  await login(page)
  await page.goto(`${BASE}/runs`)
  await page.waitForTimeout(2500)
  const view = page.getByRole('button', { name: /^view$/i }).first()
  await view.click()
  await page.waitForTimeout(4000)

  const cardCount = await page.locator('[data-slot="node-result-card"]').count()
  console.log('cards in DOM:', cardCount)

  // Try clicking on the card body (not the link)
  const firstCard = page.locator('[data-slot="node-result-card"]').first()
  await firstCard.scrollIntoViewIfNeeded()
  await firstCard.click({ timeout: 5000 })
  await page.waitForTimeout(1500)

  const modalOpen = await page.locator('[role="dialog"]').isVisible({ timeout: 1000 }).catch(() => false)
  console.log('modal opened after click:', modalOpen)

  // Try clicking specifically on the title text
  if (!modalOpen) {
    const title = firstCard.locator('div').filter({ hasText: /react|vue|angular|svelte/i }).first()
    await title.click({ timeout: 3000 }).catch(() => {})
    await page.waitForTimeout(1500)
    const modalAfter = await page.locator('[role="dialog"]').isVisible({ timeout: 1000 }).catch(() => false)
    console.log('modal opened after title click:', modalAfter)
  }
})
