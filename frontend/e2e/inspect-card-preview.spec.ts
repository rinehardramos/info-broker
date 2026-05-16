/** Inspect the EXACT preview text for the running legacy IS-brain run */
import { test, Page } from '@playwright/test'

const BASE = 'http://localhost:5173'

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

test('inspect card preview in store', async ({ page }) => {
  await login(page)
  // Use the known recent run from the user's screenshot
  await page.goto(`${BASE}/research?replay=d24b1bc1-e30c-4c40-9c5e-c4f25bbf91dc`)
  await page.waitForTimeout(5000)

  // Find any run in the store and inspect its run_google_news card preview
  const state = await page.evaluate(() => {
    // @ts-expect-error window debug
    const store = window.useRunStreamStore?.getState?.()
    if (!store) return { error: 'no store' }
    const runs = store.runsById
    const out: any[] = []
    for (const [rid, run] of Object.entries(runs)) {
      const r = run as any
      for (const nid of r.cardOrder || []) {
        const c = r.cards?.[nid]
        if (!c) continue
        if (c.nodeName?.includes('google_news') || c.nodeName?.includes('news')) {
          out.push({
            runId: rid.slice(0, 8),
            nodeId: nid,
            nodeName: c.nodeName,
            status: c.status,
            previewLen: c.preview?.length ?? 0,
            previewHead: (c.preview ?? '').slice(0, 200),
          })
        }
      }
    }
    return { runs: Object.keys(runs).length, found: out.slice(0, 3) }
  })
  console.log('store state:', JSON.stringify(state, null, 2))
})
