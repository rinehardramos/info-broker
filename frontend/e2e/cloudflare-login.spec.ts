/**
 * Drive `wrangler login` OAuth flow via Playwright.
 *
 *   1. Spawn `wrangler login` (background). Captures the OAuth URL from stdout.
 *   2. Open it in a persistent-context Chromium so the Cloudflare cookie sticks.
 *   3. If the page is the Cloudflare login screen → USER signs in manually.
 *      (We cannot do this — no credentials, possible 2FA.)
 *   4. Once on the OAuth Authorize screen, auto-click Allow/Authorize.
 *   5. Wrangler captures the callback and writes the token.
 *   6. Test asserts wrangler exited with code 0 (true success).
 */
import { test, expect, chromium } from '@playwright/test'
import { spawn } from 'node:child_process'
import * as path from 'node:path'
import * as os from 'node:os'
import * as fs from 'node:fs'

const PROFILE_DIR = path.join(os.tmpdir(), 'info-broker-cf-login-profile')
const wait = (ms: number) => new Promise(r => setTimeout(r, ms))

test('wrangler login via Playwright', async () => {
  test.setTimeout(420_000)
  fs.mkdirSync(PROFILE_DIR, { recursive: true })

  console.log('\n▶ Spawning `wrangler login`…')
  const wrangler = spawn('pnpm', ['exec', 'wrangler', 'login'], {
    cwd: process.cwd(),
    stdio: ['ignore', 'pipe', 'pipe'],
  })

  let authUrl: string | null = null
  let wranglerExit: number | null = null
  let wranglerStderr = ''

  wrangler.stdout.on('data', (chunk) => {
    const s = chunk.toString()
    process.stdout.write('[wrangler] ' + s)
    const m = s.match(/https:\/\/dash\.cloudflare\.com\/oauth2\/auth\?[^\s'"]+/)
    if (m && !authUrl) authUrl = m[0]
  })
  wrangler.stderr.on('data', (chunk) => {
    const s = chunk.toString()
    wranglerStderr += s
    process.stderr.write('[wrangler-err] ' + s)
  })
  wrangler.on('exit', (code) => { wranglerExit = code ?? 1 })

  // Capture URL
  for (let i = 0; i < 30 && !authUrl; i++) await wait(500)
  if (!authUrl) { wrangler.kill(); throw new Error('No OAuth URL captured.') }
  console.log(`\n▶ OAuth URL captured.\n`)

  const ctx = await chromium.launchPersistentContext(PROFILE_DIR, {
    headless: false,
    viewport: { width: 1280, height: 900 },
  })
  const page = ctx.pages()[0] || await ctx.newPage()
  await page.goto(authUrl, { waitUntil: 'domcontentloaded' })

  console.log('\n╔══════════════════════════════════════════════════════════════════╗')
  console.log('║   USER ACTION REQUIRED                                            ║')
  console.log('║   A Chrome window is now open at the Cloudflare OAuth page.       ║')
  console.log('║   - If asked to sign in: do so in that window (handle 2FA there). ║')
  console.log('║   - Once you reach the "Authorize" screen, I will click it for you.║')
  console.log('║   Total wait: up to 5 minutes.                                    ║')
  console.log('╚══════════════════════════════════════════════════════════════════╝\n')

  // Poll: take a screenshot every 30s for debugging; click Authorize when seen.
  let clicked = false
  for (let i = 0; i < 300; i++) {                  // 300 × 1s = 5 min
    if (wranglerExit !== null) break

    const url = page.url()
    if (i % 15 === 0) {
      console.log(`  [${i}s] currently at: ${url.slice(0, 100)}`)
      await page.screenshot({ path: `/tmp/cf-login-step-${i}.png` }).catch(() => {})
    }

    // Try to find an Authorize button on the OAuth Allow screen.
    if (/oauth2\/auth/.test(url) || /oauth/.test(url)) {
      const selectors = [
        'button:has-text("Authorize")',
        'button:has-text("Allow")',
        '[data-testid="oauth-allow-button"]',
        'button[type="submit"]:has-text("Authorize")',
      ]
      for (const sel of selectors) {
        const btn = page.locator(sel).first()
        if (await btn.isVisible({ timeout: 200 }).catch(() => false)) {
          console.log(`▶ Clicking ${sel}…`)
          await btn.click().catch(() => {})
          clicked = true
          break
        }
      }
      if (clicked) break
    }
    await wait(1000)
  }

  if (clicked) {
    console.log('\n▶ Authorize clicked — waiting for wrangler to receive the callback…')
    for (let i = 0; i < 30 && wranglerExit === null; i++) await wait(1000)
  }

  if (wranglerExit === null) {
    console.log('\n▶ Killing wrangler (still running)…')
    wrangler.kill()
  }
  await ctx.close()

  console.log(`\n▶ wrangler exit code: ${wranglerExit}`)
  if (wranglerStderr) console.log(`▶ wrangler stderr:\n${wranglerStderr}`)

  expect(wranglerExit, 'wrangler must exit 0 for the OAuth flow to be considered complete').toBe(0)
  console.log('\n✓ Authenticated.\n')
})
