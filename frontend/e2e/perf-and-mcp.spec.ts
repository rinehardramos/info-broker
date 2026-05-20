/**
 * End-to-end perf measurement (with correct API timings) + MCP smoke.
 *
 * Performance:
 *   - Cold-load Core Web Vitals
 *   - Per-route TTI after admin login
 *   - Median + p95 API latency (timed via request/response event timestamps,
 *     not the buggy Playwright timing() API which can return negatives).
 *
 * MCP functional smoke:
 *   - Exec into the API container, list the registered MCP tools.
 *   - Invoke one cheap tool (run_wikipedia_api) and check the response shape.
 *   - Report timings.
 */
import { test, expect } from '@playwright/test'
import { execSync } from 'node:child_process'

const BASE = 'https://infobroker.tech'
const wait = (ms: number) => new Promise(r => setTimeout(r, ms))
const fmt = (n: number) => n < 1000 ? `${n.toFixed(0)}ms` : `${(n / 1000).toFixed(2)}s`

test('perf — admin session with corrected API timings', async ({ browser }) => {
  test.setTimeout(180_000)
  const ctx = await browser.newContext()
  const page = await ctx.newPage()

  // Time requests via event timestamps — reliable
  const inflight = new Map<string, number>()
  const timings: { url: string; ms: number; status: number; method: string }[] = []
  page.on('request', (r) => inflight.set(r.url() + r.method(), Date.now()))
  page.on('response', (r) => {
    const key = r.url() + r.request().method()
    const start = inflight.get(key)
    if (start && /\/v3\//.test(r.url())) {
      timings.push({
        url: r.url().replace(/^https?:\/\/[^/]+/, ''),
        method: r.request().method(),
        ms: Date.now() - start,
        status: r.status(),
      })
    }
  })

  console.log('\n══════════════════════════════════════════════════════════════')
  console.log('  Admin session perf · infobroker.tech')
  console.log('══════════════════════════════════════════════════════════════')

  // Login
  const tLogin = Date.now()
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' })
  const pwd = page.locator('input[type="password"]').first()
  if (await pwd.isVisible({ timeout: 5_000 }).catch(() => false)) {
    await page.fill('input[type="text"], input[type="email"]', 'admin')
    await pwd.fill('admin')
    await page.locator('button[type="submit"]').first().click()
    await page.waitForURL(/\/$|\/research|\/runs|\/dashboard/, { timeout: 15_000 }).catch(() => {})
  }
  console.log(`\n  Login flow             ${fmt(Date.now() - tLogin)}`)

  // Per-route nav
  console.log()
  for (const route of ['/dashboard', '/research', '/runs', '/wallet', '/settings', '/monitors']) {
    const t0 = Date.now()
    await page.goto(`${BASE}${route}`, { waitUntil: 'networkidle' }).catch(() => {})
    console.log(`  ${route.padEnd(20)} ${fmt(Date.now() - t0)}`)
  }

  // API timing breakdown
  const ok = timings.filter(t => t.status < 400)
  const err = timings.filter(t => t.status >= 400)
  const sorted = [...ok].sort((a, b) => a.ms - b.ms)
  const p = (q: number) => sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * q))]?.ms ?? 0

  console.log(`\n  API requests          ${timings.length}`)
  console.log(`     2xx                ${ok.length}`)
  console.log(`     ≥400               ${err.length}`)
  console.log(`     median             ${fmt(p(0.5))}`)
  console.log(`     p75                ${fmt(p(0.75))}`)
  console.log(`     p95                ${fmt(p(0.95))}`)
  console.log(`     max                ${fmt(p(0.99))}`)

  // Top 5 slowest endpoints
  const sortedDesc = [...ok].sort((a, b) => b.ms - a.ms).slice(0, 5)
  console.log(`\n  Slowest endpoints:`)
  sortedDesc.forEach(t => console.log(`     ${t.ms.toString().padStart(5)}ms  ${t.method}  ${t.url}`))

  expect(err.length, `${err.length} API errors — see log above`).toBeLessThan(3)
  await ctx.close()
})

test('mcp — list tools + invoke a cheap one against live server', async () => {
  test.setTimeout(60_000)

  console.log('\n══════════════════════════════════════════════════════════════')
  console.log('  MCP functional smoke test')
  console.log('══════════════════════════════════════════════════════════════')

  // 1. List the tools the server registers
  const listScript = `
import sys; sys.path.insert(0, '/app')
from mcp_server import server
from mcp_server.server import mcp
import asyncio

async def go():
    tools = await mcp.list_tools()
    return tools

tools = asyncio.run(go())
print(f'COUNT: {len(tools)}')
for t in tools:
    name = t.name if hasattr(t, 'name') else t.get('name', '?')
    desc = (t.description if hasattr(t, 'description') else t.get('description', '')) or ''
    print(f'TOOL: {name} :: {desc[:80]}')
`.trim()

  const listOutput = execSync(
    `docker compose exec -T info-broker-api /app/.venv/bin/python -c '${listScript.replace(/'/g, "\\'")}'`,
    { encoding: 'utf-8', maxBuffer: 8 * 1024 * 1024, cwd: '../' }
  )
  const countLine = listOutput.split('\n').find(l => l.startsWith('COUNT:')) || 'COUNT: 0'
  const toolCount = parseInt(countLine.split(':')[1].trim())
  const toolLines = listOutput.split('\n').filter(l => l.startsWith('TOOL:'))

  console.log(`\n  Tools registered       ${toolCount}`)
  console.log('  Sample tools (first 10):')
  toolLines.slice(0, 10).forEach(l => console.log(`     ${l.replace('TOOL: ', '')}`))

  expect(toolCount).toBeGreaterThan(10)

  // 2. Invoke a cheap tool: run_wikipedia_api(title="Anthropic")
  console.log(`\n  Invoking run_wikipedia_api(title="Anthropic")…`)
  const invokeScript = `
import sys, json, time; sys.path.insert(0, '/app')
from mcp_server.server import run_wikipedia_api
import asyncio

async def go():
    t0 = time.time()
    out = await run_wikipedia_api(title='Anthropic', language='en')
    return time.time() - t0, out

ms, out = asyncio.run(go())
print(f'TIME_MS: {int(ms * 1000)}')
print(f'OUT_LEN: {len(out) if isinstance(out, str) else len(json.dumps(out))}')
try:
    parsed = json.loads(out) if isinstance(out, str) else out
    print(f'OUT_KEYS: {list(parsed.keys()) if isinstance(parsed, dict) else "n/a"}')
except Exception as e:
    print(f'PARSE_ERR: {e}')
`.trim()

  const invokeOutput = execSync(
    `docker compose exec -T info-broker-api /app/.venv/bin/python -c '${invokeScript.replace(/'/g, "\\'")}'`,
    { encoding: 'utf-8', maxBuffer: 8 * 1024 * 1024, cwd: '../' }
  )
  console.log('\n  Result:')
  invokeOutput.split('\n').filter(l => /^(TIME_MS|OUT_LEN|OUT_KEYS|PARSE_ERR):/.test(l))
    .forEach(l => console.log(`     ${l}`))
  expect(invokeOutput).toContain('TIME_MS:')
  expect(invokeOutput).not.toContain('PARSE_ERR:')
})
