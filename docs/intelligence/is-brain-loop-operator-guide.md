# IS-Brain Orchestrated Loop — Operator Guide

The IS brain runs in one of two modes:

| Mode | Flag | Shape | Use when |
|---|---|---|---|
| **single-shot** | `IS_USE_LOOP=false` (default) | One Claude Code subprocess with a fat prompt; one JSON result back | Quick lookups, simple factual queries, low-budget runs |
| **orchestrated loop** | `IS_USE_LOOP=true` | N short brain turns against a structured working memory; explicit explore → test → synthesize phases | Hypothesis-feasibility, contested topics, anything that benefits from auditable reasoning |

The loop is gated behind `IS_USE_TEMPORAL=true` (Temporal-managed workflow) AND `IS_USE_LOOP=true`. Default-off for new deployments; turn both on to enable.

---

## What each loop run produces

Every loop run writes:

1. A **typed `WorkingMemory`** object that accumulates state across turns. Persisted to the `working_memory_snapshots` table (one row per turn).
2. A **synthesis** (natural-language answer) from the final turn, stored on the final WM as `synthesis_summary`.
3. **Findings** indexed to Qdrant (`research_memory` collection) so future runs can retrieve them via cross-run memory.

UI surfaces in the Result Drawer's **Turns** tab (visible only for runs with snapshots):
- **LoopBanner** — `complete · 3/3 verified · 5 turns` or `partial · 1/3 verified · final phase test · 8 turns`
- **Synthesis panel** — the brain's final answer with inline citations
- **Per-turn rows** — hypothesis/finding/fact counts + source-class chips + ACH ranking
- **Click "Show JSON"** to inspect the full working memory at any turn

---

## The phase machine (workflow-owned, not LLM-owned)

```
preflight → [conflict_check] → budget → init_working_memory
                                              ↓
                                         ┌─→ EXPLORE ─→ TEST ─→ SYNTHESIZE → DONE
                                         │     ↑       │
                                         │     │       └→ (stagnation: abandon + force-synth)
                                         │     └← (open hypotheses < 2)
                                         └─ awaiting_input (if conflict or ask_user)
```

**Phase transitions are pure functions** in `[REDACTED:high-entropy-base64:36ch:hash=2b5e2e2c]`:
- `compute_next_phase(wm)` — explore→test when ≥2 hypotheses; test→synthesize when all resolved AND no open contradictions
- `is_stagnant_in_test(wm)` — 2+ test turns without progress → workflow force-abandons opens and advances to synthesize
- `should_terminate(wm, max_turns, cancelled)` — priority: cancelled > synthesized > max_turns_reached

`max_turns` defaults to 8 (via `IS_LOOP_MAX_TURNS`). For 3-hypothesis questions, the natural budget is 1 explore + 3 test + 1 synthesize = 5 turns.

---

## Pre-research conflict-detection gate

Before any research budget is spent, one Gemini Flash call asks "is this query unambiguous?" If the query has plausible multiple referents (entity ambiguity, scope ambiguity), the workflow blocks with a clarification question and routes through the existing `brain_answer` signal/`mark_awaiting_input` mechanism.

- Fail-open: no Gemini key → run proceeds normally
- Fail-open: LLM error or unparseable JSON → run proceeds normally (logged with `parse_failed` reason)
- Costs: ~1 Gemini Flash call per run (~$0.0001)

Catches "Tell me about Acme" (which Acme?) before spending 5 turns researching the wrong one.

---

## ACH (Analysis of Competing Hypotheses)

The loop scores each (finding × hypothesis) pair as `consistent` / `inconsistent` / `neutral` / `not_applicable`. Two ways the matrix populates:

1. **Brain emission**: the prompt asks the brain to score new findings during test turns
2. **Auto-derivation** (the reliable path): when a `hypothesis_update` cites `add_supporting_finding_ids` / `add_refuting_finding_ids`, `apply()` automatically derives `consistent` / `inconsistent` cells

**Ranking rule** (the load-bearing ACH insight): hypotheses are ranked by **fewest inconsistencies**, not most consistencies. A hypothesis with 0 inconsistencies and 1 consistency beats one with 0 inconsistencies and 15 consistencies only when ties are broken by raw count. **An inconsistency is far more disprobative than a consistency is confirmatory.**

