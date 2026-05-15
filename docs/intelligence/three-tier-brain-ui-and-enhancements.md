# Three-Tier Brain — UI Evolution & Enhancement Plan

**Status:** Draft. Companion to `three-tier-brain-architecture.md`. Sequenced AFTER MVP (M1–M9) lands and #89 regression passes manually.
**Authors:** Rinehard + Claude (Opus 4.7)
**Related:** `three-tier-brain-architecture.md` §10.3 Post-MVP Phasing (P1–P9); this doc gives the UI/enhancement breakdown of those phases.

---

## 0. Where We Are (MVP Baseline)

After M1–M9 ships, the UI surface is:

| Component | State after MVP |
|---|---|
| `frontend/src/components/preflight/PreflightPanel.tsx` | Lite — 2 modes, 2 dials, strategy auto-selected, wallet line, top-up placeholder |
| `frontend/src/components/results/ResearchFlow.tsx` | Existing — live flow nodes via WebSocket; works for legacy engine, expected to render v2 events through name compatibility |
| `frontend/src/components/results/NodeResultCard.tsx` + Modal | Existing — per-tool card with formatted/input/sources/timing tabs |
| `frontend/src/pages/Research.tsx` | Existing entry point; `?engine=v2` triggers PreflightPanel before the run |
| Wallet | No dedicated page; balance shown only inside PreflightPanel |
| Run history | No v2-specific history view; legacy `History.tsx` page handles both |

**MVP gaps the UI does not yet expose:**
- 3 of 5 dials (speed, resource, depth) are hidden behind defaults
- 4 of 6 modes invisible
- No multi-strategy picker (only 1 strategy migrated)
- No phase-progress indicator (legacy view shows tools, not phases)
- No per-tactician swim lanes (parallel tactician fan-out collapsed to a single flow)
- No candidate-comparison view (still rendered as one result, not a ranked alternatives panel)
- No wallet page (top-up, history, floor, lifetime spend)
- No mid-run extend prompt
- No annotation/feedback per finding (the structural input to RAG grading is missing from the UI)

---

## 1. Design Principles (UI-Specific)

These extend the architecture's principles (§2 of the architecture doc) to the UI layer:

1. **Surface the structure.** If isolation between tacticians is the anti-bias property, the UI must *show* the parallelism — not collapse it. Users learning to trust the system requires seeing how its parts work.
2. **Defaults are the path; advanced is one click away.** Most users will not touch all 5 dials; one-click preset Mode → Run is the happy path. Expert override is collapsed but always reachable.
3. **Show the alternatives, not the answer.** The #89 failure mode is hidden by UIs that surface only the top candidate. The post-MVP results view must present the candidate set with evidence — not just rank #1.
4. **Cost is always visible, never surprising.** RU spend, wallet balance, and projection-after-run are visible at every decision point. The user is never surprised by what a run costs.
5. **Source class is a first-class signal.** Every finding rendered in the UI shows whether it's `live_search` / `prior_research` / `training_knowledge`. Users learn to read source class as a confidence signal.
6. **Replay-ready by default.** Every run's full event stream is persisted; the UI can render any past run as if live without re-executing.

---

## 2. UI Evolution Plan

Each phase maps to an architecture-doc post-MVP phase (P1–P9). UI work is scoped per phase rather than batched into one big rewrite.

### UI-P1 — Full Preflight (companion to arch P1: full dials + modes)

**Goal:** expose all 5 dials and 6 modes; introduce a multi-strategy picker.

**Components:**
- Extend `PreflightPanel.tsx`:
  - Mode picker: 6 modes (`quick_lookup`, `leads_generation`, `data_retrieval`, `market_analysis`, `investigation`, `academic_research`). Default from classifier.
  - Strategy picker: dropdown of catalog strategies that match `applies_to` for the query. Auto-selected with one-click override.
  - 5 dials in advanced panel: speed, capability, resource, depth, hypothesis_count. Each as a segmented control with the level names.
  - Tooltip per dial level: "This dial controls X; current pick costs Y RU more/less than default."
  - Live estimate that recomputes on every dial change (debounced 300ms).
  - **Strategy minimums enforcement** — if dial selection violates `strategy.budget_minimums`, the dial control greys out the disallowed levels with a tooltip explaining why.
- New `frontend/src/components/preflight/EstimateBreakdown.tsx`:
  - Inline drilldown: "9 RU = 12 tool calls × 0.5 + 3 reasoning rounds × 1.0"
  - Token estimate parenthetical for advanced users
- New `frontend/src/components/preflight/WalletLine.tsx`:
  - Balance, held (across all in-flight runs), spendable
  - "Top up" CTA with placeholder modal for MVP, real Stripe flow when P8 lands
  - "Settings" link → wallet page (UI-P4)

