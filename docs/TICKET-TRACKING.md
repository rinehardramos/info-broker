# Ticket Tracking — issues ↔ code ↔ PRs ↔ branches

> Last reconciled: **2026-05-26** (PRs #118, #120–#129, #132–#140, #142–#144, #146–#163 merged; #68, #89, #90, #94, #95, #110, #111, #130 closed; #131 open/downgraded; API-key vault+gates #74/#75/#76 DONE (#150/#153/#154); benchmark #79/#145 DONE+live-validated; **free-enrichment/stealth program #159–#163 DONE**)

## Free-enrichment / stealth-scraping program (#159–#163)

Driven by the directive: don't gate capability behind the easiest method (paid API keys) — lead with creative free/public methods. Outcome: the free-first thesis holds where data is page-available (agent-listed run extracted 15 agent phones, zero keys); FSBO-platform *seller* contact is a genuine data wall (login/contact-form gated); county OPEN-DATA APIs are the robust free owner-of-record source.

| PR | What |
|----|------|
| #159 | Two-tier stealth: curl_cffi TLS/JA3 impersonation in `safe_fetch_url` (SSRF guards preserved) + nodriver undetected-Chromium `stealth_browser` node + `run_stealth_browser` MCP tool (Chromium in image). Renders FSBO.com/Craigslist free; Zillow PerimeterX still resists. |
| #160 | Soft-target-first leads briefing (Craigslist/FSBO.com/Houzeo first; Zillow demoted) + agent-listed gold-set item. |
| #161 | `lead_richness` scores synthesized `ranked_candidates` (not raw findings) + `field_coverage` metric (honest measurement of what the run surfaced). |
| #162 | Public-records owner identity via county OPEN-DATA APIs (Socrata/ArcGIS) — validated Cook County `datacatalog.cookcountyil.gov` returns owner mailing address as JSON. |
| #163 | Authenticated sessions: own-credential site-login vault (`sitecred:<site>`, password never returned/logged/to-brain) + nodriver login form-fill (validated end-to-end on a public test-login site). |
> Maintainer note: this is the **source of truth for "what is actually shipped vs. in-flight."**
> The older `TODO.md` (root) describes a tier roadmap and **lags reality** — trust this file and the code, not `TODO.md`.

## Why this file exists

To prevent three failure modes:

1. **Drift** — squash-merges leave the original branch looking "unmerged" in `git`, and the running dev container can drift from `main` (e.g. `docker cp` patches). We track real merge state, not git's `--no-merged`.
2. **Duplication** — a feature gets re-implemented because nobody noticed it already shipped under a different PR/branch (see #68 below).
3. **Regression** — a fix silently undoes earlier work. We keep a watchlist of areas where that has bitten us.

## How to use it (reconciliation process)

Before citing a ticket, starting a "new" feature, or trusting a branch:

1. **Verify against code, not the ticket.** `grep`/read the relevant module first — tickets and `TODO.md` lag. (e.g. `is_admin` is shipped despite `TODO.md` Tier 4.1 listing it as open.)
2. **Check real merge state, not `git --no-merged`.** Squash-merged PRs show their branch as "unmerged." Use `gh pr list --state all --json number,state,headRefName,mergedAt`.
3. **Check the running env matches `main`.** Before any fix: sync `main`, rebuild + restart the stack so containers reflect the image (not stale `docker cp` patches), then baseline-test.
4. **Search this file's Shipped Inventory before building a "new" feature** — confirm it isn't already delivered.
5. **Update this file** whenever a PR merges, an issue closes, or a branch is pruned. Bump the "Last reconciled" date.

---

## Open issues (the real backlog)

| # | Type | Title | Code-verified state | Owning work | Regression notes |
|---|------|-------|---------------------|-------------|------------------|
| **#131** | bug (infra) — **downgraded** | Live search 429 (intermittent, engine-specific) | Brave/Google bot-block the scrapers; mojeek/yandex/grokipedia return 200, and `multi_search` consensus self-heals — research **does** complete (verified: 23-branch run). Root cause = no Serper/Brave/Tavily key. | Open (low) | NOT a hard blocker. Reliable fix = configure a search key (deployment). Optional: lead with free non-bot-blocked engines. |

> Only one **infra** issue remains open (and it's downgraded) — no product bugs.

**Recently closed:** **#130** → #135 + #139 (test rate-limiter + admission-gate bypass under test, + restore-on-teardown fixture — full suite deterministic). #89 → resolved by #117 taxonomy+gates (non-reproducing); two latent hardening items in the watchlist below. #90 → #124. #110/#111 → #118. #94 → #119. #95, #91 → verified fixed. **Brain 100%-broken auth → #123**. **UI/agent:** #127 (legacy phase order), #128 (mid-run injection), #129 (#122 is_prompt regression), #134 (removed low-value dashboard entity-lookup), #136 (enlarged Research CTA 2×), #137 (temporal-trail tests → sync). **Real-estate leads-gen:** #138 (real_estate_leads strategy + 6 enrichment techniques + leads_enrich_gather tactic + composite routing + templates), #140 (`_infer_mode` lead-phrase → leads_generation), #142 (extended lead idioms), #144 (tool-health ordering + listings-first per-item enrichment). **Tooling/admin:** #143 (New Session → Agent pane), #146 (admin action-items for unhealthy/needs-key tools). **Benchmarks (issue #145):** #147 (gold-set + composite scoring + 4 anti-gaming guards), #148 (leads-gen richness + cost + recommendations).

## In-flight (multi-phase API-key vault + missing-key gates)

> Driven by run `c5aff228` (thin leads-gen output) — root cause was **missing/invalid enrichment keys**, not a decision-tree bug. The fix is to let users supply keys safely and gate runs that need them.

> **API-key trilogy COMPLETE (2026-05-25): #74 → #75 → #76 all shipped.** Load-bearing invariant throughout: a key VALUE never reaches the brain env/logs/trail or any client payload — only key NAMES + public setup info travel outward; values go only to the encrypted vault endpoint.

| # | Phase | What | State | Security invariant |
|---|-------|------|-------|--------------------|
| **#74** | 1 | Scoped **encrypted** API-key vault (user→org→global→core_settings→env; Fernet encrypt-at-rest) | **DONE → #150** (fixed global-NULL rotation bug w/ `NULLS NOT DISTINCT`) | Keys never reach brain env/logs/trail; only `IS_RUN_USER_ID`/`IS_RUN_ORG_ID` UUIDs threaded via `X-Caller-*` headers, resolved server-side at node-execute. |
| **#75** | 2 | Pre-run missing-key **decision gate** (confirm returns `missing_keys_gate` before launch; enter key / proceed-anyway; SOFT — never hard-blocks) | **DONE → #153** | Gate transmits only key_name/setup info — never a key VALUE. |
| **#76** | 3 | Reactive **mid-run** gate (keyed node-execute with no key → `missing.key` event on the live stream; per-call resolution + retry hint pick it up — NOT a blocking pause, by design) | **DONE → #154** | `X-Run-Id` threaded like the caller ids; event carries no key value. |

> **#79 leads-gen benchmark DONE (#148) + live-validated.** First live run exposed a harness bug (read empty `/runs/{id}.research` for `trigger_type='agent'` runs → false-positive `training_only`); fixed in **#151** (reads `/v3/research-trails/{id}`). Real baseline: brain does correct live research, extracts **8–10 leads/query**, but **0% per-lead contact enrichment** (no keys) → recommendation engine fires `low-richness`. Quantifies the `c5aff228` gap that #74–#76 close.
> **Latent follow-up (from #151):** `pipelines.py` run-detail attaches the trail only when `trigger_type=='agent_is'`; `'agent'` runs get `research=None`. UI uses the replay/`research-trails` path so not user-facing, but broaden the gate to "attach when a trail row exists." Also: no node implements `health_check` for the leads-gen enrichment nodes, and `pipl_people` node file is missing.

> Issue "files likely to involve" lists are **stale** (pre-#117 taxonomy). Corrected file maps live in each issue's latest comment.

## Open PRs

**None open.** (#68 `signed-callbacks-v2` was a stale duplicate of merged #84 → **closed + branch deleted 2026-05-24**.)

## Branch hygiene — prune stale squash-merged branches

Squash-merges leave the original branch looking "unmerged" in `git branch --no-merged` even though the content is in `main`. Use `gh pr list --state all` for real state, and delete branches whose PR is MERGED. As of 2026-05-24 the day's branches (#118–#124) were auto-deleted on merge. The older `feat/*` / `feature/*` branches from the #65–#117 era remain as stale remotes and are safe to prune (`git push origin --delete <branch>`) — verify each maps to a MERGED PR first.

---

## Shipped inventory (search here before building a "new" feature)

Reconciled from merged PRs; grep-verified entry points. Prevents duplication.

| Feature | Where (entry point) | PR(s) |
|---------|---------------------|-------|
| Unified phase taxonomy `extract→gather→disconfirm→synthesize` | `app/pipeline/catalogs/constants.py` `LEGAL_PHASE_IDS` | #117 |
| Tactic catalog + Apify Zillow technique | `app/pipeline/catalogs/registries/` | #117 |
| Gather-phase `ask_user` diagnostic / `no_brain_work` invariant | `app/pipeline/strategist.py` | #116 |
| MCP web_crawl/whois node-execute fixes | `app/routers/v3/nodes_api.py`, `app/pipeline/nodes/web_crawl.py`, `mcp_server/server.py` | #118 |
| **Brain OAuth via env token** (keep `CLAUDE_CODE_OAUTH_TOKEN` when no creds file) | `app/pipeline/runners/scoped_brain.py` | #123 |
| **Phase vocabulary canonicalized on `gather`** (BROADEN retired) | `app/is_prompt.py` + catalog | #122 |
| **pytest test isolation** (unique fixtures, `ON CONFLICT DO UPDATE`, conftest env-bleed fix) + `auth.py`/`pipelines.py`/`models.py` bug fixes | `tests/conftest.py`, `tests/**`, `app/routers/v3/{auth,pipelines,models}.py` | #124 |
| vitest scoped to `src/` (e2e excluded) + stale-mock fixes | `frontend/vite.config.ts`, test files | #120 |
| Org membership roles (analyst/viewer) + `is_admin` RBAC | `app/routers/v3/tenancy.py`, `require_admin` | #74, #85 |
| Admin user-management page | frontend admin | #82 |
| Multi-turn session hypothesis memory | `agent_sessions.investigated_hypotheses` | #78 |
| Metrics dashboard (API + UI) | `app/routers/v3/metrics.py`, frontend | #76, #79 |
| Dropbox / Google Drive datastore nodes | `app/pipeline/nodes/` | #75 |
| OSINT marketplace datastore nodes | `app/pipeline/nodes/` | #81 |
| Plugin scaffold generator + review UI | plugin scaffold endpoint | #77 |
| Signed webhook callbacks (HMAC + backoff) | `app/services/webhook.py` | **#84 (v3)** — _not_ #68 |
| Temporal IS workflow (Phase 0/1) | `app/temporal/` | #80, #83 |
| Run budget reservation gate | `app/pipeline/budget.py` | #66 |
| ACH consistency matrix + PIR scoring | `app/pipeline/fusion/ach.py`, `pir.py` | #71, #65, #73 |
| Tenancy enforcement (`org_id` in browser-path WHEREs) | v3 routers + `org_scope_clause` | #63 |
| Default search mode selection | preflight modes | #98, #99 |
| Assets library page | frontend assets | #108 |
| Modes & Templates visibility admin toggle | `app/routers/v3` visibility | #109 |
| DownloadMenu inline run exports | `frontend/.../runs/DownloadMenu.tsx` | (restored) f10890f / #95 |
| v2 live + DAG phase order = unified taxonomy (legacy names removed) | `PhaseProgress.tsx`, `dag/buildDagFromRun.ts`, `PhaseDAGView.tsx` | #127 |
| Mid-run instruction injection (persist follow-up to conversation_thread + steer running brain via `user_directive`) | `app/pipeline/runners/injection_queue.py`, `routers/v3/brain.py`, `strategist.py`, `scoped_brain.py` | #128 |
| Real-estate **leads-generation** — `real_estate_leads` strategy (listings→contact→owner-background→leads table), 6 enrichment techniques (hunter/opencorporates/whois/apollo/phone_osint/pipl), `leads_enrich_gather` tactic, `(real_estate,leads_generation)→real_estate_leads` composite route, templates | `catalogs/registries/{strategies,tactics,techniques}/…`, `routers/v3/preflight.py`, `investigation_templates.py` | #138 |
| Lead-phrase mode inference (`_infer_mode`: "lead list"/"find leads"/… → leads_generation when no mode picked) — makes leads-worded queries + the template auto-route to `real_estate_leads` | `app/routers/v3/preflight.py` | #140 |
| Dashboard: removed low-value entity-lookup; enlarged primary Research CTA ~2× | `frontend/src/pages/Dashboard.tsx` | #134, #136 |
| Extended lead-phrase signals (`fsbo`/`frbo`/`motivated seller`/`owner contact`/`skip trace`/… → leads_generation) | `app/routers/v3/preflight.py` `_LEADS_MODE_SIGNALS` | #142 |
| New Session button relocated to Agent pane (`handleEndSession`) | `frontend/src/components/agent/AgentChat.tsx`, `live/LiveStream.tsx` | #143 |
| **Tool-health-aware brain ordering** (healthy techniques first; unhealthy marked `⚠ UNAVAILABLE (needs <key>)`, never dropped) + **listings-first per-item enrichment** (gather lists FIRST → enrich EACH → synthesize per-row leads table; missing fields marked "not found / tool unavailable") | `app/pipeline/runners/{tool_health.py,scoped_brain.py}`, `catalogs/registries/strategies/real_estate_leads.py` | #144 |
| Admin action-items UI for unhealthy / needs-key tools/plugins | `frontend/src/components/settings/{AdminActionItems.tsx,Settings.tsx}` | #146 |
| **Benchmark harness** — curated gold-set + composite scoring (coverage×source_quality) + 4 anti-gaming guards (training-only / unregistered-tool / skipped-phase / RAG-shortcut → hard zero) | `benchmarks/{goldset,score.py,run_benchmark.py}`, `tests/benchmarks/test_score.py` | #147 (issue #145) |
| **Leads-gen benchmark extension** — leads gold-set + `lead_richness()` (10 contact/owner fields → per-lead completeness, zero-enrichment count) + cost metrics (cost_per_lead / cost_per_matched_fact / avg_duration) + `build_recommendations()` (missing-key / anti-gaming / underperforming-component / low-richness / cost-outlier / gold-set-gap, severity-sorted) | `benchmarks/{goldset/leads_items.yaml,score.py}`, `tests/benchmarks/test_leads_metrics.py` | #148 (issue #145/#79) |
| **Scoped encrypted API-key vault** — Fernet encrypt-at-rest; `resolve_api_key` user→org→global→core_settings→env; `POST/GET /v3/settings/api-keys` (scoped write-auth, presence-only GET); keys resolved server-side at node-execute, never reach brain | `app/lib/{secret_box,api_keys}.py`, `app/routers/v3/{settings,nodes_api,db}.py`, `scoped_brain.py`, `mcp_server/client.py` | #150 (#74) |
| **Benchmark reads real trail** — `fetch_trail` → `GET /v3/research-trails/{id}` (X-API-Key) + top-level `tool_calls`; guard fixes (unknown tool_calls ≠ 0; string/dict phase shapes); 429 backoff; real-trail fixtures | `benchmarks/{run_benchmark,score}.py`, `tests/benchmarks/test_real_trail_shape.py` | #151 |
| **Pre-run missing-key gate** — `technique_keys.check_missing_keys_for_strategy` (enumerates per-phase `preferred_tactic_id` techniques → vault check); `bypass_missing_keys` + `PreflightConfirmGateOut`; frontend `MissingKeysGate` + `usePreflight` union | `app/pipeline/catalogs/technique_keys.py`, `app/routers/v3/preflight.py`, `frontend/src/components/preflight/MissingKeysGate.tsx`, `hooks/usePreflight.ts` | #153 (#75) |
| **Reactive mid-run missing-key gate** — `X-Run-Id` thread (scoped_brain→mcp client→nodes_api); deduped `missing.key` stream event when a keyed node lacks its key; `node_missing_key`; frontend `MidRunKeyCard` in AgentChat | `scoped_brain.py`, `mcp_server/client.py`, `nodes_api.py`, `technique_keys.py`, `AgentChat.tsx` | #154 (#76) |
| **Benchmark real RU cost** — `fetch_trail` reads `GET /v3/runs/{id}/cost_breakdown.total_ru` (wallet ledger) + gate-UI vitest tests | `benchmarks/run_benchmark.py`, `frontend/.../MissingKeysGate.test.tsx` | #155 |

## TODO.md (root) reconciliation — what's actually done

| TODO.md item | Reality |
|--------------|---------|
| 3.6 Session multi-turn hypothesis memory | **DONE** (#78) |
| 4.1 Non-Admin RBAC / `is_admin` column | **DONE** (#74 column + `require_admin`; #85 roles) |
| 4.2 Plugin ecosystem (#45/#46/#47) | **DONE** (#77 scaffold+review; #81 marketplace nodes) |
| 4.3 New datastore nodes | **DONE** (#75 Dropbox/GDrive; #81 marketplace) |

> Recommend updating/retiring `TODO.md` so it stops contradicting shipped state.

## Regression watchlist (areas where a fix has undone prior work)

- **Phase ids** — never reintroduce legacy ACH phase names; `tests/pipeline/tests/test_no_legacy_phase_ids.py` (CI lint) guards this. (#117)
- **`run_id` visibility in UI** — must appear on every run surface; was removed by a refactor once. (memory: run_id-in-ui)
- **Tenancy `org_id` filtering** — browser-path queries must keep `org_scope_clause`; dropping it leaks cross-org rows. (#63)
- **`no_brain_work` gate** — must honor `no_tool_calls_required` so the extract phase isn't failed for 0 tool calls. (#116)
- **MCP node-execute input wrapping** — `_INPUT_TARGET_FIELDS` must exclude config-only keys (`research_goal`…) or config-only nodes regress. (#118)
- **Signed callbacks** — do not re-merge #68; v3 (#84) is canonical.
- **Brain subprocess auth** — `scoped_brain` must keep `CLAUDE_CODE_OAUTH_TOKEN` in the spawn env when no `/root/.claude/.credentials.json` file exists; popping it unconditionally broke ALL research. (#123) Beta = subscription token, not API.
- **`org_scope_clause` only on org-scoped tables** — the `pipelines` table has NO `org_id` column, so applying `org_scope_clause` there SQL-errors for non-admins. Scope pipelines by `user_id`. Don't blanket-apply org scoping. (#124)
- **Phase label** — vocabulary is `gather` everywhere; `BROADEN` retired. Don't reintroduce it as a label (distinct from the legacy-id lint, which keeps the word to forbid it). (#122) Also keep prompt-content tests in sync — #122 silently broke `test_is_prompt::test_hypothesis_first_broaden_gate` (fixed in #129).
- **Verify merges against a full-suite baseline, not an agent's selection.** #122's prompt-test break was invisible to its own test selection; only a full-suite diff caught it. When merging, diff failures against current `main` — distinguish real regressions from pre-existing (#125 temporal tests) and environmental flakiness (#130 login rate-limit).
- **Mid-run injection requires a session** — `inject_node` persistence only fires when the run has a `session_id` (agent-chat runs do; bare `/v3/preflight/confirm` runs don't). The in-memory queue is per-process — won't bridge to out-of-process temporal workers. (#128)
- **Test env state must be restored** — tests that mutate global env + reload a module (e.g. `test_admission_gate._set_gate` flipping `GATE_ENABLED`) MUST restore on teardown or they bleed into the rest of the suite (caused flaky `/v3/agent/message` 429s). Prod guards (slowapi limiter, admission gate) are bypassed under test via conftest `DISABLE_RATE_LIMIT=1` / `GATE_ENABLED=false`. (#130, #139)
- **Strategy routing matches intent BEFORE mode** — `_resolve_strategy` step-1 returns the intent-named strategy before the mode-anchor step; to route an (intent, mode) combo elsewhere, add it to `_COMPOSITE_STRATEGY` (step 0). Also `mode` only comes from `body.mode` or `_infer_mode(query)` — there is no separate mode classifier. (#138, #140)
- **Zombie `running` runs block the live app** — API restarts orphan in-process run tasks but leave `pipeline_runs.status='running'`. With `GLOBAL_MAX_CONCURRENT=2`, a few zombies saturate the admission gate so NO new run is admitted (live app + tests). Reconcile stale `running` rows (orphan_watchdog should, but verify) or `UPDATE … SET status='failed'`. (#130)
- **`async def` tests need pytest-asyncio (not installed)** — the venv lacks it despite being declared; `@pytest.mark.asyncio` tests error. Use the repo's sync `asyncio.run()` pattern instead. (#137)
- **New v2 techniques need `output_schema`** — the fail-closed startup audit (`run_audit_or_fail`) rejects a technique without one; the app won't boot. (#117, #138)
