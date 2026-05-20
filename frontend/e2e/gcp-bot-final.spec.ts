/**
 * GCP OAuth Bootstrap - final (auto + tiny manual gate).
 *
 * Auto-fills consent screen up to the Finish step, asks user to do the
 * 3-click finalization manually, signals completion by clicking the
 * "Clients" link in the sidebar (URL becomes /auth/clients...). Then
 * auto-fills OAuth client form and captures credentials.
 */
import { test, chromium } from '@playwright/test'
import type { Page } from '@playwright/test'
import * as os from 'node:os'
import * as path from 'node:path'
import * as fs from 'node:fs'

const USER_DATA_DIR = path.join(os.homedir(), '.cache', 'pw-gcp-bootstrap')
const PROJECT_ID    = 'regal-elf-496513-r0'
const SUPPORT_EMAIL = 'rinehardramos@gmail.com'
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

async function tryClick(page: Page, selectors: string[], label: string, timeout = 8000): Promise<boolean> {
  for (const sel of selectors) {
    try {
      const loc = page.locator(sel).first()
      await loc.waitFor({ state: 'visible', timeout: timeout / selectors.length })
      await loc.click({ timeout: 4000 })
      console.log('  CLICK ok: ' + label)
      return true
    } catch { /* try next */ }
  }
  console.log('  (could not click ' + label + ' - may already be done)')
  return false
}

