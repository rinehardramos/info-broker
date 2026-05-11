/**
 * Full end-to-end flow: PreFlight → brain → confirmation gate → result check
 * Monitors the brain run and reports what candidate it surfaces.
 * Run: cd frontend && npx playwright test e2e/full-flow-monitor.spec.ts --headed --project=chromium
 */
import { test, expect } from '@playwright/test'
import { execSync } from 'child_process'

const BASE = 'http://localhost:5173'
const wait = (ms: number) => new Promise(r => setTimeout(r, ms))

test.use({ baseURL: BASE, viewport: { width: 1400, height: 900 }, headless: false })
test.setTimeout(600_000) // 10 min

async function login(page: any) {
  await page.goto(`${BASE}/`)
  await wait(1000)
  if (await page.locator('input[type="password"]').isVisible().catch(() => false)) {
    await page.fill('input[placeholder*="user" i], input[type="text"]', 'admin')
    await page.fill('input[type="password"]', 'admin')
    await page.locator('button[type="submit"], button:has-text("Sign in")').click()
    await wait(3000)
  }
}

function dbQuery(sql: string) {
  try {
    return execSync(
      `docker exec info-broker-postgres-1 psql -U user -d info_broker -t -c "${sql.replace(/"/g, '\\"')}"`,
      { encoding: 'utf8' }
    ).trim()
  } catch { return '' }
}

test('full flow: spiderman query → confirmation gate → check result candidate', async ({ page }) => {
  await login(page)
  await wait(2000)
  await page.screenshot({ path: '/tmp/ff-01-start.png' })

  // Submit query
  const textarea = page.locator('textarea').first()
  await expect(textarea).toBeVisible({ timeout: 5000 })
  await textarea.fill('new series with girl in spiderman where man has a shotgun')
  await page.keyboard.press('Enter')
  console.log('[1] Query submitted')

  // Answer PreFlight
  await page.waitForSelector('text=Where did you see or hear', { timeout: 15000 })
  console.log('[2] PreFlight appeared')
  await page.screenshot({ path: '/tmp/ff-02-preflight.png' })

  const ytBtn = page.locator('button:has-text("YouTube")').first()
  if (await ytBtn.isVisible()) await ytBtn.click()
  else { await page.locator('input[placeholder*="answer"]').fill('YouTube'); await page.locator('button:has-text("Send")').click() }
  await wait(2000)

  const adBtn = page.locator('button:has-text("An ad")').first()
  if (await adBtn.isVisible()) await adBtn.click()
  console.log('[3] Answered: YouTube → An ad')
  await wait(2000)
  await page.screenshot({ path: '/tmp/ff-03-answered.png' })

  // Get the run_id from DB (most recently created agent_is run)
  await wait(3000)
  const runId = dbQuery(
    "SELECT id FROM pipeline_runs WHERE trigger_type='agent_is' AND status IN ('running','queued') ORDER BY started_at DESC LIMIT 1"
  ).split('\n')[0].trim()
  console.log('[4] Brain run_id:', runId)

  // Poll for confirmation gate or result
  console.log('[5] Waiting for brain to complete (up to 9 min)...')
  let confirmCard = false
  let resultFound = false
  let candidate = ''
  let elapsed = 0

  while (elapsed < 540) {
    await wait(10000)
    elapsed += 10

    // Check confirm card in UI
    const cardVisible = await page.locator('text=RESULT FOUND — PLEASE CONFIRM').first().isVisible().catch(() => false)
    if (cardVisible) {
      confirmCard = true
      candidate = await page.locator('text=RESULT FOUND — PLEASE CONFIRM').locator('..').locator('div[style*="fontWeight"]').first().textContent().catch(() => '') ?? ''
      console.log(`[${elapsed}s] Confirmation card appeared! Candidate: ${candidate}`)
      await page.screenshot({ path: '/tmp/ff-confirm-card.png' })
      break
    }

    // Check DB for completed run
    if (runId) {
      const status = dbQuery(`SELECT status FROM pipeline_runs WHERE id='${runId}'`).trim()
      if (status === 'confirm_pending') {
        confirmCard = true
        const row = dbQuery(
          `SELECT confirmation_data->>'result' FROM pipeline_runs WHERE id='${runId}'`
        )
        console.log(`[${elapsed}s] Gate fired (DB confirm_pending) — checking via polling`)
        break
      }
      if (status === 'succeeded' || status === 'failed') {
        resultFound = true
        const finding = dbQuery(
          `SELECT findings->0->>'title' FROM research_trails WHERE run_id='${runId}'`
        ).trim()
        console.log(`[${elapsed}s] Brain completed: status=${status}, top finding="${finding}"`)
        break
      }
    }

    if (elapsed % 30 === 0) {
      await page.screenshot({ path: `/tmp/ff-wait-${elapsed}s.png` })
      console.log(`[${elapsed}s] Still waiting... (brain running)`)
    }
  }

  // If confirmation card appeared, click "No, try another" if Spider-Noir, else "Yes"
  if (confirmCard) {
    const cardText = await page.locator('text=RESULT FOUND — PLEASE CONFIRM').locator('..').textContent().catch(() => '')
    console.log('[CONFIRM] Card text:', cardText?.slice(0, 200))

    const isSpiderNoir = (cardText ?? '').toLowerCase().includes('spider-noir') || (cardText ?? '').toLowerCase().includes('spider noir')
    if (isSpiderNoir) {
      console.log('[CONFIRM] Spider-Noir detected → clicking "No, try another"')
      await page.locator('button:has-text("No, try another")').first().click()
      await wait(3000)
      console.log('[CONFIRM] Rejection sent — brain should re-run with rejected list')

      // Wait for re-run confirmation
      let elapsed2 = 0
      while (elapsed2 < 540) {
        await wait(10000)
        elapsed2 += 10
        const card2 = await page.locator('text=RESULT FOUND — PLEASE CONFIRM').first().isVisible().catch(() => false)
        if (card2) {
          const text2 = await page.locator('text=RESULT FOUND — PLEASE CONFIRM').locator('..').textContent().catch(() => '')
          console.log(`[RERUN ${elapsed2}s] New confirmation card: ${text2?.slice(0, 200)}`)
          await page.screenshot({ path: '/tmp/ff-rerun-confirm.png' })
          break
        }
        if (elapsed2 % 30 === 0) console.log(`[RERUN ${elapsed2}s] Waiting for re-run result...`)
      }
    } else {
      console.log('[CONFIRM] Candidate is NOT Spider-Noir:', cardText?.slice(0, 100))
      await page.screenshot({ path: '/tmp/ff-non-spidernoir.png' })
    }
  }

  await page.screenshot({ path: '/tmp/ff-final.png', fullPage: false })

  // Check final DB state
  if (runId) {
    const finalStatus = dbQuery(`SELECT status FROM pipeline_runs WHERE id='${runId}'`).trim()
    const topFinding = dbQuery(`SELECT findings->0->>'title' FROM research_trails WHERE run_id='${runId}'`).trim()
    console.log('\n=== FINAL STATE ===')
    console.log('Run status:', finalStatus)
    console.log('Top finding:', topFinding || '(no trail yet — awaiting confirmation)')
  }

  expect(confirmCard || resultFound, 'Brain should complete and either gate or deliver a result').toBe(true)
})
