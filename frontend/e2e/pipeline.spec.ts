/**
 * Pipeline E2E tests — runs against the live stack (http://localhost:5173 + API on :8000).
 *
 * Run:
 *   npx playwright test --headed
 *
 * Prerequisites:
 *   docker compose up -d  (postgres, api, frontend must be running)
 */
import { test, expect, Page } from '@playwright/test'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function login(page: Page) {
  await page.goto('/login')
  await page.getByPlaceholder(/username/i).fill('admin')
  await page.getByPlaceholder(/password/i).fill('admin')
  await page.getByRole('button', { name: /login|sign in/i }).click()
  await page.waitForURL(url => !url.pathname.includes('/login'), { timeout: 10_000 })
}

// Unique name so parallel reruns don't collide
const PIPELINE_NAME = `E2E-Pipeline-${Date.now()}`

// ---------------------------------------------------------------------------
// Auth guard
// ---------------------------------------------------------------------------

test.describe('Auth gate', () => {
  test('unauthenticated user is redirected to login', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveURL(/\/login/)
  })

  test('wrong credentials shows error', async ({ page }) => {
    await page.goto('/login')
    await page.getByPlaceholder(/username/i).fill('admin')
    await page.getByPlaceholder(/password/i).fill('wrongpassword')
    await page.getByRole('button', { name: /login|sign in/i }).click()
    // Login.tsx sets error to 'Invalid credentials' on catch
    await expect(page.getByText('Invalid credentials')).toBeVisible({ timeout: 8_000 })
  })

  test('valid credentials redirect to main app', async ({ page }) => {
    await login(page)
    await expect(page).not.toHaveURL(/\/login/)
  })
})

// ---------------------------------------------------------------------------
// ResultsPanel — Pipeline tab
// ---------------------------------------------------------------------------

test.describe('ResultsPanel Pipeline tab', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('Pipeline tab is visible and active by default', async ({ page }) => {
    // Use exact text match to avoid matching "Create A Pipeline" button
    await expect(page.getByRole('button', { name: /^Pipeline$/ })).toBeVisible()
  })

  test('shows Getting Started when no pipelines exist', async ({ page }) => {
    // Wait for the pipeline list API to respond before checking count
    await page.waitForResponse(
      r => /\/api\/v3\/pipelines$/.test(r.url()) && r.status() === 200,
      { timeout: 8_000 },
    )
    // Only assertable on a fresh account; skip if pipelines already exist
    const pipelines = page.getByTitle('Run pipeline')
    const hasPipelines = await pipelines.count() > 0
    if (!hasPipelines) {
      await expect(page.getByText('Getting Started')).toBeVisible()
    }
  })
})

// ---------------------------------------------------------------------------
// Pipeline creation via PipelineBuilder
// ---------------------------------------------------------------------------

test.describe('PipelineBuilder — create pipeline', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
    // PipelineBuilder lives at /pipelines (no ID = no pre-selection)
    await page.goto('/pipelines')
  })

  test('+ New Pipeline button is visible', async ({ page }) => {
    await expect(page.getByText('+ New Pipeline')).toBeVisible({ timeout: 8_000 })
  })

  test('clicking + New Pipeline shows inline creation form', async ({ page }) => {
    await page.getByText('+ New Pipeline').click()
    await expect(page.getByPlaceholder('Pipeline name *')).toBeVisible()
    await expect(page.getByPlaceholder('Description (optional)')).toBeVisible()
  })

  test('Create button is disabled with empty name', async ({ page }) => {
    await page.getByText('+ New Pipeline').click()
    const createBtn = page.getByRole('button', { name: 'Create' })
    await expect(createBtn).toBeDisabled()
  })

  test('Cancel button dismisses form without creating', async ({ page }) => {
    await page.getByText('+ New Pipeline').click()
    await page.getByRole('button', { name: 'Cancel' }).click()
    await expect(page.getByPlaceholder('Pipeline name *')).not.toBeVisible()
  })

  test('can create a new pipeline with a name', async ({ page }) => {
    await page.getByText('+ New Pipeline').click()
    await page.getByPlaceholder('Pipeline name *').fill(PIPELINE_NAME)
    await page.getByPlaceholder('Description (optional)').fill('E2E test pipeline')
    await page.getByRole('button', { name: 'Create' }).click()

    // The new pipeline should appear in the sidebar
    await expect(page.getByText(PIPELINE_NAME)).toBeVisible({ timeout: 8_000 })
    // Form should be gone
    await expect(page.getByPlaceholder('Pipeline name *')).not.toBeVisible()
  })
})

