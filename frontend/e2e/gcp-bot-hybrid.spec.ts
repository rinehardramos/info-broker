/**
 * GCP OAuth Bootstrap - hybrid.
 *
 * Skips the brittle consent-screen automation. Opens the persistent-profile
 * browser at the consent Finish step. You click "I agree" + Continue + bottom
 * Create. The spec waits, then auto-fills the OAuth client form and captures
 * the client ID + secret.
 *
 * Usage: cd frontend && npx playwright test gcp-bot-hybrid --headed --workers=1
 */
import { test, chromium } from '@playwright/test'
import type { Page } from '@playwright/test'
import * as os from 'node:os'
import * as path from 'node:path'
import * as fs from 'node:fs'

const USER_DATA_DIR = path.join(os.homedir(), '.cache', 'pw-gcp-bootstrap')
const PROJECT_ID    = 'regal-elf-496513-r0'
const CLIENT_NAME   = 'info-broker local dev'
const JS_ORIGINS    = ['http://localhost:5173', 'http://localhost:8000']
const REDIRECT_URI  = 'http://localhost:8000/v3/auth/google/callback'
const SHOT_DIR      = '/tmp/gcp-bootstrap-shots'
const OUT_ENV_FILE  = '/tmp/gcp-bootstrap.env'

async function shoot(page: Page, label: string) {
  try {
    fs.mkdirSync(SHOT_DIR, { recursive: true })
    const p = path.join(SHOT_DIR, Date.now() + '-' + label + '.png')
    await page.screenshot({ path: p, fullPage: false })
    console.log('  shot: ' + p)
  } catch { /* ignore */ }
}

async function click(page: Page, selectors: string[], label: string, timeout = 12000): Promise<boolean> {
  for (const sel of selectors) {
    try {
      const loc = page.locator(sel).first()
      await loc.waitFor({ state: 'visible', timeout: timeout / selectors.length })
      await loc.click({ timeout: 5000 })
      console.log('  CLICK ok: ' + label + '  [' + sel + ']')
      return true
    } catch { /* try next */ }
  }
  console.log('  CLICK FAIL: ' + label)
  await shoot(page, 'fail-' + label.replace(/[^a-z0-9]+/gi, '_'))
  return false
}

