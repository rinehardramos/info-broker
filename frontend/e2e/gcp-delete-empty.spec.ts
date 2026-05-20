
import { test, chromium } from '@playwright/test'
import * as os from 'node:os'
import * as path from 'node:path'

const USER_DATA_DIR = path.join(os.homedir(), '.cache', 'pw-gcp-bootstrap')
// Keep regal-elf-496513-r0. Delete the other 4.
const TO_DELETE = [
  'symmetric-core-496513-d4',
  'strategic-guru-496513-v9',
  '[REDACTED:high-entropy-base64:24ch:hash=e8e14ff5]',
  'infobroker-496513',
]

test('shut down empty infobroker projects', async () => {
  test.setTimeout(15 * 60 * 1000)
  const ctx = await chromium.launchPersistentContext(USER_DATA_DIR, {
    channel: 'chrome', headless: false, viewport: { width: 1440, height: 900 },
  })
  const page = ctx.pages()[0] ?? await ctx.newPage()
  page.setDefaultTimeout(25_000)

  for (const pid of TO_DELETE) {
    console.log('\n=== shutting down ' + pid + ' ===')
    await page.goto('https://console.cloud.google.com/iam-admin/settings?project=' + pid, { waitUntil: 'domcontentloaded' })
    await page.waitForLoadState('networkidle', { timeout: 30_000 }).catch(() => null)
    await page.waitForTimeout(8000)

    // Find "Shut down" button
    const shutBtns = [
      'button:has-text("SHUT DOWN")',
      'button:has-text("Shut down")',
      'button:has-text("DELETE")',
      'a:has-text("SHUT DOWN")',
    ]
    let clicked = false
    for (const sel of shutBtns) {
      const loc = page.locator(sel).first()
      if (await loc.isVisible().catch(() => false)) {
        try { await loc.click({ timeout: 5000 }); clicked = true; console.log('  clicked shut-down via ' + sel); break }
        catch {}
      }
    }
    if (!clicked) {
      console.log('  no Shut down button visible - skipping ' + pid)
      await page.screenshot({ path: '/tmp/gcp-delete-' + pid + '.png' }).catch(() => null)
      continue
    }
    await page.waitForTimeout(1500)

    // Confirm dialog: type project ID into a confirmation field, then click Shut down.
    const confirmInput = page.locator('input[aria-label*="project ID" i], input[placeholder*="project ID" i], mat-dialog-container input').first()
    if (await confirmInput.isVisible().catch(() => false)) {
      await confirmInput.fill(pid).catch(() => null)
      await page.waitForTimeout(500)
    }
    // Click the final confirm button in the dialog
    const finalBtns = [
      'mat-dialog-container button:has-text("SHUT DOWN"):not([disabled])',
      'mat-dialog-container button:has-text("Shut down"):not([disabled])',
      'mat-dialog-container button:has-text("DELETE"):not([disabled])',
      'mat-dialog-container button.mat-warn:not([disabled])',
    ]
    for (const sel of finalBtns) {
      const loc = page.locator(sel).first()
      if (await loc.isVisible().catch(() => false)) {
        try { await loc.click({ timeout: 5000 }); console.log('  confirmed via ' + sel); break } catch {}
      }
    }
    await page.waitForTimeout(3500)
    console.log('  done: ' + pid)
  }

  console.log('\nAll deletions queued. Browser stays open 10 s.')
  await page.waitForTimeout(10_000)
  await ctx.close()
})