**Scope:** 1 week frontend.

### UI-P2 — Live View Evolution (companion to arch P2: full tactic catalog, more strategies)

**Goal:** make the three-tier execution visible. Phases, tacticians, gates, all rendered.

**Components:**
- New `frontend/src/components/results/PhaseProgress.tsx`:
  - Horizontal phase strip at top of the live view: `signal → broaden → red_team → rank_verify`
  - Each phase: pending / running / passed / failed badge
  - Gate result icon between phases (✓ pass, ⚠ ask_user, ✗ terminate)
- New `frontend/src/components/results/TacticianSwimLane.tsx`:
  - When a phase spawns N tacticians, render N side-by-side columns
  - Each column shows: tactic_id, slot_idx, forbidden_candidates (collapsed), live tool calls, emerging candidate name
  - Visual indicator that tacticians can't see each other (subtle "isolated" badge or separator styling)
- Refactor `ResearchFlow.tsx`:
  - Today it renders a single linear graph; v2 needs to render the phase DAG with the active phase highlighted and tactician fan-out as parallel branches
  - Keep a "Compact view" toggle that collapses the v2 layout back to legacy linear for users who prefer it
- New event handlers in `useWebSocket.ts`:
  - `is.phase_start`, `is.phase_complete`, `is.tactician_start`, `is.tactician_complete`, `is.gate_result`
  - These should already be emitted by M9's engine_v2; UI just renders them

**Scope:** 1.5 weeks frontend.

### UI-P3 — Results & Candidate Comparison (companion to arch P5: full ACH matrix)

**Goal:** present alternatives, not just the answer. This is the user-facing #89 fix.

**Components:**
- New `frontend/src/components/results/CandidateComparison.tsx`:
  - When `ranked_candidates.length >= 2`, render a comparison table:
    - Rows: candidates
    - Columns: confidence, primary signal match, supporting signal match, medium match, recency match, evidence sources
  - Top candidate highlighted but NOT visually exclusive — runner-up clearly visible
  - "Why not [candidate X]?" expandable per losing candidate showing disconfirm evidence
- New `frontend/src/components/results/ACHMatrix.tsx` (post-arch-P5):
  - 2D matrix: signal weights × hypothesis scores with ✓/✗/? cells
  - Hover any cell to see the finding that scored it
- New `frontend/src/components/results/SourceClassBadge.tsx`:
  - Inline badge on every finding: 🌐 live / 📚 prior / 🧠 training
  - Used in NodeResultCard, modal, candidate comparison
- Update `NodeResultDetailModal.tsx`:
  - New tab: "Hypothesis" — shows which slot this finding belongs to, what hypothesis the slot was testing, whether it confirmed or disconfirmed
  - Existing "Sources" tab gains the SourceClassBadge

**Scope:** 1.5 weeks frontend + small backend work to emit ACH matrix data in `is.run_complete` event.

### UI-P4 — Wallet & Billing Pages (companion to arch P8: Stripe auto-topup)

**Goal:** dedicated wallet management; transparent run cost history.

**Components:**
- New `frontend/src/pages/Wallet.tsx`:
  - Current balance, held, spendable, floor
  - Lifetime spend (RU + USD equivalent)
  - Top-up section: pick amount, Stripe checkout (P8 wires real payment; pre-P8 placeholder)
  - Auto-topup config (P8): toggle, trigger threshold, top-up amount, monthly cap, payment method
  - Floor RU setting: "Never let my wallet drop below X RU"
  - Transaction history table: timestamp, operation (topup/hold/consume/release/refund), amount, run_id link, idempotency_key
- New `frontend/src/pages/Runs.tsx` (replaces or augments existing `History.tsx`):
  - Run list with per-run RU consumed, mode, strategy, status, distinct candidate count
  - Per-run breakdown: RU per phase, RU per technique
- Backend endpoints (assume M9 already laid groundwork):
  - `GET /v3/wallet` — current state
  - `GET /v3/wallet/transactions?limit=50` — paginated audit log
  - `POST /v3/wallet/topup` — initiate top-up (returns Stripe session URL once P8 lands)
  - `PUT /v3/wallet/floor` — set floor_ru
  - `PUT /v3/wallet/auto_topup` — configure auto-topup rule
  - `GET /v3/runs/{run_id}/cost_breakdown` — per-phase per-technique RU

**Scope:** 1 week frontend + 3 days backend.

### UI-P5 — Mid-Run Controls (companion to arch P9: mid-run extend UX)

**Goal:** user can intervene mid-run on budget threshold or cancel cleanly.