// ---------------------------------------------------------------------------
// Pipeline — add and delete steps
// ---------------------------------------------------------------------------

test.describe('PipelineBuilder — steps', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
    await page.goto('/pipelines')

    // Create a fresh pipeline for this test
    await page.getByText('+ New Pipeline').click({ timeout: 8_000 })
    await page.getByPlaceholder('Pipeline name *').fill(`Steps-Test-${Date.now()}`)

    // Listen for the GET /v3/pipelines/:id detail response BEFORE clicking Create,
    // so we don't miss it if it arrives quickly after the URL update.
    const detailResponse = page.waitForResponse(
      r => /\/api\/v3\/pipelines\/[^/]+$/.test(r.url()) && r.request().method() === 'GET' && r.status() === 200,
      { timeout: 10_000 },
    )

    await page.getByRole('button', { name: 'Create' }).click()
    // Wait for URL to update to /pipelines/:id (navigate happens in createMutation.onSuccess)
    await page.waitForURL(/\/pipelines\/.+/, { timeout: 8_000 })
    // Wait for the pipeline detail API response — ensures useEffect has fired and
    // set prevPipelineId.current before tests start adding steps (eliminates race condition)
    await detailResponse
    await expect(page.getByRole('button', { name: '×' })).toHaveCount(0, { timeout: 5_000 })
  })

  test('can add a step via the Add Step dropdown', async ({ page }) => {
    const addStepSelect = page.locator('select').filter({ hasText: /Add Step/i })
    // Before: no × buttons
    await expect(page.getByRole('button', { name: '×' })).toHaveCount(0)
    await addStepSelect.selectOption({ label: 'DDG Search' })
    // After: one × button (one step added)
    await expect(page.getByRole('button', { name: '×' })).toHaveCount(1, { timeout: 5_000 })
  })

  test('deleting a step removes it from the list', async ({ page }) => {
    const addStepSelect = page.locator('select').filter({ hasText: /Add Step/i })
    await addStepSelect.selectOption({ label: 'DDG Search' })
    await expect(page.getByRole('button', { name: '×' })).toHaveCount(1, { timeout: 3_000 })
    await addStepSelect.selectOption({ label: 'RSS Monitor' })
    await expect(page.getByRole('button', { name: '×' })).toHaveCount(2)

    // Delete the first step (Step 1)
    await page.getByRole('button', { name: '×' }).first().click()

    // Only one step remains
    await expect(page.getByRole('button', { name: '×' })).toHaveCount(1)
  })

  test('saving after step deletion preserves remaining step', async ({ page }) => {
    const addStepSelect = page.locator('select').filter({ hasText: /Add Step/i })
    await addStepSelect.selectOption({ label: 'DDG Search' })
    await expect(page.getByRole('button', { name: '×' })).toHaveCount(1, { timeout: 3_000 })
    // Use Qdrant Search (no required fields) so Save stays enabled after DDG Search is deleted
    await addStepSelect.selectOption({ label: 'Qdrant Search' })
    await expect(page.getByRole('button', { name: '×' })).toHaveCount(2)

    // Delete Step 1 (DDG Search)
    await page.getByRole('button', { name: '×' }).first().click()
    await expect(page.getByRole('button', { name: '×' })).toHaveCount(1)

    // Save — URL updates to /pipelines/:id after create, so reload works
    await page.getByRole('button', { name: 'Save' }).click()
    await page.waitForTimeout(1000)

    // Reload and verify the remaining step (Qdrant Search) persists
    await page.reload()
    await expect(page.getByRole('button', { name: '×' })).toHaveCount(1, { timeout: 8_000 })
  })
})

// ---------------------------------------------------------------------------
// Pipeline — Agent Input → DDG Search → AI Scoring full flow (#30)
// ---------------------------------------------------------------------------

