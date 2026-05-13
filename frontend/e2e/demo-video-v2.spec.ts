import { test, Page } from '@playwright/test';

test.use({
  video: { mode: 'on', size: { width: 1920, height: 1080 } },
  viewport: { width: 1920, height: 1080 },
  headless: false,
});

test.setTimeout(1_200_000);

const BASE = 'http://localhost:5173';

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

type Observation = {
  section: string;
  status: 'ok' | 'issue' | 'enhancement';
  note: string;
};

const observations: Observation[] = [];

function record(section: string, status: Observation['status'], note: string) {
  observations.push({ section, status, note });
  console.log(`[OBS][${status.toUpperCase()}] ${section}: ${note}`);
}

async function subtitle(page: Page, text: string, ms = 3000) {
  await page.evaluate((t) => {
    let el = document.getElementById('__demo_subtitle__');
    if (!el) {
      el = document.createElement('div');
      el.id = '__demo_subtitle__';
      el.style.cssText = [
        'position:fixed',
        'left:50%',
        'transform:translateX(-50%)',
        'bottom:48px',
        'z-index:2147483647',
        'background:rgba(15,15,20,0.88)',
        'color:#ffffff',
        'font:600 22px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif',
        'padding:14px 28px',
        'border-radius:14px',
        'max-width:80vw',
        'text-align:center',
        'box-shadow:0 10px 40px rgba(0,0,0,0.4)',
        'border:1px solid rgba(139,92,246,0.5)',
        'pointer-events:none',
      ].join(';');
      document.body.appendChild(el);
    }
    el.textContent = t;
  }, text);
  await wait(ms);
}

async function clearSubtitle(page: Page) {
  await page.evaluate(() => {
    const el = document.getElementById('__demo_subtitle__');
    if (el) el.remove();
  });
}

async function safeScreenshot(page: Page, path: string) {
  try {
    await page.screenshot({ path, fullPage: false });
  } catch (e) {
    console.log(`[screenshot-failed] ${path}: ${(e as Error).message}`);
  }
}

async function safeGoto(page: Page, url: string) {
  try {
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
  } catch (e) {
    console.log(`[goto-failed] ${url}: ${(e as Error).message}`);
  }
}