A finding is **diagnostic** if it's consistent with one hypothesis AND inconsistent with another — those are the most analytically valuable observations and get a ★ marker in the prompt and UI.

The UI Turns tab includes a collapsible **ACH evidence matrix grid** showing each scored finding (rows) against each hypothesis (columns). Cells: `+` (green, consistent), `−` (red, inconsistent), `·` (gray, neutral), `/` (dim, not applicable). Tooltip on each cell shows the brain's note. The matrix is the canonical analyst view — every cell is auditable.

---

## Contradictions

When two findings (or hypothesis vs finding) give incompatible claims, the brain flags a `new_contradiction`. Synthesize is gated on every open contradiction being resolved — the workflow won't transition to synthesize until each contradiction has a `winner: 'a' | 'b' | 'both' | 'neither'` and a `resolution_note`.

`'both'` is the "different framings, both correct under their framework" answer — e.g., "$105M GAAP net loss" vs "$158M IFRS loss for the year" are both true under different accounting presentations.

Stagnation can fire here too: if the brain can't reconcile and we hit STAGNATION_TURNS in test phase, the workflow force-advances to synthesize (the synthesis must then acknowledge the unresolved conflict).

---

## Cross-run memory (Tier 1 priority #1)

Every loop run starts by calling `fused_retrieve()` against the query. This pulls the top 8 semantically-related findings from past runs (across semantic + bm25 + entity + temporal + feedback signals, fused via RRF).

- User-graded priors (`user_score > 0`) auto-seed `established_facts` with `verified_by='user_grade_A'`
- All retrieved priors land in `wm.cross_run_priors` for prompt context
- Every loop run also auto-indexes its findings back to `research_memory` via `post_process`

Net effect: each new run starts with the system's prior knowledge instead of cold. The brain doesn't have to re-discover the $105M figure if a previous run already found it.

**Required infrastructure:** Qdrant collection `research_memory` must be populated. The writer's payload doesn't set an explicit `ref` field; `[REDACTED:high-entropy-base64:24ch:hash=92b6e0f9]` derives it from `(run_id, finding_index)` at read time — avoids the silent dedup collapse that occurred when all results came back with `ref=""`.

---

## Source classes

Every Finding gets auto-classified by `classify_source(url, source_tool)`:

| Class | Examples | Weight |
|---|---|---|
| `primary_official` | investors.grab.com, *.gov.*, *.gov, treasury.gov | Highest |
| `registry` | sec.gov, sec.gov.ph, companieshouse.gov.uk, opencorporates.com | High |
| `news` | reuters.com, businesstimes.com.sg, bloomberg.com, techcrunch.com | Medium |
| `aggregator` | macrotrends.net, stockanalysis.com, simplywall.st | Low |
| `social` | linkedin.com, twitter.com, medium.com | Lowest live |
| `training` | no URL, source_tool="internal" | Inferred (no live evidence) |
| `unknown` | unclassified | Audit |

The synthesize-phase prompt instructs the brain to lean on primary_official and registry first; if the answer depends on aggregator-only sources, the synthesis must say so explicitly.

Classifier lives in `[REDACTED:high-entropy-base64:36ch:hash=42dffe0c]`. Brain can override via `new_findings_data[].source_class`.

---

## Deception scoring (per-finding tradecraft)

Every Finding is auto-scored by `app/pipeline/fusion/deception.py` during `apply()`. Four signals:

| Flag | Weight | What it catches |
|---|---|---|
| `source_echo` | +0.30 | Same `(title, content)` from multiple distinct sources — typical astroturfing / syndicated planted stories |
| `copied_content` | +0.20 | ≥50-char verbatim substring between two findings — boilerplate or one source recopying another |
| `too_perfect` | +0.20 | Suspiciously many non-standard fields on a single finding — manicured / fabricated payload |
| `low_source_diversity` | +0.15 | All findings from one tool — single-channel echo chamber |

