import { test, expect, request } from '@playwright/test'

const API = process.env.E2E_API_BASE || 'http://localhost:8000'
const APP = process.env.E2E_APP_BASE || 'http://localhost:5173'

async function adminToken(req: Awaited<ReturnType<typeof request.newContext>>) {
  const r = await req.post(`${API}/v3/auth/login`, {
    data: { username: 'admin', password: process.env.ADMIN_PASSWORD || 'admin' },
  })
  expect(r.ok()).toBeTruthy()
  return (await r.json()).access_token as string
}

test('admin sets global default mode and Preflight preselects it', async ({ page }) => {
  const req = await request.newContext()
  const token = await adminToken(req)

  // Reset state
  await req.put(`${API}/v3/settings/default_mode`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { value: 'leads_generation', scope: 'global' },
  })

  // Skip the UI login — inject the access token into localStorage so the session
  // store reads it on mount. (UI login is exercised elsewhere; not under test here.)
  const loginResp = await req.post(`${API}/v3/auth/login`, {
    data: { username: 'admin', password: process.env.ADMIN_PASSWORD || 'admin' },
  })
  const tokens = await loginResp.json()
  await page.goto(`${APP}/login`)
  await page.evaluate((t) => {
    localStorage.setItem('access_token', t.access_token)
    localStorage.setItem('refresh_token', t.refresh_token)
  }, tokens)

  // PreflightPanel lives inside AgentChat on the Research page, after a query is submitted.
  await page.goto(`${APP}/research`)
  const queryBox = page.getByPlaceholder(/Ask info-broker/i)
  await queryBox.waitFor({ timeout: 10_000 })
  await queryBox.fill('verify default mode')
  await queryBox.press('Enter')

  // Once Preflight renders, the mode picker chips should be present and leads_generation preselected.
  await page.waitForSelector('[data-mode-id]', { timeout: 10_000 })
  await expect(page.locator('[data-mode-id="leads_generation"][aria-pressed="true"]'))
    .toBeVisible({ timeout: 10_000 })

  // Cleanup — clear the global default
  await req.put(`${API}/v3/settings/default_mode`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { value: null, scope: 'global' },
  })
})
