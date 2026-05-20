# Burn-In Checklist — Pre-Legion Migration

Before importing the recent week's commits into your daily workflow (and especially before the Legion 5 migration), run through this. Goal: catch any regression the loading-UX rollout, loop substrate, or compose changes introduced *before* it bites you in a real investigation.

Each section: ~5 minutes. Total: ~30 minutes for the smoke pass, plus ambient observation over the next 7–14 days.

---

## Part 1 — Smoke (one sitting, ~30 min)

### 1.1 Stack starts clean

```bash
docker compose down
docker compose pull
docker compose up -d
docker compose ps    # all healthy
```

Expected: 7 services running (postgres, qdrant, temporal, info-broker-api, frontend, temporal-worker, is-temporal-worker). No neo4j, no temporal-ui, no cloudflared in the default `up`.

If any service is restarting/unhealthy, stop here. `docker compose logs <service>` to debug.

### 1.2 Memory caps are respected

```bash
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}" 2>&1 | head -10
```

Expected: each container under its `mem_limit` from `docker-compose.yml`. Brain worker (`is-temporal-worker`) should be well under 3 GB at idle.

### 1.3 Frontend cold load (loading-UX phase verification)

Open Chrome devtools → Network tab → check **Disable cache** → reload `http://localhost:5173/dashboard`.

For ~250–800 ms you should see:
- Skeleton placeholders in the 4 dashboard widgets (Spend · 7d, Open Questions, Entity knowledge, History)
- No flash of "Loading…" text
- No layout shift when real data arrives

If you see any text label like `Loading…` or `Loading...`, that's a regression — file it.

### 1.4 Run drawer cold open

Open any past run from the History table. The drawer slides out and:
- Title shows a skeleton bar (not "Loading…" text)
- Findings tab shows 3× card-shaped skeletons
- Click Summary tab → skeleton lines, then real summary
- Click Raw JSON → skeleton lines, then real JSON

### 1.5 Error state — force a failure

```bash
# Stop API while UI is open
docker stop info-broker-info-broker-api-1
```

Refresh the dashboard. Every widget should show `InlineError` with a **Retry** button — not blank, not "Something went wrong."

```bash
# Bring it back
docker start info-broker-info-broker-api-1
```

Click Retry on any widget. Data should return.

### 1.6 New brain loop end-to-end

Submit a small research query through the UI ("Who is the CEO of Anthropic?" is a good cheap one). Watch for:
- Preflight cost preview shows skeleton, then real numbers (RU + minutes + tool-call count)
- Submit succeeds
- Run progresses through phases (visible in LiveStream rail and in the drawer's Turns tab)
- Final answer renders in the Summary tab

If it stalls at any phase, see `docs/intelligence/is-brain-loop-operator-guide.md`.

### 1.7 Working memory snapshots persisted

```bash
docker compose exec postgres psql -U user -d info_broker \
  -c "SELECT run_id, turn, phase, length(working_memory::text) FROM [REDACTED:high-entropy-base64:24ch:hash=a4a1c37c] ORDER BY created_at DESC LIMIT 5;"
```

Expected: ≥3 rows for the run you just submitted (one per turn). Phase column should show explore → test → synthesize.

### 1.8 Wallet ops landed

```bash
docker compose exec postgres psql -U user -d info_broker \
  -c "SELECT created_at, kind, delta_ru, reason FROM wallet_operations ORDER BY created_at DESC LIMIT 10;"
```

Expected: per-turn `consume` rows for the recent run, one per phase.

### 1.9 No OLD-path warning fired

```bash
docker compose logs info-broker-api 2>&1 | grep -i "OLD single-shot brain path is active" | tail
```

Expected: empty output. The loop is on by default; the warning only fires if `IS_USE_LOOP=false` is explicitly set.

### 1.10 Tests pass

```bash
docker compose exec info-broker-api pytest tests/test_working_memory.py tests/test_brain_turn.py tests/test_conflict_check.py 2>&1 | tail -10
```

Expected: green on the three loop-substrate test files. If anything fails, stop here.

---

## Part 2 — Ambient observation (7–14 days)

Once a day, glance at:

### 2.1 OLD-path usage signal

```bash
./bin/burn-in-health.sh         # script described below
```

Or directly:

```bash
docker compose logs --since 24h info-broker-api 2>&1 | grep -c "OLD single-shot brain path is active"
```

Expected: 0. Any non-zero means the loop is silently failing somewhere and code is falling back.

### 2.2 Loop completion rate

```bash
docker compose exec postgres psql -U user -d info_broker -tA \
  -c "SELECT status, count(*) FROM agent_sessions WHERE created_at > now() - interval '24 hours' GROUP BY status;"
```

Expected: `completed` rows >> `failed` rows. Ratio target: ≥95%.

### 2.3 Per-phase RU spend

```bash
docker compose exec postgres psql -U user -d info_broker -tA \
  -c "SELECT reason, count(*), avg(abs(delta_ru))::int FROM wallet_operations WHERE created_at > now() - interval '24 hours' AND kind='consume' GROUP BY reason;"
```

Expected: `consume_phase_0` (explore) cheapest, `consume_phase_1` (test) variable, `consume_phase_2` (synthesize) small. If `consume_phase_1` is wildly more expensive than expected (>5× average run), the loop is burning tokens in the test phase — investigate.

### 2.4 No new error patterns

```bash
docker compose logs --since 24h is-temporal-worker 2>&1 | grep -iE "traceback|error|exception" | head -20
```

Expected: any errors are recoverable retries, not crash patterns.

---

## Part 3 — Decision gates

After **7 days of clean ambient signal**:
- Confidence on the loop substrate rises to ~93%
- Safe to proceed to OLD-path step +14 (mark `app.is_brain.run_research` deprecated, move OLD tests to `tests/legacy/`)

After **30 days of clean ambient signal**:
- Confidence rises to ~97%
- Safe to delete OLD-path code (`app/is_brain.py`, `app/temporal/activities/brain.py`, `app/temporal/workflows/is_run.py`, legacy tests, dispatcher branch)

If at any point Part 2 signals turn red:
- Set `IS_USE_LOOP=false` in `.env` and `docker compose up -d` — instantly back on OLD path
- File the regression, debug at leisure
- Reset the 30-day clock when fixed

---

## Part 4 — Legion 5 migration (when burn-in is clean on Mac)

Once Parts 1–3 pass cleanly on Mac for at least a week, the Legion migration is just:

```bash
# Inside WSL Ubuntu, repo cloned into WSL filesystem (NOT /mnt/c)
claude auth login
./bin/wsl-bootstrap.sh
```

Then re-run Part 1 of this checklist on the Legion to confirm parity. If Part 1 passes on the Legion, you're done — that's the migration.

See `docs/operations/wsl-getting-started.md` for the full prereqs and troubleshooting.

---

## What success looks like

You hit this checklist twice (Mac → Legion), no regression appears, ambient observation stays clean for 7 days. At that point: pick C (Redis cache) or A (Modes) as the next architectural thread. Until then, no new code lands.
