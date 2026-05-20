# Modes Architecture, 10/10 Gap Closure, and Groundbreaking Feature Proposals

Companion to `persona-simulations.md`. Translates the persona findings into a concrete design: a generalist substrate with persona-specific **Modes**, a roadmap of cross-cutting improvements that raise every persona to 10/10, a v2 design for feature **B**, and two net-new groundbreaking features built on the loop substrate.

---

## 1. Modes architecture (concrete spec)

**Principle.** One brain, one loop, one cross-run memory. Persona-specific behavior is configuration, not code. A `Mode` is a YAML/JSON document the loop reads at run-init.

### 1.1 Mode schema

```yaml
id: kyc_edd
label: "KYC / Enhanced Due Diligence"
version: 1
description: "BSP-compliant evidence standards for PEP/EDD reviews"

# Loop framing
prompt_persona: |
  You are a senior KYC analyst producing BSP-grade evidence.
  Every claim must cite a registry or two independent sources.
  Treat absence of evidence as a finding, not silence.

# Phase tuning (overrides defaults)
phases:
  explore: { max_turns: 3, tool_call_budget: 6 }
  test:    { max_turns: 4, tool_call_budget: 6 }
  synthesize: { max_turns: 1, tool_call_budget: 2 }

# Tool defaults (subset of MCP_TOOL_CATEGORIES)
preferred_tool_categories: [lookup, knowledge, score]
tool_weights:
  run_sec_lookup: 1.5
  run_world_check: 1.5
  run_news_search: 0.8
  run_social_search: 0.2

# Evidence rules
source_class_weights:
  registry: 1.0
  news: 0.6
  social: 0.3
  inferred: 0.1
require_independent_corroboration: true   # ≥2 sources for "supported"
confidence_threshold_to_claim: 0.9
treat_absence_as_finding: true

# Hypothesis priors (skip cold-start)
hypothesis_seeds:
  - "Subject is a nominee structure for an offshore principal"
  - "Beneficial owner has PEP exposure"
  - "Cross-border flows are loan-back or layering pattern"

# Termination
termination:
  require_contradiction_resolution: true
  require_all_pir_satisfied: true
  max_turns: 8

# Output shape
output_template: templates/edd_memo.md.j2
export_formats: [pdf, docx, markdown]
audit_trail: required    # every claim links to source + retrieval timestamp

# Open-question framing
open_question_framing: "regulator_visible"   # vs "internal" / "strategic"
```

### 1.2 Launch Mode catalogue

| Mode | Persona | Key knobs |
|---|---|---|
| `general` | Default | Balanced defaults; today's behavior |
| `kyc_edd` | KYC analyst | Registry-weighted, contradiction-resolved, audit-grade export |
| `competitive_intel` | Marketing mgr/analyst | News+social weighted, time-windowed, side-by-side comparison |
| `lead_gen` | Leads engineer | Bulk-list output, dedup-against-CRM, per-lead cost cap |
| `academic_lit_review` | Researcher | Citation-graph weighted, peer-reviewed source class privileged |
| `bizdev_partner_scan` | GTM / BD | Company-centric, deal-shape oriented, signal-density scoring |

Power users can author their own Modes; system-shipped Modes are versioned.

### 1.3 Where Modes plug in

- **Loop init** (`init_working_memory` activity) — reads Mode, seeds `WorkingMemory.hypotheses` from `hypothesis_seeds`, sets phase budgets, threshold fields.
- **Turn prompt builder** (`is_prompt_turn.py`) — injects `prompt_persona`, biases tool selection via `tool_weights`, frames open-question section per `open_question_framing`.
- **Workflow phase machine** (`is_loop_run.py`) — reads termination block; e.g. `require_contradiction_resolution` blocks transition to synthesize if open contradictions remain.
- **Synthesis** (final turn) — renders against `output_template`.
- **Run dispatcher** (`app/routers/v3/agent.py`) — accepts `mode: kyc_edd` on POST; persists with run.

### 1.4 Mode authoring as a first-class workflow

