/**
 * Demo video — full HD with subtitle overlays, all features shown.
 *
 * Run:
 *   cd frontend && npx playwright test e2e/demo-video.spec.ts --headed --project=chromium
 */
import { test } from '@playwright/test'

test.use({
  video: { mode: 'on', size: { width: 1920, height: 1080 } },
  viewport: { width: 1920, height: 1080 },
})

test.setTimeout(1_200_000) // 20 minutes

const wait = (ms: number) => new Promise(r => setTimeout(r, ms))

/** Show a subtitle overlay at the bottom of the viewport */
async function subtitle(page: import('@playwright/test').Page, text: string, durationMs = 4000) {
  await page.evaluate(([t, d]) => {
    const existing = document.getElementById('demo-subtitle')
    if (existing) existing.remove()
    const el = document.createElement('div')
    el.id = 'demo-subtitle'
    el.textContent = t as string
    Object.assign(el.style, {
      position: 'fixed', bottom: '40px', left: '50%', transform: 'translateX(-50%)',
      background: 'rgba(0,0,0,0.88)', color: '#fff', padding: '14px 36px',
      borderRadius: '8px', fontSize: '21px', fontFamily: 'system-ui, sans-serif',
      fontWeight: '500', zIndex: '99999', maxWidth: '82%', textAlign: 'center',
      letterSpacing: '0.3px', lineHeight: '1.45',
      boxShadow: '0 4px 28px rgba(0,0,0,0.55)', border: '1px solid rgba(255,255,255,0.12)',
    })
    document.body.appendChild(el)
    setTimeout(() => el.remove(), Number(d))
  }, [text, String(durationMs)])
  await wait(Math.min(durationMs, 3500))
}

/** Scroll the results panel (right column scroll area) */
async function scrollResults(page: import('@playwright/test').Page, deltaY: number) {
  // Hover over the center-right area where the results panel lives
  await page.mouse.move(1300, 540)
  await page.mouse.wheel(0, deltaY)
  await wait(600)
}

/** Wait until body text contains any of the given strings */
async function waitForText(
  page: import('@playwright/test').Page,
  matches: string[],
  timeoutMs = 600_000,
  pollMs = 5000,
): Promise<boolean> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const body = await page.locator('body').innerText().catch(() => '')
    if (matches.some(m => body.includes(m))) return true
    await wait(pollMs)
  }
  return false
}

