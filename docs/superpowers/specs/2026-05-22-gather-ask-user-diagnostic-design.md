# Gather-phase ask_user diagnostic surfaces — design

> **Date:** 2026-05-22
> **Status:** Draft (pending implementation plan)
> **Triggering incident:** Run `3dc3fc50-745a-45e7-9002-f915da9bd5d8` completed in 118 ms with 0 tool calls and 0 findings, then emitted the user-facing message *"The 'gather' phase could not extract sufficient signals from your query. Could you provide more detail?"* — blaming the user for what was actually a backend failure.

## Problem

When the strategist's gate fails with `on_fail="ask_user"`, three things go wrong today:

1. **The user-facing message is misleading.** The template at `app/pipeline/strategist.py:951` says *"could not extract sufficient signals from your query"* regardless of which phase failed and regardless of *why* it failed. The wording blames the query when the actual cause may be a backend regression, an MCP tool returning empty, or an unconfigured strategy.

2. **The trail contradicts the strategist.** `phase_output.status` is the *execution* status (did the tactician crash?), and `gate_passed` is a *separate local boolean* that is never persisted into `research_trails.trail.phases_full[]`. As a result, run `3dc3fc50`'s trail shows each phase as `status: "passed"` even though the overall run is `ask_user`. An operator reading the trail cannot tell which gate-check rejected the run.

3. **A phase can "pass" with zero brain work.** No invariant prevents a phase whose tactician produced 0 tool calls and 0 findings from being considered successful at the strategist level. Pre-`37b2a36`, this manifested as silent "succeeded in 0 s with 0 cards" runs (called out explicitly in the commit body of `37b2a36`). After `37b2a36` and `629c161`, per-strategy gate-checks reject empty output via `min_listings_returned` / `min_signal_classes_covered` / etc. — but a strategy author who forgets to declare a check, or declares an insufficient one, leaves the silent no-op path open. Today's run shows this is still happening.

Compounding factor surfaced during diagnosis: **`run_id` is not currently visible in the UI** (per a recent change), so the user could not tell support which run failed, and support could not query the trail by ID.

## Goal

After this spec ships, when a run produces no useful work, the system shall:

- Tell the user something **accurate** ("we didn't gather any results — please try again or contact support") rather than blaming the query.
- Tell an admin operator **everything** needed to root-cause from the trail alone: which phase, which gate-check, brain summary numbers, invoked tools, duration.
- Make the silent no-op pattern **impossible** at the strategist level via a top-level "no work, no pass" invariant that runs before per-strategy checks.
- Surface `run_id` on every user-facing run surface so support triage is possible from the message alone.

The brain regression that *causes* 0-tool-call runs is **out of scope** for this spec. The deliverable here is the diagnostic infrastructure that makes that regression debuggable in one query against the trail.

## Approach

This spec implements **Approach B** from brainstorming: diagnostic surfaces (record + expose `gate_result`) plus a "no work, no pass" invariant in the strategist's gate evaluator. The brain-regression debug is queued as a follow-up spec, informed by the telemetry this spec produces.

Three other approaches considered and rejected:

- **Approach A — diagnostics only.** Cheaper, but leaves the silent-no-op path open: phases can still "pass" with 0 work if a strategy author forgets to declare gate-checks. The user could discover the same misleading-message pattern next month under a new strategy.
- **Approach C — bundle brain-regression spike.** Wider scope. Brain regression likely needs `systematic-debugging` before we can spec a fix. Bundling risks blocking the diagnostic-surface fixes (which are independently valuable today) behind an unknown-scope debugging session.
- Status quo: do nothing. Rejected: today's user-facing message is actively wrong and the trail cannot answer "why did this run fail?"

## Architecture

Four touchpoints in dependency order:

```
strategist.py                research_trails (DB)         /v3/runs/* (API)         Frontend
─────────────                ────────────────────         ─────────────────        ────────
PhaseOutput +                  trail.phases_full[].         RunResult →                Friendly summary,
  gate_result {                  gate_result               JSON: {user_question,        + admin-gated detail block,
    passed,                                                       summary,              + run_id badge,
    failing_check_kind,                                           detail (admin only)}  + retry hint
    failing_check_detail,
    brain_summary {              ← also surfaces via
      tool_calls,                  admin trail-view
      findings,                    endpoint
      hypothesis_count,
      duration_ms,
      invoked_tools
    }
  }
+ "no work, no pass" invariant
  in _run_gate (runs BEFORE
  per-strategy checks)
```

