/**
 * Demo Feature Tour — records a video walking through the headline features:
 *   1. Research (preflight → engine_v2 → live cards → modal findings)   ← highlight
 *   2. File import + inference (upload doc, ask question, see RAG answer) ← highlight
 *
 * Subtitles are injected as DOM overlays so they appear directly in the
 * recorded video. Playwright writes the WebM to:
 *   test-results/demo-feature-tour-*-chromium/video.webm
 *
 * A sidecar .srt file is also written so the video can be re-encoded with
 * burned-in captions via ffmpeg if desired.
 */
import { test, type Page } from '@playwright/test'
import * as fs from 'node:fs'
import * as path from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const BASE = 'http://localhost:5173'
const SAMPLE_FILE = '/tmp/demo-fileupload-data.txt'

test.use({
  // Google Chrome at 1440×900 — fits comfortably on a 13" / 14" laptop
  // and most external monitors without window-chrome clipping.
  channel: 'chrome',
  video: { mode: 'on', size: { width: 1440, height: 900 } },
  viewport: { width: 1440, height: 900 },
  headless: false,
  launchOptions: {
    // No --auto-open-devtools-for-tabs — Chrome treats the flag's mere
    // presence as ENABLE regardless of =true/=false. Just don't pass it.
    args: ['--window-size=1440,900'],
  },
})

test.setTimeout(900_000) // 15 min

// ----------- subtitle overlay + .srt sidecar -----------

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms))

interface SubtitleEntry { startMs: number; endMs: number; text: string }
const subtitles: SubtitleEntry[] = []
let demoStartMs = 0

function fmtSrtTime(ms: number): string {
  const h = Math.floor(ms / 3_600_000)
  const m = Math.floor((ms % 3_600_000) / 60_000)
  const s = Math.floor((ms % 60_000) / 1000)
  const msPart = ms % 1000
  const p2 = (n: number) => n.toString().padStart(2, '0')
  return `${p2(h)}:${p2(m)}:${p2(s)},${msPart.toString().padStart(3, '0')}`
}

async function subtitle(page: Page, text: string, holdMs = 3500, position: 'top' | 'bottom' = 'bottom') {
  const t = Date.now()
  const startMs = t - demoStartMs
  subtitles.push({ startMs, endMs: startMs + holdMs, text })

  await page.evaluate(({ s, pos }) => {
    let el = document.getElementById('__demo_subtitle__')
    if (!el) {
      el = document.createElement('div')
      el.id = '__demo_subtitle__'
      el.style.cssText = [
        'position:fixed',
        'left:50%',
        'transform:translateX(-50%)',
        'z-index:2147483647',
        'background:rgba(15,15,20,0.92)',
        'color:#ffffff',
        'font:600 19px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif',
        'padding:11px 22px',
        'border-radius:12px',
        'max-width:80vw',
        'text-align:center',
        'box-shadow:0 10px 40px rgba(0,0,0,0.45)',
        'border:1px solid rgba(167,139,250,0.55)',
        'pointer-events:none',
        'white-space:pre-wrap',
      ].join(';')
      document.body.appendChild(el)
    }
    // Re-anchor each call so the position can toggle (typing scenes → top).
    // Bottom uses a larger offset (140px) to clear the chat-input panel
    // and pipeline status strip on /research and /runs.
    el.style.top = pos === 'top' ? '40px' : ''
    el.style.bottom = pos === 'bottom' ? '140px' : ''
    el.textContent = s
  }, { s: text, pos: position })

  await wait(holdMs)
}

async function clearSubtitle(page: Page) {
  await page.evaluate(() => {
    const el = document.getElementById('__demo_subtitle__')
    if (el) el.remove()
  })
}

async function title(page: Page, headline: string, subhead: string, holdMs = 4000) {
  const t = Date.now()
  subtitles.push({ startMs: t - demoStartMs, endMs: t - demoStartMs + holdMs, text: `${headline} — ${subhead}` })
  await page.evaluate(({ h, s }) => {
    let el = document.getElementById('__demo_title__')
    if (!el) {
      el = document.createElement('div')
      el.id = '__demo_title__'
      el.style.cssText = [
        'position:fixed',
        'inset:0',
        'z-index:2147483646',
        'background:radial-gradient(ellipse at center, #1e1535 0%, #050008 70%)',
        'display:flex',
        'flex-direction:column',
        'align-items:center',
        'justify-content:center',
        'color:#ffffff',
        'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif',
        'pointer-events:none',
      ].join(';')
      document.body.appendChild(el)
    }
    el.innerHTML = `
      <div style="font-size:64px;font-weight:700;letter-spacing:-0.02em;color:#fff">${h}</div>
      <div style="font-size:22px;font-weight:400;margin-top:18px;color:#a78bfa;letter-spacing:0.02em">${s}</div>
    `
  }, { h: headline, s: subhead })
  await wait(holdMs)
}

