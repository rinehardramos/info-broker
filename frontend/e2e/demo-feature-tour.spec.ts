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
    el.style.top = pos === 'top' ? '40px' : ''
    el.style.bottom = pos === 'bottom' ? '40px' : ''
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

// ----------- helpers -----------

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

  // ===========================================================
  //  DASHBOARD (proper time, not a flyover)
  // ===========================================================
  await page.goto(`${BASE}/dashboard`).catch(() => {})
  await wait(2500)
  await subtitle(page, 'Dashboard — at-a-glance metrics: runs today, success rate, live jobs, errors', 5500)
  await wait(2000)
  await subtitle(page, 'Recent runs table — click any row to inspect the full result', 4500)
  await wait(3000)
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
  await page.getByText(/strateg|preflight|approach|select.*strateg/i).first().waitFor({ timeout: 15_000 })
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
    'Modal — proper search-result cards with title, snippet, source link, confidence.\n' +
    'Not raw JSON — formatted for reading.',
    5500,
  )
  await wait(2500)

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
    await wait(3500)
  }

  // Close the modal
  await page.keyboard.press('Escape').catch(() => {})
  await wait(1000)

  // ----- Scroll down to the Go Deep / Analyze / Save Pipeline action row -----
  const actionsRow = page.locator(
    'button:has-text("Go Deep"), button:has-text("Analyze"), button:has-text("Save Pipeline")'
  ).first()
  if (await actionsRow.isVisible({ timeout: 2000 }).catch(() => false)) {
    await actionsRow.scrollIntoViewIfNeeded()
    await wait(1000)
    await subtitle(page,
      'Action row — Go Deep continues research, Analyze summarises, Save Pipeline templates this run.',
      5500,
    )
    await wait(3500)
  } else {
    await subtitle(page, 'Scroll the result panel to find Go Deep / Analyze / Save Pipeline.', 4000)
    await wait(2000)
  }

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
  await wait(1500)
  await subtitle(page, 'File uploading...', 2000)

  // Wait for processing → indexed
  await page.waitForFunction(
    () => /\bindexed|failed\b/i.test(document.body.textContent || '') ||
          !!document.querySelector('[data-status="indexed"], .source-indexed'),
    null,
    { timeout: 90_000 },
  ).catch(() => {})
  await wait(1500)

  await subtitle(page,
    'File parsed, chunked, embedded — ready for retrieval-augmented answers.',
    4500,
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
  await wait(2500)
  await subtitle(page, 'Every run is graded — letter grades (A-F) plus a numeric 1-6 credibility score.', 5500)
  await wait(3000)
  await subtitle(page, 'Tools, tactics, and strategies are ranked so you can see which approaches converge.', 5500)
  await wait(3000)
  await clearSubtitle(page)

  // ===========================================================
  //  PART 4 — PLUGINS
  // ===========================================================
  await title(page, 'Plugins', 'Search engines, OSINT sources, social feeds — drop-in modules', 3500)
  await clearTitle(page)
  await page.goto(`${BASE}/plugins`).catch(() => {})
  await wait(2500)
  await subtitle(page, 'Each plugin is a node the pipeline can use — install, configure, or build your own.', 5500)
  await wait(3000)
  await subtitle(page, '50+ MCP tools out of the box: SerpAPI, Brave, DDG, Wikipedia, Apify, SEC EDGAR, …', 5500)
  await wait(3000)
  await clearSubtitle(page)

  // ===========================================================
  //  PART 5 — WALLET
  // ===========================================================
  await title(page, 'Wallet', 'Research Units (RU) — pay-per-run with hold-and-settle', 3500)
  await clearTitle(page)
  await page.goto(`${BASE}/wallet`).catch(() => {})
  await wait(2500)
  await subtitle(page, 'Every run carries a cost estimate. The wallet holds RU at preflight; settles at completion.', 6000)
  await wait(3500)
  await subtitle(page, 'Transparent ledger — every charge tied to a specific run, with refunds on cancel.', 5500)
  await wait(3000)
  await clearSubtitle(page)

  // ===========================================================
  //  PART 6 — RUNS (merged history)
  // ===========================================================
  await title(page, 'Runs', 'All your investigations — filterable, exportable, replayable', 3500)
  await clearTitle(page)
  await page.goto(`${BASE}/runs`).catch(() => {})
  await wait(2500)
  await subtitle(page, 'Unified view: every run, with cost, status, duration, and filters by date / status.', 6000)
  await wait(3500)
  await subtitle(page, 'Click any row for the full result drawer — replay, download, or share.', 4500)
  await wait(2500)
  await clearSubtitle(page)

  // ===========================================================
  //  PART 7 — SETTINGS
  // ===========================================================
  await title(page, 'Settings', 'Agent config, model picks, API keys, node health', 3500)
  await clearTitle(page)
  await page.goto(`${BASE}/settings`).catch(() => {})
  await wait(2500)
  await subtitle(page, 'Pick your LLM provider, rotate API keys, monitor MCP server health from one place.', 6000)
  await wait(3500)
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