`deception_risk` ∈ [0, 1] is the sum of triggered flag weights, capped at 1.0. The UI surfaces a red chip per turn when ≥1 finding has `deception_risk ≥ 0.3`: `⚠ N flagged · source echo 3 · copied content 1`.

The detection runs on **every** `apply()` over the full merged finding set — so a finding that looks clean on its own gets re-flagged retroactively when a duplicate-from-different-source arrives later.

Use deception flags to discount evidence weight during synthesis: a hypothesis "supported by 15 findings" where 10 of them are `source_echo` flagged is weaker than "supported by 5 findings, no flags."

---

## Time-decay on cross-run priors

When `init_working_memory` retrieves prior findings via `fused_retrieve`, each prior is decayed by `app/pipeline/fusion/decay.py::calculate_decay` based on **how old the observation is** and **what kind of data it is**. Shelf lives are wired to the `source_tool` that produced the original finding:

| source_tool category | shelf life | decay curve |
|---|---|---|
| phone_osint, messaging_check | 180 d | exponential |
| smtp_verifier, email_enumerator, hunter_io | 180 d | exponential |
| linkedin_profile, apollo_zoominfo (employment) | 365 d | step (full → 30% after 1y) |
| facebook_pages, instagram_profile, twitter_search (social) | 90 d | linear |
| ph_sec_dti, opencorporates, sec_edgar (registries) | 1825 d (5y) | linear |
| hibp_lookup, pep_sanctions_screen (historical) | permanent | none |
| crypto_tracer (financial) | 90 d | exponential |
| unknown source_tool | 365 d default | linear |

**Why this matters**: a user-graded fact from 2 years ago saying "X's phone number is 555-1234" should not auto-seed a 90%-confidence `established_fact` today — phone numbers turn over. The decay reduces the seeded `Fact.confidence` automatically. If decay drives confidence to 0, the fact is dropped entirely rather than injected as a misleading 0% assertion.

The brain sees a `[decayed 80→26, -67%]` tag next to old priors in the prompt's `CROSS-RUN PRIORS` section. The UI Turns tab shows an amber chip when N priors have been aged out.

Current-run findings (everything observed *during* this run) are NOT decayed — they're all fresh by definition.

---

## PIR (Priority Intelligence Requirements) coverage

For investigation-style queries (person, company, due_diligence), the loop computes a structured **collection-plan view**: which Essential Elements of Information (EEIs) have been answered and which remain open. Doctrine source: `app/pipeline/fusion/pir.py`.

The hierarchy is **PIR → SIR → EEI**:
- **PIR** (Priority Intelligence Requirement) — a thematic area (e.g. "Identity Verification", "Risk Assessment", "Financial Profile")
- **SIR** (Specific Information Requirement) — a sub-question (e.g. "Sanctions and PEP status")
- **EEI** (Essential Element of Information) — the exact field (e.g. `pep_status`, `sanctions_status`) with keyword indicators

Two integration points:
1. **`post_process`** runs PIR mapping at run-completion and stamps `_loop_meta.pir` on the result for the WS event.
2. **Snapshot endpoint** computes PIR coverage on-the-fly from the final WM's findings — derived view, no schema changes.

Entity-type inference (`infer_entity_type(query)`) uses cheap heuristics: company markers (`Inc`, `Ltd`, `Corp`, `Holdings`, `NASDAQ:`, `10-K`, etc.) before person markers (`CEO of`, `founder of`, `background check`, `due diligence on`). Falls back to a generic template if neither fits.

The UI Turns tab surfaces:
```
● PIR coverage (company): 4/7 EEIs resolved · 3 gaps
  Missing: Corporate Identity > Legal registration > jurisdiction · Corporate Identity > Leadership > officers · …
```

with the dot colored green (≥80%), amber (≥50%), or red (<50%).

Use the gaps as a checklist: each gap tells you a concrete element that the current run did NOT answer. Re-issuing a focused follow-up query (or feeding the gaps to `new_open_questions` in a next-turn delta) targets the missing pieces.

---

## Tool gating (hard-enforced, category-driven)

The brain subprocess is spawned with `--allowedTools` listing only the MCP tools allowed in the current phase. The list is **derived** from two sources of truth, not hardcoded:

