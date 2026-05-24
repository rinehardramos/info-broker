# Ticket Tracking — issues ↔ code ↔ PRs ↔ branches

> Last reconciled: **2026-05-24**
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
| **#90** | bug | pytest test isolation (~90→**133** failures full-suite) | **Confirmed**: `_register_user` uses `ON CONFLICT DO NOTHING` (`tests/v3/test_auth.py:20`) + fixed-name fixtures + **persistent test Postgres across runs** → stale rows make some files fail even solo. | In progress | Touches only test fixtures/conftest — no prod code. |
| **#89** | bug | IS brain tunnels to RAG candidate; no BROADEN | **Partially mitigated already** (post-#117): `person.py` declares `hypothesis_count="competing"`, gather gates `distinct_identity_count`/`per_hypothesis_live_source`, `disconfirm` phase, `is_prompt.py` anti-tunneling rules. **Remaining gap**: `tactician.py:158-166` seeds slot-0 from `prior_research_seed` when prior research exists; `fusion/ach.py` scores a lone hypothesis `high`. | In progress | Brain behavior — verify with live re-run + a control (unambiguous) query so we don't over-broaden. |

> The issue's "files likely to involve" lists are **stale** (pre-#117 taxonomy). Corrected file maps live in each issue's latest comment.

## Open PRs

| PR | Branch | State | Verdict |
|----|--------|-------|---------|
| **#68** | `feat/signed-callbacks-v2` | OPEN | **STALE DUPLICATE — close it.** Identical title to **#84 `signed-callbacks-v3` (MERGED 2026-05-13)**; `app/services/webhook.py` is in `main`. Keeping it open invites a duplicate re-merge / regression. |

## Branch hygiene — prune stale squash-merged branches

These remote branches show as "unmerged" in `git branch --no-merged` but their PRs were **squash-merged** (content is in `main`). They are safe to delete; leaving them is the main source of drift confusion. Superseded `-v2`/`-v3` chains are the worst offenders.

```
# squash-merged → safe to delete (PR # in parens)
feat/research-skeleton-tactic-completion (#117)   feat/gather-ask-user-diagnostic (#116)
feat/admin-user-management (#82)                  feat/non-admin-rbac (#74)
feat/metrics-dashboard (#76)                       feat/metrics-frontend (#79)
feat/session-hypothesis-memory (#78)               feat/new-datastore-nodes (#75)
feature/osint-marketplace-datastore-nodes (#81)    feature/plugin-scaffold-review-ui (#77)
feat/results-tab-and-dag-buttons (#72)             feat/temporal-phase-0 (#80)
feat/budget-phase2 (#66)                           feat/ach-pir-v2 (#65)
feat/fast-thorough-phase-a/-b/-c (#64 closed/#69/#70)
# genuinely open: feat/signed-callbacks-v2 (#68 — see above, recommend close)
# closed-not-merged (superseded): feat/signed-callbacks (#67), feat/run-budget-phase1 (#53)
```

`gh` one-liner to delete a confirmed-merged branch: `git push origin --delete <branch>`.

---

## Shipped inventory (search here before building a "new" feature)

Reconciled from merged PRs; grep-verified entry points. Prevents duplication.

| Feature | Where (entry point) | PR(s) |
|---------|---------------------|-------|
| Unified phase taxonomy `extract→gather→disconfirm→synthesize` | `app/pipeline/catalogs/constants.py` `LEGAL_PHASE_IDS` | #117 |
| Tactic catalog + Apify Zillow technique | `app/pipeline/catalogs/registries/` | #117 |
| Gather-phase `ask_user` diagnostic / `no_brain_work` invariant | `app/pipeline/strategist.py` | #116 |
| MCP web_crawl/whois node-execute fixes | `app/routers/v3/nodes_api.py`, `app/pipeline/nodes/web_crawl.py`, `mcp_server/server.py` | #118 |
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