test('hybrid - user finishes consent, spec auto-creates OAuth client', async () => {
  test.setTimeout(15 * 60 * 1000)

  const context = await chromium.launchPersistentContext(USER_DATA_DIR, {
    channel: 'chrome', headless: false,
    viewport: { width: 1440, height: 900 },
    args: ['--disable-blink-features=AutomationControlled'],
  })
  const page = context.pages()[0] ?? await context.newPage()
  page.setDefaultTimeout(20000)

  console.log('\n====== HYBRID GCP OAuth BOOTSTRAP ======')
  console.log('Opening consent Finish step in the browser.')
  console.log('YOU: click "I agree to ..." -> "Continue" -> bottom "Create".')
  console.log('I will wait until the consent screen is published, then create the OAuth client.\n')

  await page.goto('https://console.cloud.google.com/auth/overview?project=' + encodeURIComponent(PROJECT_ID), {
    waitUntil: 'domcontentloaded',
  })
  await page.waitForLoadState('networkidle', { timeout: 30_000 }).catch(() => null)
  await page.waitForTimeout(2000)
  await shoot(page, 'hybrid-01-consent')

  // Poll the /auth/clients/create page in a separate tab every 5s.
  // When the "configure consent screen first" warning is gone, we proceed.
  // (We open the same tab, navigate, and check; if warning present, navigate back.)
  console.log('Waiting for you to navigate to /auth/clients/create when ready.')
  console.log('After clicking "I agree -> Continue -> Create", go to:')
  console.log('  https://console.cloud.google.com/auth/clients/create?project=' + PROJECT_ID)
  console.log('(Or use the sidebar: Clients -> + Create client)')
  console.log('I will poll passively in the background tab.\n')

  // Open a second page to probe quietly without disturbing user.
  const probe = await context.newPage()
  let consentReady = false
  for (let i = 0; i < 120; i++) {
    await probe.waitForTimeout(5000)
    try {
      await probe.goto('https://console.cloud.google.com/auth/clients/create?project=' + encodeURIComponent(PROJECT_ID), {
        waitUntil: 'domcontentloaded',
        timeout: 20_000,
      })
      await probe.waitForLoadState('networkidle', { timeout: 10_000 }).catch(() => null)
      await probe.waitForTimeout(1500)
      const warning = await probe.locator('text=/must first configure your consent screen/i').first().isVisible().catch(() => false)
      if (!warning) {
        consentReady = true
        console.log('  consent looks ready - proceeding with OAuth client form')
        break
      }
      console.log('  (still waiting on consent... iteration ' + (i+1) + ')')
    } catch (e) { console.log('  probe error: ' + e) }
  }
  await probe.close().catch(() => null)
  if (!consentReady) {
    console.log('TIMEOUT: consent screen never reached ready state.')
    await context.close()
    return
  }

  // Navigate the main page to the OAuth client form.
  await page.goto('https://console.cloud.google.com/auth/clients/create?project=' + encodeURIComponent(PROJECT_ID), {
    waitUntil: 'domcontentloaded',
  })
  await page.waitForLoadState('networkidle', { timeout: 30_000 }).catch(() => null)
  await page.waitForTimeout(2500)
  await shoot(page, 'hybrid-02-form')

  // Application type → Web application
  console.log('Filling OAuth client form...')
  await click(page, [
    'mat-select[formcontrolname="applicationType"]',
    'mat-select[aria-label*="Application type" i]',
    '[role="combobox"]:near(:text("Application type"))',
  ], 'OpenAppType', 12000)
  await page.waitForTimeout(800)
  await click(page, [
    'mat-option:has-text("Web application")',
    '[role="option"]:has-text("Web application")',
  ], 'PickWebApp', 8000)
  await page.waitForTimeout(800)

  // Name
  const nameInput = page.locator('input[formcontrolname="displayName"], input[formcontrolname="name"]').first()
  await nameInput.fill(CLIENT_NAME, { timeout: 8000 }).catch(() => null)
  await page.waitForTimeout(500)

  // JS origins
  console.log('  adding JS origins')
  for (const origin of JS_ORIGINS) {
    const addBtns = page.locator('button:has-text("ADD URI"), button:has-text("Add URI")')
    await addBtns.first().click({ timeout: 8000 }).catch(() => null)
    await page.waitForTimeout(400)
    const uriInputs = page.locator('input[aria-label*="URIs" i], input[formcontrolname="uri"]')
    await uriInputs.last().fill(origin).catch(() => null)
    await page.waitForTimeout(300)
  }

  // Redirect URI
  console.log('  adding redirect URI')
  const addAll = page.locator('button:has-text("ADD URI"), button:has-text("Add URI")')
  const n = await addAll.count()
  if (n >= 1) await addAll.nth(n - 1).click({ timeout: 6000 }).catch(() => null)
  await page.waitForTimeout(400)
  const uriAll = page.locator('input[aria-label*="URIs" i], input[formcontrolname="uri"]')
  await uriAll.last().fill(REDIRECT_URI).catch(() => null)
  await page.waitForTimeout(600)
  await shoot(page, 'hybrid-03-filled')

  // Submit
  console.log('  submitting')
  await click(page, [
    'button:has-text("CREATE"):not([disabled])',
    'button:has-text("Create"):not([disabled])',
  ], 'Submit', 10000)

  // Capture creds from modal
  console.log('Waiting for credentials modal...')
  await page.locator('text=/your client ID|client_id\.json|Client ID|Client secret/i')
    .first().waitFor({ timeout: 3 * 60 * 1000 })
  await page.waitForTimeout(2000)
  await shoot(page, 'hybrid-04-modal')

  const text = await page.locator('body').innerText()
  const idMatch  = text.match(/\b\d{8,}-[a-z0-9]+\.apps\.googleusercontent\.com\b/)
  const secMatch = text.match(/\bGOCSPX-[A-Za-z0-9_-]{20,}\b/)
  if (idMatch && secMatch) {
    console.log('\n========== CAPTURED ==========')
    console.log('GOOGLE_CLIENT_ID=' + idMatch[0])
    console.log('GOOGLE_CLIENT_SECRET=' + secMatch[0])
    console.log('==============================')
    fs.writeFileSync(OUT_ENV_FILE, 'GOOGLE_CLIENT_ID=' + idMatch[0] + '\nGOOGLE_CLIENT_SECRET=' + secMatch[0] + '\n')
    console.log('  saved to ' + OUT_ENV_FILE)
  } else {
    console.log('  REGEX MISS - body length: ' + text.length)
  }

  await page.waitForTimeout(15_000)
  await context.close()
})
