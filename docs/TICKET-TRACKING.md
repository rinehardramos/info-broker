# Ticket Tracking — issues ↔ code ↔ PRs ↔ branches

> Last reconciled: **2026-05-24** (PRs #118, #120–#129, #132 merged; #68, #89 closed; issues #130, #131 filed)
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
| **#131** | bug (infra) | Live search 429-blocked locally → research can't complete | Brave/Google return HTTP 429 / bot-block to the local stack IP; no Serper/Brave/Tavily keys. Gather gate then fails for lack of live sources even though the brain works. | Filed | Blocks ALL local research testing; prod likely has search keys. |
| **#130** | bug (infra) | Login rate-limit (60/min) makes full pytest suite flaky | After #90's isolation fix, cumulative logins across the suite trip the 60/min limit → later tests' logins get 429. Files pass in isolation (`test_pipelines.py` 50/0) but flake in the full run. | Filed | Different mechanism than #90 (rate limiter, not fixtures). Bypass limiter under test, or share tokens. |

> Only **infra** issues remain open — no product bugs.

**Recently closed:** #89 → **closed (resolved by #117 taxonomy + gather gates; verified non-reproducing 2026-05-24).** Two latent hardening items (tactician slot-0 `prior_research_seed`; ACH lone-hypothesis "high") live in the regression watchlist below — no active symptom, file standalone only if needed. #90 → #124. #110/#111 → #118. #94 → #119. #95, #91 → verified fixed. **Brain 100%-broken auth bug → #123** (kept env OAuth token). **UI/agent work:** #127 (legacy phase order in v2 live + DAG + lint), #128 (mid-run injection persist+steer), #129 (#122 is_prompt assertion regression).

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
