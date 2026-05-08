/**
 * Demo video recording script — captures a full walkthrough of info-broker features.
 *
 * Run:
 *   cd frontend && npx playwright test e2e/demo-video.spec.ts --headed --project=chromium
 *
 * Prerequisites:
 *   - Full stack running: docker compose up -d
 *   - ANTHROPIC_API_KEY set in the API container
 *
 * Output:
 *   - Video saved to test-results/ (Playwright default output dir)
 *   - Final screenshot at test-results/demo-final.png
 */
import { test, expect } from '@playwright/test'

// Slow mode — viewer can follow
test.use({
  video: 'on',
  viewport: { width: 1440, height: 900 },
})

test.setTimeout(600_000) // 10 minutes

const wait = (ms: number) => new Promise(r => setTimeout(r, ms))

test('info-broker full feature demo', async ({ page }) => {
  // ── 1. LOGIN ──────────────────────────────────────────────────────────────
  await page.goto('/login')
  await wait(1500)
  await page.getByPlaceholder(/username/i).fill('admin')
  await wait(500)
  await page.getByPlaceholder(/password/i).fill('admin')
  await wait(500)
  await page.getByRole('button', { name: /login|sign in/i }).click()
  await page.waitForURL(url => !url.pathname.includes('/login'), { timeout: 10_000 })
  await wait(2000)

  // ── 2. AGENT CHAT — IS toggle is ON by default ───────────────────────────
  await page.goto('/')
  await page.waitForLoadState('networkidle')
  await wait(2000)

  // ── 3. FILE UPLOAD — show the upload zone ────────────────────────────────
  // The drop zone is visible in the chat input area; just pause so viewers see it
  await wait(1500)

  // ── 4. SEND IS RESEARCH QUERY ────────────────────────────────────────────
  const textarea = page.getByPlaceholder(/ask info-broker/i)
  await textarea.fill('Who are the top AI agent frameworks in 2026 and who created them?')
  await wait(1000)
  await textarea.press('Enter')
  await wait(3000) // Let the research start and a run tab appear

  // ── 5. SHOW RESEARCH IN PROGRESS — click into the new run tab ────────────
  // Wait for a run tab to appear (text contains "Research:" prefix or query words)
  await expect(async () => {
    const count = await page.locator('text=/Research:|AI agent/').count()
    expect(count).toBeGreaterThan(0)
  }).toPass({ timeout: 30_000 })

  const runTab = page.locator('text=/Research:|AI agent/').last()
  await runTab.click()
  await wait(3000)

  // Let viewers watch tool calls / the ResearchFlow graph for a moment
  await wait(15000)

  // ── 6. NAVIGATE TO PIPELINE BUILDER ──────────────────────────────────────
  const pipelineLink = page.locator('text=Pipeline').first()
  if (await pipelineLink.isVisible()) {
    await pipelineLink.click()
    await wait(3000)
  }

  // ── 7. NAVIGATE BACK TO AGENT — watch results accumulate ─────────────────
  await page.goto('/')
  await page.waitForLoadState('networkidle')
  await wait(3000)

  // Re-open the run tab we were watching
  const runTabAgain = page.locator('text=/Research:|AI agent/').last()
  if (await runTabAgain.isVisible()) {
    await runTabAgain.click()
    await wait(2000)
  }

  // ── 8. WAIT FOR RESEARCH TO COMPLETE ─────────────────────────────────────
  // Poll every 5 s for up to 2.5 minutes (30 × 5 000 ms)
  for (let i = 0; i < 30; i++) {
    await wait(5000)
    const bodyText = await page.locator('body').innerText()
    if (
      bodyText.includes('succeeded') ||
      bodyText.includes('Findings') ||
      bodyText.includes('Go Deeper')
    ) {
      console.log('[DEMO] Research complete — results visible')
      break
    }
    console.log(`[DEMO] Still waiting for results… (poll ${i + 1}/30)`)
  }
  await wait(2000)

  // ── 9. SHOW RESULTS — scroll through findings ────────────────────────────
  await page.mouse.wheel(0, 300)
  await wait(2000)
  await page.mouse.wheel(0, 300)
  await wait(2000)

  // ── 10. CLICK ANALYZE ────────────────────────────────────────────────────
  const analyzeBtn = page.locator('text=/Analyze|Re-Analyze/').first()
  if (await analyzeBtn.isVisible()) {
    await analyzeBtn.click()
    await wait(15000) // Wait for analysis to run
  }

  // ── 11. SHOW ANALYSIS RESULTS ────────────────────────────────────────────
  await page.mouse.wheel(0, 300)
  await wait(3000)

  // ── 12. NAVIGATE TO KNOWLEDGE GRAPH ──────────────────────────────────────
  await page.goto('/knowledge')
  await wait(3000)
  await page.mouse.wheel(0, 200)
  await wait(2000)

  // ── 13. NAVIGATE TO LIVE PROCESSES ───────────────────────────────────────
  await page.goto('/admin/processes')
  await wait(3000)
  await page.mouse.wheel(0, 200)
  await wait(2000)

  // ── 14. NAVIGATE TO PLUGINS ──────────────────────────────────────────────
  await page.goto('/plugins')
  await wait(3000)
  await page.mouse.wheel(0, 300)
  await wait(2000)

  // ── 15. NAVIGATE TO SETTINGS ─────────────────────────────────────────────
  await page.goto('/settings')
  await wait(3000)
  await page.mouse.wheel(0, 200)
  await wait(2000)

  // ── 16. NAVIGATE BACK TO AGENT ───────────────────────────────────────────
  await page.goto('/')
  await wait(3000)

  // ── 15. FINAL SCREENSHOT ─────────────────────────────────────────────────
  await page.screenshot({ path: 'test-results/demo-final.png', fullPage: true })
  await wait(3000)
})