test.describe('PipelineBuilder — Agent Input → DDG Search → AI Scoring', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
    await page.goto('/pipelines')

    // Create a fresh pipeline
    await page.getByText('+ New Pipeline').click({ timeout: 8_000 })
    await page.getByPlaceholder('Pipeline name *').fill(`AgentInput-Test-${Date.now()}`)

    const detailResponse = page.waitForResponse(
      r => /\/api\/v3\/pipelines\/[^/]+$/.test(r.url()) && r.request().method() === 'GET' && r.status() === 200,
      { timeout: 10_000 },
    )
    await page.getByRole('button', { name: 'Create' }).click()
    await page.waitForURL(/\/pipelines\/.+/, { timeout: 8_000 })
    await detailResponse
    await expect(page.getByRole('button', { name: '×' })).toHaveCount(0, { timeout: 5_000 })
  })

  test('can build and save Agent Input → DDG Search → AI Scoring pipeline', async ({ page }) => {
    const addStepSelect = page.locator('select').filter({ hasText: /Add Step/i })
    const panel = page.getByTestId('node-config-panel')

    // Helper: open step config, fill first text input, close
    async function fillFirstInput(nodeType: string, value: string) {
      await page.getByTestId(`step-card-${nodeType}`).click()
      await expect(panel).toBeVisible({ timeout: 5_000 })
      await panel.locator('input[type="text"]').first().fill(value)
      await panel.getByRole('button', { name: 'Done' }).click()
      await expect(panel).not.toBeVisible({ timeout: 3_000 })
    }

    // Helper: ensure sourceNodeType → targetNodeType edge exists via the OUTPUTS section
    async function ensureConnected(sourceNodeType: string, targetNodeType: string) {
      await page.getByTestId(`step-card-${sourceNodeType}`).click()
      await expect(panel).toBeVisible({ timeout: 5_000 })
      await expect(panel.getByText('OUTPUTS')).toBeVisible({ timeout: 3_000 })
      // Click only if not already connected (auto-wiring may have done it)
      const btn = panel.getByTestId(`output-connect-${targetNodeType}`)
      const label = await btn.textContent()
      if (label?.trim() === 'Connect') {
        await btn.click()
        await expect(btn).toHaveText('Connected', { timeout: 3_000 })
      }
      await panel.getByRole('button', { name: 'Done' }).click()
      await expect(panel).not.toBeVisible({ timeout: 3_000 })
    }

    // --- Add steps ---
    // agent_input is locked (no × button) — verify via step-card testid instead
    await addStepSelect.selectOption({ label: 'Agent Input' })
    await expect(page.getByTestId('step-card-agent_input')).toBeVisible({ timeout: 5_000 })

    await addStepSelect.selectOption({ label: 'DDG Search' })
    await expect(page.getByRole('button', { name: '×' })).toHaveCount(1, { timeout: 5_000 })

    await addStepSelect.selectOption({ label: 'AI Scoring' })
    await expect(page.getByRole('button', { name: '×' })).toHaveCount(2, { timeout: 5_000 })

    // --- Fill required config fields ---
    // DDG Search has no required fields (query comes from upstream input)
    await fillFirstInput('agent_input', 'what is pi?')
    await fillFirstInput('ai_scoring', 'relevant to mathematics')

    // --- Ensure edges: Agent Input → DDG Search, DDG Search → AI Scoring ---
    // Each ensureConnected call opens the panel and clicks Done, which auto-saves.
    await ensureConnected('agent_input', 'ddg_search')
    await ensureConnected('ddg_search', 'ai_scoring')

    // Done auto-saves — wait for the last PUT to complete before reloading
    await page.waitForResponse(
      r => /\/api\/v3\/pipelines\/[^/]+$/.test(r.url()) && r.request().method() === 'PUT' && r.status() === 200,
      { timeout: 10_000 },
    )

    // --- Reload and verify all 3 steps persisted ---
    await page.reload()
    await expect(page.getByTestId('step-card-agent_input')).toBeVisible({ timeout: 8_000 })
    await expect(page.getByRole('button', { name: '×' })).toHaveCount(2, { timeout: 8_000 })
  })
})

// ---------------------------------------------------------------------------
// PipelineBuilder — reorder steps (#32)
// ---------------------------------------------------------------------------