test('info-broker full feature demo — HD with subtitles', async ({ page }) => {

  // ══════════════════════════════════════════════════════════════════════════
  // 1. LOGIN
  // ══════════════════════════════════════════════════════════════════════════
  await page.goto('/login')
  await wait(1000)
  await subtitle(page, 'info-broker — Nation-state grade OSINT Research Platform', 3500)

  await page.getByPlaceholder(/username/i).fill('admin')
  await wait(300)
  await page.getByPlaceholder(/password/i).fill('admin')
  await wait(300)
  await page.getByRole('button', { name: /login|sign in/i }).click()
  await page.waitForURL(url => !url.pathname.includes('/login'), { timeout: 10_000 })
  await wait(1500)

  // ══════════════════════════════════════════════════════════════════════════
  // 2. HOME — Agent Chat
  // ══════════════════════════════════════════════════════════════════════════
  await page.goto('/')
  await page.waitForLoadState('networkidle')
  await wait(1000)
  await subtitle(page, 'Agent Chat — Intelligent Search (IS) enabled by default', 3500)
  await subtitle(page, 'File upload zone supports CSV, Excel, PDF, DOCX, TXT as research context', 3500)

  // ══════════════════════════════════════════════════════════════════════════
  // 3. TYPE DEEP RESEARCH QUERY
  // ══════════════════════════════════════════════════════════════════════════
  const query =
    'Investigate the competitive landscape of AI agent memory systems in 2026: ' +
    'compare Mem0 vs Zep vs Letta vs Cognee architectures, benchmark accuracy, ' +
    'identify the founders and their backgrounds, analyze funding rounds, ' +
    'and predict which will dominate enterprise adoption by 2027'

  await subtitle(page, 'Sending a complex multi-faceted deep research query…', 3000)
  const textarea = page.getByPlaceholder(/ask info-broker/i)
  for (const char of query) {
    await textarea.press(char === ' ' ? 'Space' : char)
    await wait(12)
  }
  await wait(1200)
  await subtitle(page, 'Query classified COMPLEX (score 5+) — depth 5, 40 branches, no cap', 3500)
  await textarea.press('Enter')
  await wait(2500)

  // ══════════════════════════════════════════════════════════════════════════
  // 4. WATCH RESEARCH FLOW GRAPH BUILD
  // ══════════════════════════════════════════════════════════════════════════
  await subtitle(page, 'IS Brain spawning — Claude Code subprocess with 50+ MCP tools', 4500)
  await wait(8000)

  await subtitle(page, 'Live Research Flow — tool calls streaming as a real-time DAG graph', 5000)
  await wait(10000)

  await subtitle(page, 'Strategy selected via LLM — Competitive Intelligence sub-strategy', 5000)
  await wait(10000)

  await subtitle(page, 'Techniques: DDG search → web crawl → entity extraction → relationship mapping', 5000)
  await wait(8000)

  // Scroll to see lower part of graph
  await page.mouse.move(1300, 540)
  await page.mouse.wheel(0, 400)
  await wait(4000)
  await page.mouse.wheel(0, 400)
  await wait(4000)
  await subtitle(page, 'Auto-scaling graph — nodes shrink as research tree grows deeper', 4000)
  await wait(5000)
  await page.mouse.wheel(0, -800)
  await wait(3000)

  // ══════════════════════════════════════════════════════════════════════════
  // 5. WAIT FOR RESEARCH TO COMPLETE
  // ══════════════════════════════════════════════════════════════════════════
  await subtitle(page, 'Research running — recursive branches resolving in parallel…', 3000)

  let elapsed = 0
  const pollInterval = 8000
  const maxWait = 600_000 // 10 min
  let done = false
  while (elapsed < maxWait) {
    await wait(pollInterval)
    elapsed += pollInterval
    const body = await page.locator('body').innerText().catch(() => '')
    if (
      body.includes('Intelligent Search') && body.includes('succeeded') ||
      body.includes('FINDINGS') ||
      body.includes('Go Deeper') ||
      body.includes('Analyze')
    ) {
      done = true
      console.log(`[DEMO] Research complete after ~${Math.round(elapsed / 1000)}s`)
      break
    }
    if (elapsed % 40000 === 0) {
      await subtitle(page, `Research in progress… (${Math.round(elapsed / 1000)}s elapsed)`, 3000)
    }
    console.log(`[DEMO] Waiting for research… ${Math.round(elapsed / 1000)}s`)
  }

  if (!done) {
    console.log('[DEMO] Timed out waiting for research — continuing anyway')
  }
  await wait(2000)

  // ══════════════════════════════════════════════════════════════════════════
  // 6. FINDINGS — scroll through results
  // ══════════════════════════════════════════════════════════════════════════
  await subtitle(page, 'Research complete — findings with confidence scores and source URLs', 4500)
  await scrollResults(page, 300)
  await wait(2500)
  await scrollResults(page, 400)
  await wait(2500)
  await subtitle(page, 'Each finding shows confidence %, source tool, and clickable URL', 4000)
  await scrollResults(page, 400)
  await wait(2500)
  await scrollResults(page, 400)
  await wait(2500)

  // ══════════════════════════════════════════════════════════════════════════
  // 7. INVESTIGATION BREAKDOWN — SCORECARD
  // ══════════════════════════════════════════════════════════════════════════
  await subtitle(page, 'Investigation Breakdown — per-strategy scorecard with A–F grades', 4500)
  await scrollResults(page, 400)
  await wait(2000)
  await scrollResults(page, 400)
  await wait(2000)

  // Expand the scorecard section
  const scorecardToggle = page.locator('button', { hasText: /Investigation Breakdown/ }).first()
  if (await scorecardToggle.isVisible({ timeout: 3000 }).catch(() => false)) {
    await scorecardToggle.click()
    await wait(1500)
    await subtitle(page, 'Strategy grade, tactic yield rates, and per-technique performance', 4000)
    await scrollResults(page, 300)
    await wait(2500)
    await scrollResults(page, 300)
    await wait(2500)
  } else {
    await subtitle(page, 'Scorecard grades each strategy, tactic, and tool automatically', 4000)
    await wait(3000)
  }

  // ══════════════════════════════════════════════════════════════════════════
  // 8. GO DEEPER + SAVE PIPELINE (pre-analysis)
  // ══════════════════════════════════════════════════════════════════════════
  await subtitle(page, 'Go Deeper and Save Pipeline always available after findings', 4500)
  await scrollResults(page, 500)
  await wait(2000)
  await scrollResults(page, 500)
  await wait(2000)

  const goDeeperBtn = page.locator('button', { hasText: /Go Deeper/ }).first()
  const savePipelineBtn = page.locator('button', { hasText: /Save Pipeline/ }).first()
  if (await goDeeperBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
    await subtitle(page, 'Go Deeper — spawns a new IS run using current findings as leads', 4000)
    await wait(3000)
  }
  if (await savePipelineBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
    await subtitle(page, 'Save Pipeline — persists this research flow as a reusable pipeline', 4000)
    await wait(3000)
  }

  // ══════════════════════════════════════════════════════════════════════════
  // 9. ANALYZE — entity extraction + relationship mapping
  // ══════════════════════════════════════════════════════════════════════════
  // Scroll up to find Analyze button
  await page.mouse.move(1300, 540)
  await page.mouse.wheel(0, -3000)
  await wait(2000)

  const analyzeBtn = page.locator('button', { hasText: /^Analyze$/ }).first()
  const analyzeVisible = await analyzeBtn.isVisible({ timeout: 5000 }).catch(() => false)

  if (analyzeVisible) {
    await subtitle(page, 'Running Intelligence Analysis — entity extraction + relationship mapping', 5000)
    await analyzeBtn.scrollIntoViewIfNeeded()
    await wait(500)
    await analyzeBtn.click()
    await wait(2000)
    await subtitle(page, 'Analyzer running in background — extracting entities, relationships, insights', 5000)

    // Wait for analysis to complete (up to 3 minutes)
    const analysisComplete = await waitForText(
      page,
      ['ENTITIES', 'RELATIONSHIPS', 'INSIGHTS', 'Re-Analyze', 'NEXT STEPS'],
      180_000,
      5000,
    )

    if (analysisComplete) {
      await subtitle(page, 'Analysis complete — entities, relationships, strategic insights extracted', 4500)
      await wait(2000)
    } else {
      await subtitle(page, 'Analysis running — results will appear when complete', 3000)
      await wait(2000)
    }
  } else {
    await subtitle(page, 'Analysis runs on demand — extracts entities and relationships from findings', 4000)
    await wait(3000)
  }

  // ══════════════════════════════════════════════════════════════════════════
  // 10. ANALYSIS RESULTS — entities, relationships, insights
  // ══════════════════════════════════════════════════════════════════════════
  await subtitle(page, 'Analysis results — grouped entities by type', 4000)
  await scrollResults(page, 400)
  await wait(2500)
  await scrollResults(page, 400)
  await wait(2500)
  await subtitle(page, 'Relationship graph — who funds whom, who competes with whom', 4000)
  await scrollResults(page, 400)
  await wait(2500)
  await subtitle(page, 'Strategic insights + actionable recommendations', 4000)
  await scrollResults(page, 400)
  await wait(2500)
  await scrollResults(page, 400)
  await wait(2500)

  // ══════════════════════════════════════════════════════════════════════════
  // 11. NEXT STEPS — Go Deeper, Re-Analyze, Save Pipeline, Export
  // ══════════════════════════════════════════════════════════════════════════
  await subtitle(page, 'NEXT STEPS: Go Deeper, Re-Analyze, Save Pipeline, Export (PDF/CSV/Excel)', 5000)
  await scrollResults(page, 400)
  await wait(2000)
  await scrollResults(page, 400)
  await wait(3000)

  // Hover over Export to show dropdown without triggering download
  const exportBtn = page.locator('button', { hasText: /^Export$/ }).first()
  if (await exportBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
    await exportBtn.hover()
    await wait(500)
    await exportBtn.click()
    await wait(2000)
    await subtitle(page, 'Export findings as PDF report, CSV dataset, or multi-sheet Excel', 4000)
    await wait(2500)
    // Close export dropdown
    await page.keyboard.press('Escape')
    await wait(500)
  }

  // ══════════════════════════════════════════════════════════════════════════
  // 12. PERFORMANCE DASHBOARD — global scorecard
  // ══════════════════════════════════════════════════════════════════════════
  await page.goto('/performance')
  await page.waitForLoadState('networkidle')
  await wait(1500)
  await subtitle(page, 'Global Performance Dashboard — aggregate grades across all research runs', 4500)
  await wait(3000)
  await subtitle(page, 'Tool Leaderboard — A–F grades per MCP tool, error rates, total runs', 4500)
  await page.mouse.move(960, 540)
  await page.mouse.wheel(0, 400)
  await wait(2500)
  await subtitle(page, 'Tactic summary — which investigation tactics yield the best results', 4000)
  await page.mouse.wheel(0, 400)
  await wait(2500)
  await page.mouse.wheel(0, 400)
  await wait(2000)

  // ══════════════════════════════════════════════════════════════════════════
  // 13. KNOWLEDGE GRAPH
  // ══════════════════════════════════════════════════════════════════════════
  await page.goto('/knowledge')
  await page.waitForLoadState('networkidle')
  await wait(1500)
  await subtitle(page, 'Knowledge Graph — Neo4j-backed entity + relationship explorer', 4000)
  await wait(3000)
  await page.mouse.move(960, 540)
  await page.mouse.wheel(0, 400)
  await wait(2500)
  await page.mouse.wheel(0, 400)
  await wait(2000)

  // ══════════════════════════════════════════════════════════════════════════
  // 14. LIVE PROCESSES
  // ══════════════════════════════════════════════════════════════════════════
  await page.goto('/admin/processes')
  await page.waitForLoadState('networkidle')
  await wait(1500)
  await subtitle(page, 'Live Processes — MCP tool call observability and session tracking', 4000)
  await wait(3000)

  // ══════════════════════════════════════════════════════════════════════════
  // 15. PLUGINS PAGE
  // ══════════════════════════════════════════════════════════════════════════
  await page.goto('/plugins')
  await page.waitForLoadState('networkidle')
  await wait(1500)
  await subtitle(page, 'Plugin Gallery — 70+ pipeline nodes across source, enrich, score, filter, export', 4000)
  await wait(2000)
  await page.mouse.move(960, 540)
  await page.mouse.wheel(0, 500)
  await wait(2500)
  await page.mouse.wheel(0, 500)
  await wait(2500)
  await page.mouse.wheel(0, 500)
  await wait(2000)

  // ══════════════════════════════════════════════════════════════════════════
  // 16. SETTINGS
  // ══════════════════════════════════════════════════════════════════════════
  await page.goto('/settings')
  await page.waitForLoadState('networkidle')
  await wait(1500)
  await subtitle(page, 'Settings — LLM model tiers, API keys, Claude Code authentication', 4000)
  await wait(3000)

  // ══════════════════════════════════════════════════════════════════════════
  // 17. FINAL — back to home
  // ══════════════════════════════════════════════════════════════════════════
  await page.goto('/')
  await page.waitForLoadState('networkidle')
  await wait(1500)

  await subtitle(page, 'info-broker — Nation-state grade OSINT research platform', 5000)
  await wait(2000)
  await subtitle(page, '1,000+ tests  |  70+ nodes  |  5-signal memory fusion  |  38 domain strategies', 5000)
  await wait(2000)
  await subtitle(page, 'Unlimited research depth  |  Auto scorecard  |  Global performance analytics', 5000)
  await wait(2000)
  await subtitle(page, 'Built with Claude Code + Superpowers', 4000)
  await wait(3000)

  await page.screenshot({ path: 'test-results/demo-final.png', fullPage: false })
  await wait(1500)
})
