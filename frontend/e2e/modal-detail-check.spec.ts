import { test, type Page } from '@playwright/test'

const BASE = 'http://localhost:5173'

async function login(page: Page) {
  await page.goto(`${BASE}/login`)
  const v = await page.locator('input[type="password"]').first().isVisible({ timeout: 2000 }).catch(() => false)
  if (v) {
    await page.fill('input[type="text"], input[type="email"]', 'admin')
    await page.fill('input[type="password"]', 'admin')
    await page.locator('button[type="submit"]').first().click()
    await page.waitForURL(/\/$|\/research|\/jobs|\/runs/, { timeout: 8_000 })
  }
}

test('click a real result card and inspect modal detail', async ({ page }) => {
  test.setTimeout(420_000)

  // Capture is.tool_result WS frames so we can verify whether event.output
  // is being sent by the backend at all.
  const toolResultFrames: Array<{ call_id: string; hasOutput: boolean; outputType: string; preview: string }> = []
  page.on('websocket', (ws) => {
    ws.on('framereceived', (f) => {
      try {
        const msg = JSON.parse(typeof f.payload === 'string' ? f.payload : f.payload.toString())
        if (msg.type === 'is.tool_result') {
          toolResultFrames.push({
            call_id: msg.call_id ?? '',
            hasOutput: 'output' in msg,
            outputType: Array.isArray(msg.output) ? 'array' : typeof msg.output,
            preview: typeof msg.preview === 'string' ? msg.preview.slice(0, 120) : '',
          })
        }
      } catch { /* binary */ }
    })
  })

  await login(page)
  await page.goto(`${BASE}/research`)
  await page.waitForTimeout(1500)

  const input = page.locator('textarea, input[type="text"]').filter({ hasNot: page.locator('[type="password"]') }).first()
  await input.waitFor({ timeout: 5000 })
  await input.fill('Who is the CEO of OpenAI in 2026?')
  await input.press('Enter')

  await page.getByText(/strateg|preflight|approach|select.*strateg/i).first().waitFor({ timeout: 15_000 })
  await page.waitForTimeout(1500)
  await page.getByRole('button', { name: /^run$/i }).first().click()
  console.log('Run clicked', new Date().toISOString())

  // Wait until at least 8 cards have streamed in — enough to include
  // search-result cards (run_web_search / run_google_news), not just
  // the ToolSearch meta card.
  await page.waitForFunction(
    () => document.querySelectorAll('[data-slot="node-result-card"]').length >= 8,
    null,
    { timeout: 180_000 }
  )
  await page.waitForTimeout(8_000) // let a few more land
  console.log('Cards ready')

  // List card titles so we can verify which we click
  const titles = await page.locator('[data-slot="node-result-card"]').evaluateAll(
    (els) => els.map((el) => el.querySelector('span')?.textContent?.trim() ?? '')
  )
  console.log('Card titles:', JSON.stringify(titles))

  // Pick by the card's TITLE span (first child), not by descendant text —
  // ToolSearch cards mention 'web_search' in their body which polluted the
  // previous selector. The title span is always the tool name.
  const allCards = page.locator('[data-slot="node-result-card"]')
  let targetIdx = -1
  for (let i = 0; i < titles.length; i++) {
    const t = titles[i]
    if (/^run_(web_search|google_news|intelligent_search)$/.test(t)) {
      targetIdx = i
      break
    }
  }
  console.log('Target idx:', targetIdx, 'title:', titles[targetIdx])
  if (targetIdx < 0) {
    console.log('No result-bearing card found by title')
    return
  }
  const target = allCards.nth(targetIdx)
  const found = await target.isVisible().catch(() => false)
  console.log('Result-bearing card visible:', found)
  if (!found) return

  await target.scrollIntoViewIfNeeded()
  await page.screenshot({ path: 'test-results/modal-1-before-click.png' })
  await target.click()
  await page.waitForTimeout(1500)

  const modalOpen = await page.locator('[role="dialog"]').isVisible().catch(() => false)
  console.log('Modal opened:', modalOpen)
  await page.screenshot({ path: 'test-results/modal-2-formatted-tab.png' })

  // Try to spot whether FindingView rendered (has .text-emerald-400 confidence bars or similar)
  const findingRows = await page.locator('[role="dialog"] >> text=/\\d+ finding|source ↗|confidence/i').count()
  const rawJsonInModal = await page.locator('[role="dialog"] >> text=/^\\s*\\{/').count()
  console.log('finding-like elements in modal:', findingRows)
  console.log('JSON-ish content in modal:', rawJsonInModal)

  // Diagnostic: dump the is.tool_result WS frames we captured
  console.log(`captured ${toolResultFrames.length} is.tool_result frames`)
  const withOutput = toolResultFrames.filter((f) => f.hasOutput).length
  console.log(`  ...frames with output field: ${withOutput}`)
  toolResultFrames.slice(0, 3).forEach((f, i) =>
    console.log(`  [${i}] hasOutput=${f.hasOutput} outputType=${f.outputType} preview=${f.preview.slice(0, 80)}`)
  )

  // Click the Raw Output tab too for comparison
  const rawTab = page.getByRole('tab', { name: /raw output/i }).first()
  if (await rawTab.isVisible().catch(() => false)) {
    await rawTab.click()
    await page.waitForTimeout(500)
    await page.screenshot({ path: 'test-results/modal-3-raw-tab.png' })
  }

  // Hold open for inspection
  await page.waitForTimeout(180_000)
})
