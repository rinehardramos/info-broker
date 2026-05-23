/**
 * Regression: canonical no-brain-work query must produce accurate ask_user surface.
 *
 * Asserts:
 *   1. Misleading copy ("could not extract sufficient signals") is absent.
 *   2. RunBadge is visible with a UUID title.
 *   3. AdminGateDetail renders "no_brain_work" chip for admin users.
 *
 * Run: cd frontend && npx playwright test e2e/ask-user-diagnostic.spec.ts --reporter=list
 *
 * NOTE (WSL2 Ubuntu 26.04): If Playwright browser binaries are incompatible with
 * the host kernel, this test is deferred to CI or a developer machine. The spec
 * file itself is the deliverable; running it is a separate concern.
 * See: Task 14 implementer report — "browser binaries incompatible with WSL2 Ubuntu 26.04".
 */
import { test, expect } from '@playwright/test'

test.use({ baseURL: 'http://localhost:5173' })
test.setTimeout(120_000)

const CANONICAL_QUERY = 'show all properties for rent in chicago with a budget of $500 to $1000'

test('canonical no-work query produces accurate ask_user surface with RunBadge', async ({ page }) => {
  // ── Login ──────────────────────────────────────────────────────────────────
  await page.goto('/login')
  // Mirror the login pattern used in agent-pipeline.spec.ts
  await page.getByPlaceholder(/username/i).fill('admin')
  await page.getByPlaceholder(/password/i).fill('admin')
  await page.getByRole('button', { name: /login|sign\s*in/i }).click()
  await page.waitForURL((u) => !u.pathname.includes('/login'), { timeout: 15_000 })

  // ── Submit canonical query ─────────────────────────────────────────────────
  // The main chat input has placeholder "ask info-broker" (from agent-pipeline.spec.ts)
  const input = page.getByPlaceholder(/ask info-broker|ask|search|query|message/i).first()
  await input.fill(CANONICAL_QUERY)
  await input.press('Enter')

  // ── Wait for ask_user diagnostic text ─────────────────────────────────────
  // The UI should show wording from the no_brain_work path:
  //   "didn't gather" OR "try a more specific" OR similar.
  // waitForFunction polls the DOM so it handles slow networks.
  await page.waitForFunction(
    () =>
      document.body.innerText.includes("didn't gather") ||
      document.body.innerText.includes("try a more specific") ||
      document.body.innerText.includes("no results were gathered"),
    { timeout: 90_000 },
  )

  // ── Misleading wording MUST be absent ─────────────────────────────────────
  await expect(page.getByText(/could not extract sufficient signals/i)).toHaveCount(0)

  // ── RunBadge present ───────────────────────────────────────────────────────
  // RunBadge renders with data-testid="run-badge" and a UUID in the title attribute.
  const badge = page.locator('[data-testid="run-badge"]').first()
  await expect(badge).toBeVisible()
  await expect(badge).toHaveAttribute('title', /[0-9a-f]{8}-[0-9a-f]{4}/i)

  // ── AdminGateDetail present (admin run) ────────────────────────────────────
  // For admin users, AdminGateDetail renders a chip with the failing_check_kind code.
  // For the canonical query the kind is "no_brain_work".
  await expect(page.getByText(/no_brain_work/).first()).toBeVisible({ timeout: 5_000 })

  // Screenshot for evidence
  await page.screenshot({ path: '/tmp/ask-user-no-brain-work.png', fullPage: true })
})
