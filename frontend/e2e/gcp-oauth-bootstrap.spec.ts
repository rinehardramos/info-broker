/**
 * GCP OAuth Bootstrap — drives Google Cloud Console UI to create an
 * OAuth 2.0 Client ID for the info-broker app.
 *
 * Usage:
 *   cd frontend && npx playwright test ../scripts/gcp-oauth-bootstrap --reporter=line
 *
 * The browser opens with a persistent context at ~/.[REDACTED:high-entropy-base64:23ch:hash=43ba3826]
 * so your Google sign-in survives between runs. First run: sign in manually
 * when prompted. The script pauses for any uncertain step — your job is just
 * to click through if selectors don't match.
 *
 * On success, prints the Client ID + Secret to stdout for you to paste into .env.
 */
import { test, expect, chromium, type Page } from '@playwright/test'
import * as os from 'node:os'
import * as path from 'node:path'

test.use({ headless: false })

const USER_DATA_DIR = path.join(os.homedir(), '.cache', 'pw-gcp-bootstrap')
const APP_NAME = 'info-broker local dev'
const REDIRECT_URI = 'http://localhost:8000/v3/auth/google/callback'
const JS_ORIGINS = ['http://localhost:5173', 'http://localhost:8000']

async function waitForUser(page: Page, message: string, timeoutMs = 300_000) {
  console.log('\n⏸  ' + message)
  console.log('   Click "Resume" in the Playwright Inspector when ready.\n')
  await page.pause() // opens Playwright Inspector; user clicks Resume to continue
}