async function clearTitle(page: Page) {
  await page.evaluate(() => {
    const el = document.getElementById('__demo_title__')
    if (el) el.remove()
  })
}

/** Wait for the main content area to actually paint (>= minBytes of text or
 *  >= minNodes elements) before narrating. Prevents the demo from talking
 *  over a still-loading blank page like /plugins or /knowledge. */
async function waitForContent(page: Page, opts: { minNodes?: number; timeoutMs?: number } = {}) {
  const { minNodes = 30, timeoutMs = 8000 } = opts
  await page.waitForLoadState('networkidle', { timeout: timeoutMs }).catch(() => null)
  await page.waitForFunction(
    (min) => document.querySelectorAll('main *, [data-slot], button, [role]').length >= min,
    minNodes,
    { timeout: timeoutMs },
  ).catch(() => null)
  // Small settle for animations
  await new Promise(r => setTimeout(r, 400))
}

/** Scroll the largest scrollable container so off-screen content is visible
 *  in the recording. Returns the total pixels actually scrolled so callers
 *  can fall back to keyboard scrolling if the auto-detect found nothing. */
async function scrollThroughContent(page: Page, totalPx = 800, stepDelay = 1100) {
  // ALWAYS use the page's mouse wheel — it works whether the scrollable
  // element is window or a flex panel, and lets the viewer see the
  // scrollbar move. The previous DOM-walk approach missed flex containers
  // where the overflow-y was on a different ancestor.
  const steps = 5
  const stepPx = Math.round(totalPx / steps)
  for (let i = 0; i < steps; i++) {
    await page.mouse.wheel(0, stepPx)
    await page.waitForTimeout(stepDelay)
  }
  await page.waitForTimeout(stepDelay)
  // Reset both window and any inner scrollables so the next scene starts clean
  await page.evaluate(() => {
    window.scrollTo({ top: 0 })
    document.querySelectorAll<HTMLElement>('*').forEach(el => {
      const s = getComputedStyle(el)
      if (s.overflowY === 'auto' || s.overflowY === 'scroll') el.scrollTop = 0
    })
  })
}

// ----------- helpers -----------

/** Wipe all of the logged-in user's prior uploaded sources so the file-upload
 *  scene starts clean — no library clutter, no scrolling chip list. */
async function cleanupSources(page: Page) {
  try {
    const resp = await page.request.get(`${BASE.replace(':5173', ':8000')}/v3/sources`, {
      headers: { Authorization: `Bearer ${await page.evaluate(() => localStorage.getItem('access_token'))}` },
    })
    if (!resp.ok()) return
    const items = (await resp.json()) as Array<{ id: string }>
    for (const item of items) {
      await page.request.delete(
        `${BASE.replace(':5173', ':8000')}/v3/sources/${item.id}`,
        { headers: { Authorization: `Bearer ${await page.evaluate(() => localStorage.getItem('access_token'))}` } },
      ).catch(() => null)
    }
    console.log(`cleanupSources: removed ${items.length} prior uploads`)
  } catch { /* non-blocking */ }
}

async function login(page: Page) {
  await page.goto(`${BASE}/login`)
  await wait(1500)
  const pw = page.locator('input[type="password"]').first()
  if (await pw.isVisible({ timeout: 2000 }).catch(() => false)) {
    await page.fill('input[type="text"], input[type="email"]', 'admin')
    await pw.fill('admin')
    await page.locator('button[type="submit"]').first().click()
    await page.waitForURL(/\/$|\/research|\/jobs|\/runs|\/dashboard/, { timeout: 8_000 })
  }
}

// ----------- the demo -----------

