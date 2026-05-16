/**
 * Capture screenshots of the current state of the latest run.
 * Helps diagnose "result is in JSON" + "tasks running but inactive" reports.
 */
import { test, Page } from '@playwright/test'
import { writeFileSync } from 'node:fs'

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

test('screenshot what user sees', async ({ page }) => {
  test.setTimeout(60_000)
  await login(page)
  await page.goto(`${BASE}/runs`)
  await page.waitForTimeout(3000)
  await page.screenshot({ path: '/tmp/01-runs-page.png', fullPage: false })

  // Click first View button
  const view = page.getByRole('button', { name: /^view$/i }).first()
  await view.click()
  await page.waitForTimeout(5000)
  await page.screenshot({ path: '/tmp/02-run-detail.png', fullPage: false })

  // Click a card to open modal
  const card = page.locator('[data-slot="node-result-card"]').first()
  if (await card.isVisible({ timeout: 2000 }).catch(() => false)) {
    await card.click()
    await page.waitForTimeout(2500)
    await page.screenshot({ path: '/tmp/03-modal-default.png', fullPage: false })

    // Try each tab
    for (const tabName of ['Formatted', 'Input', 'Hypothesis', 'Sources', 'Timing', 'Raw']) {
      const tab = page.getByRole('tab', { name: new RegExp(tabName, 'i') })
      if (await tab.isVisible({ timeout: 500 }).catch(() => false)) {
        await tab.click()
        await page.waitForTimeout(800)
        await page.screenshot({ path: `/tmp/04-modal-${tabName.toLowerCase()}.png`, fullPage: false })
      }
    }
  }

  console.log('screenshots written to /tmp/0*.png')
})
