# Feature Matrix

A living regression-catching artifact. For each major user-facing feature, record its current
health and the evidence. **Update this table as part of any feature/fix PR** — when you touch a
feature, set its status and cite a `file:line` or commit. Status legend:

- **HEALTHY** — works as intended, verified.
- **MODIFIED** — intentionally changed (note why).
- **IMPACTED** — degraded/partially broken by an unrelated change (a regression).
- **REMOVED** — deliberately deleted (note the commit).
- **UNVERIFIED** — not checked this pass; do not assume healthy.

Last full audit: **2026-05-31** (branch `fix/run-results-and-chat-regressions`). The audit was
prompted by a cluster of regressions from the "v2 run view" migration (`323968a`, `a83f826`).

| Feature | Status | Evidence / Notes |
|---|---|---|
| Research/agent run view (v2) | HEALTHY (fixed) | action row rewired; `RunResultsView.tsx` |
| Post-run: Save as Pipeline | HEALTHY (fixed) | real `createPipeline` + navigate; was dead `demo:savePipeline` stub |
| Post-run: Summary (was Analyze) | HEALTHY (fixed) | `SummaryModal.tsx` — analyzer-backed, cached, modal; replaces dead `demo:analyze` stub |
| Post-run: Go Deeper | DISABLED (intentional) | no backend yet; greyed in `RunResultsView.tsx` |
| Downloads / exports | HEALTHY (fixed) | tenancy 404 fixed (`run_visibility_clause`); `DownloadMenu` added to run view |
| Run results for `agent` runs | HEALTHY (fixed) | `get_run` now attaches trail for `agent` + `agent_is` (`pipelines.py`) |
| Progress bar (run view) | HEALTHY (fixed) | reconciles terminal status from run record; `ResearchFlow.tsx` |
| Run id visibility/copy | HEALTHY (fixed) | `DebugBadge` click-to-copy; honors [run_id-in-UI rule] |
| Chat history retention | HEALTHY (fixed) | `@platform/chat-ui` `useChatHistory` (always re-hydrates on switch) + `SessionPicker` in AgentChat; reusable library |
| New Session button | HEALTHY (fixed) | `@platform/chat-ui` `NewSessionButton` — always visible; replaces gated button |
| Pipeline builder | HEALTHY | `PipelineBuilder.tsx` + passing test |
| Monitoring dashboard | HEALTHY | vendored `@platform/monitoring-ui`; admin-gated |
| Cost / Usage dashboard | HEALTHY | `PerformanceDashboardPage` (#170) |
| Admin / user management | HEALTHY | paginated (#171) |
| API-key vault | HEALTHY | scoped encrypted vault; missing-key gates (#150/#153/#154) |
| Share links | HEALTHY | `/share/:token`; `ShareDialog` wired in run view |
| Benchmark reports | HEALTHY | `BenchmarkReportsPage`; responsive fix (c0d5c37) |
| Knowledge Graph | REMOVED (intentional) | `1fd20b4`; orphan client `api/v3.ts:451` |
| Live Processes | REMOVED (intentional) | `1fd20b4` |
| Wallet top-up | MODIFIED (MVP) | "Stripe checkout coming soon" `TopupSection.tsx` — post-MVP |

## Dead-stub watchlist

Stubs that LOOK functional but do nothing. Grep for these patterns when auditing:

- `dispatchEvent(new CustomEvent('demo:...'))` with no `addEventListener` — the v2 run-view
  regression. **All three (`demo:goDeeper/analyze/savePipeline`) are now removed.**
- Empty handlers `() => {}` / handlers that only `console.log`.
- "coming soon" / "not implemented" labels — confirm they're intentional MVP gaps, not silent breakage.

## Process

This matrix is the answer to "did the build regress anything?" Before merging a build that touches
shared UI (run view, chat, layout) or tenancy/read paths, re-check the affected rows and update
status + evidence here. Keep it honest: mark UNVERIFIED rather than guessing.
