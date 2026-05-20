
import { test, chromium } from '@playwright/test'
import * as os from 'node:os'
import * as path from 'node:path'

test.use({ headless: false })
const USER_DATA_DIR = path.join(os.homedir(), '.cache', 'pw-gcp-bootstrap')

test('probe resource manager DOM', async () => {
  test.setTimeout(5 * 60 * 1000)
  const ctx = await chromium.launchPersistentContext(USER_DATA_DIR, {
    channel: 'chrome', headless: false,
    viewport: { width: 1440, height: 900 },
  })
  const page = ctx.pages()[0] ?? await ctx.newPage()
  await page.goto('https://console.cloud.google.com/cloud-resource-manager', { waitUntil: 'domcontentloaded' })
  await page.waitForLoadState('networkidle', { timeout: 30_000 }).catch(()=>null)
  await page.waitForTimeout(4000)

  const probe = await page.evaluate(() => {
    const matches: any[] = []
    // walk all leaf elements with text 'infobroker'
    document.querySelectorAll('*').forEach((el) => {
      const t = (el.textContent || '').trim()
      if (t === 'infobroker' && el.children.length === 0) {
        // dump parent chain and siblings
        const row = el.closest('mat-row') || el.closest('tr') || el.closest('[role="row"]') || el.parentElement?.parentElement?.parentElement
        const rowHtml = row ? (row as HTMLElement).outerHTML.slice(0, 2000) : '(no row found)'
        const rowText = row ? (row.textContent || '').trim().slice(0, 500) : ''
        // Look for project-id-like strings anywhere within the row
        const rowEl = row as HTMLElement | null
        const allText = rowEl ? Array.from(rowEl.querySelectorAll('*')).map(n => (n.textContent || '').trim()).filter(s => s.length > 0 && s.length < 80) : []
        matches.push({
          tagPath: el.tagName + '>' + (el.parentElement?.tagName || ''),
          rowTagName: row?.tagName,
          rowClass: rowEl?.className?.slice(0, 200),
          rowText,
          texts: allText.slice(0, 30),
          rowHtml: rowHtml.slice(0, 1500),
        })
      }
    })
    return matches.slice(0, 3)
  })
  console.log('PROBE:')
  for (const m of probe) {
    console.log('---')
    console.log('rowTag:', m.rowTagName, 'class:', m.rowClass)
    console.log('rowText:', m.rowText)
    console.log('texts:', JSON.stringify(m.texts))
    console.log('html:', m.rowHtml)
  }
  await page.waitForTimeout(2000)
  await ctx.close()
})