1. **`MCP_TOOL_CATEGORIES`** — every MCP tool is registered with one of 8 categories: `source`, `lookup`, `enrich`, `score`, `knowledge`, `meta`, `destination`, `clarification`.
2. **`PHASE_ALLOWED_CATEGORIES`** — each phase enumerates which categories are allowed:

| Phase | Allowed categories | Purpose |
|---|---|---|
| `explore` | source, knowledge, clarification | broad discovery + reuse prior work |
| `test` | source, lookup, enrich, score, knowledge, clarification | + targeted verification + enrichment |
| `synthesize` | clarification | force use of accumulated findings; no new research |

The runtime allowlist is computed by `allowed_tools_for_phase(phase)`:
```
tools = { name : cat for (name, cat) in MCP_TOOL_CATEGORIES if cat in PHASE_ALLOWED_CATEGORIES[phase] }
       - IS_DENY_TOOLS env override
```

The brain sees the exact list in the prompt's TOOLS section, and any tool outside the list is HARD-BLOCKED at subprocess level — Claude Code returns permission-denied if the brain tries one.

### Adding a new tool

Two steps:

1. In `mcp_server/server.py`, add the `@mcp.tool()` async function as usual.
2. In `app/pipeline/runners/working_memory.py::MCP_TOOL_CATEGORIES`, add `"your_new_tool": "<category>"` — that's it. The tool inherits the gating policy for its category across every phase.

**Forgot step 2?** The tool is silently DENIED in every phase (explicit opt-in is safer than accidental opt-out). The brain won't see it in the prompt and can't call it. This is the design — unregistered tools never leak into the loop.

**Safety net** — `tests/test_mcp_tool_categorization_lint.py` runs in CI and fails the build if an `@mcp.tool()` exposed by `mcp_server/server.py` is missing from `MCP_TOOL_CATEGORIES`. The failure message lists the missing tool names so the developer knows exactly what to add. Same lint also catches **phantom entries** (registry rows where the underlying `@mcp.tool()` was deleted) and **unhandled categories** (a category used by tools but not declared in any phase nor explicitly excluded).

### Categorization rules of thumb

| Category | Use when… |
|---|---|
| `source` | broad collection / search returning lists (web search, RSS, twitter, github search) |
| `lookup` | directed retrieval by ID/URL/name (registries, fetch-this-page, whois, hunter.io) |
| `enrich` | augments existing data via API (summarizer, ai_provider, financial_projections) |
| `score` | scoring / rating tools |
| `knowledge` | READ-only access to the research corpus (get_past_research, list_recent_runs) — safe for brain |
| `meta` | WRITE operations or admin (save_pipeline, save_research_trail, log_cycle) — NEVER brain-callable |
| `destination` | exports / outputs (export_research) — user-driven, never brain |
| `clarification` | human-in-loop (ask_user) — available in all phases |

### Runtime incident-response lever

Set `IS_DENY_TOOLS=tool_name1,tool_name2` env var on the IS-temporal-worker container to hard-block specific tools without redeploying. Useful if a tool starts misbehaving (rate-limit storm, broken upstream, security incident) — restart the worker with the deny list, no code change needed.

---

## Falsification conditions

Every Hypothesis MUST include a `falsification_condition` — a concrete statement of what evidence would refute it. The EXPLORE-phase prompt requires it; hypotheses without one show `⚠ no falsification_condition — hypothesis is too vague` in the next turn's prompt.

This is the structural fix for "unfalsifiable hypothesis" reasoning errors — forces specificity at formation time rather than auditing for fallacies after the fact.

---

## Observability

Every brain turn writes one log line:

```
brain_turn run=<id> turn=N phase=X new_hyps=A hyp_updates=B (ids=...)
            new_findings=C new_facts=D strategies=E synthesis_len=F
```

If a turn produces an empty delta (silent regression — brain emitted JSON but nothing usable), the worker logs:

```
brain_turn run=... turn=N phase=X EMPTY DELTA (parse=..., raw_len=L, head='...')
```

`init_working_memory` logs cross-run seeding:

```
init_working_memory run=<id> seeded_facts=N cross_run_priors=M graded=K
```

`post_process` logs indexing:

