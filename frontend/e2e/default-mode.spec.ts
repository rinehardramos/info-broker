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
  await req.put(`${API}/v3/settings/default-mode`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { value: 'lead_gen', scope: 'global' },
  })

  // Log in via the UI so the session store is populated.
  // The login form uses placeholder text (no aria-label), so we target by name attribute.
  await page.goto(`${APP}/login`)
  await page.locator('input[name="username"]').fill('admin')
  await page.locator('input[name="password"]').fill(process.env.ADMIN_PASSWORD || 'admin')
  await page.getByRole('button', { name: /sign in/i }).click()

  // PreflightPanel lives on the Dashboard (/) via AgentChat — there is no /search route.
  await page.goto(`${APP}/`)
  await page.waitForSelector('[data-mode-id]', { timeout: 10_000 })
  await expect(page.locator('[data-mode-id="lead_gen"][aria-pressed="true"]'))
    .toBeVisible({ timeout: 10_000 })

  // Cleanup — clear the global default
  await req.put(`${API}/v3/settings/default-mode`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { value: null, scope: 'global' },
  })
})