A Mode is editable in-app by the user. The shape that the persona sims actually want isn't 5 hard-coded modes — it's *"this saved query/segment/watchlist *is* a Mode"*. So Modes and saved-templates collapse into one primitive:

```
A Mode = (prompt persona) + (tool/source biases) + (output template) + (optional seed hypotheses)
A Template = a Mode pinned to a specific question shape
A Watchlist = a Template + a cron + a diff-since-last alert
A Segment = a Template that outputs a list, not a memo
```

Same primitive, four UX presentations.

### 1.5 Migration plan

1. Extract today's OSINT-isms out of the brain prompt into `modes/general.yaml`. Loop becomes domain-neutral.
2. Ship `kyc_edd`, `competitive_intel`, `lead_gen` as the first three; the persona sims already have the knob values.
3. Add `mode` param to run-create; default `general` for back-compat.
4. UI: Mode picker on Research page. Mode badge in Run cards and drawer.
5. Open Mode authoring to users in v2.

---

## 2. Cross-cutting 10/10 gap closure

The persona sims surfaced 11 gaps. Modes architecture closes some; the rest are independent and each lifts ≥2 personas.

### 2.1 Closed by Modes

- **Saved templates / segments / watchlists** — Modes-as-primitive collapses this.
- **Audit / brief export templates** — `output_template` per Mode.
- **Confidence thresholds + source-class weights** — Mode config.
- **Open-questions framing** — Mode-driven.

### 2.2 Independent improvements (sequenced)

| # | Improvement | Personas lifted | Effort | Priority |
|---|---|---|---|---|
| 1 | **Push/export surface** — Slack/Notion/docx/CSV/webhook | Mgr, Analyst, GTM, Leads | M | P0 |
| 2 | **Structured confidence + source_class fields** on every finding (not just prose) | All 5 | M | P0 |
| 3 | **Negative-evidence as first-class fact** ("checked X, not found") | All 5 | S | P0 |
| 4 | **API/MCP parity with UI** for the new absorption endpoints | GTM, Leads (unlocks fully); Analyst (indirect) | S | P0 |
| 5 | **$-denominated cost + per-unit benchmarks** on G | Mgr, GTM, Leads | S | P1 |
| 6 | **Side-by-side multi-entity comparison view** | Mgr, Analyst, BD | M | P1 |
| 7 | **Annotation tags + propagation into B** | KYC, Analyst | S | P1 |
| 8 | **Retrieval-score transparency on E** | KYC | XS | P1 |
| 9 | **Open-questions aging + dismissal** | All 5 | XS | P2 |
| 10 | **Quote extraction with attribution** (not just findings) | Analyst, KYC | M | P2 |
| 11 | **Citation density indicator on headline** | Analyst, KYC | XS | P2 |

### 2.3 Why P0 picks are P0

- (1) **Push/export** was unprompted in 4/5 sims. Without it, the tool fights for attention against where users already work. With it, the tool *feeds* their existing surface — much lower adoption friction.
- (2) **Structured confidence/source_class** is the trust gate. Without it, every other feature has a "but can I trust it?" caveat. With it, downstream consumers (other LLMs, templates, exports) can filter and weight.
- (3) **Negative evidence** is a quiet but pervasive gap. Today, "we checked SEC and found no Reyes" leaves no trace. Tomorrow, that's a Fact with `verified_absent: true`. KYC needs it for regulators; marketing needs it to avoid re-running dead leads; leads-eng needs it to not re-enrich rejected accounts.
- (4) **API parity** is the difference between "valuable to ICs who use the UI" and "valuable to engineering teams who orchestrate." 1.5× the TAM at near-zero marginal effort because absorption endpoints already exist; need to ensure they're equally accessible via MCP.

---

## 3. Feature B v2 — Personal Knowledge Graph (PKG)

Today's B aggregates *prose findings* across runs for a queried entity and groups facts whose first 40 chars match to detect contradictions. This is a heuristic on the wrong substrate. v2 promotes facts to atomic claims and makes the graph the substrate.