test.describe('PipelineBuilder — reorder steps', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
    await page.goto('/pipelines')
    await page.getByText('+ New Pipeline').click({ timeout: 8_000 })
    await page.getByPlaceholder('Pipeline name *').fill(`Reorder-Test-${Date.now()}`)
    const detailResponse = page.waitForResponse(
      r => /\/api\/v3\/pipelines\/[^/]+$/.test(r.url()) && r.request().method() === 'GET' && r.status() === 200,
      { timeout: 10_000 },
    )
    await page.getByRole('button', { name: 'Create' }).click()
    await page.waitForURL(/\/pipelines\/.+/, { timeout: 8_000 })
    await detailResponse
    await expect(page.getByRole('button', { name: '×' })).toHaveCount(0, { timeout: 5_000 })
  })

  test('can move a step up and the order persists after save', async ({ page }) => {
    const addStepSelect = page.locator('select').filter({ hasText: /Add Step/i })

    // Use 2 enrich/score nodes with no required fields so order is deterministic and Save stays enabled
    // Order after add: Qdrant Search (1), Manual Scoring (2)
    await addStepSelect.selectOption({ label: 'Qdrant Search' })
    await expect(page.getByRole('button', { name: '×' })).toHaveCount(1, { timeout: 5_000 })
    await addStepSelect.selectOption({ label: 'Manual Scoring' })
    await expect(page.getByRole('button', { name: '×' })).toHaveCount(2, { timeout: 5_000 })

    // Verify initial order: Qdrant Search is first
    const firstBefore = await page.locator('[data-testid^="step-card-"]').first().getAttribute('data-testid')
    expect(firstBefore).toBe('step-card-qdrant_search')

    // Move Manual Scoring (step 2, nth(1) ▲) up → new order: Manual Scoring · Qdrant Search
    await page.getByTitle('Move up').nth(1).click()

    // First step card should now be Manual Scoring
    await expect(async () => {
      const firstAfter = await page.locator('[data-testid^="step-card-"]').first().getAttribute('data-testid')
      expect(firstAfter).toBe('step-card-manual_scoring')
    }).toPass({ timeout: 3_000 })

    // Save via toolbar Save button (dirty after move)
    await Promise.all([
      page.waitForResponse(
        r => /\/api\/v3\/pipelines\/[^/]+$/.test(r.url()) && r.request().method() === 'PUT' && r.status() === 200,
        { timeout: 10_000 },
      ),
      page.getByRole('button', { name: 'Save' }).click(),
    ])

    // Reload and verify Manual Scoring is still first
    await page.reload()
    await expect(page.getByRole('button', { name: '×' })).toHaveCount(2, { timeout: 8_000 })
    const firstAfterReload = await page.locator('[data-testid^="step-card-"]').first().getAttribute('data-testid')
    expect(firstAfterReload).toBe('step-card-manual_scoring')
  })
})

// ---------------------------------------------------------------------------
// Pipeline tab — click pipeline to view results
// ---------------------------------------------------------------------------

