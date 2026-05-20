
import { test, chromium } from '@playwright/test'
import * as os from 'node:os'
import * as path from 'node:path'

const USER_DATA_DIR = path.join(os.homedir(), '.cache', 'pw-gcp-bootstrap')
const PROJECT_IDS = [
  'symmetric-core-496513-d4',
  'strategic-guru-496513-v9',
  'regal-elf-496513-r0',
  'decoded-shadow-496513-n5',
  'infobroker-496513',
]

test('find OAuth client across infobroker projects', async () => {
  test.setTimeout(5 * 60 * 1000)
  const ctx = await chromium.launchPersistentContext(USER_DATA_DIR, {
    channel: 'chrome', headless: false, viewport: { width: 1440, height: 900 },
  })
  const page = ctx.pages()[0] ?? await ctx.newPage()

  for (const pid of PROJECT_IDS) {
    await page.goto('https://console.cloud.google.com/auth/clients?project=' + pid, { waitUntil: 'domcontentloaded' })
    await page.waitForLoadState('networkidle', { timeout: 20_000 }).catch(() => null)
    await page.waitForTimeout(2500)
    const noneVisible = await page.locator('text=/no OAuth clients to display|no clients/i').first().isVisible().catch(() => false)
    // Look for any client_id-shaped text on the page
    const body = await page.locator('body').innerText()
    const ids = Array.from(body.matchAll(/\b\d{8,}-[a-z0-9]+\.apps\.googleusercontent\.com\b/g)).map(m => m[0])
    console.log(`[${pid}]  none=${noneVisible}  ids=${JSON.stringify(ids)}`)
  }

  await page.waitForTimeout(10_000)
  await ctx.close()
})