### 3.1 Claim schema

```python
class Claim(BaseModel):
    id: UUID
    subject: str          # canonical entity id (resolved, not raw string)
    predicate: str        # controlled vocabulary per Mode (e.g. 'director_of', 'pep_status', 'revenue_band')
    object: Any           # entity id, scalar, enum, or temporal range
    
    # Provenance
    source_url: str | None
    source_tool: str
    source_class: Literal['registry','news','social','inferred','user_attested','negative']
    cited_text: str | None        # exact span from source
    
    # Confidence & validity
    confidence: float             # [0,1]
    
    # Temporal validity (critical)
    valid_from: date | None       # when claim became true
    valid_to: date | None         # when claim stopped being true (None = still valid)
    observed_at: datetime         # when we recorded it
    
    # Lineage
    run_id: UUID
    turn_n: int
    user_id: UUID
    
    # Verification
    corroborated_by: list[UUID] = []   # ids of other Claims agreeing
    contradicted_by: list[UUID] = []   # ids of other Claims disagreeing
    superseded_by: UUID | None = None  # later claim that replaces this one
```

### 3.2 What this unlocks

| Capability | Before (v1) | After (v2 PKG) |
|---|---|---|
| Contradiction detection | First-40-char string match | Same (subject, predicate, valid_at) with disagreeing object |
| Time-travel queries | Impossible | `claims_about(X, as_of=2023-06-01)` |
| Supersession | Impossible | Newer claim with later `valid_from` auto-supersedes |
| Cross-entity inference | Impossible | "Find all subjects where predicate=director_of points to entity Y" |
| Audit export | Prose dump | Structured claim list with full provenance |
| Negative evidence | Lost | `source_class: negative` is a first-class claim |
| Confidence aggregation | Per-finding | Per-(subject, predicate) — Bayesian over claims |

### 3.3 Storage

- New table `kg_claims` (Postgres) — atomic claims with the schema above.
- Embed claims into Qdrant (`text` = "{subject} {predicate} {object}") so `fused_retrieve()` returns claims, not just finding chunks.
- Existing `kg_contradictions` table becomes a materialized view over `kg_claims`.

### 3.4 Loop integration

The synthesize phase already emits findings. Modify the turn output parser to *also* emit structured claims when the brain's output schema allows. The brain doesn't need to know about PKG — the parser converts findings → claims using Mode-specific predicate vocabularies. Older runs continue to surface only as prose findings (back-compat).

### 3.5 UX changes

The B widget on Dashboard becomes a graph-aware entity view:

```
What I know about "Maridel Holdings Inc."           [as of: 2026-05-20 ▾] [ⓘ 14 claims, 2 contradictions, 1 superseded]

  ✅ director_of           Reyes               registry      2022-01 → present     0.95   3 sources
  ✅ director_of           Cruz                registry      2023-08 → present     0.92   2 sources
  ⚠  registration_date    2011-04-15          registry      observed 2024         0.80
  ⚠  registration_date    2011-06-15          news          observed 2025         0.60   ← contradicts above
  ✅ pep_status            none                world_check   observed 2026-05      0.90
  ⊘  pep_status_sg        UNKNOWN             —             checked, not found    n/a    (negative)

[+ open contradiction]   [+ time-travel: 2024-01]   [+ export structured]
```

### 3.6 Effort + sequencing