test('create google oauth client id', async () => {
  test.setTimeout(900_000) // 15 min — accounts for manual login + 2FA

  // Persistent context so the user only has to log in once.
  const context = await chromium.launchPersistentContext(USER_DATA_DIR, {
    channel: 'chrome',
    headless: false,
    viewport: { width: 1400, height: 900 },
    args: ['--disable-blink-features=AutomationControlled'],
  })

  const page = context.pages()[0] ?? await context.newPage()

  // Go to credentials. If not logged in, this redirects to Google's login.
  await page.goto('https://console.cloud.google.com/apis/credentials', { waitUntil: 'domcontentloaded' })

  // Detect login redirect — pause for the user if so.
  const url = page.url()
  if (/accounts\.google\.com|signin/i.test(url)) {
    await waitForUser(
      page,
      'Please sign in to your Google account. ' +
        'Make sure you land on the Credentials page, pick the correct project (top bar), ' +
        'then resume.',
    )
  } else {
    console.log('Looks like you are already signed in. Continuing.')
  }

  // Confirm we're on the credentials page with a project selected.
  console.log('Current URL:', page.url())

  // Ensure OAuth consent screen is configured. If not, Google blocks the
  // "Create OAuth client ID" form. We probe by trying to click "+ Create
  // Credentials" → "OAuth client ID" and pause if Google asks to configure
  // the consent screen first.
  console.log('\n→ Clicking "+ Create Credentials" → "OAuth client ID"...')
  try {
    await page.getByRole('button', { name: /create credentials/i }).click({ timeout: 10_000 })
    await page.getByRole('menuitem', { name: /oauth client id/i }).click({ timeout: 5_000 })
  } catch (e) {
    await waitForUser(
      page,
      'Could not auto-click "+ Create Credentials → OAuth client ID". ' +
        'Please click it manually, then resume.',
    )
  }

  // If Google demands consent-screen config first, pause for user to do it.
  await page.waitForLoadState('networkidle').catch(() => {})
  const consentNeeded = await page
    .getByText(/configure consent screen|oauth consent screen first/i)
    .first()
    .isVisible({ timeout: 3000 })
    .catch(() => false)

  if (consentNeeded) {
    await waitForUser(
      page,
      'Google needs you to configure the OAuth Consent Screen first. ' +
        'Click "Configure Consent Screen", fill it out (User type: External, ' +
        'app name "info-broker", scopes default, add your email as a test user), ' +
        'then navigate back to Credentials → + Create Credentials → OAuth client ID, ' +
        'and resume.',
    )
  }

  // ----- Now we should be on the "Create OAuth client ID" form -----
  console.log('\n→ Filling the OAuth client ID form...')

  try {
    // Application type
    const appTypeSelect = page.getByRole('combobox', { name: /application type/i }).first()
    await appTypeSelect.click({ timeout: 8000 })
    await page.getByRole('option', { name: /web application/i }).click({ timeout: 5000 })

    // Name
    await page.getByRole('textbox', { name: /name/i }).first().fill(APP_NAME)

    // Authorized JavaScript origins
    for (const origin of JS_ORIGINS) {
      const addOriginBtn = page.getByRole('button', { name: /add uri/i }).first()
      await addOriginBtn.scrollIntoViewIfNeeded()
      await addOriginBtn.click()
      // The newly-revealed URI textbox under "Authorized JavaScript origins"
      const newField = page.locator('input[aria-label*="URI" i]').last()
      await newField.fill(origin)
    }

    // Authorized redirect URIs — scroll to that section
    const redirectSection = page.getByText(/authorized redirect URIs/i).first()
    await redirectSection.scrollIntoViewIfNeeded()
    // First "Add URI" button under that heading
    const allAddUriBtns = page.getByRole('button', { name: /add uri/i })
    const lastAddUri = allAddUriBtns.last()
    await lastAddUri.click()
    const redirectField = page.locator('input[aria-label*="URI" i]').last()
    await redirectField.fill(REDIRECT_URI)
  } catch (e) {
    await waitForUser(
      page,
      `Auto-fill failed (${(e as Error).message.slice(0, 100)}). ` +
        `Please fill manually:\n` +
        `  - Application type: Web application\n` +
        `  - Name: ${APP_NAME}\n` +
        `  - Authorized JavaScript origins: ${JS_ORIGINS.join(', ')}\n` +
        `  - Authorized redirect URIs: ${REDIRECT_URI}\n` +
        `Then click Create and resume.`,
    )
  }

  console.log('\n→ Clicking Create...')
  try {
    await page.getByRole('button', { name: /^create$/i }).click({ timeout: 10_000 })
  } catch {
    await waitForUser(page, 'Could not click Create automatically. Please click it, then resume.')
  }

  // ----- Wait for the credentials modal -----
  console.log('\n→ Waiting for Client ID + Secret modal...')
  let clientId = ''
  let clientSecret = ''

  try {
    // Heuristic: Google shows the Client ID and a "client secret" label.
    // We extract by selecting the value beside those labels.
    await page.getByText(/your client ID/i).first().waitFor({ timeout: 30_000 })
    const allText = await page.locator('body').innerText()

    // Client ID format: <digits>-<alnum>.apps.googleusercontent.com
    const idMatch = allText.match(/\b\d{8,}-[a-z0-9]+\.apps\.googleusercontent\.com\b/)
    if (idMatch) clientId = idMatch[0]

    // Client Secret format: GOCSPX-<24+ chars>
    const secMatch = allText.match(/\bGOCSPX-[A-Za-z0-9_-]{20,}\b/)
    if (secMatch) clientSecret = secMatch[0]
  } catch {
    // ignored — fall through to manual capture
  }

  if (!clientId || !clientSecret) {
    await waitForUser(
      page,
      'Could not auto-extract the Client ID and/or Secret. ' +
        'Please copy them from the modal manually, paste them into your .env file, ' +
        'then resume to close the browser.',
    )
  } else {
    console.log('\n✅ Credentials captured:\n')
    console.log('   GOOGLE_CLIENT_ID=' + clientId)
    console.log('   GOOGLE_CLIENT_SECRET=' + clientSecret)
    console.log('\nPaste those into your .env, then `docker compose up -d info-broker-api` to reload.\n')
  }

  // Leave the browser open briefly so the user can see the result.
  await page.waitForTimeout(8_000)
  await context.close()

  expect(clientId, 'Client ID was not captured').not.toBe('')
  expect(clientSecret, 'Client Secret was not captured').not.toBe('')
})