### Conceptual changes

1. **`gate_result` is a first-class piece of phase output.** It travels through `_aggregate` → strategist's `RunResult` → engine → `research_trails`. The existing `phase_output.status` (execution status) is kept; `gate_result.passed` is the new authoritative gate signal.
2. **Top-level invariant in `_run_gate`:** if `tool_calls == 0 AND findings == 0`, `gate_passed=False` and `failing_check_kind="no_brain_work"`. Runs before per-strategy checks.
3. **`RunResult.user_question` becomes structured** (`{summary, detail, run_id, phase_id}`) instead of a plain string.
4. **`run_id` is required on every UI surface** that shows a run (history row, ask_user prompt, error toast). New `RunBadge` component carries this.

### Boundaries

- No change to the tactician code path. No change to the brain subprocess. No change to MCP integration.
- No change to gate-check kinds shipped in `37b2a36` — they still run; the invariant runs **before** them.
- DB-schema-wise: `research_trails.trail` is already `jsonb`. The new `gate_result` key is purely additive. No migration.
- Existing tenancy / IDOR controls (`working_memory.py:50`, `absorption.py:79`) cover the new surfaces — no new auth model.

## Components and data shapes

### `PhaseOutput.gate_result` (new field)

```python
class GateResult(TypedDict):
    passed: bool
    failing_check_kind: str | None         # "min_listings_returned", "no_brain_work", or None when passed
    failing_check_detail: dict[str, Any]   # sanitized; see "Sanitization contract" below
    brain_summary: BrainSummary

class BrainSummary(TypedDict):
    tool_calls: int
    findings: int
    hypothesis_count: int          # surviving hypothesis count
    duration_ms: int               # phase wall-clock
    invoked_tools: list[str]       # distinct MCP / built-in tools touched
```

Built inside `_run_gate` and attached to `phase_output` before the strategist appends it to `completed_phases`.

### `_run_gate` — "no work, no pass" invariant

```python
def _run_gate(phase_output, phase, envelope) -> GateResult:
    summary = _build_brain_summary(phase_output)

    # Top-level invariant: a phase that produced 0 tool calls AND 0 findings
    # cannot pass, regardless of strategy-specific checks. Catches stub tactics,
    # broken MCP, OAuth failures, and any "ran to completion with no real work"
    # pattern. Required because a strategy author may forget to declare checks.
    if summary["tool_calls"] == 0 and summary["findings"] == 0:
        return GateResult(
            passed=False,
            failing_check_kind="no_brain_work",
            failing_check_detail={"tool_calls": 0, "findings": 0},
            brain_summary=summary,
        )

    # ... existing per-strategy gate-check loop ...
    # Each check returns failing_check_kind on first failure.
```

`AND` semantics, not `OR`: `tool_calls > 0` with `findings == 0` is a legitimate "we searched but found nothing" case and should be handled by the per-strategy `min_*` checks with a specific message ("we searched but found nothing matching your filter"). The invariant only catches the pathological 0/0 case.

### `RunResult.user_question` — structured payload

```python
class UserQuestionPayload(TypedDict):
    summary: str           # user-safe, accurate, never blames the query
    detail: GateResult     # admin-only; server-filtered before serialization
    run_id: str            # always present
    phase_id: str          # always present
```

The `summary` text is template-mapped per `failing_check_kind`. Example mapping:

| failing_check_kind         | summary                                                                                              |
|----------------------------|------------------------------------------------------------------------------------------------------|
| `no_brain_work`            | "The system didn't gather any results for this query. This may be a temporary issue — please try again or contact support." |
| `min_listings_returned`    | "We couldn't find listings matching your criteria. Try broadening location or budget."               |
| `min_signal_classes_covered` | "Not enough information was gathered to answer this query. Please try a more specific query."     |
| (other strategy checks)    | Strategy-author may supply a custom summary; otherwise the fallback is exactly: `"We couldn't complete the '{phase_id}' phase for this query. Please try a more specific query or contact support."` (substitutes phase_id only — never the failing check internals). |

