/**
 * IS Brain live test — uses Chrome debug mode to observe the IS brain
 * organically selecting and using new pipeline plugins.
 *
 * Run:
 *   cd frontend && npx playwright test e2e/is-brain-live.spec.ts --headed --project=chromium
 *
 * Prerequisites:
 *   - Chrome running with --remote-debugging-port=9222
 *   - Full stack: docker compose up -d
 *   - ANTHROPIC_API_KEY set in the API container (or OAuth token injected)
 */
import { test, expect } from '@playwright/test'

const TEST_USER = { username: 'admin', password: 'admin' }

// IS brain research can take a while — 5 minutes
test.setTimeout(300_000)

test('IS brain: research query produces findings in UI', async ({ page }) => {
  // Login
  await page.goto('/login')
  await page.getByPlaceholder(/username/i).fill(TEST_USER.username)
  await page.getByPlaceholder(/password/i).fill(TEST_USER.password)
  await page.getByRole('button', { name: /login|sign in/i }).click()
  await page.waitForURL(url => !url.pathname.includes('/login'), { timeout: 10_000 })

  // Navigate to agent chat
  await page.goto('/research')
  await page.waitForLoadState('networkidle')

  // Count existing run tabs before sending
  const runTabsBefore = await page.locator('text=/Research:|AI agent/').count()
  console.log(`[TEST] Existing run tabs: ${runTabsBefore}`)

  // Send the research query
  const textarea = page.getByPlaceholder('Ask info-broker… (Enter to send)')
  await expect(textarea).toBeVisible({ timeout: 10_000 })
  await textarea.fill('Who are the top 3 AI agent framework founders in 2026?')
  await textarea.press('Enter')
  console.log('[TEST] Message sent, waiting for IS brain...')

  // A new run tab should appear in the sidebar (text contains "Research:" or the query)
  // The IS brain creates a pipeline_run with trigger_type=agent_is
  // Wait for a new tab to appear (the run starts as queued/running)
  await expect(async () => {
    const currentTabs = await page.locator('text=/Research:|AI agent/').count()
    expect(currentTabs).toBeGreaterThan(runTabsBefore)
  }).toPass({ timeout: 30_000 })
  console.log('[TEST] New run tab appeared!')

  // Wait for the run to complete, hit the confirm gate, or error
  await expect(async () => {
    const text = await page.locator('body').innerText()

    // Fail fast on auth/error states
    if (text.includes('not authenticated') || text.includes('Claude Code error') ||
        text.includes('IS Research — Failed') || text.includes('Research failed')) {
      throw new Error(`Research failed: ${text.match(/Research failed[^\n]*/)?.[0] ?? 'see UI'}`)
    }

    // Confirm gate — click through it and keep waiting
    if (text.includes("Yes, that's it")) {
      console.log('[TEST] Confirm gate appeared — clicking through')
      await page.getByText("Yes, that's it").first().click()
    }

    const hasResults = text.includes('succeeded') || text.includes('Findings') ||
                       text.includes('confidence') || text.includes('Go Deeper') ||
                       text.includes('RESULT FOUND')
    expect(hasResults).toBe(true)
  }).toPass({ timeout: 240_000 })
  console.log('[TEST] Research completed with results!')

  // Screenshot the results
  await page.screenshot({ path: 'test-results/is-brain-live-result.png', fullPage: true })

  // Verify findings are present
  const bodyText = await page.locator('body').innerText()
  console.log('[TEST] Page contains findings:', bodyText.includes('confidence') || bodyText.includes('Findings'))
  console.log('[TEST] Page text (last 2000 chars):', bodyText.slice(-2000))
})
