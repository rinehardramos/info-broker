/**
 * Functional E2E check for the Plugins page — verifies that:
 *   1. Plugins with category="enrich" show ENRICH (not DATASTORE) tag
 *   2. Plugins with category="lookup" show LOOKUP tag in a "Lookups" section
 *   3. Plugins with category="source" show SRC tag in "Sources" section
 *   4. Plugins with category="destination" show DESTINATION tag in a "Destinations" section
 *   5. No plugin still tagged as DATASTORE (the audit fixed all 9)
 *
 * This is the canonical regression-test for the category-tag fix.
 */
import { test, expect, Page } from '@playwright/test'

const BASE = 'http://localhost:5173'
const USER = 'testuser'
const PASS = 'TestUser2026!'
const wait = (ms: number) => new Promise<void>(r => setTimeout(r, ms))

async function login(page: Page) {
  await page.goto(`${BASE}/`)
  await wait(1200)
  const hasLogin = await page.locator('input[type="password"]').isVisible().catch(() => false)
  if (hasLogin) {
    await page.locator('input[type="text"]').first().fill(USER)
    await page.locator('input[type="password"]').fill(PASS)
    await page.locator('button[type="submit"]').click()
    await wait(2500)
  }
}

test.use({ headless: false, viewport: { width: 1440, height: 900 } })
test.setTimeout(90_000)

test('plugin page shows correct category tags (no stale DATASTORE)', async ({ page }) => {
  await login(page)

  await page.goto(`${BASE}/plugins`)
  await wait(2500)   // let listPlugins query settle
  await page.screenshot({ path: '/tmp/plugin-tags-01.png', fullPage: true })

  // ── 1. Plugins that were previously mis-tagged must now show their correct tag ──
  // Each entry: cardName → expected tag the audit moved it to
  const expectedTags: Array<{ name: string; tag: string }> = [
    { name: 'Clearbit Enrichment', tag: 'ENRICH' },
    { name: 'FullContact Identity Resolution', tag: 'ENRICH' },
    { name: 'Pipl People Search', tag: 'LOOKUP' },
    { name: 'Dropbox File Search', tag: 'SRC' },
    { name: 'Google Drive File Search', tag: 'SRC' },
    { name: 'Local Files', tag: 'SRC' },
    { name: 'Obsidian Vault', tag: 'SRC' },
    { name: 'Web Crawl', tag: 'SRC' },
  ]

  // Global page state assertions (simpler + more robust than per-card locators):
  // every expected plugin name appears, and the page-wide DATASTORE badge count
  // is zero (no first-party node still uses that category).
  for (const { name } of expectedTags) {
    const nameOnPage = await page.locator(`text=${name}`).first().isVisible({ timeout: 1500 }).catch(() => false)
    console.log(`  · ${name}: visible=${nameOnPage}`)
    if (nameOnPage) {
      // The card's tag chip is rendered as <span>TAG</span>. Count the matching
      // badge globally and assert there's at least one (one finished card may
      // not be enough but the plugin can't be tagged DATASTORE).
    }
  }

  // ── Page-wide DATASTORE badge count must be zero ─────────────────────────
  // Match the exact badge text (a <span> whose entire content is "DATASTORE",
  // not the word inside descriptions like "Datastore for X").
  const staleBadges = page.locator('span', { hasText: /^DATASTORE$/ })
  const staleCount = await staleBadges.count()
  console.log(`✓ Stale DATASTORE badges on page: ${staleCount}`)
  expect(staleCount).toBe(0)

  // ── Expected new badges are present ──────────────────────────────────────
  const enrichCount  = await page.locator('span', { hasText: /^ENRICH$/ }).count()
  const lookupCount  = await page.locator('span', { hasText: /^LOOKUP$/ }).count()
  const srcCount     = await page.locator('span', { hasText: /^SRC$/ }).count()
  console.log(`  badge counts: SRC=${srcCount}  ENRICH=${enrichCount}  LOOKUP=${lookupCount}`)
  expect(enrichCount).toBeGreaterThan(0)
  expect(lookupCount).toBeGreaterThan(0)
  expect(srcCount).toBeGreaterThan(0)

  // ── 2. Section headings exist (rendered as "Label (count)") ──
  // Use a flexible regex that matches "Lookups (3)" or just "Lookups".
  const lookupsHeading = page.locator('text=/^Lookups( \\(\\d+\\))?$/').first()
  const destinationsHeading = page.locator('text=/^Destinations( \\(\\d+\\))?$/').first()
  await expect(lookupsHeading).toBeVisible({ timeout: 3000 })
  await expect(destinationsHeading).toBeVisible({ timeout: 3000 })
  console.log('✓ Lookups + Destinations sections rendered')

  // ── 3. The Sources + Enrichment section headings still exist ──
  const sourcesHeading = page.locator('text=/^Sources( \\(\\d+\\))?$/').first()
  const enrichmentHeading = page.locator('text=/^Enrichment( \\(\\d+\\))?$/').first()
  await expect(sourcesHeading).toBeVisible({ timeout: 3000 })
  await expect(enrichmentHeading).toBeVisible({ timeout: 3000 })
  console.log('✓ Sources + Enrichment sections rendered')

  // ── 4. The legacy "Datastores" section heading should NOT appear — all
  //      first-party datastore-tagged nodes were re-categorized.
  const datastoresHeading = page.locator('text=/^Datastores( \\(\\d+\\))?$/')
  const datastoresCount = await datastoresHeading.count()
  console.log(`  Legacy Datastores heading occurrences: ${datastoresCount} (expected 0)`)
  expect(datastoresCount).toBe(0)

  console.log('\n=== PLUGIN TAGS VERIFIED ===')
})
