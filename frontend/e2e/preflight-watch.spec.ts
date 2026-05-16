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

test('preflight + watch live view for 3 minutes', async ({ page }) => {
  test.setTimeout(600_000)

  const wsEvents: string[] = []
  page.on('websocket', (ws) => {
    wsEvents.push(`OPEN ${ws.url()}`)
    ws.on('close', () => wsEvents.push(`CLOSE ${ws.url()}`))
    ws.on('framereceived', (f) => {
      try {
        const msg = JSON.parse(typeof f.payload === 'string' ? f.payload : f.payload.toString())
        if (msg.type && msg.type !== 'ping') wsEvents.push(`RECV ${msg.type} run=${msg.run_id ?? ''}`)
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

  // Wait for preflight panel and click Run
  await page.getByText(/strateg|preflight|approach|select.*strateg/i).first().waitFor({ timeout: 15_000 })
  await page.waitForTimeout(1500)
  const runBtn = page.getByRole('button', { name: /^run$/i }).first()
  await runBtn.click()
  console.log('Run clicked at', new Date().toISOString())

  // Watch for 3 minutes, screenshot every 20s, log DOM stats
  const intervals = [20, 40, 60, 90, 120, 150, 180]
  for (const sec of intervals) {
    await page.waitForTimeout(sec * 1000 - (intervals[intervals.indexOf(sec) - 1] ?? 0) * 1000)
    const cardCount = await page.locator('[data-slot="node-result-card"]').count()
    const swimSlots = await page.locator('text=/Slot \\d+/').count()
    const phaseBadgeText = await page.locator('text=/signal extraction|broaden|red team|rank verify/i').allTextContents()
    const noEventsText = await page.getByText(/no node events received yet/i).isVisible().catch(() => false)
    const headerStore = await page.locator('text=/store:/i').first().textContent().catch(() => null)
    console.log(`@${sec}s cards=${cardCount} slots=${swimSlots} noEvents=${noEventsText} header=${headerStore?.trim()}`)
    await page.screenshot({ path: `test-results/watch-${String(sec).padStart(3,'0')}s.png`, fullPage: false })
  }

  console.log('--- WS event log ---')
  wsEvents.slice(0, 120).forEach((e) => console.log(' ', e))
  console.log(`(total ws events: ${wsEvents.length})`)

  // Click the first succeeded card and screenshot the modal so we can
  // verify card-vs-modal alignment without manual interaction.
  const firstCard = page.locator('[data-slot="node-result-card"]').first()
  if (await firstCard.isVisible().catch(() => false)) {
    await firstCard.scrollIntoViewIfNeeded()
    await firstCard.click()
    await page.waitForTimeout(1200)
    const modalOpen = await page.locator('[role="dialog"]').isVisible().catch(() => false)
    console.log('Modal opened:', modalOpen)
    await page.screenshot({ path: 'test-results/watch-modal-formatted.png' })
    // Switch to Raw tab too so we can see the structured output
    const rawTab = page.getByRole('tab', { name: /raw output/i }).first()
    if (await rawTab.isVisible().catch(() => false)) {
      await rawTab.click()
      await page.waitForTimeout(500)
      await page.screenshot({ path: 'test-results/watch-modal-raw.png' })
    }
  } else {
    console.log('No card visible — modal capture skipped')
  }

  // Hold the browser open at the end so you can poke around in DevTools.
  console.log('\n>>> Holding browser open for 5 minutes. Inspect freely. <<<')
  await page.waitForTimeout(300_000)
})