test('info-broker — full feature demo v2', async ({ page }) => {
  // ============================================================
  // SCENE 1 — LOGIN (30s)
  // ============================================================
  await safeGoto(page, `${BASE}/login`);
  await wait(1500);

  await subtitle(page, 'infobroker — Intelligence Platform · infobroker.tech', 3000);
  await safeScreenshot(page, '/tmp/demo-01-login.png');

  await subtitle(page, 'Violet brand · shadcn card · Google & GitHub SSO placeholders', 3500);

  // Check for brand mark
  try {
    const hasLogo = await page.locator('svg, img[alt*="logo" i], [class*="logo" i]').first().isVisible({ timeout: 2000 });
    record('login', hasLogo ? 'ok' : 'enhancement', hasLogo ? 'Login page brand mark visible' : 'No clear brand mark on login');
  } catch {
    record('login', 'enhancement', 'Brand mark check timed out');
  }

  await subtitle(page, 'Signing in as admin...', 2000);

  // Type credentials slowly
  const usernameInput = page.locator('input[name="username"], input[type="text"], input[placeholder*="user" i], input[placeholder*="email" i]').first();
  const passwordInput = page.locator('input[name="password"], input[type="password"]').first();

  try {
    await usernameInput.click({ timeout: 5000 });
    await usernameInput.fill('');
    await usernameInput.pressSequentially('admin', { delay: 20 });
    await passwordInput.click();
    await passwordInput.fill('');
    await passwordInput.pressSequentially('admin', { delay: 20 });
    record('login', 'ok', 'Credentials entered successfully');
  } catch (e) {
    record('login', 'issue', `Failed to fill credentials: ${(e as Error).message}`);
  }

  await wait(800);
  await subtitle(page, 'Authenticating...', 1500);

  try {
    const submit = page.locator('button[type="submit"], button:has-text("Sign in"), button:has-text("Login"), button:has-text("Log in")').first();
    await submit.click({ timeout: 5000 });
    await page.waitForURL(/\/(dashboard|research|home)/i, { timeout: 15000 }).catch(() => {});
    record('login', 'ok', 'Sign-in submitted, redirect attempted');
  } catch (e) {
    record('login', 'issue', `Submit failed: ${(e as Error).message}`);
  }

  await wait(2000);
  await clearSubtitle(page);

  // ============================================================
  // SCENE 2 — DASHBOARD (45s)
  // ============================================================
  await safeGoto(page, `${BASE}/dashboard`);
  await wait(2500);
  await safeScreenshot(page, '/tmp/demo-02-dashboard.png');

  await subtitle(page, 'Dashboard — real-time research activity at a glance', 3500);

  // Inspect stat cards
  try {
    const cards = page.locator('[class*="card" i]').filter({ hasText: /run|success|live|error|rate/i });
    const cardCount = await cards.count();
    const dashText = await page.textContent('body').catch(() => '');
    const hasDashPlaceholders = (dashText || '').includes('—');
    record(
      'dashboard',
      hasDashPlaceholders ? 'enhancement' : 'ok',
      `Found ~${cardCount} stat cards; placeholders (— em-dashes) ${hasDashPlaceholders ? 'present (API likely returning empty)' : 'not detected'}`,
    );
  } catch (e) {
    record('dashboard', 'issue', `Stat cards inspection failed: ${(e as Error).message}`);
  }

  await subtitle(page, 'Stat cards: runs today · success rate · live · errors', 3500);
  await wait(1000);

  await subtitle(page, 'Recent runs — click Show on any row to inspect', 3500);

  try {
    const showBtn = page.locator('button:has-text("Show"), button[aria-label*="show" i]').first();
    if (await showBtn.isVisible({ timeout: 2000 })) {
      await showBtn.click();
      await wait(2000);
      await safeScreenshot(page, '/tmp/demo-02b-dashboard-drawer.png');
      await subtitle(page, 'Run drawer — full result payload, timing, tools used', 3000);
      // Try to close
      const closeBtn = page.locator('button[aria-label*="close" i], button:has-text("Close"), [role="dialog"] button').last();
      await closeBtn.click({ timeout: 2000 }).catch(() => {});
      await page.keyboard.press('Escape').catch(() => {});
      record('dashboard', 'ok', 'Recent runs drawer opened and closed');
    } else {
      record('dashboard', 'enhancement', 'No recent runs available for admin yet; table empty');
    }
  } catch (e) {
    record('dashboard', 'enhancement', `Drawer interaction skipped: ${(e as Error).message}`);
  }

  await wait(1500);
  await safeScreenshot(page, '/tmp/demo-02c-dashboard-after.png');
  await clearSubtitle(page);

  // ============================================================
  // SCENE 3 — RESEARCH / AGENT CHAT (2 min)
  // ============================================================
  await safeGoto(page, `${BASE}/research`);
  await wait(3000);
  await safeScreenshot(page, '/tmp/demo-03-research.png');

  await subtitle(page, 'Research — 3-column intelligence workspace', 3500);
  await subtitle(page, 'Left: Pipeline Builder · Center: Agent Chat · Right: Live Stream', 4000);

  // Check IS toggle
  try {
    const isToggle = page.locator('[role="switch"], button:has-text("IS"), label:has-text("IS"), input[type="checkbox"]').first();
    const isVisible = await isToggle.isVisible({ timeout: 3000 });
    record('research', isVisible ? 'ok' : 'enhancement', isVisible ? 'IS toggle present' : 'IS toggle not clearly visible');
    if (isVisible) {
      // Ensure it's enabled
      try {
        const ariaChecked = await isToggle.getAttribute('aria-checked');
        if (ariaChecked === 'false') {
          await isToggle.click();
          await wait(500);
        }
      } catch {}
    }
  } catch (e) {
    record('research', 'enhancement', `IS toggle check error: ${(e as Error).message}`);
  }

  await subtitle(page, 'Intelligent Search — Claude Code subprocess powering 50+ OSINT tools', 4000);

  // Type query
  const query =
    'Investigate the AI memory systems competitive landscape in 2026: compare Mem0, Zep, Letta architectures and identify key investors';

  try {
    const input = page
      .locator('textarea, input[type="text"][placeholder*="ask" i], input[type="text"][placeholder*="query" i], [contenteditable="true"]')
      .first();
    await input.click({ timeout: 5000 });
    await input.pressSequentially(query, { delay: 15 });
    record('research', 'ok', 'Query typed into agent input');
    await wait(500);
    await subtitle(page, 'Sending deep research query...', 2000);
    await page.keyboard.press('Enter');
  } catch (e) {
    record('research', 'issue', `Could not submit query: ${(e as Error).message}`);
  }

  await wait(3000);
  await subtitle(page, 'Research initiated — watch the live stream for real-time tool execution', 4000);
  await wait(8000);
  await safeScreenshot(page, '/tmp/demo-03b-research-live.png');

  // Inspect live stream pane
  try {
    const liveText = await page.textContent('body').catch(() => '');
    const hasLive = /tool|search|fetch|memo|invest|finding|status|running/i.test(liveText || '');
    record(
      'research',
      hasLive ? 'ok' : 'enhancement',
      hasLive ? 'Live stream appears to have content' : 'Live stream appears empty 8s after submit; may need longer wait',
    );
  } catch {
    record('research', 'enhancement', 'Could not introspect live stream content');
  }

  await subtitle(page, 'Live stream shows tool calls, findings, and status as they arrive', 4000);
  await wait(2000);
  await safeScreenshot(page, '/tmp/demo-03c-research-final.png');
  await clearSubtitle(page);

  // ============================================================
  // SCENE 4 — PIPELINE BUILDER (30s)
  // ============================================================
  await safeGoto(page, `${BASE}/pipelines`);
  await wait(2500);
  await safeScreenshot(page, '/tmp/demo-04-pipelines.png');

  await subtitle(page, 'Pipeline Builder — visual drag-and-drop node editor', 3500);
  await subtitle(page, 'Chain data sources, transformers, and output nodes', 3500);

  try {
    const nodes = page.locator('[class*="node" i], [data-type*="node" i], .react-flow__node');
    const nodeCount = await nodes.count();
    record(
      'pipelines',
      nodeCount > 0 ? 'ok' : 'enhancement',
      nodeCount > 0 ? `Pipeline canvas shows ~${nodeCount} nodes` : 'Pipeline canvas empty — enhancement: add default templates',
    );
  } catch (e) {
    record('pipelines', 'enhancement', `Pipeline introspection failed: ${(e as Error).message}`);
  }

  await wait(1500);
  await clearSubtitle(page);

  // ============================================================
  // SCENE 5 — HISTORY (30s)
  // ============================================================
  await safeGoto(page, `${BASE}/history`);
  await wait(2500);
  await safeScreenshot(page, '/tmp/demo-05-history.png');

  await subtitle(page, 'History — complete run log with filters', 3500);
  await subtitle(page, 'Filter by date or status · Show drawer · Download CSV/XLSX', 4000);

  try {
    const rows = page.locator('table tbody tr, [role="row"]');
    const rowCount = await rows.count();
    record(
      'history',
      rowCount > 0 ? 'ok' : 'enhancement',
      rowCount > 0 ? `History shows ${rowCount} rows` : 'History empty — no run history for admin yet',
    );
  } catch (e) {
    record('history', 'enhancement', `History introspection failed: ${(e as Error).message}`);
  }

  // Try status filter
  try {
    const statusFilter = page
      .locator('select, [role="combobox"], button:has-text("Status"), button:has-text("All")')
      .first();
    if (await statusFilter.isVisible({ timeout: 2000 })) {
      await statusFilter.click();
      await wait(1500);
      await page.keyboard.press('Escape').catch(() => {});
      record('history', 'ok', 'Status filter is interactive');
    }
  } catch {}

  await wait(1500);
  await clearSubtitle(page);

  // ============================================================
  // SCENE 6 — PERFORMANCE DASHBOARD (30s)
  // ============================================================
  await safeGoto(page, `${BASE}/performance`);
  await wait(2500);
  await safeScreenshot(page, '/tmp/demo-06-performance.png');

  await subtitle(page, 'Performance Dashboard — strategy / tactic / technique grades', 4000);
  await subtitle(page, 'Grades every research strategy on the A–F Admiralty scale', 4000);

  try {
    const perfText = await page.textContent('body').catch(() => '');
    const hasGrades = /\b[ABCDEF]\b|admiralty|grade|score/i.test(perfText || '');
    record(
      'performance',
      hasGrades ? 'ok' : 'enhancement',
      hasGrades ? 'Performance page shows grading content' : 'No grade data visible — needs run data to populate',
    );
  } catch (e) {
    record('performance', 'enhancement', `Performance introspection failed: ${(e as Error).message}`);
  }

  await wait(1500);
  await clearSubtitle(page);

  // ============================================================
  // SCENE 7 — SETTINGS (30s)
  // ============================================================
  await safeGoto(page, `${BASE}/settings`);
  await wait(2500);
  await safeScreenshot(page, '/tmp/demo-07-settings.png');

  await subtitle(page, 'Settings — agent configuration, API keys, node health', 4000);

  try {
    const agentSection = page.locator('text=/agent/i').first();
    const nodeHealth = page.locator('text=/node health|health/i').first();
    const aVis = await agentSection.isVisible({ timeout: 2000 }).catch(() => false);
    const nVis = await nodeHealth.isVisible({ timeout: 2000 }).catch(() => false);
    record(
      'settings',
      aVis && nVis ? 'ok' : 'enhancement',
      `Agent settings visible: ${aVis}, Node health visible: ${nVis}`,
    );
  } catch (e) {
    record('settings', 'enhancement', `Settings introspection failed: ${(e as Error).message}`);
  }

  // Click Core Settings (admin)
  try {
    const core = page
      .getByRole('button', { name: 'Core Settings' })
      .first();
    if (await core.isVisible({ timeout: 3000 })) {
      await core.click();
      await wait(2000);
      await safeScreenshot(page, '/tmp/demo-07b-core-settings.png');
      await subtitle(page, 'Core Settings — LLM provider keys, JWT config, search API keys', 4500);
      record('settings', 'ok', 'Core Settings (admin) opened');
    } else {
      record('settings', 'enhancement', 'Core Settings tab not visible for admin');
    }
  } catch (e) {
    record('settings', 'enhancement', `Core Settings click failed: ${(e as Error).message}`);
  }

  await wait(2000);
  await clearSubtitle(page);

  // ============================================================
  // SCENE 8 — OBSERVATIONS REPORT
  // ============================================================
  await subtitle(page, 'Demo complete — observations logged', 3000);
  console.log('\n=========== DEMO OBSERVATIONS ===========');
  console.log(JSON.stringify(observations, null, 2));
  console.log('=========================================\n');
  await clearSubtitle(page);
  await wait(1000);
});
