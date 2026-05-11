/**
 * Test: PreFlight clarification gate + answer flow + signal decomposition
 * Run: cd frontend && npx playwright test e2e/preflight-test.spec.ts --headed --project=chromium
 */
import { test, expect } from '@playwright/test'

const BASE = 'http://localhost:5173'
const wait = (ms: number) => new Promise(r => setTimeout(r, ms))

test.use({
  baseURL: BASE,
  viewport: { width: 1400, height: 900 },
  headless: false,
})

test.setTimeout(300_000)

async function login(page: any) {
  await page.goto(`${BASE}/`)
  await wait(1000)
  const loginVisible = await page.locator('input[type="password"]').isVisible().catch(() => false)
  if (loginVisible) {
    await page.fill('input[placeholder*="user" i], input[type="text"]', 'admin')
    await page.fill('input[type="password"]', 'admin')
    await page.locator('button[type="submit"], button:has-text("Login"), button:has-text("Sign in")').click()
    await wait(2000)
  }
}

test('PreFlight gate: spiderman query should ask provenance before launching brain', async ({ page }) => {
  const errors: string[] = []
  page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()) })

  await login(page)
  await page.screenshot({ path: '/tmp/pf-01-main.png' })
  console.log('Screenshot 1: main UI')

  const textarea = page.locator('textarea').first()
  await expect(textarea).toBeVisible({ timeout: 5000 })
  // Wait extra 3s for WS to connect before submitting (avoids first-load race)
  await wait(3000)
  await textarea.fill('new series with girl in spiderman where man has a shotgun')
  await page.screenshot({ path: '/tmp/pf-02-typed.png' })
  console.log('Screenshot 2: query typed')

  await page.keyboard.press('Enter')
  console.log('Query submitted, waiting for PreFlight...')

  await wait(10000)
  await page.screenshot({ path: '/tmp/pf-03-after-submit.png' })
  console.log('Screenshot 3: 8s after submit')

  const questionVisible  = await page.locator('text=Where did you see or hear').first().isVisible().catch(() => false)
  const youtubeVisible   = await page.locator('text=YouTube').first().isVisible().catch(() => false)
  const noResearching    = !(await page.locator('text=Researching').isVisible().catch(() => false))

  console.log('PreFlight question visible:', questionVisible)
  console.log('YouTube option visible:', youtubeVisible)
  console.log('No "Researching…" in chat:', noResearching)

  expect(questionVisible, 'PreFlight question should appear').toBe(true)
  expect(youtubeVisible, 'YouTube option chip should be visible').toBe(true)
  expect(noResearching, '"Researching…" should not show while blocked').toBe(true)
})

test('Full flow: answer PreFlight → brain launches with signal decomposition → mid-research confirm', async ({ page }) => {
  const errors: string[] = []
  page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()) })

  await login(page)

  // Submit the spiderman query
  const textarea = page.locator('textarea').first()
  await expect(textarea).toBeVisible({ timeout: 5000 })
  await textarea.fill('new series with girl in spiderman where man has a shotgun')
  await page.keyboard.press('Enter')
  console.log('Query submitted')

  // Wait for PreFlight question
  await page.waitForSelector('text=Where did you see or hear', { timeout: 15000 })
  console.log('PreFlight question appeared')
  await page.screenshot({ path: '/tmp/pf-04-question.png' })

  // Answer: YouTube
  const youtubeBtn = page.locator('button:has-text("YouTube"), [role="button"]:has-text("YouTube")').first()
  if (await youtubeBtn.isVisible().catch(() => false)) {
    await youtubeBtn.click()
    console.log('Clicked YouTube option')
  } else {
    // Fallback: type in the text input
    const answerInput = page.locator('input[placeholder*="answer"], input[placeholder*="type"]').first()
    if (await answerInput.isVisible().catch(() => false)) {
      await answerInput.fill('YouTube')
      await page.locator('button:has-text("Send")').click()
      console.log('Typed YouTube in text input')
    }
  }

  await wait(3000)
  await page.screenshot({ path: '/tmp/pf-05-after-youtube.png' })
  console.log('Screenshot 5: after YouTube answer')

  // Check for follow-up question (ad vs organic)
  const followUpVisible = await page.locator('text=ad').first().isVisible().catch(() => false)
  console.log('Follow-up question (ad/organic) visible:', followUpVisible)

  if (followUpVisible) {
    // Answer: An ad
    const adBtn = page.locator('button:has-text("An ad"), [role="button"]:has-text("ad")').first()
    if (await adBtn.isVisible().catch(() => false)) {
      await adBtn.click()
      console.log('Clicked "An ad" option')
    }
    await wait(3000)
    await page.screenshot({ path: '/tmp/pf-06-after-ad.png' })
    console.log('Screenshot 6: after ad answer')
  }

  // Brain should now launch — wait for it to appear in LIVE or for mid-research confirmation
  console.log('Waiting up to 60s for brain launch or mid-research confirmation...')
  await wait(10000)
  await page.screenshot({ path: '/tmp/pf-07-brain-launched.png' })
  console.log('Screenshot 7: 10s after final answer')

  // Check outcomes
  const brainRunning     = await page.locator('text=researching').first().isVisible().catch(() => false)
  const midResearchQ     = await page.locator('text=Was this').first().isVisible().catch(() => false)
  const spiderNoirResult = await page.locator('text=Spider-Noir').first().isVisible().catch(() => false)

  console.log('Brain running (in LIVE):', brainRunning)
  console.log('Mid-research confirmation question visible:', midResearchQ)
  console.log('Spider-Noir result visible:', spiderNoirResult)

  if (errors.length) console.log('Console errors:', errors.slice(0, 3))

  await wait(30000)
  await page.screenshot({ path: '/tmp/pf-08-final.png', fullPage: false })
  console.log('Screenshot 8: final state after 30s')

  const midResearchFinal = await page.locator('text=Was this').first().isVisible().catch(() => false)
  const anyResult        = await page.locator('.finding-card, [data-finding], text=confidence').first().isVisible().catch(() => false)

  console.log('Mid-research confirm (final):', midResearchFinal)
  console.log('Any result rendered:', anyResult)

  // Core assertion: brain launched after clarification
  expect(brainRunning || midResearchQ || anyResult,
    'Brain should launch OR ask mid-research confirmation after PreFlight answers').toBe(true)
})