test('demo feature tour — research + file upload + inference', async ({ page }) => {
  demoStartMs = Date.now()

  // ---- Fail-fast: abort the demo on any obvious issue so we can fix it
  //      and re-record. We catch:
  //        - Browser console errors (filter known noisy ones)
  //        - Failed HTTP requests (5xx) on /v3/* (backend issues)
  //        - Page crashes / WebSocket errors
  const issues: string[] = []
  const fatal = (msg: string) => {
    console.log(`\n🛑 DEMO ABORTED — ${msg}\n`)
    issues.push(msg)
    throw new Error(msg)
  }
  page.on('pageerror', (e) => fatal(`pageerror: ${e.message}`))
  page.on('crash', () => fatal('page crashed'))
  page.on('console', (m) => {
    if (m.type() !== 'error') return
    const text = m.text()
    // ignore known harmless dev-mode warnings
    if (/React Router Future Flag|DevTools|hmr|Download the React DevTools/i.test(text)) return
    // Radix Primitive.button.SlotClone ref warning — dev-only, no prod impact.
    if (/Function components cannot be given refs|SlotClone/i.test(text)) return
    issues.push(`console.error: ${text.slice(0, 200)}`)
  })
  page.on('response', async (r) => {
    if (r.status() < 500) return
    const url = r.url()
    if (!url.includes('/v3/') && !url.includes('/api/')) return
    issues.push(`HTTP ${r.status()}: ${r.request().method()} ${url}`)
  })

  // -- Title card
  await page.goto(BASE)
  await title(page, 'info-broker', 'Live OSINT research with AI assistance · 2026 demo', 4500)
  await clearTitle(page)

  // -- Login (show SSO buttons even if disabled — visually convey the option)
  await page.goto(`${BASE}/login`)
  await wait(1200)
  await subtitle(page, 'Sign in — password, Google, or GitHub SSO', 4000, 'top')
  await wait(2500)
  await login(page)
  await wait(1500)
  await clearSubtitle(page)

  // Clean slate: remove prior uploads so the file-upload scene later
  // is realistic (single new file in an empty library).
  await cleanupSources(page)

  // ===========================================================
  //  DASHBOARD (proper time, not a flyover)
  // ===========================================================
  await page.goto(`${BASE}/dashboard`).catch(() => {})
  await waitForContent(page, { minNodes: 40 })
  await subtitle(page, 'Dashboard — at-a-glance metrics: runs today, success rate, live jobs, errors', 5500)
  await wait(2000)
  await subtitle(page, 'Recent runs table — click any row to inspect the full result', 4500)
  await scrollThroughContent(page, 600, 900)
  await clearSubtitle(page)

  // ===========================================================
  //  PART 1 — RESEARCH (the headline feature)
  // ===========================================================
  await title(page, 'Research', 'The headline feature — Heuer methodology, live cards, modal detail', 4500)
  await clearTitle(page)
  await page.goto(`${BASE}/research`)
  await wait(2000)

  await subtitle(page, 'Research workspace — pipeline · agent chat · live stream', 4000, 'top')
  await subtitle(page,
    "Let's ask: 'Who is the CEO of OpenAI in 2026?'\n" +
    'The agent will pick a strategy, run parallel hypotheses, stream live results.',
    5500,
    'top',
  )

  // Type query — keep subtitle at TOP so the input field stays visible.
  const input = page
    .locator('textarea, input[type="text"]')
    .filter({ hasNot: page.locator('[type="password"]') })
    .first()
  await input.waitFor({ timeout: 5000 })
  await input.click()
  await input.pressSequentially('Who is the CEO of OpenAI in 2026?', { delay: 18 })
  await wait(600)
  await subtitle(page, 'Submitting query...', 1800, 'top')
  await input.press('Enter')

  // Preflight panel appears
  await page.getByText(/intent|strateg|preflight|approach|hypothes|mode|detected/i).first().waitFor({ timeout: 15_000 })
  await wait(1000)
  await subtitle(page,
    'Preflight — the brain proposes investigation strategies.\n' +
    'Each carries a cost estimate. Pick one and click Run.',
    5500,
  )

  const runBtn = page.getByRole('button', { name: /^run$/i }).first()
  await runBtn.click()
  await wait(1500)
  // Note: Run click already sets activeJobId + col1Content via PreflightPanel's
  // onConfirmed callback, so the page is already on the run-results view.
  // Don't try to switch tabs — earlier attempts clicked the wrong element and
  // navigated AWAY from where cards render.
  await subtitle(page, 'Engine v2 launched — Heuer analytic methodology, 4 phases', 4000)

  // Wait for first phase to start
  await wait(3000)
  await subtitle(page,
    'Phase 1 of 4 — SIGNAL EXTRACTION.\n' +
    'The brain parses the query into structured entities & intent.',
    5000,
  )

  await page.waitForFunction(
    () => document.querySelectorAll('[data-slot="node-result-card"]').length >= 3,
    null,
    { timeout: 120_000 },
  ).catch(() => {})

  await subtitle(page,
    'Phase 2 — BROADEN. Three tacticians search in parallel.\n' +
    'Each tool call streams as a card. No raw JSON — readable summaries.',
    6000,
  )

  await page.waitForFunction(
    () => document.querySelectorAll('[data-slot="node-result-card"]').length >= 8,
    null,
    { timeout: 90_000 },
  ).catch(() => {})

  await subtitle(page, 'Cards arrive live — click any one for the full result.', 3500)

  // Find a run_web_search card to click
  const titles = await page.locator('[data-slot="node-result-card"]').evaluateAll((els) =>
    els.map((el) => el.querySelector('span')?.textContent?.trim() ?? ''),
  )
  let targetIdx = titles.findIndex((t) => /^run_(web_search|google_news)$/.test(t))
  if (targetIdx < 0) targetIdx = 0

  const cards = page.locator('[data-slot="node-result-card"]')
  await cards.nth(targetIdx).scrollIntoViewIfNeeded()
  await wait(800)
  await cards.nth(targetIdx).click()
  await wait(1500)

  // ----- Modal walk-through -----
  await subtitle(page,
    'Modal — proper search-result cards with title, snippet, source link, confidence.',
    5000,
  )
  await wait(2500)
  // Scroll inside the modal so additional findings below the fold are
  // visible to the viewer instead of staying off-screen.
  await page.evaluate(async () => {
    const dialog = document.querySelector('[role="dialog"]') as HTMLElement | null
    if (!dialog) return
    const scrollable = Array.from(dialog.querySelectorAll<HTMLElement>('*')).find(el => {
      const s = getComputedStyle(el)
      return (s.overflowY === 'auto' || s.overflowY === 'scroll') &&
             el.scrollHeight > el.clientHeight + 50
    }) ?? dialog
    for (let i = 0; i < 4; i++) {
      scrollable.scrollTop += 180
      await new Promise(r => setTimeout(r, 700))
    }
    scrollable.scrollTop = 0
  })

  const sourcesTab = page.getByRole('tab', { name: /sources/i }).first()
  if (await sourcesTab.isVisible({ timeout: 1500 }).catch(() => false)) {
    await sourcesTab.click()
    await wait(800)
    await subtitle(page, 'Sources tab — every URL behind the answer, gradable for trust', 4500)
    await wait(3000)
  }

  const detailsTab = page.getByRole('tab', { name: /details/i }).first()
  if (await detailsTab.isVisible({ timeout: 1500 }).catch(() => false)) {
    await detailsTab.click()
    await wait(800)
    await subtitle(page, 'Details tab — query params, timing, raw payload (collapsed) for power users', 5000)
    // Expand the collapsed Raw payload <details> so users see it's there.
    await page.locator('[role="dialog"] summary:has-text("Raw payload")').first()
      .click({ force: true }).catch(() => {})
    await wait(2500)
    await subtitle(page, 'Raw payload expanded — full JSON for debugging or programmatic consumers.', 4500)
    await wait(2500)
  }

  // Close the modal
  await page.keyboard.press('Escape').catch(() => {})
  await wait(1000)

  // ----- Demo the Go Deep / Analyze / Save Pipeline action buttons -----
  const goDeepBtn = page.locator('button:has-text("Go Deep")').first()
  const analyzeBtn = page.locator('button:has-text("Analyze")').first()
  const saveBtn = page.locator('button:has-text("Save Pipeline"), button:has-text("Save as Pipeline")').first()

  if (await goDeepBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
    await goDeepBtn.scrollIntoViewIfNeeded()
    await wait(800)
    await subtitle(page,
      'Three actions on a finished run: Go Deeper, Analyze, Save as Pipeline.',
      4500,
    )
    await wait(2500)

    // ACTUALLY click each button. RunActionRow's onClick handlers dispatch
    // CustomEvents (demo:goDeeper / demo:analyze / demo:savePipeline) — no
    // backend side effects, safe for the demo.
    await subtitle(page,
      'Go Deeper — spawns new hypotheses around the top result.',
      4500,
    )
    await goDeepBtn.click().catch(() => {})
    await wait(2000)

    if (await analyzeBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
      await subtitle(page,
        'Analyze — summarises all findings into a coherent narrative answer.',
        4500,
      )
      await analyzeBtn.click().catch(() => {})
      await wait(2000)
    }

    if (await saveBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
      await subtitle(page,
        'Save as Pipeline — templates this run so the workflow can be re-run with new inputs.',
        5000,
      )
      await saveBtn.click().catch(() => {})
      await wait(2000)
    }
  } else {
    await subtitle(page, 'Action row buttons (Go Deeper / Analyze / Save Pipeline) below the cards.', 4000)
    await wait(2000)
  }

  await clearSubtitle(page)

  // ----- DAG in bottom panel — 3 layers deep -----
  // The full investigation DAG lives permanently in the bottom panel of the
  // run-results view; no toolbar click needed. Scroll the bottom panel into
  // view and pan through the layers.
  await page.evaluate(() => window.scrollBy({ top: 400 }))
  await wait(1500)
  await subtitle(page,
    'Bottom panel: full investigation DAG — phases (signal extraction → broaden → red team → rank verify).',
    5500,
  )
  await wait(3500)
  await subtitle(page,
    'Each phase fans out into parallel tacticians (slot 0, 1, 2…) — layer 2.',
    5000,
  )
  await scrollThroughContent(page, 500, 900)
  await subtitle(page,
    'Layer 3: each tactician runs tool calls; the findings hang off as leaves.\n' +
    'Click any node to inspect the full payload.',
    6000,
  )
  await wait(3500)
  await page.evaluate(() => window.scrollTo({ top: 0 }))
  await wait(800)
  await clearSubtitle(page)

  // ===========================================================
  //  PART 2 — FILE UPLOAD + INFERENCE
  // ===========================================================
  await title(page, 'File upload', 'Drop a document. Ask questions about it.', 3500)
  await clearTitle(page)

  // The upload zone lives in the chat panel; go back to research
  await page.goto(`${BASE}/research`)
  await wait(2500)

  await subtitle(page,
    "Below the chat box: drop documents (.pdf .docx .csv .xlsx .txt).\n" +
    "We'll upload a briefing about a fictitious company.",
    5500,
  )

  // Locate the hidden file input and set our sample
  const fileInput = page.locator('input[type="file"]').first()
  await fileInput.setInputFiles(SAMPLE_FILE)
  await wait(1000)
  await subtitle(page, 'File uploading…', 1800, 'top')

  // Wait up to 15s for indexed status; race it against a fixed cap so the
  // demo doesn't dead-air for up to 90s on slow embedding runs.
  await Promise.race([
    page.waitForFunction(
      () => /\bindexed|failed\b/i.test(document.body.textContent || ''),
      null,
      { timeout: 15_000 },
    ).catch(() => null),
    page.waitForTimeout(15_000),
  ])
  await subtitle(page,
    'File parsed, chunked, embedded — ready for retrieval-augmented answers.',
    3500,
  )

  // Ask a question about the file
  const chatInput = page
    .locator('textarea, input[type="text"]')
    .filter({ hasNot: page.locator('[type="password"]') })
    .first()
  await chatInput.click()
  await subtitle(page, 'Asking the agent a question grounded in the uploaded file...', 4000, 'top')
  await chatInput.pressSequentially('Who is the CEO of ACME Research Group and what are the strategic priorities?', { delay: 18 })
  await wait(600)
  await chatInput.press('Enter')

  // Wait for an answer to stream in
  await wait(15_000)
  await subtitle(page,
    'Agent retrieves matching chunks from the file and answers in context.\n' +
    'Source citations link back to the document.',
    5500,
  )

  await wait(4000)
  await clearSubtitle(page)

  // ===========================================================
  //  PART 3 — PERFORMANCE DASHBOARD
  // ===========================================================
  await title(page, 'Performance', 'Strategies, tactics & techniques graded on Admiralty scale', 3500)
  await clearTitle(page)
  await page.goto(`${BASE}/performance`).catch(() => {})
  await waitForContent(page, { minNodes: 50 })
  await subtitle(page, 'Every run is graded — letter grades (A-F) plus a numeric 1-6 credibility score.', 5500)
  await wait(2500)
  await subtitle(page, 'Tools, tactics, and strategies are ranked so you can see which approaches converge.', 5500)
  await scrollThroughContent(page, 1000, 1100) // reveal Strategy Usage + Run History tables
  await clearSubtitle(page)

  // ===========================================================
  //  PART 4 — PLUGINS
  // ===========================================================
  await title(page, 'Plugins', 'Search engines, OSINT sources, social feeds — drop-in modules', 3500)
  await clearTitle(page)
  await page.goto(`${BASE}/plugins`).catch(() => {})
  await waitForContent(page, { minNodes: 50 })
  await subtitle(page, 'Each plugin is a node the pipeline can use — install, configure, or build your own.', 5500)
  await wait(3000)
  await subtitle(page, '50+ MCP tools out of the box: SerpAPI, Brave, DDG, Wikipedia, Apify, SEC EDGAR, …', 5500)
  await scrollThroughContent(page, 700, 900)
  await clearSubtitle(page)

  // ===========================================================
  //  PART 5 — WALLET
  // ===========================================================
  await title(page, 'Wallet', 'Research Units (RU) — pay-per-run with hold-and-settle', 3500)
  await clearTitle(page)
  await page.goto(`${BASE}/wallet`).catch(() => {})
  await waitForContent(page, { minNodes: 40 })
  await subtitle(page, 'Every run carries a cost estimate. The wallet holds RU at preflight; settles at completion.', 6000)
  await wait(2500)
  await subtitle(page, 'Transparent ledger — every charge tied to a specific run, with refunds on cancel.', 5500)
  await scrollThroughContent(page, 700, 900)
  await clearSubtitle(page)

  // ===========================================================
  //  PART 6 — RUNS (merged history)
  // ===========================================================
  await title(page, 'History', 'All your investigations — filterable, exportable, replayable', 3500)
  await clearTitle(page)
  await page.goto(`${BASE}/runs`).catch(() => {})
  await waitForContent(page, { minNodes: 40 })
  await subtitle(page, 'Unified view: every run, with cost, status, duration, and filters by date / status.', 6000)
  await wait(2500)
  await subtitle(page, 'Click any row for the full result drawer — replay, download, or share.', 4500)
  await scrollThroughContent(page, 700, 900)
  await clearSubtitle(page)

  // ===========================================================
  //  PART 7 — SETTINGS
  // ===========================================================
  await title(page, 'Settings', 'Agent config, model picks, API keys, node health', 3500)
  await clearTitle(page)
  await page.goto(`${BASE}/settings`).catch(() => {})
  await waitForContent(page, { minNodes: 50 })
  await subtitle(page, 'Pick your LLM provider, rotate API keys, monitor MCP server health from one place.', 6000)
  await scrollThroughContent(page, 700, 900)
  await clearSubtitle(page)

  // ===========================================================
  //  OUTRO
  // ===========================================================
  await title(page, 'That\'s the tour', 'github.com/your-org/info-broker', 5000)
  await clearTitle(page)

  // ----------- write the .srt sidecar -----------
  const srtLines: string[] = []
  subtitles.forEach((sub, i) => {
    srtLines.push(String(i + 1))
    srtLines.push(`${fmtSrtTime(sub.startMs)} --> ${fmtSrtTime(sub.endMs)}`)
    srtLines.push(sub.text)
    srtLines.push('')
  })
  const outDir = path.resolve(__dirname, '..', 'test-results')
  if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true })
  const srtPath = path.join(outDir, 'demo-feature-tour.srt')
  fs.writeFileSync(srtPath, srtLines.join('\n'))
  console.log(`Subtitles written: ${srtPath}`)
  console.log(`Total subtitles: ${subtitles.length}`)

  if (issues.length) {
    console.log(`\n⚠️  ${issues.length} ISSUES DETECTED — will block clean recording:`)
    issues.slice(0, 20).forEach((i) => console.log('  -', i))
    throw new Error(`${issues.length} issue(s) detected during demo — fix and retry`)
  }
})
