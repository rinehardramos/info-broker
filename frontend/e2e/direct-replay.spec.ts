/** Direct replay test — navigate to a known run-id URL and inspect store state */
import { test, Page } from '@playwright/test'

const BASE = 'http://localhost:5173'
const KNOWN_RUN = 'a08f354a-26e2-4e79-ad4a-f2b7ea4cd7ca'  // 7-card run

async function login(page: Page) {
  await page.goto(`${BASE}/login`)
  const v = await page.locator('input[type="password"]').first().isVisible({ timeout: 2000 }).catch(() => false)
  if (v) {
    await page.fill('input[type="text"], input[type="email"]', 'admin')
    await page.fill('input[type="password"]', 'admin')
    await page.locator('button[type="submit"]').first().click()
    await page.waitForURL(/\/$|\/research|\/jobs/, { timeout: 8_000 })
  }
}

test('direct replay of 7-card run', async ({ page }) => {
  test.setTimeout(120_000)
  page.on('console', msg => {
    const text = msg.text()
    if (text.startsWith('replayRunIntoStore') || text.includes('replay')) {
      console.log('[browser]', msg.type(), text.slice(0, 200))
    }
  })
  const replayResponses: { status: number; cards: number }[] = []
  page.on('response', async resp => {
    if (resp.url().includes('/replay')) {
      try {
        const body = await resp.json()
        replayResponses.push({ status: resp.status(), cards: (body.cards ?? []).length })
      } catch { /* */ }
    }
  })

  await login(page)
  await page.goto(`${BASE}/research?replay=${KNOWN_RUN}`)
  await page.waitForTimeout(5000)

  console.log('replay HTTP responses:', replayResponses)

  // Inspect the store directly via window injection
  const storeState = await page.evaluate((runId) => {
    // @ts-expect-error window debug
    const store = window.useRunStreamStore?.getState?.()
    const run = store?.runsById?.[runId]
    // @ts-expect-error window debug
    const sessionStore = window.useSessionStore?.getState?.()
    return {
      hasRun: !!run,
      cardOrderLength: run?.cardOrder?.length ?? 0,
      cardsCount: run ? Object.keys(run.cards ?? {}).length : 0,
      phasesCount: run ? Object.keys(run.phases ?? {}).length : 0,
      rankedCandidates: run?.rankedCandidates?.length ?? 0,
      activeJobId: sessionStore?.activeJobId,
      col1Content: sessionStore?.col1Content,
    }
  }, KNOWN_RUN)
  console.log('store state:', storeState)

  const cards = await page.locator('[data-slot="node-result-card"]').count()
  console.log('cards in DOM:', cards)

  // All tab-like buttons
  const buttons = await page.locator('button').filter({ hasText: /Pipeline|Results|Run/ }).allInnerTexts()
  console.log('tab buttons:', buttons)

  // Probe for whether the column even mounted
  const allButtonsCount = await page.locator('button').count()
  console.log('total buttons in DOM:', allButtonsCount)

  // What's actually in the left column?
  const leftPanelText = (await page.locator('body').innerText()).slice(0, 600)
  console.log('first 600 chars of body:', leftPanelText)

  await page.waitForTimeout(2000)
})
