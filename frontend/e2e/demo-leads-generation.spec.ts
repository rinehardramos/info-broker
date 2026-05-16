/**
 * Leads Generation Demo — records a short video focused on the two leads-
 * generation flows:
 *   1. CHAT — type a natural-language prompt; agent generates qualified leads
 *   2. FILE — upload a CSV of company names; agent enriches each row
 *
 * Saves to docs/demos/v0.6.0/leads-generation.webm after passing.
 */
import { test, type Page } from '@playwright/test'
import * as fs from 'node:fs'
import * as path from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const BASE = 'http://localhost:5173'
const SAMPLE_LEADS = '/tmp/demo-leads-list.csv'

test.use({
  channel: 'chrome',
  video: { mode: 'on', size: { width: 1440, height: 900 } },
  viewport: { width: 1440, height: 900 },
  headless: false,
  launchOptions: { args: ['--window-size=1440,900'] },
})

test.setTimeout(900_000)

// ----------- shared overlay helpers (mirror demo-feature-tour) -----------

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

async function subtitle(page: Page, text: string, holdMs = 4000, position: 'top' | 'bottom' = 'bottom') {
  const startMs = Date.now() - demoStartMs
  subtitles.push({ startMs, endMs: startMs + holdMs, text })
  await page.evaluate(({ s, pos }) => {
    let el = document.getElementById('__demo_subtitle__')
    if (!el) {
      el = document.createElement('div')
      el.id = '__demo_subtitle__'
      el.style.cssText = [
        'position:fixed','left:50%','transform:translateX(-50%)','z-index:2147483647',
        'background:rgba(15,15,20,0.92)','color:#fff',
        'font:600 19px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif',
        'padding:11px 22px','border-radius:12px','max-width:80vw','text-align:center',
        'box-shadow:0 10px 40px rgba(0,0,0,0.45)','border:1px solid rgba(167,139,250,0.55)',
        'pointer-events:none','white-space:pre-wrap',
      ].join(';')
      document.body.appendChild(el)
    }
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
  subtitles.push({
    startMs: Date.now() - demoStartMs,
    endMs: Date.now() - demoStartMs + holdMs,
    text: `${headline} — ${subhead}`,
  })
  await page.evaluate(({ h, s }) => {
    let el = document.getElementById('__demo_title__')
    if (!el) {
      el = document.createElement('div')
      el.id = '__demo_title__'
      el.style.cssText = [
        'position:fixed','inset:0','z-index:2147483646',
        'background:radial-gradient(ellipse at center, #1e1535 0%, #050008 70%)',
        'display:flex','flex-direction:column','align-items:center','justify-content:center',
        'color:#fff','font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif',
        'pointer-events:none',
      ].join(';')
      document.body.appendChild(el)
    }
    el.innerHTML = `
      <div style="font-size:60px;font-weight:700;letter-spacing:-0.02em">${h}</div>
      <div style="font-size:20px;margin-top:18px;color:#a78bfa">${s}</div>
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

async function login(page: Page) {
  await page.goto(`${BASE}/login`)
  await wait(1500)
  const pw = page.locator('input[type="password"]').first()
  if (await pw.isVisible({ timeout: 2000 }).catch(() => false)) {
    await page.fill('input[type="text"], input[type="email"]', 'admin')
    await pw.fill('admin')
    await page.locator('button[type="submit"]').first().click()
    await page.waitForURL(/\/$|\/research|\/dashboard|\/jobs|\/runs/, { timeout: 8_000 })
  }
}

// ----------- the demo -----------

test('demo leads generation — chat + file upload flows', async ({ page }) => {
  demoStartMs = Date.now()

  // Fail-fast (same filter as the main demo)
  const issues: string[] = []
  page.on('pageerror', (e) => {
    issues.push(`pageerror: ${e.message}`)
    throw new Error(`pageerror: ${e.message}`)
  })
  page.on('console', (m) => {
    if (m.type() !== 'error') return
    const text = m.text()
    if (/React Router Future Flag|DevTools|hmr|Download the React DevTools/i.test(text)) return
    if (/Function components cannot be given refs|SlotClone/i.test(text)) return
    issues.push(`console.error: ${text.slice(0, 200)}`)
  })

  await page.goto(BASE)
  await title(page, 'Leads generation', 'Two paths to qualified leads — chat & file upload', 4500)
  await clearTitle(page)

  await login(page)
  await wait(1200)
  await page.goto(`${BASE}/research`)
  await wait(2500)

  // ===========================================================
  // PART 1 — CHAT-BASED LEADS
  // ===========================================================
  await title(page, 'Lead-gen via chat', 'Describe your ideal customer; the agent surfaces matching companies', 4000)
  await clearTitle(page)

  await subtitle(page,
    "Type a natural-language prompt — no rigid form fields.\n" +
    "The agent decides what to search, parses results, and de-dupes.",
    5500, 'top',
  )

  const chatInput = page
    .locator('textarea, input[type="text"]')
    .filter({ hasNot: page.locator('[type="password"]') })
    .first()
  await chatInput.waitFor({ timeout: 5000 })
  await chatInput.click()
  // Use explicit "find leads" / "prospect list" signals so the brain's
  // keyword classifier (orchestrator.py:classify_query) picks the `lead`
  // strategy instead of defaulting to media_identification / person.
  await chatInput.pressSequentially(
    'Find leads: 5 mid-sized fintech SaaS companies in Southeast Asia. ' +
    'Build a prospect list — focus on ones that closed Series B in the last 18 months.',
    { delay: 14 },
  )
  await wait(700)
  await subtitle(page, 'Submitting lead-gen query...', 2000, 'top')
  await chatInput.press('Enter')

  // Preflight strategy picker
  await page.getByText(/intent|strateg|preflight|approach|hypothes|mode|detected/i).first()
    .waitFor({ timeout: 15_000 }).catch(() => {})
  await wait(1000)
  await subtitle(page,
    "The brain proposes strategies — pick the one tuned for company-discovery.\n" +
    "Click Run and the engine streams candidates live.",
    5500,
  )

  const runBtn = page.getByRole('button', { name: /^run$/i }).first()
  await runBtn.click()
  await wait(2000)
  await subtitle(page, 'Engine searches in parallel: company DBs, news, SEC, LinkedIn signals…', 5000)

  // Wait for cards to appear
  await page.waitForFunction(
    () => document.querySelectorAll('[data-slot="node-result-card"]').length >= 5,
    null,
    { timeout: 180_000 },
  ).catch(() => {})

  await subtitle(page,
    "Each card is a candidate lead with citations.\n" +
    "Click for the full evidence: domain, funding history, key people.",
    6000,
  )

  // Click the first result-bearing card
  const cards = page.locator('[data-slot="node-result-card"]')
  const titles = await cards.evaluateAll(els =>
    els.map(el => el.querySelector('span')?.textContent?.trim() ?? ''),
  )
  let idx = titles.findIndex(t => /^run_(web_search|google_news|apollo|linkedin)/.test(t))
  if (idx < 0) idx = 0
  await cards.nth(idx).scrollIntoViewIfNeeded()
  await wait(800)
  await cards.nth(idx).click()
  await wait(1500)
  await subtitle(page,
    "Lead detail — title, snippet, source link, confidence.\n" +
    "Use Sources tab to verify and grade each citation.",
    5500,
  )
  await wait(3500)
  await page.keyboard.press('Escape').catch(() => {})
  await wait(1000)
  await clearSubtitle(page)

  // ===========================================================
  // PART 2 — FILE UPLOAD LEAD ENRICHMENT
  // ===========================================================
  await title(page, 'Lead-gen via file upload', 'Upload a list; agent enriches each row', 4000)
  await clearTitle(page)
  await page.goto(`${BASE}/research`)
  await wait(2500)

  await subtitle(page,
    "Got an existing list? Drop the CSV — file is parsed, indexed, then\n" +
    "the agent can answer questions grounded in those rows.",
    4500, 'top',
  )

  // Upload the leads list. Indexing happens in the background (embedding +
  // Qdrant write); we don't need to BLOCK the demo on it — the next chat
  // turn will pick up the source as soon as it's indexed. Show a short
  // upload-status subtitle, then move on.
  const fileInput = page.locator('input[type="file"]').first()
  await fileInput.setInputFiles(SAMPLE_LEADS)
  await wait(1000)
  await subtitle(page, '5-company leads list uploading…', 2000, 'top')

  // Wait up to 15s for indexed status — long enough for fast tests, short
  // enough not to bore the viewer. Whichever resolves first wins.
  await Promise.race([
    page.waitForFunction(
      () => /\bindexed|failed\b/i.test(document.body.textContent || ''),
      null,
      { timeout: 15_000 },
    ).catch(() => null),
    page.waitForTimeout(15_000),
  ])
  await subtitle(page,
    'CSV parsed, chunked, embedded — RAG context ready.',
    3000,
  )

  // Ask agent to enrich
  const input2 = page
    .locator('textarea, input[type="text"]')
    .filter({ hasNot: page.locator('[type="password"]') })
    .first()
  await input2.click()
  await subtitle(page,
    'Asking the agent to enrich each company from the uploaded list...',
    4500, 'top',
  )
  await input2.pressSequentially(
    'For each company in the uploaded prospect list, find their CEO and ' +
    'most recent funding round. Output as a leads enrichment table.',
    { delay: 14 },
  )
  await wait(700)
  await input2.press('Enter')

  // Don't dead-wait for the agent. Narrate while the request streams.
  await subtitle(page,
    "Agent retrieves matching rows from the file, runs targeted searches\n" +
    "per company, and assembles a structured table with citations.",
    6000,
  )
  // Brief tail so the viewer sees the live response start to land.
  await wait(4000)

  await clearSubtitle(page)

  await title(page, "That's it", '/research handles both flows in one workspace', 4500)
  await clearTitle(page)

  // Write SRT sidecar
  const srtLines: string[] = []
  subtitles.forEach((sub, i) => {
    srtLines.push(String(i + 1))
    srtLines.push(`${fmtSrtTime(sub.startMs)} --> ${fmtSrtTime(sub.endMs)}`)
    srtLines.push(sub.text)
    srtLines.push('')
  })
  const outDir = path.resolve(__dirname, '..', 'test-results')
  if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true })
  fs.writeFileSync(path.join(outDir, 'demo-leads-generation.srt'), srtLines.join('\n'))
  console.log(`Subtitles written: ${path.join(outDir, 'demo-leads-generation.srt')}`)

  if (issues.length) {
    console.log(`\n⚠️  ${issues.length} issues detected:`)
    issues.slice(0, 20).forEach(i => console.log('  -', i))
    throw new Error(`${issues.length} issue(s) during demo`)
  }
})
