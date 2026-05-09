/**
 * Demo video — full HD with subtitle overlays and deep research.
 *
 * Run:
 *   cd frontend && npx playwright test e2e/demo-video.spec.ts --headed --project=chromium
 */
import { test, expect } from '@playwright/test'

test.use({
  video: { mode: 'on', size: { width: 1920, height: 1080 } },
  viewport: { width: 1920, height: 1080 },
})

test.setTimeout(900_000) // 15 minutes

const wait = (ms: number) => new Promise(r => setTimeout(r, ms))

/** Inject a subtitle overlay at the bottom of the viewport */
async function subtitle(page: import('@playwright/test').Page, text: string, durationMs = 4000) {
  await page.evaluate(([t, d]) => {
    const existing = document.getElementById('demo-subtitle')
    if (existing) existing.remove()
    const el = document.createElement('div')
    el.id = 'demo-subtitle'
    el.textContent = t
    Object.assign(el.style, {
      position: 'fixed', bottom: '40px', left: '50%', transform: 'translateX(-50%)',
      background: 'rgba(0,0,0,0.85)', color: '#fff', padding: '12px 32px',
      borderRadius: '8px', fontSize: '20px', fontFamily: 'system-ui, sans-serif',
      fontWeight: '500', zIndex: '99999', maxWidth: '80%', textAlign: 'center',
      letterSpacing: '0.3px', lineHeight: '1.4',
      boxShadow: '0 4px 24px rgba(0,0,0,0.5)', border: '1px solid rgba(255,255,255,0.1)',
    })
    document.body.appendChild(el)
    setTimeout(() => el.remove(), Number(d))
  }, [text, String(durationMs)])
  await wait(Math.min(durationMs, 3000))
}

