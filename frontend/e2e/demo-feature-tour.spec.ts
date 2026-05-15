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
  // Use the user's installed Google Chrome (not bundled chromium) in headed
  // mode at 1080p — captures hi-res WebM video.
  channel: 'chrome',
  video: { mode: 'on', size: { width: 1920, height: 1080 } },
  viewport: { width: 1920, height: 1080 },
  headless: false,
  launchOptions: {
    args: ['--auto-open-devtools-for-tabs=false'],
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

async function subtitle(page: Page, text: string, holdMs = 3500) {
  const t = Date.now()
  const startMs = t - demoStartMs
  subtitles.push({ startMs, endMs: startMs + holdMs, text })

  await page.evaluate((s) => {
    let el = document.getElementById('__demo_subtitle__')
    if (!el) {
      el = document.createElement('div')
      el.id = '__demo_subtitle__'
      el.style.cssText = [
        'position:fixed',
        'left:50%',
        'transform:translateX(-50%)',
        'bottom:48px',
        'z-index:2147483647',
        'background:rgba(15,15,20,0.92)',
        'color:#ffffff',
        'font:600 22px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif',
        'padding:14px 28px',
        'border-radius:14px',
        'max-width:80vw',
        'text-align:center',
        'box-shadow:0 10px 40px rgba(0,0,0,0.45)',
        'border:1px solid rgba(167,139,250,0.55)',
        'pointer-events:none',
        'white-space:pre-wrap',
      ].join(';')
      document.body.appendChild(el)
    }
    el.textContent = s
  }, text)

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

  // -- Login
  await login(page)
  await wait(1200)

  // ===========================================================
  //  QUICK TOUR — supporting features (flyover, 8-12s each)
  // ===========================================================
  // Dashboard
  await page.goto(`${BASE}/dashboard`).catch(() => {})
  await wait(2500)
  await subtitle(page, 'Dashboard — runs today, success rate, live jobs, errors at a glance', 4500)
  await wait(500)

  // History
  await page.goto(`${BASE}/history`).catch(() => {})
  await wait(2500)
  await subtitle(page, 'History — every run logged, filterable, exportable as CSV/XLSX', 4500)
  await wait(500)

  // Performance
  await page.goto(`${BASE}/performance`).catch(() => {})
  await wait(2500)
  await subtitle(page, 'Performance — strategies, tactics, and techniques graded on the Admiralty scale', 4500)
  await wait(500)

  // Pipelines
  await page.goto(`${BASE}/pipelines`).catch(() => {})
  await wait(2500)
  await subtitle(page, 'Pipelines — drag-and-drop node editor for custom research workflows', 4500)
  await wait(500)

  // Settings (quick glance)
  await page.goto(`${BASE}/settings`).catch(() => {})
  await wait(2500)
  await subtitle(page, 'Settings — agent config, model picks, MCP servers, API keys', 4500)
  await wait(500)
  await clearSubtitle(page)

  // ===========================================================
  //  PART 1 — RESEARCH (the headline feature)
  // ===========================================================
  await title(page, 'Research', 'The headline feature — Heuer methodology, live cards, modal detail', 4500)
  await clearTitle(page)
  await page.goto(`${BASE}/research`)
  await wait(2000)

  await subtitle(page, 'Research workspace — pipeline · agent chat · live stream', 4000)
  await subtitle(page,
    "Let's ask: 'Who is the CEO of OpenAI in 2026?'\n" +
    'The agent will pick a strategy, run parallel hypotheses, and stream results.',
    5500,
  )

  // Type query
  const input = page
    .locator('textarea, input[type="text"]')
    .filter({ hasNot: page.locator('[type="password"]') })
    .first()
  await input.waitFor({ timeout: 5000 })
  await input.click()
  await input.pressSequentially('Who is the CEO of OpenAI in 2026?', { delay: 18 })
  await wait(600)
  await subtitle(page, 'Submitting query...', 1800)
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
  await wait(1200)
  await subtitle(page, 'Engine v2 launched — Heuer analytic methodology, 4 phases', 4000)

  // Wait for first phase to start
  await wait(4000)
  await subtitle(page,
    'Phase 1 of 4 — SIGNAL EXTRACTION.\n' +
    'The brain parses the query into structured entities & intent.',
    5000,
  )

  // Wait for cards to start streaming
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
  await wait(500)
  await cards.nth(targetIdx).click()
  await wait(1500)

  await subtitle(page,
    'Modal — full result detail.\n' +
    'Title, snippet, source link, confidence — formatted for reading, not JSON.',
    5500,
  )

  await wait(2000)

  // Show the Sources tab too for variety
  const sourcesTab = page.getByRole('tab', { name: /sources/i }).first()
  if (await sourcesTab.isVisible({ timeout: 1500 }).catch(() => false)) {
    await sourcesTab.click()
    await wait(800)
    await subtitle(page, 'Sources tab — every URL behind the answer, gradable for trust', 4500)
  }

  // Close the modal
  await page.keyboard.press('Escape').catch(() => {})
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
  await chatInput.pressSequentially('Who is the CEO of ACME Research Group and what are the strategic priorities?', { delay: 18 })
  await wait(600)
  await subtitle(page, 'Asking the agent a question grounded in the uploaded file...', 4000)
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