- M1 — Add `kg_claims` table + claim-extraction parser in turn output. Dual-write: prose finding stays + claim emitted. ~3 days.
- M2 — Rewire B endpoint to query claims instead of prose-group. ~2 days.
- M3 — Time-travel UI + supersession ledger. ~3 days.
- M4 — Negative-evidence integration (closes gap #3 above for free). ~1 day.

Total ~9 days end-to-end, partially overlapping with structured-confidence work (gap #2).

---

## 4. Two groundbreaking features

Criteria: hard to copy without the loop substrate, broadly valued across personas, plausibly category-defining. Two candidates picked from a longer shortlist (also-rans listed at end).

### 4.1 Feature X — **Adversarial Audit Co-Agent**

**What.** After the brain synthesizes, a structurally separate "red-team" run launches with the inverse goal: *find evidence that the synthesis is wrong*. It searches actively for refuting sources, alternative explanations, deception signals, and source-class downgrades. Output is appended to the run as a "Challenge Report" — passes, partial, or failed.

**Why this is groundbreaking.** Every LLM tool today does "self-critique" by asking the same model to second-guess in the same context. That's theater — the model has anchored on its own conclusion. A *separate run* with a *separate budget*, an *adversarial prompt*, and *different tool defaults* genuinely attacks the conclusion. We can do this because we own the loop and have a budget engine. Competitors with single-shot brains physically can't.

**Concrete shape.**

```
1. Brain finishes synthesize phase → emits final claims with confidence.
2. Workflow launches IsAdversarialAuditWorkflow with:
     - frozen claim list from the original run
     - prompt: "For each claim, find the strongest refutation. Apply ACH."
     - budget: 20% of original run's RU
     - tool defaults: news + social weighted (vs registry); recency boosted
3. Auditor produces:
     - per-claim verdict: confirmed | weakened | refuted
     - new contradictions surfaced
     - source-class downgrades suggested
     - alternative hypotheses considered but rejected by primary run
4. Original run's claims update: confidence adjusted by audit verdict.
5. Drawer gets a "🛡 Audit" tab with the challenge report.
```

**Persona value.**

- **KYC analyst** — closes the regulator gap. "Our tool didn't just conclude X; it actively tried to refute X and failed." Audit-defensible.
- **Marketing manager** — protects against agency-favored narratives. Counterfactual on competitor positioning.
- **Marketing analyst** — covers the analyst's back when shipping briefs.
- **GTM / Leads engineer** — confidence calibration for downstream scoring models.

**Risks + mitigations.**
- *Cost.* 20% RU cap + Mode-configurable. KYC mode opt-in by default; lead_gen mode off.
- *False confidence drop.* Audit verdicts include their *own* confidence; the drawer shows both sides.
- *Loop divergence.* Audit run runs against frozen claims; doesn't compete with primary.

**Effort.** ~5–7 days. Reuses loop substrate, budget engine, working memory, MCP catalog. Net-new is the adversarial prompt set, the per-claim verdict schema, and the drawer tab.

---

### 4.2 Feature Y — **Living Subjects (Active Watch + Diff Alerts)**

**What.** Promote a queried subject (entity, segment, or hypothesis) into a `LivingSubject`. The system re-runs research on a cron, diffs against the prior canonical state, and pushes *only the deltas* to the user's channel of choice (Slack, email, webhook). Combines C (diff), F (continue thread), H (open questions), the cron substrate, and the push/export work above into one coherent loop.

**Why this is groundbreaking.** Existing tools are pull-based: you go to them and ask. Living Subjects flips the orientation: the tool watches *for* you and tells you *when something changes*. The substrate makes this cheap — run, compare to last claim graph, push diffs. WorldCheck offers "ongoing monitoring" but at enterprise pricing with shallow signals; we offer it with the same depth as a manual run plus auto-diff.

**Concrete shape.**

```yaml
living_subject:
  id: ls_001
  name: "Maridel Holdings - ongoing monitor"
  query: "Beneficial ownership and adverse media on Maridel Holdings Inc."
  mode: kyc_edd
  cadence: weekly                         # or cron expression
  diff_strategy: claim_graph              # vs finding_diff
  alert_when:
    - new_contradiction: true
    - new_pep_hit: true
    - confidence_change: { min_delta: 0.2 }
    - new_supporting_source: { source_class: registry }
  push:
    - channel: slack
      destination: "#compliance-alerts"
      template: short_summary
    - channel: email
      destination: "kyc-team@bank.example"
      template: full_diff
  budget_per_run: 50 RU
  active: true
```

**Persona value.**

- **KYC analyst** — turn EDD memos into living dossiers. Regulator update on Reyes? Push to channel within hours.
- **Marketing manager** — competitive intel becomes ambient. "Competitor X changed pricing" lands in Slack without a query.
- **Marketing analyst** — eliminates the Monday "what changed last week" pull.
- **GTM / Leads engineer** — turns Living Subjects into pipeline triggers via webhook.
- **BD / partner scan** — track 50 potential partners' deal activity passively.

**Why this is bigger than it looks.** Living Subjects + PKG (Feature B v2) compose:

- A LivingSubject's diff is a *claim-level* diff, not a prose diff.
- Each cycle's claims feed PKG → cumulative entity memory grows continuously.
- Contradictions emerge between cycles automatically; pushed as alerts.
- The Adversarial Audit (Feature X) runs on each cycle's synthesis → trust stays calibrated.

The three features form a flywheel: PKG accumulates, Audit calibrates, Living Subjects push the deltas.

**Risks + mitigations.**
- *Cost runaway.* Per-LS budget caps + per-user monthly RU ceiling. Disable LS automatically on consecutive zero-delta runs (entity went quiet).
- *Alert fatigue.* `alert_when` rules enforce material-only pushes; default templates are diff-only.
- *Cron sprawl.* Reuse existing Temporal infrastructure; LS = scheduled workflow + diff post-processor.

**Effort.** ~7–10 days. Depends on push/export surface (gap #1) being in place. PKG (B v2) sharpens but doesn't block the MVP — first version can diff against last run's findings prose, then upgrade to claim graph once PKG ships.

---

### 4.3 Also-rans (briefly)

- **Synthesis-as-conversation.** Chat against the finished run's evidence ledger. Valuable but lower differentiation; many tools moving here.
- **Causal/reasoning ledger.** Show *why* the brain concluded what. Worth shipping eventually; subset of audit + claim graph.
- **Parallel multi-subject runs with cross-diff.** Powerful for competitive intel but partly addressed by side-by-side comparison (gap #6).
- **Provenance-preserving export.** Important but it's a feature of *export*, not a category-shifter. Captured under push/export gap.

---

## 5. Sequencing — what to build first

The doc above is roughly 6–8 weeks of work compressed into one document. Honest dependency analysis:

```
┌─────────────────────────────────────────────────────────────────┐
│  Week 1–2:  Modes architecture + ship 3 launch Modes            │
│             ├─ Closes 4 gaps; foundational for everything below │
│             └─ Unblocks proper analyst/marketing/leads scoring  │
├─────────────────────────────────────────────────────────────────┤
│  Week 2–3:  P0 gaps in parallel                                 │
│             ├─ Push/export surface (gap #1)                     │
│             ├─ Structured confidence + source_class (gap #2)    │
│             ├─ Negative-evidence (gap #3)                       │
│             └─ API parity for absorption endpoints (gap #4)     │
├─────────────────────────────────────────────────────────────────┤
│  Week 4–5:  Feature B v2 — Personal Knowledge Graph             │
│             └─ Builds on structured confidence + source_class   │
├─────────────────────────────────────────────────────────────────┤
│  Week 5–6:  Feature X — Adversarial Audit Co-Agent              │
│             └─ Builds on PKG (per-claim verdicts)               │
├─────────────────────────────────────────────────────────────────┤
│  Week 6–8:  Feature Y — Living Subjects                         │
│             └─ Builds on Modes + push/export + PKG diffing      │
└─────────────────────────────────────────────────────────────────┘
```

P1/P2 gap items (side-by-side, annotation tags, retrieval-score, etc.) interleave wherever an engineer is unblocked between major work items.

## 6. Open questions for the owner

1. Are launch Modes set to `kyc_edd / competitive_intel / lead_gen` — or should we add `academic_lit_review` from day one given the user's intelligence-research bias?
2. Push/export channels: Slack + Notion + webhook first, or pick one based on the user's actual surface?
3. Adversarial Audit: opt-in per Mode, or always-on with per-Mode budget?
4. Living Subjects pricing/quota model: per-user RU ceiling, per-LS cap, or both?