**Components:**
- New `frontend/src/components/results/MidRunExtendDialog.tsx`:
  - Triggered by WebSocket event `is.budget_threshold` (80% consumed) when `depth ∈ {deep, abyss}`
  - Shows: current consumption, remaining hold, options (+5 RU / +20 RU / stop with partial results)
  - "Stop" returns the run gracefully; "+N RU" calls `wallet.extend_hold` and resumes
- New `frontend/src/components/results/CancelRunButton.tsx`:
  - Available at every point during a run
  - Confirmation: "Cancel will commit consumed RU and release the rest. Continue?"
  - Calls a new backend endpoint that signals the strategist to terminate gracefully
- Backend:
  - `is.budget_threshold` event emitted from strategist when threshold hits
  - `POST /v3/runs/{run_id}/cancel` — sets strategist termination flag
  - `POST /v3/runs/{run_id}/extend` — increases hold by amount

**Scope:** 4 days frontend + 3 days backend.

### UI-P6 — Investigation Replay & Export (no architecture-doc phase counterpart — pure UI)

**Goal:** any completed run can be replayed and exported.

**Components:**
- New `frontend/src/components/results/RunReplay.tsx`:
  - Loads run's event stream from `GET /v3/runs/{run_id}/events`
  - Plays back at user-controlled speed (1x, 2x, 4x, instant)
  - Same visual components as live view; just driven by replay timeline instead of WebSocket
  - Pause / scrub through phase boundaries
- New `frontend/src/components/results/ExportRun.tsx`:
  - Export formats: Markdown, PDF, JSON
  - Includes: query, envelope, all phase outputs with findings, ranked candidates, evidence sources, RU breakdown
  - "Share read-only link" — backend stores a signed token; recipient sees the run without auth
- Backend:
  - `GET /v3/runs/{run_id}/events` — paginated event replay
  - `POST /v3/runs/{run_id}/export` — generate export, return signed URL
  - `POST /v3/runs/{run_id}/share` — generate share token

**Scope:** 1 week frontend + 4 days backend.

---

## 3. Enhancement Catalog

Beyond UI evolution, enhancements that add capabilities. Sized as small / medium / large. Each is independently shippable.

### 3.1 Annotation & Feedback (small, high-value)

**What:** per-finding user grading (A/B/C/D) inside `NodeResultDetailModal`. Stores into `findings_grades` table; feeds RAG quality (verified findings get boosted retrieval weight, low-graded ones suppressed).

**Why:** closes the loop between user judgment and system improvement. Today the user can grade an entire run but not individual findings. Per-finding grades give RAG much finer-grained training signal.

**Architecture impact:** RAG retrieval ranks by graded confidence, not just similarity. Reinforces design doc §11 decision "user-graded A research is authoritative."

**Effort:** ~3 days backend + 2 days frontend. Smallest high-impact change.

### 3.2 Saved Query Templates & Per-User Defaults (small)

**What:** save a query + envelope + strategy as a named template. Saved templates appear in the preflight as one-click run-this-again.

**Why:** users running similar investigations weekly (compliance checks, lead refreshes) shouldn't re-pick dials every time. Templates encode their workflow.

**Effort:** 3 days. Mostly storage + a UI dropdown in preflight.

### 3.3 Mode Recommendation Engine (medium)

**What:** classifier output suggests not just strategy but mode based on past runs of similar queries. Learns from user-graded outcomes.

**Why:** users often pick the wrong mode for their query (`quick_lookup` on a forensic investigation, or `investigation` on a one-off lookup). Recommender lowers friction.

**Architecture impact:** new `mode_recommendation` table; classifier extended to consult it.

**Effort:** 1 week. Bigger lift in calibration data collection than in code.

### 3.4 Cost Forecasting & Budget Alerts (small)

**What:** in the wallet page, show monthly burn rate, projected end-of-month spend. Email/push alert when wallet drops below user-set threshold.

**Why:** users who do hundreds of runs/month need visibility before they hit the floor. Forecasting prevents surprise top-ups.

**Effort:** 2 days backend (rolling average), 2 days frontend (chart).

### 3.5 A/B Compare Runs (medium)

**What:** run the same query through two different mode+dial combinations side-by-side. Live view shows two columns; results page shows differences.

**Why:** users will want to know if a more expensive mode actually buys them better answers. A/B compare gives them empirical data on their own queries.

**Architecture impact:** the strategist accepts a `compare_with_run_id` param; backend ensures both runs are pinned to the same query string for fair comparison.

**Effort:** 1 week. Most of it is rendering the dual-view; backend changes are small.

### 3.6 Investigation Graph Visualization (medium)

**What:** full DAG view of a completed run: phases → tacticians → specialists → findings → sources. Nodes clickable to see contents. Edges show information flow.

**Why:** complex investigations are hard to follow as a linear card list. A DAG is the natural shape and exposes which tactician contributed which findings.

**Effort:** 1 week frontend (D3 or react-flow). Backend already emits enough to drive this.

