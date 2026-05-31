# Run-Results Fixes, Chat Regressions & Feature Matrix — Design

**Date:** 2026-05-31
**Author:** Claude (with Rinehard Ramos)
**Status:** Approved — implementing
**Trigger run investigated:** `46c08561-0636-4a80-b2eb-9a628d27d4a6` (status `succeeded`, 11 findings, `trigger_type='agent'`)

## Problem

A "v2 run view" migration (`323968a` + `a83f826`) routed all phase-populated runs to
`RunResultsView` and surfaced post-run action buttons as **dead stubs**. Combined with
backend tenancy gaps and a chat-history regression (`d5713e2`, `f27c4ef`), a cluster of
features silently broke. This spec fixes them and adds a maintained **feature matrix** so
regressions are caught systematically.

## Root causes (all confirmed against the running stack)

| # | Symptom | Root cause | Evidence |
|---|---------|------------|----------|
| 1 | All downloads fail | Export query forces `AND pr.org_id = <user_org>`; run's `org_id` is NULL → `NULL = org` false → 404 | logs: `POST /v3/exports/research/46c08561… → 404`; `exports.py:72-80` |
| 2 | Results view empty for some runs | `get_run` attaches trail only when `trigger_type=='agent_is'`; this run is `'agent'` | `pipelines.py:413` |
| 3 | Save as Pipeline / Go Deeper / Analyze do nothing | Stubs dispatch `demo:*` CustomEvents with no listeners | `RunResultsView.tsx:159-198` |
| 4 | (new) Summary | Analyzer node works (`analyzer.py:174`, `/v3/research-trails/analyze`) but no button reaches it | — |
| 5 | Progress stuck ~70% | Bar = `callCount/maxCalls` until `status` terminal; status flips only on a `job.completed` event this run never delivered | `ResearchFlow.tsx:466-474`, `:401` |
| 6 | (new) `run:<id>` not copyable | `DebugBadge` shows truncated, non-interactive text | `RunResultsView.tsx:14-33` |
| 7 | (new) Chat history not retained | Rehydrate guarded by `if (chatMessages.length>0) return`, only re-runs on token change; restored msgs get synthetic IDs/lost types; no session picker | `AgentChat.tsx:309-361` |
| 8 | (new) New Session button missing | Button gated behind `{(messages.length>0 || sessionId) && …}` → hidden on empty pane | `AgentChat.tsx:766-779` |

## Fixes

### A. Backend tenancy (fixes 1 & 2)
- **Export + get_run org scope:** a run-scoped read must match
  `org_id = <user_org> OR (org_id IS NULL AND user_id = <me>)`. Introduce a small helper
  (e.g. `run_visibility_clause(user)`) and use it in `exports.py` and `get_run`. Admins keep
  the empty clause. This retroactively fixes all existing NULL-org runs.
- **get_run trigger_type:** attach the research trail for **both** `'agent'` and `'agent_is'`.
- **Stamp org_id on new agent runs:** ensure every agent-run INSERT writes
  `org_id = user_org_id(user)` so the NULL set stops growing (approved). Existing rows are
  covered by the read-path fallback; no destructive backfill required.

### B. Summary button (fixes 3 + 4)
Replace the broken **Analyze** stub with a working **Summary** button.
- On click: call the existing analyzer endpoint (`POST /v3/research-trails/analyze`), which
  already persists to `research_trails.analysis` (the cache).
- Open a **modal** rendering the analysis. If `analysis` already exists for the run, show it
  instantly with a **Regenerate** action. While generating, show a loading state driven by the
  existing `analysis.started/completed/failed` WS events.
- "Summary" **replaces** "Analyze" (same feature; no duplicate greyed button).