### `research_trails.trail.phases_full[]` — extension

Each phase entry gains a `gate_result` key with the shape above. Strategist always writes it — even on success — so the audit trail is uniform. Pre-existing rows without the key are rendered with `(no gate data — run predates 2026-05-22)` in the admin view.

### Frontend components

- **`AskUserPrompt`** — renders `summary` for everyone, plus a collapsible `<AdminGateDetail>` section that mounts only when `user.is_admin || user.role === 'admin'`. The detail shows `failing_check_kind`, the per-check detail, brain summary, and a copy-run_id button.
- **`RunBadge`** (new) — renders `run_id` as an 8-char prefix chip with the full UUID in the `title` tooltip and copied to clipboard on click. Used in: ask_user surface, History row, error toast, run-detail header.

### API endpoint contract

The existing `/v3/agent/confirm/pending` and run-create endpoints return `user_question` as a structured object instead of a string. For non-admin callers, the API **omits** the `detail` field entirely (not redact-with-null) — cleaner schema, smaller payload, no info-leak surface. Admin gating happens at the route layer following the `working_memory.py:50` pattern. Client-side flags cannot reveal the field.

## Data flow

Tracing what happens for the query "show all properties for rent in chicago" *after* this spec ships:

```
1. Frontend                 POST /v3/preflight {query}
                             └─ classifier → real_estate
                            POST /v3/pipelines/runs {query, strategy=real_estate}
                            ▲
                            │ run_id returned, shown as RunBadge immediately

2. API → engine_v2          insert pipeline_runs(status='running', query=...)
                            engine_v2.run(strategy=real_estate)

3. Strategist extract       tactician_fn(extract, ...) → phase_output_extract
                            _run_gate(phase_output_extract):
                              summary = build(phase_output_extract)
                              # tool_calls == 0, findings == 0
                              → GateResult(passed=False,
                                           failing_check_kind="no_brain_work",
                                           failing_check_detail={tool_calls:0, findings:0},
                                           brain_summary=...)
                            phase_output_extract.gate_result = gate_result
                            ▲
                            │ FIRST CHANGE — gate decision lives on the phase output

4. Strategist on_fail=      RunResult(status="ask_user",
   ask_user                              user_question=UserQuestionPayload(
                                            summary="The system didn't gather any
                                                     results. Please try again or
                                                     contact support.",
                                            detail=gate_result,
                                            run_id=...,
                                            phase_id="extract"),
                                          phases=[phase_output_extract])
                            ▲
                            │ SECOND CHANGE — structured payload, accurate summary

5. engine_v2 persists       UPDATE pipeline_runs SET status='ask_user', finished_at=now()
                            INSERT research_trails(trail=...)
                              with phases_full[0].gate_result populated
                            ▲
                            │ THIRD CHANGE — trail persists gate_result.
                            │ jsonb_pretty(trail) now tells the truth.

6. Frontend ask_user        GET /v3/agent/confirm/pending → list including:
                              { run_id, summary, detail?, phase_id }
                            ▲
                            │ detail present only when caller is admin
                            │ (server-side filter)

7. UI renders               <AskUserPrompt>
                              <p>{summary}</p>
                              <RunBadge runId={run_id} />
                              {isAdmin && <AdminGateDetail detail={detail}/>}
                              <button>Refine query</button>
                              <button>Retry</button>
                            </AskUserPrompt>
```

### Invariants this flow enforces

1. **The failing phase is named in both message and trail** — no more "could not extract signals" when gather failed.
2. **`gate_result` is computed once and flows everywhere** — single source of truth.
3. **The 118 ms-empty-output case cannot silently "succeed".** Before per-strategy checks run, the `no_brain_work` invariant catches it.
4. **Admin detail is server-gated**, not client-toggleable.
5. **`run_id` is in the payload of every ask_user / error surface** — non-optional, wired into `RunBadge` so the UI cannot accidentally remove it.

