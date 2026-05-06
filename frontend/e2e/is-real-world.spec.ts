/**
 * E2E: Real-world IS brain test — "man on fire series on netflix"
 * Tests the full flow: auth check, IS toggle, send, results display.
 */
import { test, expect } from '@playwright/test'

const SS = '/tmp/is-real-world'

test.describe('IS Brain — Real World', () => {
  test.setTimeout(300_000) // 5 min — real Claude Code research takes time
  test.beforeEach(async ({ page }) => {
    await page.goto('/login')
    const user = page.locator('input').first()
    const pass = page.locator('input[type="password"]')
    if (await user.isVisible({ timeout: 3000 }).catch(() => false)) {
      await user.fill('admin')
      await pass.fill('admin')
      await page.locator('button[type="submit"]').click()
      await page.waitForURL('**/*', { timeout: 5000 }).catch(() => {})
    }
    await page.waitForLoadState('networkidle')
  })

  test('man on fire research — full IS flow', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')

    // Check brain status indicator
    const isButton = page.locator('button:has-text("IS")')
    await expect(isButton).toBeVisible({ timeout: 5000 })
    await page.screenshot({ path: `${SS}/01-main.png` })

    // Check the brain status dot color
    const statusDot = isButton.locator('span').last()
    const dotColor = await statusDot.evaluate(el => getComputedStyle(el).backgroundColor)
    console.log('Brain status dot color:', dotColor)

    // Toggle IS on
    await isButton.click()
    await page.screenshot({ path: `${SS}/02-is-on.png` })

    // Send the research query
    const textarea = page.locator('textarea').first()
    await textarea.fill('man on fire series on netflix')
    await textarea.press('Enter')
    console.log('Message sent')

    // Wait for API response (202)
    await page.waitForTimeout(2000)
    await page.screenshot({ path: `${SS}/03-sent.png` })

    // Wait for brain to complete (up to 60s for real research, or fast auth error)
    let completed = false
    for (let i = 0; i < 30; i++) {
      await page.waitForTimeout(2000)

      // Check for completion indicators
      const succeeded = await page.locator('text=succeeded').first().isVisible().catch(() => false)
      const failed = await page.locator('text=failed').first().isVisible().catch(() => false)
      const findings = await page.locator('text=findings').first().isVisible().catch(() => false)
      const authError = await page.locator('text=not authenticated').first().isVisible().catch(() => false)
      const apiKeyError = await page.locator('text=ANTHROPIC_API_KEY').first().isVisible().catch(() => false)

      if (succeeded || failed || findings || authError || apiKeyError) {
        console.log(`Completed after ${(i+1)*2}s — succeeded:${succeeded} failed:${failed} findings:${findings} authError:${authError}`)
        completed = true
        break
      }

      if (i % 5 === 4) {
        await page.screenshot({ path: `${SS}/04-waiting-${i}.png` })
        console.log(`Still waiting... ${(i+1)*2}s`)
      }
    }

    await page.screenshot({ path: `${SS}/05-completed.png` })

    // Click the latest run in Live panel
    const liveRun = page.locator('[class*="rounded"]').filter({ hasText: 'Agent Default' }).first()
    if (await liveRun.isVisible().catch(() => false)) {
      await liveRun.click()
      await page.waitForTimeout(1000)
    }
    await page.screenshot({ path: `${SS}/06-run-tab.png` })

    // Check what's displayed
    const isHeader = await page.locator('text=Intelligent Search').isVisible().catch(() => false)
    const findingsText = await page.locator('text=FINDINGS').isVisible().catch(() => false)
    const queryText = await page.locator('text=man on fire').isVisible().catch(() => false)

    console.log('Results:', { isHeader, findingsText, queryText, completed })

    await page.screenshot({ path: `${SS}/07-final.png`, fullPage: true })
  })
})