test.describe('Pipeline tab — pipeline row click', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('clicking pipeline name is responsive', async ({ page }) => {
    // Wait for pipelines to load
    await page.waitForResponse(
      r => /\/api\/v3\/pipelines$/.test(r.url()) && r.status() === 200,
      { timeout: 8_000 },
    )

    // Ensure Pipeline tab is active
    await page.getByRole('button', { name: /^Pipeline$/ }).click()

    // Check if any pipelines exist — skip if none
    const pipelineRows = page.locator('[data-testid^="pipeline-row-"]')
    const count = await pipelineRows.count()
    if (count === 0) {
      test.skip()
      return
    }

    // Pipeline name span is always cursor:pointer (it selects the latest run when one exists)
    const firstRow = pipelineRows.first()
    const nameSpan = firstRow.locator('span.truncate')
    await expect(nameSpan).toBeVisible()
    const cursor = await nameSpan.evaluate(el => getComputedStyle(el).cursor)
    expect(cursor).toBe('pointer')

    // Clicking name should NOT navigate away (navigation is only via the ✎ edit button)
    const urlBefore = page.url()
    await nameSpan.click()
    await page.waitForTimeout(500)
    expect(page.url()).toBe(urlBefore)

    // If the pipeline has runs, a run tab should now be active
    const hasRunTab = await page.locator('button[class*="rounded"]').filter({ hasText: /●/ }).count() > 0
    // (hasRunTab being true is a bonus; when no runs exist nothing happens — both are valid)
  })

  test('edit button navigates to pipeline builder', async ({ page }) => {
    await page.waitForResponse(
      r => /\/api\/v3\/pipelines$/.test(r.url()) && r.status() === 200,
      { timeout: 8_000 },
    )

    await page.getByRole('button', { name: /^Pipeline$/ }).click()

    const editButtons = page.getByTitle('Edit pipeline')
    const count = await editButtons.count()
    if (count === 0) {
      test.skip()
      return
    }

    await editButtons.first().click()
    await expect(page).toHaveURL(/\/pipelines\//, { timeout: 5_000 })
  })

  test('play button click triggers a pipeline run', async ({ page }) => {
    await page.waitForResponse(
      r => /\/api\/v3\/pipelines$/.test(r.url()) && r.status() === 200,
      { timeout: 8_000 },
    )

    await page.getByRole('button', { name: /^Pipeline$/ }).click()

    const playButtons = page.getByTitle('Run pipeline')
    const count = await playButtons.count()
    if (count === 0) {
      test.skip()
      return
    }

    // Click play — should trigger API call
    const runResponse = page.waitForResponse(
      r => /\/api\/v3\/pipelines\/[^/]+\/run/.test(r.url()) && r.request().method() === 'POST',
      { timeout: 8_000 },
    )
    await playButtons.first().click()
    const resp = await runResponse
    expect([200, 201, 202, 422]).toContain(resp.status()) // 202 accepted, 422 if validation errors
  })

  test('Create Pipeline button is always visible', async ({ page }) => {
    await page.waitForResponse(
      r => /\/api\/v3\/pipelines$/.test(r.url()) && r.status() === 200,
      { timeout: 8_000 },
    )
    await page.getByRole('button', { name: /^Pipeline$/ }).click()
    // Either the empty-state "Create A Pipeline" or the always-visible "+ Create Pipeline"
    await expect(
      page.getByRole('button', { name: /Create.*Pipeline/i }),
    ).toBeVisible({ timeout: 8_000 })
  })
})

// ---------------------------------------------------------------------------
// Pipeline — run and LiveStream
// ---------------------------------------------------------------------------

test.describe('Pipeline — run flow', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('play button triggers a run and appears in LiveStream', async ({ page }) => {
    // This test is skipped if no pipelines exist
    const playButtons = page.getByTitle('Run pipeline')
    const count = await playButtons.count()
    if (count === 0) {
      test.skip()
      return
    }

    await playButtons.first().click()
    // A pause button should appear (run in progress) or run appears in LiveStream
    await expect(
      page.getByTitle('Pause (cancel run)').or(page.locator('[style*="#facc15"]')),
    ).toBeVisible({ timeout: 10_000 })
  })
})

// ---------------------------------------------------------------------------
// Plugins page
// ---------------------------------------------------------------------------

test.describe('Plugins page', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
    await page.goto('/plugins')
  })

  test('shows INTEGRATIONS and PIPELINE NODES sections', async ({ page }) => {
    // Use getByRole heading to avoid substring collision with page subtitle
    await expect(page.getByRole('heading', { name: 'INTEGRATIONS' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'PIPELINE NODES' })).toBeVisible()
  })

  test('LinkedIn Scraper card has Enabled/Disabled toggle', async ({ page }) => {
    await expect(page.getByText('LinkedIn Scraper')).toBeVisible()
    await expect(
      page.getByRole('button', { name: /Enabled|Disabled/i }).first(),
    ).toBeVisible()
  })

  test('clicking a NodePlugin card navigates to detail page', async ({ page }) => {
    await page.getByText('DDG Search').click()
    await expect(page).toHaveURL(/\/plugins\/node\/ddg_search/)
    await expect(page.getByText('CONFIG SCHEMA')).toBeVisible()
  })
})

// ---------------------------------------------------------------------------
// Security — direct API auth enforcement (via fetch in browser context)
// ---------------------------------------------------------------------------

test.describe('Security — API auth', () => {
  test('unauthenticated API call returns 401 or 403', async ({ page }) => {
    const response = await page.request.get('http://localhost:8000/v3/pipelines')
    expect([401, 403]).toContain(response.status())
  })

  test('pipeline endpoint rejects bad token', async ({ page }) => {
    const response = await page.request.get('http://localhost:8000/v3/pipelines', {
      headers: { Authorization: 'Bearer totally.invalid.token' },
    })
    expect([401, 403]).toContain(response.status())
  })
})