test('info-broker full feature demo — HD with subtitles', async ({ page }) => {

  // ══════════════════════════════════════════════════════════════════════════
  // 1. LOGIN
  // ══════════════════════════════════════════════════════════════════════════
  await page.goto('/login')
  await subtitle(page, 'info-broker — Intelligent Research Platform', 3000)
  await page.getByPlaceholder(/username/i).fill('admin')
  await wait(400)
  await page.getByPlaceholder(/password/i).fill('admin')
  await wait(400)
  await page.getByRole('button', { name: /login|sign in/i }).click()
  await page.waitForURL(url => !url.pathname.includes('/login'), { timeout: 10_000 })
  await wait(1500)

  // ══════════════════════════════════════════════════════════════════════════
  // 2. AGENT CHAT — show IS toggle, file upload zone
  // ══════════════════════════════════════════════════════════════════════════
  await page.goto('/')
  await page.waitForLoadState('networkidle')
  await subtitle(page, 'Agent Chat — Intelligent Search enabled by default', 3500)
  await subtitle(page, 'File upload zone supports CSV, Excel, PDF, DOCX, TXT', 3500)

  // ══════════════════════════════════════════════════════════════════════════
  // 3. DEEP RESEARCH QUERY — designed for 5-level depth
  // ══════════════════════════════════════════════════════════════════════════
  const query = 'Investigate the competitive landscape of AI agent memory systems in 2026: ' +
    'compare Mem0 vs Zep vs Letta vs Cognee architectures, benchmark accuracy, ' +
    'identify the founders and their backgrounds, analyze funding rounds, ' +
    'and predict which will dominate enterprise adoption by 2027'

  await subtitle(page, 'Sending a complex multi-faceted research query...', 3000)
  const textarea = page.getByPlaceholder(/ask info-broker/i)
  // Type slowly for dramatic effect
  for (const char of query) {
    await textarea.press(char === ' ' ? 'Space' : char)
    await wait(15) // fast typing animation
  }
  await wait(1500)
  await subtitle(page, 'Query classified as COMPLEX (score +5) — triggers deep research', 3000)
  await textarea.press('Enter')
  await wait(2000)

  // ══════════════════════════════════════════════════════════════════════════
  // 4. WATCH RESEARCH GRAPH BUILD IN REAL-TIME
  // ══════════════════════════════════════════════════════════════════════════
  await subtitle(page, 'IS Brain spawning — recursive tree search with 50+ MCP tools', 4000)

  // Wait for run tab to appear
  await expect(async () => {
    const count = await page.locator('text=/Research:|competitive|memory/i').count()
    expect(count).toBeGreaterThan(0)
  }).toPass({ timeout: 30_000 })

  // Click latest run tab to see the graph
  const runTab = page.locator('text=/Research:|Agent Default/').last()
  if (await runTab.isVisible()) {
    await runTab.click()
    await wait(2000)
  }

  await subtitle(page, 'Live Research Flow — tool calls stream as a DAG graph', 5000)
  await wait(5000)

  // Show the graph building for an extended period
  await subtitle(page, 'Strategy: Person Investigation + Competitive Intelligence sub-strategy', 5000)
  await wait(8000)

  await subtitle(page, 'Selectors: company names, founder profiles, funding data, benchmarks', 5000)
  await wait(8000)

  await subtitle(page, 'Techniques: DDG search, web crawl, LinkedIn, SEC filings, Google News', 5000)
  await wait(8000)

  // Scroll to see more of the graph if it extends
  await page.mouse.wheel(0, 200)
  await wait(3000)
  await page.mouse.wheel(0, 200)
  await wait(3000)

  await subtitle(page, 'Auto-scaling graph — nodes shrink as the tree grows deeper', 4000)
  await wait(5000)

  // ══════════════════════════════════════════════════════════════════════════
  // 5. WAIT FOR RESEARCH TO COMPLETE
  // ══════════════════════════════════════════════════════════════════════════
  await subtitle(page, 'Waiting for research to complete...', 3000)

  for (let i = 0; i < 40; i++) {
    await wait(5000)
    const bodyText = await page.locator('body').innerText()
    if (bodyText.includes('succeeded') || bodyText.includes('Go Deeper') || bodyText.includes('Findings')) {
      console.log('[DEMO] Research complete')
      break
    }
    if (i % 5 === 0 && i > 0) {
      await subtitle(page, `Research in progress... (${i * 5}s elapsed)`, 3000)
    }
    console.log(`[DEMO] Polling ${i + 1}/40`)
  }
  await wait(2000)

  // ══════════════════════════════════════════════════════════════════════════
  // 6. SHOW RESEARCH RESULTS — scroll through findings
  // ══════════════════════════════════════════════════════════════════════════
  await subtitle(page, 'Research complete — browsing findings with confidence scores', 4000)
  await page.mouse.wheel(0, 400)
  await wait(3000)
  await page.mouse.wheel(0, 400)
  await wait(3000)
  await page.mouse.wheel(0, 400)
  await wait(3000)

  // ══════════════════════════════════════════════════════════════════════════
  // 7. ANALYZE — entity extraction + relationship mapping
  // ══════════════════════════════════════════════════════════════════════════
  // Scroll back up to find Analyze button
  await page.mouse.wheel(0, -1200)
  await wait(2000)

  const analyzeBtn = page.locator('text=/Analyze|Re-Analyze/').first()
  if (await analyzeBtn.isVisible()) {
    await subtitle(page, 'Running Intelligence Analysis — entity extraction + relationship mapping', 5000)
    await analyzeBtn.click()
    await wait(20000) // Analysis takes time
    await subtitle(page, 'Analysis complete — entities, relationships, insights extracted', 4000)
  }

  // Scroll to see analysis results
  await page.mouse.wheel(0, 400)
  await wait(3000)
  await page.mouse.wheel(0, 400)
  await wait(3000)

  // ══════════════════════════════════════════════════════════════════════════
  // 8. SHOW ACTION BUTTONS — Go Deeper, Save Pipeline, Export
  // ══════════════════════════════════════════════════════════════════════════
  await page.mouse.wheel(0, 400)
  await wait(2000)
  await subtitle(page, 'Action buttons: Go Deeper, Re-Analyze, Save Pipeline, Export (PDF/CSV/Excel)', 5000)
  await wait(3000)

  // ══════════════════════════════════════════════════════════════════════════
  // 9. KNOWLEDGE GRAPH PAGE
  // ══════════════════════════════════════════════════════════════════════════
  await page.goto('/knowledge')
  await wait(2000)
  await subtitle(page, 'Knowledge Graph — Neo4j-backed entity + relationship explorer', 4000)
  await wait(3000)
  await page.mouse.wheel(0, 300)
  await wait(2000)

  // ══════════════════════════════════════════════════════════════════════════
  // 10. LIVE PROCESSES PAGE
  // ══════════════════════════════════════════════════════════════════════════
  await page.goto('/admin/processes')
  await wait(2000)
  await subtitle(page, 'Live Processes — MCP tool call observability and session tracking', 4000)
  await wait(3000)

  // ══════════════════════════════════════════════════════════════════════════
  // 11. PLUGINS PAGE
  // ══════════════════════════════════════════════════════════════════════════
  await page.goto('/plugins')
  await wait(2000)
  await subtitle(page, 'Plugin Gallery — 70+ pipeline nodes across source, enrich, score, filter, export', 4000)
  await wait(2000)
  await page.mouse.wheel(0, 500)
  await wait(3000)
  await page.mouse.wheel(0, 500)
  await wait(2000)

  // ══════════════════════════════════════════════════════════════════════════
  // 12. SETTINGS PAGE
  // ══════════════════════════════════════════════════════════════════════════
  await page.goto('/settings')
  await wait(2000)
  await subtitle(page, 'Settings — LLM model tiers, API keys, core configuration', 4000)
  await wait(3000)

  // ══════════════════════════════════════════════════════════════════════════
  // 13. BACK TO AGENT — final view
  // ══════════════════════════════════════════════════════════════════════════
  await page.goto('/')
  await wait(2000)
  await subtitle(page, 'info-broker — Nation-state grade OSINT research platform', 5000)
  await wait(2000)

  await subtitle(page, '1,000+ tests | 70+ nodes | 5-signal memory fusion | 38 domain strategies', 5000)
  await wait(3000)

  await subtitle(page, 'Built with Claude Code + Superpowers', 4000)
  await wait(3000)

  await page.screenshot({ path: 'test-results/demo-final.png', fullPage: true })
  await wait(2000)
})