```
post_process: indexed X findings to research_memory
```

`conflict_check` logs verdicts:

```
conflict_check: query IS ambiguous (kind=entity): Which 'Acme' are you referring to?
conflict_check: query is unambiguous
conflict_check: could not parse JSON from LLM (fail-open). raw head='...'
```

Querying snapshots from psql:

```sql
SELECT turn, phase,
       jsonb_array_length(coalesce(working_memory->'hypotheses','[]'::jsonb)) AS hyps,
       (working_memory->>'hypotheses_resolved')::int AS resolved,
       jsonb_array_length(coalesce(working_memory->'findings','[]'::jsonb)) AS findings,
       jsonb_array_length(coalesce(working_memory->'evidence_matrix','[]'::jsonb)) AS matrix
  FROM working_memory_snapshots
 WHERE run_id = '<uuid>'
 ORDER BY turn;
```

---

## Common operations

**Trigger a loop run from API** (assuming `IS_USE_TEMPORAL=true IS_USE_LOOP=true`):
```
POST /v3/agent/message
{ "message": "...", ... }
```
Dispatches via `app/routers/v3/agent.py` → `IsLoopRunWorkflow` on the `is-run-tasks` Temporal queue.

**Trigger a loop run programmatically** (bypasses preflight; useful for tests):
```python
from temporalio.client import Client
from app.temporal.workflows.is_loop_run import IsLoopRunWorkflow, ISLoopRunInput
c = await Client.connect("localhost:7233")
await c.start_workflow(IsLoopRunWorkflow.run, ISLoopRunInput(...),
                       id=f"is-loop-run-{run_id}", task_queue="is-run-tasks")
```

**Read snapshots**:
```
GET /v3/runs/{run_id}/working-memory   →  { run_id, total_turns, synthesis_summary, snapshots: [...] }
```

**Cancel a run**: send the `cancel_run` Temporal signal.

**Answer a conflict-gate clarification or ask_user pause**: send the `brain_answer` signal with the answer string.

---

## Tuning knobs

| Env var | Default | Effect |
|---|---|---|
| `IS_USE_TEMPORAL` | `false` | Required for the loop path |
| `IS_USE_LOOP` | `false` | Enables the orchestrated loop |
| `IS_LOOP_MAX_TURNS` | `8` | Hard cap on turns per run |
| `IS_BRAIN_TURN_TIMEOUT` | `180` (seconds) | Per-turn subprocess timeout |
| `IS_MCP_CONFIG` | `/app/config/is-mcp-config.docker.json` | MCP server config the brain spawns with |
| `GEMINI_API_KEY` (or DB `core_settings.gemini_api_key`) | — | Required for conflict-detection gate |

In `[REDACTED:high-entropy-base64:36ch:hash=2b5e2e2c]`:
- `MAX_OPEN_QUESTIONS = 5` — cap on simultaneously-open clarifications
- `MAX_TURNS_DEFAULT = 8`
- `PHASE_TRANSITION_MIN_HYPOTHESES = 2` — minimum to leave explore
- `STAGNATION_TURNS = 2` — test turns without resolution before force-synth

In `app/is_prompt_turn.py`:
- `TURN_TOOL_CALL_BUDGET = 6` — per-turn tool call cap (told to brain in prompt)
- `TURN_REASONING_BUDGET_SECONDS = 30` — advisory reasoning budget

---

## Verification routine

After any change that touches the loop:

1. **Unit tests** — `pytest tests/test_working_memory.py tests/test_brain_turn.py tests/test_conflict_check.py` (~75 tests)
2. **End-to-end UI test** — `cd frontend && npx playwright test loop-features-functional.spec.ts`
3. **Live smoke**: trigger a fresh loop run and watch the worker logs for the expected turn pattern (`hyp_updates=1` each test turn, `synthesis_len>1000` on the synthesize turn). Empty-delta warnings indicate prompt overload.

The `loop-features-functional` Playwright test is the canonical UI-feature alignment check — it exercises every visible surface (LoopBanner, Synthesis panel, source-class chips, ACH ranking rows, per-turn rows, JSON expand) and will catch when a new backend field has no UI hookup. Run it after any UI or schema change.