### Operator's view post-fix

```jsonc
{
  "status": "ask_user",
  "phases": ["extract"],
  "phases_full": [
    {
      "phase_id": "extract",
      "status": "passed",                      // execution status — kept
      "gate_result": {                         // NEW
        "passed": false,
        "failing_check_kind": "no_brain_work",
        "failing_check_detail": {"tool_calls": 0, "findings": 0},
        "brain_summary": {
          "tool_calls": 0,
          "findings": 0,
          "hypothesis_count": 0,
          "duration_ms": 73,
          "invoked_tools": []
        }
      },
      "metadata": { ... }
    }
  ]
}
```

That row, alone, is enough to start the brain-regression debug without paging the user.

### Behavioral consequence: which phase gets named in the message changes

The triggering incident (run `3dc3fc50`) showed both `extract` AND `gather` running with 0 work, then ask_user fired naming **gather**. That happened because pre-spec, extract's gate let 0/0 pass and only gather had a strategy check that rejected it.

Post-spec, the `no_brain_work` invariant fires on **the first phase** that produces 0/0 — which for this query is **extract**. So the user-facing message for the same incident will name `extract`, not `gather`, and gather will never run. This is correct (the run should never have proceeded past extract producing no work) but worth flagging for anyone diffing the before/after behavior: a regression report mentioning "gather" today will reproduce as an "extract" message tomorrow.

## Error handling, edge cases, security

### Sanitization contract — `failing_check_detail`

`failing_check_detail` is constrained to a small, audited value set. A single helper `_sanitize_check_detail(d: dict) -> dict` drops any key whose value is not in `{int, float, str (≤120 chars — applies to **every** string value, top-level and nested), bool, list of same, dict of same (one level deep)}`. Specifically **forbidden**:

