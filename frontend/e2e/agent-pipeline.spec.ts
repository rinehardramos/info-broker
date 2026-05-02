/**
 * Agent System Pipeline E2E tests.
 *
 * Run (headed Chrome):
 *   cd frontend && npx playwright test e2e/agent-pipeline.spec.ts --headed --project=chromium
 *
 * Prerequisites: docker compose up -d (full stack running on localhost:5173 + :8000)
 */
import { test, expect, Page } from '@playwright/test'

const SYSTEM_PIPELINE_ID = '00000000-0000-4000-8000-000000000001'
const TEST_USER = { username: 'admin', password: 'admin' }

async function login(page: Page) {
  await page.goto('/login')
  await page.getByPlaceholder(/username/i).fill(TEST_USER.username)
  await page.getByPlaceholder(/password/i).fill(TEST_USER.password)
  await page.getByRole('button', { name: /login|sign in/i }).click()
  await page.waitForURL(url => !url.pathname.includes('/login'), { timeout: 10_000 })
}

test.describe('Agent Settings — pipeline selector', () => {
  test.beforeEach(async ({ page }) => { await login(page) })

  test('Settings > Agent shows system default pipeline with [Default] label', async ({ page }) => {
    await page.goto('/settings')
    await page.getByRole('button', { name: /^agent$/i }).click()
    await expect(page.getByText(/agent settings/i)).toBeVisible()
    const option = page.locator('select option').filter({ hasText: '[Default]' })
    await expect(option).toBeVisible()
    await expect(option).toContainText('Agent Default')
  })
})

test.describe('AgentChat — pipeline name in header', () => {
  test.beforeEach(async ({ page }) => { await login(page) })

  test('Agent header shows active pipeline name', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText(/\[Default\]/)).toBeVisible({ timeout: 8_000 })
  })
})

test.describe('Agent message — creates pipeline run', () => {
  test.beforeEach(async ({ page }) => { await login(page) })

  test('sending a message creates a pipeline run and shows status', async ({ page }) => {
    await page.goto('/')
    const textarea = page.getByPlaceholder(/ask info-broker/i)
    await textarea.fill('test query for e2e')
    await textarea.press('Enter')
    await expect(page.getByText(/research started/i)).toBeVisible({ timeout: 8_000 })
  })
})

test.describe('Pipeline Builder — system pipeline constraints', () => {
  test.beforeEach(async ({ page }) => { await login(page) })

  test('system pipeline shows DEFAULT badge and has no delete button', async ({ page }) => {
    await page.goto('/pipelines')
    await page.getByText('Agent Default').first().click()
    await expect(page.getByText('DEFAULT')).toBeVisible({ timeout: 5_000 })
    const deleteBtn = page.getByRole('button', { name: /delete/i })
    await expect(deleteBtn).not.toBeVisible()
  })

  test('agent_input node shows FIXED label and has no remove button', async ({ page }) => {
    await page.goto('/pipelines')
    await page.getByText('Agent Default').first().click()
    await expect(page.locator('[data-testid="step-card-agent_input"]')).toBeVisible({ timeout: 5_000 })
    await expect(page.getByTitle(/required and cannot be moved/i)).toBeVisible()
  })
})

test.describe('Settings — set custom agent pipeline', () => {
  test.beforeEach(async ({ page }) => { await login(page) })

  test('can set a user pipeline as active agent pipeline', async ({ page }) => {
    const loginRes = await page.request.post('/api/v3/auth/login', {
      data: TEST_USER,
    })
    const { access_token } = await loginRes.json()

    const nodeId = crypto.randomUUID()
    const createRes = await page.request.post('/api/v3/pipelines', {
      data: {
        name: 'E2E Agent Override',
        nodes: [{ id: nodeId, node_type: 'agent_input', label: 'CLI', config: {}, position_x: 0, position_y: 0 }],
        edges: [],
      },
      headers: { Authorization: `Bearer ${access_token}` },
    })
    expect(createRes.ok()).toBeTruthy()
    const created = await createRes.json()

    await page.goto('/settings')
    await page.getByRole('button', { name: /^agent$/i }).click()
    await page.selectOption('select', created.id)
    await expect(page.getByText('Saved')).toBeVisible({ timeout: 5_000 })

    await page.goto('/')
    await expect(page.getByText('E2E Agent Override')).toBeVisible({ timeout: 8_000 })
  })
})
