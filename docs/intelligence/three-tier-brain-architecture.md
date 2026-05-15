# Three-Tier Brain Architecture with Catalog-Driven Execution

**Status:** Draft outline — captures architectural commentary from design session 2026-05-15. Not yet implementation-ready; sections marked `[TBD]` need fleshing out before any ticket is filed.

**Authors:** Rinehard + Claude (Opus 4.7, this session)
**Related:** Issue #89 (IS brain tunnels to RAG-retrieved candidate). This design supersedes the prompt-only fix landed for #89, which remains as defense-in-depth.
**Supersedes:** Nothing; greenfield.

---

## 0. Executive Summary

Today the IS brain conflates three jobs into one Claude Code subprocess: choosing a strategy, planning tactics for each phase of that strategy, and executing the tool calls. When prior research is injected into context, the same biased brain reads it, anchors on it, and treats it as the answer (#89, "Zhao Lusi tunnel"). Prompt-as-guardrail is soft: the existing prompt already says "≥3 distinct hypotheses, ≥1 live search per H, anti-anchor rule" and the brain ignored all of it.

This design replaces that monolith with a three-tier architecture:

1. **Strategist** ("general") — picks a strategy from a catalog, decomposes it into a phase DAG, holds the campaign view, replans between phases. Never executes a tool call.
2. **Tactician** ("team lead") — one per parallel hypothesis per phase, scoped to its own unit of work, picks tactics from a catalog, emits tasks. Cannot see peer tacticians.
3. **Specialist** — picks a technique from a catalog, executes one tool call against a typed task spec. Cannot see hypotheses, peer tasks, or the query as a whole.

Selection at every layer is **catalog-driven** (closed-set classification, not free generation) and **budget-constrained** (a typed envelope prunes catalog options before the role sees them). The user elects strategy + budget at **preflight**, not the system. Budget is denominated in **Research Units (RU)** — a synthetic wallet currency ($1 = 10 RU) that's pre-allocated against the user's wallet at run start so concurrent runs cannot double-spend.

The structural anti-bias property: branches that confirm different facets of the same candidate are *one tactician with multiple tasks*, not multiple hypotheses. The Zhao Lusi failure mode becomes physically impossible because Tactician H2 has no visibility into H1's findings — no signal to anchor on.

**Delivery approach:** MVP-first (see §10.1). Ship a minimum slice that proves the anti-tunneling property on #89 — 1 strategy, 2 tactics, 5 typed techniques, 2 dials, 2 modes, no replan/recurse, no parity gate. Flesh out catalog breadth, dial expressiveness, and replan logic after the structural property is validated end-to-end.

---

## 1. Problem Statement

### 1.1 Symptom

Run `873e093f-5af6-469c-a0d5-8f972e6473b5` (#89): query "asian girl with mole in cheek bone and has an advertisement where she uses a curling iron" converged on Zhao Lusi as the answer without exploring alternatives. All 9 findings named Zhao Lusi. All 4 branches sourced from `prior_research` (RAG) or `training_knowledge`. No live search enumerated other candidates.

### 1.2 Root Cause

- **Bias has nowhere to be filtered.** The brain reads the query, the RAG hit, the strategy prose, and decides — all in one reasoning context. Bias toward RAG-confirmed candidates propagates from interpretation to planning to execution to ranking with no isolation between stages.
- **Prompt rules are advisory.** `app/is_prompt.py` and `app/pipeline/strategies/media_identification.py` already encode the rules (≥3 hypotheses, hypothesis-first BROADEN, RED TEAM disconfirm, distinct identities). They were violated. Soft enforcement requires the same agent that's biased to police itself.
- **Branches collapse to facets, not identities.** `subject_background of X`, `physical_signal_match of X`, `brand_first of X` were counted as three branches, but they're three confirmations of one hypothesis. The system has no structural way to distinguish "distinct hypothesis" from "additional confirmation of the same hypothesis".

### 1.3 Why the Prompt-Only Fix Isn't Enough

The PR landed for #89 strengthens prompt rules: prior research is reframed as H_PRIOR (one hypothesis among many) for identification queries when unverified, and authoritative baseline when user-graded A. This raises the floor but doesn't change the failure mode — the same brain still reads, still anchors, still decides. Defense in depth keeps the prompt edits; this design adds the structural enforcement layer that prompts alone can't provide.

---

## 2. Design Principles

1. **Strategy is the design; the brain fills in details.** Strategies are declarative phase DAGs with typed unit-of-work contracts. Brains don't get to bend the plan toward a preferred answer.
2. **Role isolation by visibility.** No tactician sees a peer tactician's findings. No specialist sees the query, the hypotheses, or its peer tasks. Bias cannot anchor on what it cannot see.
3. **Closed-set selection at every layer.** Strategists pick from a strategy catalog; tacticians from a tactic catalog; specialists from a technique catalog. No layer invents new options at runtime. Catalogs are auditable and version-controlled.
4. **Budget is a typed envelope, not advice.** Cost-class metadata on tactics and techniques drives runtime pruning. The tactician physically cannot pick an expensive tactic if budget excludes it.
5. **Cost in research units, fees downstream.** Budget is measured in stable RU (research units), mapped to model fees by a separate billing layer. RU stays meaningful across model-pricing changes.
6. **User agency at preflight, autonomy during run.** The user picks strategy, mode, and budget envelope at preflight. The system runs autonomously inside that envelope, only escalating on budget-exhaustion or user-disambiguation gates.
7. **Defense in depth.** Prompt-level rules stay (they describe the intent); execution-level isolation enforces. If one layer fails, the other catches.

---

## 3. Architecture Overview

```
Query
  │
  ▼
[Classifier]  →  suggested mode + strategy candidates + cost estimates
  │
  ▼
[Preflight UI]  ← user picks Mode (default) or overrides dials + strategy
  │
  ▼
BudgetEnvelope (frozen for run)
  │
  ▼
┌──────────────────── Strategist ─────────────────────┐
│  Picks strategy from catalog (user-elected)         │
│  Emits phase DAG: P1 → P2 → P3 → P4                 │
│  Owns gates and replan authority                    │
│  Sees: query, classifier output, phase aggregates   │
│  Does NOT see: raw tool results, peer-phase details │
└─────────────────────────────────────────────────────┘
  │
  ▼ (per phase, fan out by hypothesis_count dial)
┌──────────── Tactician(s) — N parallel ──────────────┐
│  Picks tactic from catalog (scope-filtered)         │
│  Emits tasks for specialists                        │
│  Sees: own unit_of_work, own findings, catalog      │
│  Does NOT see: peer tacticians, other phases        │
└─────────────────────────────────────────────────────┘
  │
  ▼ (per task, fan out)
┌────────────── Specialist(s) ────────────────────────┐
│  Picks technique from catalog (typed spec)          │
│  Executes one tool call                             │
│  Sees: one task spec                                │
│  Does NOT see: hypotheses, peer tasks, full query   │
└─────────────────────────────────────────────────────┘
  │
  ▼
[Phase Gate]  →  ok | replan | terminate | escalate-to-user
  │
  ▼ (loop until DAG complete)
[Fusion / ACH ranking]  →  result
```

Information flow:
- **Top-down by typed contract** (strategist→tactician via unit_of_work, tactician→specialist via task).
- **Bottom-up by aggregation** (specialist findings → tactician summary → phase output → strategist aggregate).
- **Sideways forbidden.** Tacticians do not communicate. Specialists do not communicate. Cross-cutting insight is rebuilt at the fusion layer where the strategist synthesizes phase aggregates.

---

## 4. The Four Catalogs

### 4.1 Strategy Catalog

**Schema:**
```python
Strategy = {
  id: str,                          # "media_identification"
  applies_to: QueryClassifier,      # signals that select this strategy
  phases: list[PhaseSpec],          # ordered or DAG
  default_mode: OptimizationMode,
  budget_minimums: BudgetEnvelope,  # floors for any envelope picking this strategy
}

PhaseSpec = {
  id: str,                          # "broaden"
  depends_on: list[phase_id],
  unit_of_work_contract: dict,      # what tacticians receive
  hypothesis_count_policy: str,     # "from_dial" | "fixed:N" | "from_prior_phase"
  gate: GateSpec,                   # function: phase_output → ok|replan|terminate
}

GateSpec = {
  checks: list[CheckSpec],          # e.g., distinct_identity_count >= 3
  on_fail: str,                     # "replan" | "swap_tactic" | "ask_user" | "terminate"
}
```

**Status today:** 28 strategy files exist in `app/pipeline/strategies/`. They emit prose, not phase DAGs.

**Gap:** schema-ize each strategy as `{phases, gates}`. The natural-language version stays inside each phase to brief the tactician on intent.

### 4.2 Tactic Catalog [NEW]

**Schema:**
```python
Tactic = {
  id: str,                          # "hypothesis_first_search"
  phase_compatibility: list[phase_id],
  accepts: UnitOfWorkContract,
  produces: list[TaskSpec],         # how the tactician decomposes into tasks
  cost_class: str,                  # "cheap" | "moderate" | "expensive"
  required_techniques: list[technique_id],
  enforcement: dict,                # e.g., {"min_distinct_outputs": 3}
}
```

**Status today:** Tactics are buried as prose inside strategies. "BROADEN hypothesis-first", "RED TEAM disconfirm", "ACH scoring", "counter-curation", "subject-role coherence check" — all currently inline text.

**Gap:** extract into `app/pipeline/tactics/` as one file per tactic with the schema above. Initial set ~12-20 tactics covering identification, verification, analysis, retrieval families.

### 4.3 Technique Catalog

**Schema:**
```python
Technique = {
  id: str,                          # "web_search"
  tool_name: str,                   # MCP tool to call
  input_schema: JSONSchema,
  output_schema: JSONSchema,
  cost_class: str,
  failure_modes: list[str],         # documented failure shapes
  retry_policy: dict,
}
```

**Status today:** `app/pipeline/techniques.py` exists with a `format_techniques_for_prompt()` function; MCP tool registry is the source of truth. Tools are called freeform — brain decides params, brain decides what "good enough" means.

**Gap:** wrap each MCP tool with a typed input/output contract. Specialist validates the task spec, calls the tool, validates the response. No reasoning at this layer.

### 4.4 Optimization Mode Catalog [NEW]

**Schema:**
```python
OptimizationMode = {
  id: str,                          # "investigation"
  dial_defaults: BudgetEnvelope,    # speed/capability/resource/depth/hypothesis_count
  tactic_bias: dict[tactic_id, float],  # selector weights
  strategy_suggestions: list[strategy_id],
}
```

**Examples:**

| Mode | speed | capability | resource | depth | hypotheses | tactic bias |
|---|---|---|---|---|---|---|
| quick_lookup | fast | light | tiny | shallow | single | retrieval-heavy |
| leads_generation | fast | general | heavy | shallow | paired | contact_extraction, linkedin_lookup |
| data_retrieval | fast | light | medium | search | single | tmdb, structured-source-first |
| market_analysis | normal | general | heavy | deep | competing | comparative, trend_analysis |
| investigation | slow | high | heavy | deep | adversarial | counter_ruration, disconfirm, wayback |
| academic_research | slow | high | medium | abyss | competing | primary_source, citation_chain |

**Same query in different modes picks different tactics** from the same strategy. This is where the user expresses intent.

---

## 5. Budget Model

### 5.1 Research Unit (RU)

**Definition:** RU is the user-facing wallet currency. It is purchased, walletable, and spent against runs.

**Purchase ratio:** $1 = 10 RU (1 RU = $0.10). This is the v1 fee schedule; downstream billing layer can adjust without changing the runtime.

**Internal calibration:** 1 RU ≈ 10k input + output tokens at `general` capability tier (Sonnet-class). The estimator computes runs in tokens internally; tokens are mapped to RU at run-bind time. This keeps RU stable across model-pricing changes — only the token-per-RU multiplier changes, not the user's wallet semantics.

**Why a synthetic unit, not direct token billing:**
- **Stable across model swaps.** Switching strategist from Opus 4.7 → 4.8 may halve token cost; users still pay the same RU per equivalent work.
- **User-comprehensible quantities.** "A typical investigation costs ~20 RU" is easier to reason about than "~200k tokens".
- **Decouples runtime from billing.** Pricing changes, promotions, enterprise discounts, free-tier grants are all wallet-layer concerns; the runtime only ever consults the wallet.

**Display:** UI shows the composite breakdown ("~12 tool calls, ~3 reasoning rounds, ~9 RU = $0.90") so the user sees comprehensible quantities while the wallet tracks honestly.

**Wallet, hold, and pre-allocation mechanics:** see §5.6.

### 5.2 The Five Dials

| Dial | Levels | Default | Affects |
|---|---|---|---|
| **Speed** | slow / normal / fast / very_fast / extreme | normal | Concurrency, retry budget, queue priority, premium routing |
| **Capability** | light / general / high | general | Per-role model assignment |
| **Resource** | tiny / light / medium / heavy / unlimited | medium | Tactician fan-out, tactic catalog pruning by cost_class |
| **Depth** | shallow / search / deep / abyss | search | Strategist replan/recurse rounds per phase |
| **Hypothesis Count** | single / paired / competing / adversarial / swarm | competing | Parallel tacticians per divergent phase |

#### 5.2.1 Capability → per-role model triple

The user sees one dial; the runtime resolves to a triple:

| User dial | Strategist | Tactician | Specialist |
|---|---|---|---|
| light | haiku-4.5 | haiku-4.5 | haiku-4.5 |
| general | sonnet-4.6 | sonnet-4.6 | haiku-4.5 |
| high | opus-4.7 | sonnet-4.6 | haiku-4.5 |
| (future) extreme | opus-thinking | opus-4.6 | sonnet-4.6 |

Specialist almost always wants light — it executes a typed spec, no reasoning. Strategist quality matters most because bad planning wastes the budget downstream.

#### 5.2.2 Speed is not orthogonal to cost

Faster usually costs more RU (concurrent calls, premium-routed inference, larger retry budget). The estimator must multiply RU by the speed factor — bumping `slow → extreme` at fixed other dials can ~1.5-2x RU.

#### 5.2.3 Hypothesis count semantics

`competing` (3-4) is the ACH baseline. `adversarial` (5-8) adds **forbidden_candidates lists** between peers — when Tactician H2 spawns, it receives `forbidden = peers' likely picks` to actively diverge. `swarm` (>8) is high-stakes; diminishing returns past ~7 in practice.

Per-phase, not global: dial sets *broaden phase* fan-out; red-team phase derives from broaden survivors; rank phase is always 1.

### 5.3 Effort Composite & Estimator

```python
effort_score = w_s(speed) × w_c(capability) × w_r(resource) × w_d(depth) × w_h(hypothesis_count)
estimated_ru = base_strategy_ru × effort_multiplier
```

Estimator inputs: strategy spec × dial values × historical calibration. Outputs: `estimated_ru`, `estimated_ru_p90`, `est_wall_time_s`, `est_branches`, `est_tool_calls`, `est_recurse_rounds`.

[TBD] Calibration approach: collect token + tool-call distributions from current `agent_runs` table, fit per-strategy multipliers. Initial v1 uses hand-tuned weights; recalibrate after N=100 real runs.

### 5.4 Hard Caps (Admin-Set, User-Immutable)

- **RU ceiling** per run: kill switch regardless of dials and wallet balance. Default 500 RU (~$50/run hard cap). Protects user from runaway costs even if wallet has plenty.
- **Wall-clock cap** per run: default 30 min.
- **Per-phase RU cap**: default 40% of run ceiling.

### 5.5 Mid-Run Budget Policy

Triggered when consumed RU crosses thresholds of the *pre-allocated hold* (see §5.6):

- **80% consumed**: pause and ask user to extend (+5 RU / +20 RU / stop) if `depth ∈ {deep, abyss}`. Extension reserves additional RU from the wallet on confirmation.
- **80% consumed**: auto-degrade to cheaper tactics for remaining phases if `depth ∈ {shallow, search}` — no user interruption.
- **100% consumed**: hard cut, return partial results with `truncated: true`. Unused portion of the hold (none in this case) returns to wallet.

### 5.6 Wallet and Pre-Allocation

Each user has a single wallet holding their RU balance. Wallets are purchased ($1 = 10 RU at v1), topped up via payment provider, and consumed by runs.

#### 5.6.1 Wallet Schema

```python
Wallet = {
  user_id: UUID,
  balance_ru: int,            # spendable + held = current_total (no negative balance)
  held_ru: int,               # reserved across in-flight runs; subtracted from balance for new holds
  auto_topup: AutoTopupRule | None,
  floor_ru: int,              # user-set "don't drop below"; default 0
  updated_at: timestamp,
  version: int,               # optimistic concurrency token
}

AutoTopupRule = {
  enabled: bool,
  trigger_when_below_ru: int, # e.g., 20 RU
  topup_amount_ru: int,       # e.g., 100 RU
  payment_method_id: str,     # tokenized; runtime never sees raw card
  monthly_cap_ru: int,        # safety cap on auto-topup per calendar month
}
```

#### 5.6.2 The Six Wallet Operations

| Operation | Effect | When |
|---|---|---|
| `topup` | `balance += amount` | User purchase or auto-topup fires |
| `hold` | `held += amount; available = balance - held` | Run accepted at preflight |
| `consume` | `balance -= delta; held -= delta` (atomic) | Each phase commits actual RU usage |
| `release` | `held -= remaining` | Run completes with hold left over |
| `refund` | `balance += amount` | Run failed entirely; full hold returns |
| `extend_hold` | `held += additional` (if balance allows) | Mid-run 80%-threshold user-approved top-up |

**Spendable = `balance - held`.** A second concurrent run can only hold against `spendable`, not raw `balance`. This is the structural guarantee that two runs cannot double-spend.

#### 5.6.3 Hold Semantics (Pre-Allocation)

When the user confirms a run at preflight:

1. **Estimator computes p90** (worst-realistic) RU for the run.
2. **Wallet hold transaction:**
   - Atomic check: `available_ru >= p90` AND `(balance_ru - p90) >= floor_ru`. (DB-level `SELECT FOR UPDATE` on wallet row, or optimistic version-check + retry.)
   - On pass: increment `held_ru` by `p90`. Run record stores `hold_amount = p90`.
   - On fail: reject run → preflight surfaces "insufficient RU; top up or lower budget".
3. **Run executes inside the hold.** Each phase's actual consumption commits against the hold, decrementing both `held_ru` and `balance_ru` together (the consumed portion is gone; the unconsumed portion of the hold stays reserved).
4. **Run completion:**
   - Success: `release` unused hold back to spendable balance.
   - Hard-cut at 100%: hold fully consumed, nothing to release.
   - Failure (system error before any phase ran): full `refund`.

**Why p90 not p50:** if we held only the median estimate, half the runs would hit "out of RU" mid-execution and need to prompt the user. p90 catches the long tail; the unused portion is released anyway.

#### 5.6.4 Concurrency Safety

The wallet row is the contended resource. Two runs starting milliseconds apart both pass a naive `if balance >= cost` check and both proceed → wallet goes negative. Required guards:

- **DB transaction with row-lock** (`SELECT ... FOR UPDATE`) around the hold operation in PostgreSQL.
- **Idempotency keys** on hold/consume/release so retries don't double-charge.
- **Optimistic version field** as cheap secondary defense: hold increments `version`; consume/release/refund must match.

#### 5.6.5 Hard-Stop Threshold and Top-Up

**Hard stop conditions** (any of):
- `available_ru < estimated_p90_for_pending_run` → reject new run at preflight
- `balance_ru - p90 < floor_ru` → reject new run (user-set safety floor)
- Mid-run extend request exceeds available → run continues to hard-cut at original hold

**Top-up flows:**

1. **Manual top-up.** User clicks "Top up" → payment provider redirect → webhook confirms → `topup` op increments balance. Preflight blocks until balance sufficient.
2. **Auto top-up.** When `balance_ru < AutoTopupRule.trigger_when_below_ru`, a background job invokes the stored payment method for `topup_amount_ru` worth. Subject to `monthly_cap_ru` to prevent runaway charges. Failures (declined card, cap reached) downgrade to manual flow with email notification.

**v1 scope:** manual top-up only. Auto top-up deferred to v1.1 once Stripe integration is stable.

#### 5.6.6 Wallet ↔ Budget Envelope Interaction

The preflight estimator produces a budget envelope; the wallet validates *affordability*:

```
estimator(query, dials) → BudgetEnvelope {estimated_ru, p90_ru, ...}
                ↓
wallet.try_hold(user_id, p90_ru, floor_ru) → {ok: true} | {ok: false, reason: "insufficient" | "below_floor"}
                ↓ ok
run begins with envelope + hold_id
```

The runtime always consults the hold balance, never the wallet directly. This means a run completes deterministically — even if the user spends their wallet down to zero on another tab mid-run, the hold protects the current run from being affected.

---

## 6. Preflight UX Flow

```
Query submitted
  ↓
[Classifier]  →  suggested mode + top-3 strategies + initial estimate
  ↓
┌─────────────────────────── Preflight UI ────────────────────────────┐
│                                                                      │
│  Mode:       ( ) quick_lookup  (•) investigation  ( ) academic       │
│              [advanced ▾]                                            │
│                                                                      │
│  Strategy:   media_identification  [auto-selected, change ▾]         │
│                                                                      │
│  ─── advanced dials (click to expand) ─────────────────────          │
│  Speed:       slow  (•)normal  fast  very_fast  extreme              │
│  Capability:  light  (•)general  high                                │
│  Resource:    tiny  light  (•)medium  heavy  unlimited               │
│  Depth:       shallow  (•)search  deep  abyss                        │
│  Hypotheses:  single  paired  (•)competing  adversarial  swarm       │
│                                                                      │
│  Estimate:    ~9 RU ($0.90)  ·  ~4 min  ·  ~12 tool calls           │
│  Wallet:      147 RU available  →  138 RU after this run            │
│                                                                      │
│                                              [ Cancel ]  [ Run ▶ ]   │
└──────────────────────────────────────────────────────────────────────┘
```

**Friction minimization:**
- Default path: user picks Mode → estimate appears → user clicks Run. One click.
- Advanced override: dial panel exposes Mode's pre-filled values; user can tweak.
- Strategy is auto-selected from classifier; expand-to-change for power users.
- Estimate recomputes live on every dial change.

**Mode → Strategy ordering rationale:** users know their *goal* better than the *method*. Mode-first is friendlier than strategy-first.

[TBD] Save-preferred-defaults per user. Defer to v2.

---

## 7. Runtime Roles

### 7.1 Strategist (General)

**Picks:** phase decomposition from chosen strategy.
**Emits:** phase plan (DAG), gate definitions, replan decisions.
**Sees:**
- Query (sanitized — entity-only, no leading interpretation)
- Classifier output
- Strategy catalog entry for elected strategy
- Aggregated phase outputs (after each phase completes)
- Budget envelope and consumption so far

**Does NOT see:**
- Raw tool results
- Peer-phase internal task decomposition
- Specific candidate names mid-phase (only aggregated rankings post-phase)

**Model:** per capability dial (high→opus, general→sonnet, light→haiku).
**Call shape:** short, structured. ~3-6 calls per run (initial plan + replans). Total Opus budget per run small.

### 7.2 Tactician (Team Lead)

**Picks:** tactic from catalog matching its assigned phase + unit_of_work.
**Emits:** task specs for specialists.
**Sees:**
- Its single unit_of_work (`{phase, objective, scope_in, scope_out, prior_findings_slice, success_criteria, forbidden_candidates}`)
- Tactic catalog filtered by phase compatibility + budget cost-class
- Specialist findings for its own tasks only

**Does NOT see:**
- Peer tacticians (their existence, their tasks, their findings)
- Other phases (past or future)
- The original query in full (only its objective slice)

**Model:** per capability dial.
**Spawned:** N instances per divergent phase per `hypothesis_count` dial. Each instance receives a different `unit_of_work` (different hypothesis slot).

### 7.3 Specialist

**Picks:** technique from catalog matching its task's `technique_id`.
**Emits:** typed findings per technique's output_schema.
**Sees:**
- One task spec (`{technique_id, params, expect_schema, fail_modes, budget}`)

**Does NOT see:**
- Hypotheses
- Other tasks
- The query as a whole
- Findings from any other specialist

**Model:** light (haiku) almost always. Specialists don't reason about results — they execute, validate, return.
**Failure mode:** `{status: "no_evidence" | "tool_error" | "schema_violation", details}`. No opinions.

---

## 8. Phase DAG & Gates

### 8.1 Gates

Each phase has a gate function that runs after phase completion:

```python
gate(phase_output, budget_state) → "ok" | "replan" | "swap_tactic" | "ask_user" | "terminate"
```

**Example gates for media_identification:**

| Phase | Gate checks |
|---|---|
| signal_extraction | ≥1 primary signal extracted; ≥1 supporting signal OR explicit "no supporting signal" |
| broaden | `distinct_identity_count(branches) >= hypothesis_count_dial` AND every hypothesis has ≥1 live source |
| red_team | every surviving hypothesis has ≥1 disconfirm search logged |
| rank_verify | top candidate has confidence ≥ 0.4 OR `ask_user` for disambiguation |

**The Zhao Lusi case fails the broaden gate** because `distinct_identity_count = 1` (all branches confirm Zhao Lusi). Strategist replans broaden with corrective hint: `forbidden_candidates += [Zhao Lusi]; require ≥2 alternative identity hypotheses with live searches`.

### 8.2 Replan Authority

When a gate fails, the strategist chooses:
1. **Replan same phase** with corrective hint (cheap, default)
2. **Swap tactic** within the phase (moderate; e.g., switch from `hypothesis_first_search` to `actor_career_pivot`)
3. **Re-decompose strategy** (expensive; rarely needed)
4. **Escalate to user** (when ambiguity is structural, e.g., the query is genuinely under-specified)

Bounded by `depth` dial: `shallow=0 replans`, `search=1`, `deep=3`, `abyss=unlimited until RU cap`.

---

## 9. Worked Example: media_identification on the #89 Query

**Query:** "asian girl with mole in cheek bone and has an advertisement where she uses a curling iron"

**Preflight:**
- Classifier picks `media_identification` strategy + `investigation` mode
- Mode resolves to: `(slow, high, heavy, deep, adversarial)`
- Estimator projects: ~18 RU ($1.80), ~9 min, ~20 tool calls
- Wallet check: user has 147 RU. Hold of 22 RU placed (p90 estimate). 125 RU remains available for other concurrent runs.
- User clicks Run

**Strategist plan:**
- Phase 1: signal_extraction (1 tactician)
- Phase 2: broaden (5 tacticians in parallel — adversarial)
- Phase 3: red_team (per surviving hypothesis)
- Phase 4: rank_verify (1 tactician)

**Phase 1 (signal_extraction):**
- Tactician picks tactic `signal_hierarchy`
- Specialists run NLP techniques
- Output: PRIMARY=`female subject with cheek mole`, SUPPORTING=`curling iron use`, CONTEXT=`YouTube ad, recent`

**Phase 2 (broaden, 5 tacticians):**
- Strategist spawns 5 tacticians with disjoint unit_of_work:
  - T1 (H_PRIOR): "verify or refute RAG hit `Zhao Lusi`"
  - T2 (H_actor_career): "find female celebrity in 2025-2026 hair-tool brand ads, NOT Zhao Lusi"
  - T3 (H_genre_blind): "find female celebrity with distinctive cheek mole, NOT Zhao Lusi"
  - T4 (H_long_tail): "find K-pop/J-pop/SEA female idol in 2025 curling-iron ad"
  - T5 (H_brand_first): "identify curling-iron brand recent ad campaigns; who endorses?"
- Each tactician picks `hypothesis_first_search` tactic, emits 2-3 specialist tasks
- 5 tacticians × ~3 specialists = ~15 specialist tool calls in parallel
- Tacticians cannot see peers — T2 doesn't know T1 confirmed Zhao Lusi

**Phase 2 Gate:**
- `distinct_identity_count` ≥ 4 (Zhao Lusi, plus IVE Wonyoung, plus aespa Karina, plus a long-tail candidate)
- Every hypothesis has ≥1 live source
- Pass.

**Phase 3 (red_team):**
- Each surviving hypothesis gets a disconfirm task
- Specialists search for falsifiers: "does Wonyoung have a cheek mole? does aespa Karina have a curling iron ad? did Zhao Lusi's TYMO ad happen on YouTube?"
- Outputs feed ACH matrix

**Phase 4 (rank_verify):**
- Strategist (or rank-tactician) computes ACH scores per PIR weights
- Top candidate emerges with confidence
- All considered candidates returned in `alternatives_considered`

**Result:** the user sees a ranked answer with ≥3 distinct candidates and their evidence — not a confident single-answer tunnel.

---

## 10. Migration Plan

### 10.1 MVP Scope (Phase 0 — ship first, flesh out after)

**Goal of MVP:** prove the anti-tunneling property end-to-end on the #89 query with a *minimum* slice of the architecture. Validate the structural fix works before investing in catalog breadth, full dial expressiveness, or replan/recurse logic.

**MVP must demonstrate:**

1. **Isolation by visibility works** — two tacticians on the same query reach different candidates because they cannot see each other's findings
2. **Catalog-driven selection works** — closed-set picks at each layer, no free generation
3. **Budget envelope binds** — RU is held at preflight, consumed per phase, released at end
4. **Preflight election works** — user picks mode and strategy explicitly before run
5. **#89 regression passes** — re-running the original Zhao Lusi query produces ≥3 distinct identity candidates

**Cut from MVP, kept in full design:**

| Component | MVP shape | Full design |
|---|---|---|
| Dials | 2 dials: `capability` + `hypothesis_count` only | 5 dials (speed/capability/resource/depth/hypotheses) |
| Modes | 2 modes: `quick_lookup` + `investigation` | 6 modes |
| Strategies | 1 strategy: `media_identification` | 28 strategies migrated |
| Tactics in catalog | 2-3 tactics for BROADEN phase only | Full tactic catalog (~12-20) |
| Techniques typed | 5 wrapped: web_search, image_search, tmdb, google_news, prior_research | All MCP tools |
| Replan/recurse | None — gate failure terminates run | Bounded replan per depth dial |
| Forbidden_candidates | Not enforced — `hypothesis_count=competing` (3) without forbid lists | Full strategist-computed forbid allocation |
| ACH fusion | Simple penalty-weighted ranker | Full ACH matrix with disconfirm scoring |
| Hypothesis count | `competing` (3) only | All 5 tiers (single → swarm) |
| Auto-topup | Manual only | Stripe-backed auto-topup |
| Dual-run parity | No 10% rollout gate; toggle behind `?engine=v2` query param | Full A/B parity check |
| Mid-run extend | Not exposed — hard-cut at 100% | 80%-threshold extend prompt |

**Acceptance:** the #89 query, run through MVP, returns at least 2 candidates whose identity differs from Zhao Lusi, each with ≥1 live tool source. `research_trails.trail.branches` shows distinct `candidate_name` values per branch.

### 10.2 MVP Phasing

| Phase | Scope | Est. time |
|---|---|---|
| M1 | Wallet v2 schema migration + 6 ops (hold/consume/release/refund/extend/topup) with idempotency | 3 days |
| M2 | Catalog scaffolding — TypedDicts/loaders for Strategy, Tactic, Technique, Mode (no content) | 1 day |
| M3 | Convert `media_identification.py` from prose to phase DAG (4 phases: signal/broaden/red_team/rank) | 2 days |
| M4 | Extract 2 tactics for BROADEN phase: `hypothesis_first_search`, `prior_research_seed` | 1 day |
| M5 | Specialist typed wrapper for 5 MCP tools with input/output schema | 2 days |
| M6 | Strategist runtime (lite) — phase DAG executor, no replan, terminates on gate fail | 2 days |
| M7 | Tactician runtime (lite) — N parallel scoped Claude Code subprocesses with `unit_of_work` injection | 2 days |
| M8 | Preflight UI (lite) — 2 modes + strategy display + RU estimate + wallet balance | 2 days |
| M9 | End-to-end wiring + `?engine=v2` toggle + #89 regression test | 1 day |

**Total MVP:** ~16 dev-days. Realistic 3-4 calendar weeks with reviews and overhead.

### 10.3 Post-MVP Phasing (after MVP ships and #89 regression passes)

| Phase | Scope | Est. time |
|---|---|---|
| P1 | Full dial set (5 dials) + 6 modes + advanced preflight UI | 1 week |
| P2 | Full tactic catalog extraction across remaining strategies | 2 weeks |
| P3 | Replan/recurse logic in strategist (bounded by depth dial) | 1 week |
| P4 | Forbidden_candidates strategist-computed allocation for adversarial mode | 3 days |
| P5 | Full ACH matrix fusion | 1 week |
| P6 | Other strategies migrated (`person`, `company`, `due_diligence` first) | ongoing |
| P7 | Dual-run parity framework + automated cutover gate | 1 week |
| P8 | Auto top-up via Stripe + monthly cap enforcement | 1 week |
| P9 | Mid-run extend UX (80% threshold prompt) | 3 days |

### 10.4 Tickets to File

**MVP (file all up front so dependency graph is visible):**

- **#90** [MVP-M1] Wallet v2 — schema migration + 6 ops + audit table + idempotency
- **#91** [MVP-M2] Catalog scaffolding — TypedDicts and loaders for the four catalog types
- **#92** [MVP-M3] `media_identification` strategy as phase DAG
- **#93** [MVP-M4] Extract 2 BROADEN tactics: `hypothesis_first_search`, `prior_research_seed`
- **#94** [MVP-M5] Specialist typed wrapper for 5 MCP tools
- **#95** [MVP-M6] Strategist runtime (lite — no replan)
- **#96** [MVP-M7] Tactician runtime (lite — scoped subprocess fan-out)
- **#97** [MVP-M8] Preflight UI (lite — 2 modes, 2 dials)
- **#98** [MVP-M9] E2E wiring + `?engine=v2` toggle + #89 regression test

**Post-MVP (file when MVP ships):**

- **#99** [P1] Full dial set + remaining modes + advanced preflight
- **#100** [P2] Tactic catalog full extraction
- **#101** [P3] Strategist replan/recurse
- **#102** [P4] Forbidden_candidates allocation
- **#103** [P5] ACH matrix fusion
- **#104** [P6] Migrate `person`/`company`/`due_diligence` strategies
- **#105** [P7] Dual-run parity framework
- **#106** [P8] Stripe auto-topup
- **#107** [P9] Mid-run extend UX

### 10.5 Dual-Run Strategy (Post-MVP)

During MVP, the new engine is opt-in via `?engine=v2`; no parity gating. After MVP ships and the #89 regression passes, P7 introduces formal dual-run on 10% of `media_identification` traffic. Compare on: (a) accuracy/recall on a labeled eval set, (b) RU within ±20% of estimate, (c) `distinct_identity_count` distribution shift, (d) user-grade A rate. Cutover when new engine ≥ legacy on (a) and parity on (d).

---

## 11. Decision Log

| Decision | Rationale | Alternatives rejected |
|---|---|---|
| Three roles (general/team-lead/specialist) | Information visibility is the anti-bias enforcement layer | Two roles (general+executor): conflates planning and tactics, same failure mode as today. Four roles: over-engineered for current scale. |
| Catalog-driven at every layer | Closed-set selection prevents free invention and tunneling; catalogs are version-controlled and auditable | Free-form selection with prompt rules: this is exactly what's broken today. |
| RU = synthetic wallet unit (≈10k tokens internally), purchased at $1=10 RU | Stable across model swaps and pricing changes; user-comprehensible quantities; decouples runtime from billing | RU = raw tokens: forces user to reason in tokens; price changes break wallet semantics. RU = tool calls: hides tier-cost differences. |
| Pre-allocated p90 hold against wallet, not p50 | Protects against mid-run "out of RU" interruptions on the long tail; unused hold returns | Hold = p50: half of runs hit mid-run prompt. Hold = max-cap: locks too much wallet for parallel runs. |
| Wallet row-lock + idempotency keys for concurrency | Cheap structural guarantee that two concurrent runs cannot double-spend | Optimistic-only: race window allows oversubscription. Pessimistic global lock: serializes all runs unnecessarily. |
| Forbidden_candidates computed by strategist from priors (RAG + classifier + training first-pass), not from live peer findings | Preserves "strategist sees priors and aggregates, not raw tool results"; deterministic, free, auditable; enables true-parallel tactician fan-out | (B) Two-phase coordinator with extra LLM call: more moving parts, +1 RU and +5s latency, no real benefit since priors are already available. (C) Staggered start with late-binding: breaks no-peer-visibility invariant — defeats the entire isolation property of the architecture. |
| Five dials, not single tier | Speed/capability/resource/depth/hypotheses are orthogonal; collapsing them hides what the user is buying | Single tier (Quick/Standard/Thorough): loses orthogonality; fast-shallow vs slow-deep can't be expressed. |
| Hypothesis count as its own dial | Directly addresses #89 failure mode; not derivable from other dials; per-phase fan-out is independent from breadth/depth/speed | Derived from depth or resource: loses the ACH-specific control. |
| Mode picker primary, dials advanced | Users know goal better than method; one-click default UX | Strategy picker primary: leaks implementation into UX. |
| Capability as single user dial → per-role triple | UX simplicity without sacrificing per-role efficiency | Three separate model pickers: overwhelming for users. |
| Preflight election by user, not strategist | User has the most context about urgency, budget, depth needed; strategist autonomy is unbounded by user intent today | Strategist auto-picks: hard to undo; cost surprises. |
| Defense in depth (prompt + structure) | If structural enforcement misses an edge case, prompt rules catch it; if prompt rules are ignored, structure enforces | Either alone: #89 already shows prompt-only fails; structure-only loses the intent-documentation prompts provide. |

---

## 12. Open Questions (Resolve Before P1)

1. **RU calibration data.** Pull token + tool-call distributions from `agent_runs` for the last 90 days. Fit per-strategy RU baselines under the assumption 1 RU ≈ 10k tokens. Decide v1 multiplier constants and the token-per-RU ratio. **Owner:** [TBD]. **Blocking:** estimator implementation in P6.
1.5. **Wallet table — extend or new?** Existing `app/pipeline/budget.py` has a `reserve_budget` with auto-provision logic. Decide: extend the existing wallet schema to add `held_ru`, `floor_ru`, `auto_topup`, `version` columns, or introduce a new `wallet_v2` table with a migration. Recommendation: extend, since reservation semantics already live there.
2. **Forbidden_candidates lists for adversarial hypothesis count.** ~~Computed by strategist (sees aggregates) or by a separate fan-out coordinator?~~ **RESOLVED:** strategist computes from priors only (RAG hits + classifier candidates + training-knowledge first-pass), not from live findings. Hard invariant "strategist never sees raw tool results, only aggregated phase outputs" is preserved because priors are pre-execution data. Allocation rule: slot 0 = no forbid (verifies obvious), slot 1 = forbid top-1, slot N = forbid top-N. Logged with phase plan for audit. Late-binding via staggered start was rejected — breaks no-peer-visibility invariant.
3. **Mode + Strategy interaction precedence.** Mode tactic_bias floats vs. strategy required_tactics — which wins on conflict?
4. **Mid-run dial change UX.** Can user raise depth/budget mid-run without canceling? Probably yes for depth, no for capability (would invalidate findings).
5. **Specialist retry on schema violation.** If tool returns unparseable output, specialist retries with stricter prompt to tool wrapper, or escalates to tactician? Cost vs. completeness trade.
6. **Backward compat for in-flight runs.** Cutover plan for runs queued at the moment of switch. Likely: drain queue on legacy engine, new queries hit new engine, no migration of in-flight state.

---

## 13. Out of Scope

- Multi-user budget pooling, organization-level RU accounting
- Strategy authoring UI (catalog edits stay in code for now)
- Real-time collaboration (multiple users on one run)
- Long-running campaigns spanning hours/days (current scope: single-query bounded run)
- Custom technique authoring by end-users
- Federated specialists (running on user infrastructure)

---

## 14. Appendix

### 14.1 Catalog Schemas in Full (TypedDict / JSON)

[TBD] Move from inline section-4 examples to full canonical schemas with validation rules. Defer until P1 ticket scopes the schema work.

### 14.2 Hold Lifecycle State Machine

```
                              ┌─────────────────┐
       preflight.confirm  →→→ │   REQUESTED     │
                              └─────────────────┘
                                      │
                  wallet.try_hold(p90)│  (atomic UPDATE-with-guard)
                ┌─────────────────────┴──────────────────┐
                ▼                                        ▼
         ok: held_ru+=p90                       fail: insufficient
                │                                        │
                ▼                                        ▼
       ┌─────────────────┐                    ┌──────────────────┐
       │     HELD        │                    │   REJECTED       │
       │  (run begins)   │                    │ → topup prompt   │
       └─────────────────┘                    └──────────────────┘
                │
   ┌────────────┼────────────┬──────────────┬────────────────┐
   ▼            ▼            ▼              ▼                ▼
phase.consume(δ) consume(δ) consume(δ)  extend_hold(+Δ)   timeout/crash
   │            │            │              │                │
   ▼            ▼            ▼              ▼                ▼
held-=δ      held-=δ     held-=δ        held+=Δ          (transition
balance-=δ   balance-=δ  balance-=δ     (if available)    on watchdog)
   │            │            │              │                │
   └────────────┴────────────┴──────────────┘                │
                       │                                     │
        ┌──────────────┼──────────────┐                      │
        ▼              ▼              ▼                      ▼
   80% threshold   100% reached   run completes      ┌──────────────┐
        │              │              │              │   ORPHANED   │
        ▼              ▼              ▼              │ (held_ru     │
   pause + ask     hard_cut        release           │  stuck)      │
   user(deep+)    (truncated)      held-=remaining   └──────────────┘
        │              │              │                      │
   ┌────┴────┐         │              │           scheduled job:
   ▼         ▼         │              │           release after T=2h
extend     stop        │              │                      │
hold       run         │              │                      ▼
+5/+20     hard_cut    │              │                  release
   │         │         │              │                  (audit: orphan)
   └─────────┴─────────┴──────────────┴──────────────────────┘
                       │
                       ▼
              ┌─────────────────┐
              │   SETTLED       │
              │ (audit row in   │
              │  wallet_ops)    │
              └─────────────────┘
```

**State invariants:**

- `held_ru >= 0` always (PostgreSQL CHECK constraint)
- `balance_ru >= held_ru` always (CHECK constraint)
- `held_ru >= sum(active_holds.hold_amount)` (consistency rule — held aggregates per-run holds)
- Every state transition appends a `wallet_operations` row with `idempotency_key`

**Failure recovery:**

- **Network drop between `consume` request and response:** client retries with same idempotency_key; server returns prior result, no double-charge.
- **Worker crash mid-run:** watchdog job (cron, 5-min interval) scans for runs in HELD state with `last_heartbeat > 2h`; transitions to ORPHANED, releases held_ru, logs the leak for ops review.
- **DB unreachable during hold attempt:** existing code returns `True` ("allow run on DB failure") which leaks free runs. V2 should fail closed — reject the run with "wallet check failed, try again", not silently allow it.

### 14.3 References

- Issue #89 — "IS brain tunnels to RAG-retrieved candidate; no fresh hypothesis BROADEN phase"
- `docs/intelligence/is-brain-methodology.md` — Existing IS brain methodology doc; this design supersedes the runtime sections but builds on the SAT/ACH theory
- Memory notes:
  - `feedback_create_tickets_before_fixing.md`
  - `project_is_brain_lessons.md` — "inverted research posture", "BROADEN phase missing"
  - `project_analyst_gaps.md`
- Heuer, *Psychology of Intelligence Analysis* (ACH methodology background)
- Anthropic Claude Code agent architecture (tool-use loop reference)