- Exception objects or string-coerced tracebacks (file paths leak internal layout)
- Raw `Finding` / `Source` / `Hypothesis` objects (may contain scraped PII)
- MCP tool response bodies (may contain backend hostnames, response headers, upstream credentials)
- Absolute file paths starting with `/` or `C:\`
- Verbatim user query content or verbatim finding text (reflected-content risk)
- Anything matching `app/security.py` redaction patterns, if such helpers exist (confirm during implementation)

Default is **deny**, not permit. Gate-check authors who want to expose additional fields must add them through the sanitizer; unknown shapes are dropped.

### Edge cases

| Case | Behavior |
|---|---|
| Pre-spec trail row (no `gate_result` key) | Admin view renders `(no gate data — run predates 2026-05-22)`. Non-admin view: no behavior change. |
| `invoked_tools` length exceeds 50 | Truncated to top 10 by call count, with `_truncated: <n>` field. Bounds payload size. |
| Strategy declares 0 gate-checks (only invariant runs) | Invariant carries it. `failing_check_kind="no_brain_work"` for 0/0 case; per-strategy fallback message otherwise. |
| Phase succeeds (gate passes) | `gate_result.passed=true`, `failing_check_kind=null`, `brain_summary` still populated (always-on observability for admin view). No user-facing change for success path. |
| Replan loop hits gate-fail multiple times | Trail records `gate_result` for each attempt as separate `phases_full[]` entries with `metadata.replan_attempt` distinguishing them. Admin view shows the chain. |
| `tool_calls > 0` but `findings == 0` | Invariant passes (AND semantics). Per-strategy `min_*` checks decide with their own specific messages. |
| Engine crashes while writing trail | `RunResult` still returned to API; ask_user surface still works. Trail row may be absent or partial. Admin sees `(trail incomplete)`. Run is not auto-retried. |
| Non-admin finds someone else's `run_id` | Existing IDOR controls in `working_memory.py:50` / `absorption.py:79` apply: API rejects access to non-owned `run_id`. `RunBadge` is not a new vulnerability — it surfaces an ID the user already owns. |

### Backwards compatibility

- **Strategist `RunResult.user_question`** changes from `str | None` → `UserQuestionPayload | None`. Internal callers (`app/routers/v3/agent.py`, `app/routers/v3/preflight.py`, others — grep during implementation) updated in lockstep.
- **API JSON response** for `/v3/agent/confirm/pending` and run-create now nests `user_question` as an object. Frontend is updated in lockstep. No external/webhook consumer of this field (verified: `webhook_deliveries` table does not carry `user_question`).
- **research_trails schema** — no DB migration; `trail` is already `jsonb`, `gate_result` is purely additive.

### Security checklist

- ✅ Admin gate enforced server-side at the route layer (not client-side toggleable)
- ✅ `detail` field omitted from JSON entirely for non-admin (not redacted-with-null)
- ✅ `failing_check_detail` sanitized through a single deny-by-default helper
- ✅ `run_id` exposure non-sensitive (UUID, ownership-gated by existing IDOR controls)
- ✅ No new untrusted-input ingestion surface
- ✅ No new auth/identity surface (reuses `get_current_user` + `is_admin || role=='admin'`)
- ✅ `RunBadge` copy-to-clipboard uses standard browser API (no eval, no user-controlled escape paths)
- ⚠️ Implementation must confirm no gate-check author writes user-controlled content (query substrings, finding text) into `failing_check_detail`. The 120-char string cap limits blast radius but does not prevent reflected-content patterns. Spec mandates: never include verbatim query / finding text in `failing_check_detail`.

## Testing contract

This is the section most influenced by the user-stated requirement: **"thoroughly tested" means real-world functional testing of the local stack, not mocks alone**. Mocked unit tests are required but insufficient.

### Both layers required for every behavior

For each acceptance criterion below, **two tests** are required: a mocked unit test (fast, in CI) AND a real-environment functional test (run against the local docker compose stack per `docs/operations/backend-deploy.md`, with real Postgres / real brain / real MCP / real tunnel).

| Behavior | Mocked unit test | Real-env functional test |
|---|---|---|
| `gate_result` populated on every phase output (pass and fail) | Inject mock tactician, assert `phase_output.gate_result` present and structurally valid | Run real query through stack; `SELECT trail FROM research_trails WHERE run_id=...` and assert `phases_full[*].gate_result` is present |
| `no_brain_work` invariant fires on 0/0 | Mock tactician returning 0/0, assert `gate_result.failing_check_kind == "no_brain_work"` | Run real query that triggers 0/0 (today's bug pattern); observe ask_user with `no_brain_work` rather than misleading message |
| Trail and `RunResult` agree | Strategist test: `RunResult.user_question.detail == phases[-1].gate_result` | Real run: query DB, hit GET endpoint for same run, assert JSON `detail` matches persisted `trail.phases_full[-1].gate_result` byte-for-byte |
| Admin gating | API unit test: `user.is_admin=False` → `detail` key omitted; `True` → present | Log in as admin user via real local UI, hit endpoint, see detail. Logout, log in as non-admin, hit endpoint, verify detail absent. Screenshot evidence. |
| `RunBadge` on every ask_user surface | React component test renders the prompt with mock state, asserts presence | Playwright e2e: real query → real ask_user surface → assert `[data-testid=run-badge]` in DOM, truncated UUID, copy-to-clipboard works |
| `failing_check_detail` sanitization | Unit test passes adversarial dicts (Exception objects, raw findings, paths, long strings); assert helper drops them | n/a — structural; unit test sufficient |
| `invoked_tools` truncation at 50+ | Unit test with synthetic 60-tool list; assert top-10 + `_truncated: 50` | Real run with a strategy that lists many tools, observe truncation |

### Functional-test execution protocol (mandated by this spec)

Each PR implementing a slice of this spec **must include in its description**:

1. The local stack state used (`docker compose ps` output)
2. The exact query string used to exercise the change
3. The resulting `run_id`
4. Either: the DB row showing the new `gate_result` shape, OR a screenshot of the UI showing the new surface, OR the actual API response JSON from `curl https://api.infobroker.tech/v3/agent/confirm/pending`
5. A note stating whether the test was run against `localhost:8000` or `https://api.infobroker.tech` (tunnel path)

PRs that say "tests pass" without functional evidence are rejected.

### Regression test for THIS specific run

A canonical functional test ensures the bug pattern cannot recur:

