# OLD Single-Shot Brain Path — Phase-out Readiness Assessment

Status of task #117: assessing whether the legacy single-shot `app.is_brain.run_research` path can be removed in favor of the orchestrated loop (Path B / `IsLoopRunWorkflow`).

**Verdict: ~85% confidence — flip default ON, keep code as fallback, schedule deletion after 30 days of clean production data.**

Below 90% threshold for full deletion. Phased approach instead.

---

## What's working (justifies promotion to default)

1. **Loop substrate fully shipped** (commit `a41d010`)
   - `IsLoopRunWorkflow` + `run_brain_turn` activity + `init_working_memory` + working_memory_snapshots table
   - Phase machine (explore → test → synthesize)
   - Workflow-owned termination + MAX_TURNS hard cap
   - Per-turn budget enforcement
2. **Wallet ops recording verified** earlier in this session — 5 wallet_operations per 5-turn run, per-phase breakdown matches expectations.
3. **Workflow + activity tests passing** (`tests/test_working_memory.py`, `tests/test_brain_turn.py`, `tests/test_conflict_check.py`).
4. **Docker default `IS_USE_LOOP=true`** in docker-compose.yml — every fresh stack since the compose change uses the loop.

## What's blocking 90%+ (justifies keeping OLD code as fallback)

1. **Code-level default disagrees with docker-level default.**
   - `app/routers/v3/agent.py:31` reads `IS_USE_LOOP = os.getenv("IS_USE_LOOP", "false") == "true"` — defaults to **false** when env unset.
   - `docker-compose.yml` sets `IS_USE_LOOP: ${IS_USE_LOOP:-true}` — defaults to **true**.
   - Any non-Docker deploy (pytest, scripts, future K8s overlays without explicit env) silently falls back to OLD path. Should be flipped.
2. **No production-burn-in data on loop path.**
   - Local validation only. No customer data on durability of working_memory snapshots under realistic load, on retry behavior, on subscription quota interaction at 2+ concurrent.
   - 30 days of clean operation on the loop default before deletion is reasonable.
3. **Multiple test files still target OLD path.**
   - `tests/test_is_brain.py`, `tests/test_is_brain_strategy.py`, `tests/test_is_prompt.py`, `tests/test_error_filter.py` import `app.is_brain.{run_research, build_prompt, _classify_finding}`.
   - These keep `is_brain.py` exercised by CI; removing the module breaks the suite.
4. **`app/temporal/activities/brain.py` (old single-shot activity) is still imported by `ISRunWorkflow`.**
   - This is the activity-side equivalent of the OLD path. If `IS_USE_LOOP=false` is ever set, this kicks in.
5. **Deception scoring not yet observed on a live loop run.**
   - The score is computed and stored, but nothing has hit a high-deception finding yet for visual confirmation.
6. **No telemetry on per-Mode loop performance.**
   - Mode→tool-weight effects on tool selection haven't been measured.

## Phased plan

### Now (this commit)
- **Flip code default to true** in `app/routers/v3/agent.py:31` so `IS_USE_LOOP` defaults to `true` matching docker, eliminating the silent-fallback hole. One-line change, instantly reversible by setting `IS_USE_LOOP=false`.
- **Add deprecation log line** when OLD path actually executes (`logger.warning("OLD single-shot path used. Loop is preferred. Set IS_USE_LOOP=true.")`). Surfaces accidental fallback in logs.

### +14 days (when telemetry confirms loop is healthy)
- Mark `app/is_brain.run_research` with a `DeprecationWarning` at import time.
- Move OLD-path tests into a `tests/legacy/` directory so they're easy to remove later.

### +30 days (assuming no regression reports)
- Delete `app/is_brain.py` module.
- Delete `app/temporal/activities/brain.py` (single-shot activity).
- Delete `app/temporal/workflows/is_run.py` (single-shot workflow).
- Delete `tests/legacy/test_is_brain*.py`.
- Drop `IS_USE_LOOP` env var entirely (always true).
- Remove the dispatcher branch in `agent.py`.

### Rollback plan if a 30-day window reveals issues
- Set `IS_USE_LOOP=false` in env to instantly fall back. Code path stays alive until +30d.
- After +30d: if a regression is found and OLD path was deleted, revert the deletion commit (`git revert <sha>`). Code returns to fallback state.

## Re-assessment after the now-step

If the loop default behaves cleanly for 14 days in real use:
- Confidence rises to ~93%
- Move to +14d step
After 30 days of clean operation:
- Confidence rises to ~97%
- Proceed with deletion

## What to monitor

| Signal | Source | Healthy reading |
|---|---|---|
| Loop-completed-runs / total-runs | `agent_sessions` + `working_memory_snapshots` | >95% |
| OLD-path-used count | New deprecation log line | 0 per day |
| Loop p95 duration vs OLD p95 | `wallet_operations` finished_at - started_at | within 1.3× |
| Loop p95 RU vs OLD p95 RU | `wallet_operations.delta` aggregated | within 1.5× (loop is allowed to be slightly more expensive for quality) |
| Loop error rate by phase | `working_memory_snapshots.phase` + run.status | <5% per phase |

## Open question for the owner

This assessment recommends **flipping the code default now + scheduling deletion for +30 days**. Alternative path: **delete OLD path immediately** if you're comfortable with the rollback being a `git revert` rather than an env-flag flip.

My recommendation: phased. Subscription auth + custom subprocess is finicky enough that having an env-flag rollback is worth 30 days of dead code.
