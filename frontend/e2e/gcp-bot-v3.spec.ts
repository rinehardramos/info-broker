/**
 * GCP OAuth Bootstrap v3 - automated.
 * Built atop the working manual-spec structure. URL-based navigation +
 * keyboard input + Page type-only import to avoid pnpm resolver quirks.
 */
import { test, chromium } from '@playwright/test'
import type { Page } from '@playwright/test'
import * as os from 'node:os'
import * as path from 'node:path'
import * as fs from 'node:fs'

test.use({ headless: false })

const USER_DATA_DIR = path.join(os.homedir(), '.cache', 'pw-gcp-bootstrap')
const PROJECT_NAME  = 'infobroker'
const CLIENT_NAME   = 'info-broker local dev'
const JS_ORIGINS    = ['http://localhost:5173', 'http://localhost:8000']
const REDIRECT_URI  = 'http://localhost:8000/v3/auth/google/callback'
const SHOT_DIR      = '/tmp/gcp-bootstrap-shots'
const OUT_ENV_FILE  = '/tmp/gcp-bootstrap.env'
const SUPPORT_EMAIL = 'rinehardramos@gmail.com'

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

test('create google oauth client id v3', async () => {
  test.setTimeout(15 * 60 * 1000)

  const context = await chromium.launchPersistentContext(USER_DATA_DIR, {
    channel: 'chrome',
    headless: false,
    viewport: { width: 1440, height: 900 },
    args: ['--disable-blink-features=AutomationControlled'],
  })
  const page = context.pages()[0] ?? await context.newPage()
  page.setDefaultTimeout(20000)

  console.log('STEP 1: select infobroker project (hardcoded ID)')
  // We have 5 infobroker projects in this account from earlier runs.
  // The picker UI is unreliable to scrape, so use the known-good ID
  // observed in the dialog screenshot: regal-elf-496513-r0.
  const PROJECT_ID = 'regal-elf-496513-r0'
  console.log('  PROJECT_ID = ' + PROJECT_ID)
  await page.goto('https://console.cloud.google.com/home/dashboard?project=' + encodeURIComponent(PROJECT_ID), {
    waitUntil: 'domcontentloaded',
  })
  await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => null)
  if (/accounts\\.google\\.com/.test(page.url())) {
    console.log('  WARN: not signed in - waiting up to 3 min')
    await page.waitForURL(/console\\.cloud\\.google\\.com/, { timeout: 3 * 60 * 1000 })
  }
  await page.waitForTimeout(3000)
  await shoot(page, '01-project-active')

  console.log('STEP 3: go to OAuth consent screen for ' + PROJECT_ID)
  await page.goto('https://console.cloud.google.com/auth/overview?project=' + encodeURIComponent(PROJECT_ID), {
    waitUntil: 'domcontentloaded',
  })
  await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => null)
  await page.waitForTimeout(3000)
  await shoot(page, '[REDACTED:high-entropy-base64:27ch:hash=4d6018f4]')

  // Click "GET STARTED" if the consent overview shows it
  await click(page, [
    'button:has-text("GET STARTED")', 'button:has-text("Get started")',
    'a:has-text("GET STARTED")', 'a:has-text("Get started")',
  ], 'GetStarted', 6000)
  await page.waitForTimeout(2500)
  await shoot(page, '05-consent-step1')

  // App info: name + user support email
  const appNameSel = 'input[formcontrolname="displayName"], input[formcontrolname="appName"], input[aria-label*="App name" i]'
  const appNameLoc = page.locator(appNameSel).first()
  if (await appNameLoc.isVisible().catch(() => false)) {
    await appNameLoc.fill('info-broker').catch(() => null)
    console.log('  filled app name')
  } else {
    console.log('  WARN: app name field not visible — trying first input on page')
    await page.locator('input[type="text"]').first().fill('info-broker').catch(() => null)
  }

  // Pick user support email
  await click(page, [
    'mat-select[formcontrolname="supportEmail"]',
    '[role="combobox"]:near(:text("User support email"))',
    'mat-select:near(:text("User support email"))',
  ], 'OpenSupportEmail', 6000)
  await page.waitForTimeout(800)
  await click(page, [
    'mat-option:has-text("' + SUPPORT_EMAIL + '")',
    '[role="option"]:has-text("' + SUPPORT_EMAIL + '")',
    'mat-option', '[role="option"]',
  ], 'PickSupportEmail', 6000)
  await page.waitForTimeout(500)
  await shoot(page, '06-app-info-filled')
  await click(page, ['button:has-text("NEXT")', 'button:has-text("Next")'], 'Next-AppInfo', 6000)
  await page.waitForTimeout(2500)
  await shoot(page, '07-audience')

  // Audience: External
  await click(page, [
    'input[type="radio"][value="EXTERNAL"]',
    'mat-radio-button:has-text("External") input',
    'label:has-text("External") input[type="radio"]',
  ], 'PickExternal', 8000)
  await page.waitForTimeout(500)
  await click(page, ['button:has-text("NEXT")', 'button:has-text("Next")'], 'Next-Audience', 6000)
  await page.waitForTimeout(2500)
  await shoot(page, '08-contact')

  // Contact step's "Email addresses *" is a Material chip-grid input.
  // Try multiple selector strategies in priority order.
  let emailFilled = false
  const emailSelectors = [
    'input[matChipInputFor]',
    'mat-chip-grid input',
    'input.mat-mdc-chip-input',
    'mat-form-field:has(label:has-text("Email addresses")) input',
    'input[aria-label*="Email addresses" i]',
  ]
  for (const sel of emailSelectors) {
    const loc = page.locator(sel).first()
    if (await loc.isVisible().catch(() => false)) {
      try {
        await loc.click({ timeout: 3000 })
        await page.keyboard.type(SUPPORT_EMAIL, { delay: 25 })
        await page.keyboard.press('Enter')
        emailFilled = true
        console.log('  filled email addresses via: ' + sel)
        break
      } catch { /* try next */ }
    }
  }
  if (!emailFilled) {
    // Last resort: find an active section's first visible input via JS.
    const ok = await page.evaluate((email) => {
      const all = Array.from(document.querySelectorAll('input')) as HTMLInputElement[]
      for (const inp of all) {
        const r = inp.getBoundingClientRect()
        if (r.width === 0 || r.height === 0) continue
        // Look for inputs inside a form-field labelled "Email addresses"
        const ff = inp.closest('mat-form-field')
        const labelEl = ff?.querySelector('label, mat-label')
        if (labelEl && /Email addresses/i.test(labelEl.textContent || '')) {
          inp.focus()
          // Use a native input event so Angular reactive forms pick it up.
          const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
          setter?.call(inp, email)
          inp.dispatchEvent(new Event('input', { bubbles: true }))
          inp.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
          inp.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', bubbles: true }))
          return true
        }
      }
      return false
    }, SUPPORT_EMAIL)
    if (ok) { emailFilled = true; console.log('  filled email addresses via JS dispatch') }
    else console.log('  WARN: email field not found')
  }
  await page.waitForTimeout(800)
  await shoot(page, '08b-email-filled')
  await click(page, ['button:has-text("NEXT")', 'button:has-text("Next")'], 'Next-Contact', 6000)
  await page.waitForTimeout(2500)
  await shoot(page, '09-finish')

  // Finish step: check "I agree" checkbox, click Continue, then click bottom Create.
  // The checkbox uses Material checkbox with label "I agree to the Google API Services: User Data Policy".
  let agreed = false
  const cbSelectors = [
    'mat-checkbox:has-text("I agree")',
    'mat-checkbox:has-text("agree")',
    'label:has-text("I agree")',
    'label:has-text("agree")',
    'input[type="checkbox"][aria-label*="agree" i]',
  ]
  for (const sel of cbSelectors) {
    const loc = page.locator(sel).first()
    if (await loc.isVisible().catch(() => false)) {
      try {
        await loc.click({ timeout: 3000 })
        agreed = true
        console.log('  checked I agree via: ' + sel)
        break
      } catch { /* try next */ }
    }
  }
  if (!agreed) {
    // JS fallback to check the agree checkbox.
    const ok = await page.evaluate(() => {
      const cbs = Array.from(document.querySelectorAll('input[type="checkbox"]')) as HTMLInputElement[]
      for (const cb of cbs) {
        const r = cb.getBoundingClientRect()
        if (r.width === 0 || r.height === 0) continue
        if (!cb.checked) {
          cb.click()
          return true
        }
      }
      return false
    })
    if (ok) { agreed = true; console.log('  checked I agree via JS click') }
    else console.log('  WARN: agree checkbox not found')
  }
  await page.waitForTimeout(500)
  await shoot(page, '09b-agree-checked')

  // Click "Continue" in the Finish step (the one inside the section, not the bottom Create).
  await click(page, [
    'button:has-text("CONTINUE"):not([disabled])',
    'button:has-text("Continue"):not([disabled])',
  ], 'ContinueFinish', 6000)
  await page.waitForTimeout(1500)

  // Now click the bottom "Create" button (the form's submit button).
  await click(page, [
    'button:has-text("CREATE"):not([disabled])',
    'button:has-text("Create"):not([disabled])',
  ], 'FinishConsent', 8000)
  // Consent takes a few seconds to propagate to the OAuth client form.
  await page.waitForTimeout(8000)
  await shoot(page, '10-consent-done')

  console.log('STEP 4: create OAuth client (web app)')
  // New URL for the OAuth client create form
  await page.goto('https://console.cloud.google.com/auth/clients/create?project=' + encodeURIComponent(PROJECT_ID), {
    waitUntil: 'domcontentloaded',
  })
  await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => null)
  await page.waitForTimeout(3000)
  await shoot(page, '11-clients-create')

  // If the URL fell back somewhere else, navigate via Credentials > Create Credentials
  if (!/auth\/clients\/create/.test(page.url())) {
    console.log('  fallback: navigating via Credentials page')
    await page.goto('https://console.cloud.google.com/apis/credentials?project=' + encodeURIComponent(PROJECT_ID), {
      waitUntil: 'domcontentloaded',
    })
    await page.waitForTimeout(2500)
    await click(page, [
      'button:has-text("CREATE CREDENTIALS")', 'button:has-text("Create credentials")',
    ], 'CreateCreds', 8000)
    await page.waitForTimeout(800)
    await click(page, ['text=OAuth client ID'], 'OAuthClientItem', 6000)
    await page.waitForTimeout(2500)
  }

  // Application type → Web application
  await click(page, [
    'mat-select[formcontrolname="applicationType"]',
    'mat-select[aria-label*="Application type" i]',
    '[role="combobox"]:near(:text("Application type"))',
  ], 'OpenAppType', 10000)
  await page.waitForTimeout(800)
  await click(page, [
    'mat-option:has-text("Web application")',
    '[role="option"]:has-text("Web application")',
  ], 'PickWebApp', 6000)
  await page.waitForTimeout(800)

  // Client name
  const clientNameSel = 'input[formcontrolname="displayName"], input[formcontrolname="name"], input[aria-label="Name"]'
  await page.locator(clientNameSel).first().fill(CLIENT_NAME, { timeout: 8000 }).catch(() => null)
  await page.waitForTimeout(500)

  // Add JS origins
  console.log('  adding JS origins')
  for (const origin of JS_ORIGINS) {
    const addBtns = page.locator('button:has-text("ADD URI"), button:has-text("Add URI")')
    await addBtns.first().click({ timeout: 8000 }).catch(() => null)
    await page.waitForTimeout(400)
    const uriInputs = page.locator('input[aria-label*="URIs" i], input[formcontrolname="uri"]')
    await uriInputs.last().fill(origin).catch(() => null)
    await page.waitForTimeout(300)
  }

  // Add redirect URI (last ADD URI button = redirect section)
  console.log('  adding redirect URI')
  const addAll = page.locator('button:has-text("ADD URI"), button:has-text("Add URI")')
  const n = await addAll.count()
  if (n >= 1) await addAll.nth(n - 1).click({ timeout: 6000 }).catch(() => null)
  await page.waitForTimeout(400)
  const uriAll = page.locator('input[aria-label*="URIs" i], input[formcontrolname="uri"]')
  await uriAll.last().fill(REDIRECT_URI).catch(() => null)
  await page.waitForTimeout(600)
  await shoot(page, '12-oauth-form-filled')

  console.log('STEP 5: click Create on OAuth form')
  await click(page, [
    'button:has-text("CREATE"):not([disabled])',
    'button:has-text("Create"):not([disabled])',
  ], 'SubmitOAuth', 10000)

  console.log('STEP 6: capture creds from result modal')
  await page.locator('text=/your client ID|client_id\.json|Client ID|Client secret/i')
    .first().waitFor({ timeout: 3 * 60 * 1000 })
  await page.waitForTimeout(2000)
  await shoot(page, '13-creds-modal')

  const text = await page.locator('body').innerText()
  const idMatch  = text.match(/\b\d{8,}-[a-z0-9]+\.apps\.googleusercontent\.com\b/)
  const secMatch = text.match(/\bGOCSPX-[A-Za-z0-9_-]{20,}\b/)
  if (idMatch && secMatch) {
    console.log('CAPTURED:')
    console.log('GOOGLE_CLIENT_ID=' + idMatch[0])
    console.log('GOOGLE_CLIENT_SECRET=' + secMatch[0])
    fs.writeFileSync(OUT_ENV_FILE, 'GOOGLE_CLIENT_ID=' + idMatch[0] + '\nGOOGLE_CLIENT_SECRET=' + secMatch[0] + '\n')
    console.log('  saved to ' + OUT_ENV_FILE)
  } else {
    console.log('  REGEX MISS - body length: ' + text.length)
  }

  await page.waitForTimeout(15_000)
  await context.close()
})