```
Given: query "show all properties for rent in chicago with a budget of $500 to $1000"
And:   real_estate strategy is selected
When:  the run completes
Then:  EITHER (status == "succeeded" AND tool_calls > 0 AND findings > 0)
       OR     (status == "ask_user" AND failing_check_kind != null AND failing_check_kind != "")
```

The 118 ms-empty-success pattern is **inadmissible** by this assertion. The brain-regression investigation is a downstream track; this test guarantees the symptom won't slip past silently again.

### Structured logging mandate

The strategist emits a single structured log line per gate evaluation, in addition to persisting to the trail:

```python
log.info(
    "strategist.gate_result",
    extra={
        "run_id": self._run_id,
        "phase_id": phase.id,
        "gate_passed": gate_result["passed"],
        "failing_check_kind": gate_result["failing_check_kind"],
        "tool_calls": gate_result["brain_summary"]["tool_calls"],
        "findings": gate_result["brain_summary"]["findings"],
        "duration_ms": gate_result["brain_summary"]["duration_ms"],
        "replan_attempt": phase_output.metadata.get("replan_attempt", 0),
    },
)
```

Trails are queryable by `run_id` post-hoc; logs are aggregable across runs to answer "how often is `no_brain_work` firing this week?". Both surfaces are required.

## Appendix — brain-regression investigation (out of scope, tracked)

Once this spec ships, the next failing run surfaces `no_brain_work` with a complete `brain_summary`. That telemetry is the starting point for actually debugging the brain regression. Investigation hypotheses pre-recorded so they're not lost:

1. **Why does the real tactician produce 0 tool calls in 118 ms for `real_estate` queries?**
   - *Hypothesis A:* OAuth token to Claude Code is expired or being rejected silently (related to commits `880d032` "surface brain-subprocess auth/HTTP failures loudly" and `1f6ddf0` "bind-mount host ~/.claude → container for auto-refresh")
   - *Hypothesis B:* MCP config for real_estate's preferred tools is broken (relates to open issues #110 `run_web_crawl` JSON decode and #111 `run_whois_lookup` zero items)
   - *Hypothesis C:* Strategy resolver isn't actually selecting `real_estate` for this query — some no-op strategy is being chosen instead
   - *Hypothesis D:* `auto_create_techniques` is OFF and the strategy references a technique that doesn't exist; tactician falls through silently
2. **Why is `surviving_hypothesis_count: 0` even when `hypotheses_explored: 1`?** Either the single hypothesis is being immediately disconfirmed, or the metric is computed incorrectly. May relate to open issue #89 (IS brain tunneling without BROADEN).
3. **Cross-check against run `dc9de0b4`** — the earlier failed run that DID emit "Gate failed on phase 'broaden'": took 13 s of real brain work and went through the IS-brain loop (different code path from research-skeleton). Understanding which router sends `real_estate` queries down the 118 ms path while `who are the top 3...` queries take the 13 s path is the start of the debug.

These hypotheses become the basis of a separate **debugging** spec (not a design spec), using `superpowers:systematic-debugging`, once the diagnostic infrastructure here is in place.

## Out of scope (explicit)

- Fixing the brain regression itself (deferred to the investigation track above)
- Adding new gate-check kinds beyond the eight shipped in `37b2a36`
- Changing the strategy resolver / classifier
- Restoring `DownloadMenu` (open issue #95) — unrelated
- Frontend `localStorage`-in-jsdom test failures (open issue #91)
- Pytest test-isolation failures (open issue #90)

## Open questions for implementation plan

These are deliberately left to the implementation plan rather than this spec:

1. Exact placement of `_sanitize_check_detail` (a security helper colocated with `app/security.py`, or strategist-local?)
2. Whether `gate_result` should also surface in WebSocket stream events (`/v3/stream`) for live observation of replan loops — likely yes, but adds a touchpoint.
3. Whether to emit a Prometheus / structured-log counter for `failing_check_kind` distribution (related: open Tier 4.4 "Performance Dashboard" backlog item).
4. Exact wording of per-`failing_check_kind` summary messages — needs a quick UX/copy review before merge.