### 3.7 Mid-Run Hypothesis Override (large, post-MVP-only)

**What:** during a run, a user can add a forbidden candidate or suggest an additional hypothesis. The strategist replans the next phase to incorporate.

**Why:** sometimes the user has context the brain doesn't ("I know it's not Zhao Lusi — focus on K-pop"). Today they cancel and restart; with override they'd guide.

**Architecture impact:** strategist must support partial replan (architecture doc P3) before this is buildable. Strict post-MVP-P3 dependency.

**Effort:** 2 weeks combined backend + frontend; depends on P3 being live.

### 3.8 Team / Organization Wallets (large, called out of scope in architecture §13)

**What:** organization-level wallet that multiple users draw from; per-user spend caps; admin reporting.

**Why:** enterprise customers will not run on per-user wallets.

**Effort:** ~3 weeks. Touches wallet schema, auth, billing, and admin UX.

### 3.9 Run Sharing & Public Read-Only Links (small)

**What:** any completed run can be shared via a signed token URL. Recipient sees the run output without account.

**Why:** investigators share results with stakeholders who don't have system accounts. Today this requires manual export; with sharing it's a one-click link.

**Effort:** 3 days. Mostly auth-layer signed token + read-only render mode.

### 3.10 Strategy Authoring UI (large, architecture §13 out-of-scope)

**What:** power users / admins author new strategies via a form-based UI rather than editing Python files.

**Why:** opens the system to non-engineers (analysts, ops). Each new strategy unblocks new query classes.

**Architecture impact:** catalog system already supports it (closed-set selection at runtime, just need form-based editing of the catalog entries).

**Effort:** ~3 weeks. Form UI + validation + audit log + admin permission gating.

---

## 4. Sequencing Recommendation

Order optimized for user-visible value × engineering effort × structural dependency:

| Phase | Pack | What | Effort |
|---|---|---|---|
| MVP | M1–M9 | Architectural foundation | (in progress) |
| UI-P1 + 3.4 | preflight-1 | Full preflight + cost forecasting | 1.5 weeks |
| 3.1 | annotation | Per-finding grading (high-value, small) | 1 week |
| UI-P2 | live-1 | Phase progress + tactician swim lanes | 1.5 weeks |
| UI-P4 | wallet-1 | Wallet page + run cost history | 1.5 weeks |
| UI-P3 | results-1 | Candidate comparison + source class badges | 1.5 weeks |
| 3.9 | sharing | Public read-only run links | 3 days |
| 3.2 | templates | Saved query templates | 3 days |
| UI-P6 | replay | Run replay + export | 1.5 weeks |
| 3.5 | ab-compare | A/B run compare | 1 week |
| 3.6 | dag-viz | Investigation graph viz | 1 week |
| UI-P5 | mid-run | Mid-run controls (after arch P9) | 1 week |
| 3.3 | recommender | Mode recommendation engine | 1 week |
| 3.7 | override | Mid-run hypothesis override (after arch P3) | 2 weeks |
| 3.10 | strategy-ui | Strategy authoring UI (after arch P6 stabilizes) | 3 weeks |
| 3.8 | org-wallet | Team/organization wallets | 3 weeks |

**Critical UX gate**: UI-P3 (candidate comparison) is the most important UI work — it's the user-facing #89 fix. Without it, the structural anti-tunneling is invisible to users because they still see only "the answer". Prioritize ahead of nice-to-haves.

---

## 5. Open Questions

1. **Mobile parity.** The full preflight panel + swim lane view is desktop-heavy. Do we target mobile parity for v1 or accept "desktop-first, mobile read-only"?
2. **Dark mode coherence.** Existing UI is dark-themed; new components must match. Confirm no light-mode targets are coming.
3. **Replay storage.** Full event stream per run is potentially MBs. Retain forever, or expire after N days unless the run is favorited/exported?
4. **Per-finding grading granularity.** Admiralty Code (A1–F6) is more nuanced than A/B/C/D. Worth the UX complexity?
5. **Mode recommendation cold-start.** With no calibration data, the recommender will be wrong often. Ship behind a feature flag until N runs?
6. **Strategy picker discoverability.** When 28+ strategies exist, how does the user find the right one if classifier picks wrong? Search? Categories?

---

## 6. Out of Scope (for this doc — pure UI/enhancement)

These belong to the architecture doc, not here:
- New strategies migrated to phase-DAG format (arch P2)
- Replan/recurse logic in strategist (arch P3)
- Forbidden_candidates allocation (arch P4)
- Full ACH matrix fusion at backend (arch P5, but UI rendering of it is UI-P3)
- Dual-run parity framework (arch P7)
- Auto-topup payment integration (arch P8, but the UI rule is UI-P4)