### C. Save as Pipeline (fix 3)
Wire the stub to the proven `handleSavePipeline` flow from `ResultsPanel.tsx:595`
(`POST /v3/pipelines` from the run's nodes/edges, then `navigate(/pipeline/{id})`). Extract the
logic into a shared hook/helper so both views call one implementation.

### D. Go Deeper (fix 3)
Disable (greyed, tooltip "coming soon") — no working backend. Tracked for future wiring to
`onGoDeeper`/`sendMessage`.

### E. Downloads in run view (approved)
Backend fix A makes the existing `DownloadMenu` work (Runs list + result drawer). Additionally
mount a `DownloadMenu` in the run-results action row so it's reachable while viewing a run.

### F. Progress reconciliation (fix 5)
The run status is already polled (`GET /v3/pipelines/runs/{id}`). When the backing run status is
terminal, force `activeFlow.status` terminal so the bar snaps to 100% even if `job.completed`
was missed. Implement as a reconciliation effect in `ResearchFlow` (or its store) keyed on the
polled/streamed terminal status.

### G. Run-id click-to-copy (fix 6)
Make the `DebugBadge` `run:` value a button that copies the **full** runId to the clipboard with
a transient "copied" confirmation. (Honors the standing "run_id must be visible/usable" rule.)

### H. Chat history retention (fix 7)
- Remove/relax the `if (chatMessages.length>0) return` guard so switching sessions reloads
  server history; re-run rehydrate when the selected session changes, not only on token change.
- Preserve message `type`/`role` when restoring (don't collapse to flat user/agent text).
- Add a minimal **session picker** (list past sessions via `listSessions`, load via `getSession`)
  so archived sessions are reachable. Keep scope tight: a dropdown/list in the Agent pane.

### I. New Session button (fix 8)
Always render the New Session entry point (also when the pane is empty). When there's no active
session, it provisions/starts a fresh session rather than only clearing local state.

### J. Feature matrix (new deliverable)
Commit `docs/FEATURE-MATRIX.md`: a table of major features with status
(HEALTHY / MODIFIED / IMPACTED / REMOVED / UNVERIFIED) + evidence (file:line or commit), plus a
"dead stubs" watchlist. This is the regression-catching artifact the user asked for; update it
as part of future feature work. Seed it from the audit findings below.

## Feature matrix (seed)

| Feature | Status | Evidence |
|---|---|---|
| Post-run actions (Go Deeper / Analyze / Save as Pipeline) | REMOVED→fixing | `RunResultsView.tsx:159-198` dead `demo:*` stubs |
| Downloads / exports | IMPACTED→fixing | export 404 on NULL-org runs; not in run view |
| Research/agent run view | IMPACTED→fixing | get_run trail gap + progress stuck |
| Chat history | IMPACTED→fixing | rehydrate guard `AgentChat.tsx:311` |
| New Session button | IMPACTED→fixing | gated `AgentChat.tsx:766` |
| Knowledge Graph | REMOVED (intentional) | `1fd20b4`; orphan client `api/v3.ts:451` |
| Live Processes | REMOVED (intentional) | `1fd20b4` |
| Pipeline builder / Monitoring / Cost dashboard / Admin / API-key vault / Share links / Benchmark reports | HEALTHY | per audit |

## Testing
- **Backend (TDD):** export org-scope returns 200 for a NULL-org run owned by the caller;
  `get_run` attaches trail for `trigger_type='agent'`; agent-run INSERT stamps `org_id`.
- **Frontend:** Save-as-Pipeline calls `createPipeline`; Summary opens modal + uses cached
  analysis with Regenerate; Go Deeper disabled; progress→100% on terminal status; run-id copy;
  chat rehydrate on session switch preserves types; New Session always visible.
- **Real functional run:** use run `46c08561` (11 findings) on the running stack — downloads
  return files, Summary modal renders, bar reaches 100%, history reloads.

## Out of scope
- Re-adding Knowledge Graph / Live Processes (intentionally removed).
- Stripe top-up (documented post-MVP).
- Destructive org_id backfill (read-path fallback covers existing data).

## Implementation order
1. Backend tenancy (A) — unblocks downloads + results.
2. Run-action row: Save-as-Pipeline (C), Summary modal (B), Go Deeper disable (D), Download (E).
3. Progress reconciliation (F) + run-id copy (G).
4. Chat history (H) + New Session (I).
5. Feature matrix doc (J).
Each item: failing test → fix → verify; group into logical PRs.