test('final bootstrap', async () => {
  test.setTimeout(20 * 60 * 1000)

  const context = await chromium.launchPersistentContext(USER_DATA_DIR, {
    channel: 'chrome', headless: false,
    viewport: { width: 1440, height: 900 },
    args: ['--disable-blink-features=AutomationControlled'],
  })
  const page = context.pages()[0] ?? await context.newPage()
  page.setDefaultTimeout(20_000)

  console.log('\n=== PHASE 1: auto-fill consent up to Finish step ===')
  await page.goto('https://console.cloud.google.com/auth/overview?project=' + PROJECT_ID, { waitUntil: 'domcontentloaded' })
  await page.waitForLoadState('networkidle', { timeout: 30_000 }).catch(() => null)
  await page.waitForTimeout(3000)

  // GET STARTED (only if consent not started)
  await tryClick(page, ['a:has-text("GET STARTED")', 'button:has-text("GET STARTED")'], 'GetStarted', 6000)
  await page.waitForTimeout(2500)

  // App name
  const appName = page.locator('input[formcontrolname="displayName"], input[formcontrolname="appName"]').first()
  if (await appName.isVisible().catch(() => false)) {
    await appName.fill('info-broker').catch(() => null)
    console.log('  filled app name')
  }
  // Support email
  await tryClick(page, [
    'mat-select[formcontrolname="supportEmail"]',
    '[role="combobox"]:near(:text("User support email"))',
  ], 'OpenSupportEmail', 6000)
  await page.waitForTimeout(800)
  await tryClick(page, ['mat-option:has-text("' + SUPPORT_EMAIL + '")', 'mat-option'], 'PickSupportEmail', 5000)
  await page.waitForTimeout(500)
  await tryClick(page, ['button:has-text("NEXT")', 'button:has-text("Next")'], 'NextApp', 5000)
  await page.waitForTimeout(2000)

  // Audience: External
  await tryClick(page, [
    'mat-radio-button:has-text("External") input',
    'input[type="radio"][value="EXTERNAL"]',
  ], 'External', 6000)
  await page.waitForTimeout(500)
  await tryClick(page, ['button:has-text("NEXT")', 'button:has-text("Next")'], 'NextAudience', 5000)
  await page.waitForTimeout(2000)

  // Contact email (mat-chip-grid input)
  const chipInput = page.locator('mat-chip-grid input, input[matChipInputFor]').first()
  if (await chipInput.isVisible().catch(() => false)) {
    await chipInput.click()
    await page.keyboard.type(SUPPORT_EMAIL, { delay: 25 })
    await page.keyboard.press('Enter')
    console.log('  filled contact email')
  }
  await page.waitForTimeout(600)
  await tryClick(page, ['button:has-text("NEXT")', 'button:has-text("Next")'], 'NextContact', 5000)
  await page.waitForTimeout(2000)
  await shoot(page, 'phase1-done')

  console.log('\n=== PHASE 2: MANUAL FINISH STEP ===')
  console.log(' ')
  console.log(' >>> IN THE CHROME WINDOW NOW: <<<')
  console.log('   1. Check "I agree to Google API Services: User Data Policy"')
  console.log('   2. Click the "Continue" button INSIDE the Finish section')
  console.log('   3. Click the bottom blue "Create" button')
  console.log('   4. After consent is created, click "Clients" in the LEFT SIDEBAR (under Google Auth Platform)')
  console.log(' ')
  console.log(' I am waiting for the URL to switch to /auth/clients...')
  console.log(' ')

  // Wait for the URL to navigate to /auth/clients (signal that consent is done)
  try {
    await page.waitForURL(/\/auth\/clients(\?|$)/, { timeout: 15 * 60 * 1000 })
  } catch {
    console.log('TIMEOUT waiting for /auth/clients navigation. Aborting.')
    await context.close()
    return
  }
  console.log('  >>> detected /auth/clients - taking over <<<')
  await page.waitForTimeout(2500)

  console.log('\n=== PHASE 3: create OAuth client ===')
  await page.goto('https://console.cloud.google.com/auth/clients/create?project=' + PROJECT_ID, { waitUntil: 'domcontentloaded' })
  await page.waitForLoadState('networkidle', { timeout: 30_000 }).catch(() => null)
  await page.waitForTimeout(3000)
  await shoot(page, 'phase3-form')

  // Application type → Web application
  await tryClick(page, [
    'mat-select[formcontrolname="applicationType"]',
    'mat-select[aria-label*="Application type" i]',
    '[role="combobox"]:near(:text("Application type"))',
  ], 'OpenAppType', 10_000)
  await page.waitForTimeout(800)
  await tryClick(page, [
    'mat-option:has-text("Web application")',
    '[role="option"]:has-text("Web application")',
  ], 'PickWebApp', 6000)
  await page.waitForTimeout(800)

  // Name
  const clientNameInput = page.locator('input[formcontrolname="displayName"], input[formcontrolname="name"]').first()
  await clientNameInput.fill(CLIENT_NAME, { timeout: 8000 }).catch(() => null)
  await page.waitForTimeout(500)

  // JS origins (click ADD URI then fill)
  for (const origin of JS_ORIGINS) {
    const addBtns = page.locator('button:has-text("ADD URI"), button:has-text("Add URI")')
    await addBtns.first().click({ timeout: 8000 }).catch(() => null)
    await page.waitForTimeout(400)
    const uriInputs = page.locator('input[aria-label*="URIs" i], input[formcontrolname="uri"]')
    await uriInputs.last().fill(origin).catch(() => null)
    await page.waitForTimeout(300)
  }

  // Redirect URI (last ADD URI button)
  const addAll = page.locator('button:has-text("ADD URI"), button:has-text("Add URI")')
  const n = await addAll.count()
  if (n >= 1) await addAll.nth(n - 1).click({ timeout: 6000 }).catch(() => null)
  await page.waitForTimeout(400)
  const uriAll = page.locator('input[aria-label*="URIs" i], input[formcontrolname="uri"]')
  await uriAll.last().fill(REDIRECT_URI).catch(() => null)
  await page.waitForTimeout(600)
  await shoot(page, 'phase3-filled')

  console.log('  submitting OAuth client form')
  await tryClick(page, [
    'button:has-text("CREATE"):not([disabled])',
    'button:has-text("Create"):not([disabled])',
  ], 'Submit', 10_000)

  // Capture credentials from result modal
  console.log('\n=== PHASE 4: capture credentials ===')
  await page.locator('text=/your client ID|client_id\.json|Client ID|Client secret/i')
    .first().waitFor({ timeout: 3 * 60 * 1000 })
  await page.waitForTimeout(2000)
  await shoot(page, 'phase4-modal')
  const text = await page.locator('body').innerText()
  const idMatch  = text.match(/\b\d{8,}-[a-z0-9]+\.apps\.googleusercontent\.com\b/)
  const secMatch = text.match(/\bGOCSPX-[A-Za-z0-9_-]{20,}\b/)
  if (idMatch && secMatch) {
    console.log('\n========== CREDENTIALS CAPTURED ==========')
    console.log('GOOGLE_CLIENT_ID=' + idMatch[0])
    console.log('GOOGLE_CLIENT_SECRET=' + secMatch[0])
    console.log('==========================================')
    fs.writeFileSync(OUT_ENV_FILE, 'GOOGLE_CLIENT_ID=' + idMatch[0] + '\nGOOGLE_CLIENT_SECRET=' + secMatch[0] + '\n')
    console.log('  saved to ' + OUT_ENV_FILE)
  } else {
    console.log('  REGEX MISS - body length: ' + text.length + ' - please copy manually')
  }

  await page.waitForTimeout(20_000)
  await context.close()
})
