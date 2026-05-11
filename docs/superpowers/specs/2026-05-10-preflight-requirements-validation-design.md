# PreFlight Requirements Validation — Design Spec

**Date:** 2026-05-10
**Status:** Draft (Phase 1)
**Depends on:** IS brain methodology (`app/is_prompt.py`), agent endpoint (`app/routers/v3/agent.py`), grounding pass (`fused_retrieve`), existing `ask_user()` tool infrastructure
**Related work:**
- `docs/superpowers/specs/2026-05-10-is-brain-intelligence-methodology-design.md` — establishes STEP 0 decomposition + gap analysis inside the brain prompt; PreFlight moves that gate **outside** the brain.
- `docs/intelligence/is-brain-methodology.md` — living methodology.

## Problem Statement

The IS brain (a Claude Code subprocess) consistently produces **confident wrong answers** when queries are incomplete or ambiguous. It begins research before validating that it has enough information to research the right thing. Two confirmed regressions:

1. **Amazon ad case.** Query: *"new series with girl in spiderman where man has a shotgun"*. Brain answered "The Last of Us S2." Correct answer: a 2026 Amazon promo reel that compiled clips from multiple shows. The brain never asked **where the user saw it** — the single highest-value disambiguator.

2. **Dyson case.** Query: *"who is the person in the Dyson commercial"*. Brain answered from training data without asking **which ad** or **which year**. The referential phrase "the Dyson commercial" assumes shared context the user did not articulate.

### Why a better prompt is not sufficient

The IS brain methodology spec (2026-05-10) already added STEP 0 (Decompose + Gap Analysis + Ask If Gaps) to the prompt. It improved behavior but did not eliminate the failure mode. Root cause:

> **The brain self-assesses whether it has enough information.** It is biased by training data toward answering rather than asking, and toward selecting the most plausible interpretation rather than acknowledging ambiguity. A self-assessment that the model is biased to fail at, executed inside the same call that decides to act, will fail.

Self-assessment must be **lifted out of the brain** into a deterministic + lightweight-LLM pipeline that runs **before** the brain launches and produces a structured `ValidationResult` the brain is forced to honor. The brain does not get to decide whether to ask; PreFlight decides, and the brain executes.

## Goal

Build a three-layer requirements validation module — `app/pipeline/preflight.py` — that runs after grounding, before brain launch, and:

- Extracts query slots (subject, provenance, scope, goal, disambiguator) using a fast deterministic pass plus one Haiku call.
- Applies a deterministic rules table to detect missing required slots.
- Emits a tiered `ValidationResult` that either (a) lets the brain proceed, (b) forces a clarification turn via the existing `ask_user()` tool, or (c) lets the brain proceed with a Tier-3 disclaimer.

Phase 1 targets ~60–70% coverage of real-world ambiguity. Phase 2 (deferred) takes coverage to ~88–93%.

## Architecture

### Component Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                    Agent endpoint (v3/agent.py)                  │
│                                                                  │
│  ┌────────────────────┐     ┌────────────────────────────────┐   │
│  │ Grounding pass     │────▶│ PreFlight                      │   │
│  │ fused_retrieve()   │     │  app/pipeline/preflight.py     │   │
│  └────────────────────┘     └────────────────────────────────┘   │
│                                          │                       │
│                                          ▼                       │
│                       ┌──────────────────────────────────────┐   │
│                       │ ValidationResult                     │   │
│                       │   tier ∈ {1, 2, 3}                   │   │
│                       │   blocking, first_question, slots    │   │
│                       └──────────────────────────────────────┘   │
│                                          │                       │
│                                          ▼                       │
│                       ┌──────────────────────────────────────┐   │
│                       │ build_prompt() injects:              │   │
│                       │   T1: validated slots                │   │
│                       │   T2: [PREFLIGHT: CLARIFICATION      │   │
│                       │        REQUIRED] block               │   │
│                       │   T3: disclaimer block               │   │
│                       └──────────────────────────────────────┘   │
│                                          │                       │
│                                          ▼                       │
│                       ┌──────────────────────────────────────┐   │
│                       │ IS brain (Claude Code subprocess)    │   │
│                       │   T2 → first action MUST be          │   │
│                       │        ask_user(first_question, …)   │   │
│                       └──────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

### Three Layers

```
                           QUERY
                             │
                             ▼
   ┌──────────────────────────────────────────────────────┐
   │ LAYER 1 — Deterministic extraction (~5ms, no LLM)    │
   │   regex + simple NER + lexicon                       │
   │   → ExtractionResult (advisory hints)                │
   └──────────────────────────────────────────────────────┘
                             │
                             ▼
   ┌──────────────────────────────────────────────────────┐
   │ LAYER 2 — Slot extraction (1 Haiku call, ~300ms)     │
   │   query + Layer 1 hints → structured slots           │
   │   confidence < 0.7 → null                            │
   │   → SlotResult                                       │
   └──────────────────────────────────────────────────────┘
                             │
                             ▼
   ┌──────────────────────────────────────────────────────┐
   │ LAYER 3 — Requirements rules (<1ms, pure Python)     │
   │   ~20 conditions → priority-ordered MissingSlot list │
   │   → ValidationResult { tier, blocking, question }    │
   └──────────────────────────────────────────────────────┘
```

### Layer 1 — Deterministic Extraction

Pure-Python pass producing an `ExtractionResult` of advisory hints. No model call. Target latency ≤ 5ms.

| Feature | Detection | Example tokens |
|---|---|---|
| `proper_nouns` | Capitalized non-sentence-initial tokens; multi-word title-case spans | "Dyson", "The Last of Us" |
| `temporal_signal` | Lexicon: `new`, `recent`, `latest`, `upcoming`, `current`, year tokens (`19xx`/`20xx`), `last week`, `this year` | "new series", "2026" |
| `platform_hint` | Lexicon: `YouTube`, `Facebook`, `Instagram`, `TikTok`, `Netflix`, `Prime`, `Hulu`, `ad`, `commercial`, `streaming`, `billboard`, `podcast` | "ad", "Netflix" |
| `first_person_evidence` | Lexicon: `saw`, `heard`, `watched`, `noticed`, `found`, `read`, `caught`, `came across` | "I saw" |
| `referential_phrase` | Pattern: `(this\|that\|the)\s+(ad\|commercial\|show\|series\|video\|article\|guy\|person\|woman\|man)`; demonstrative + descriptive cluster | "the commercial", "this ad" |
| `polysemous_term` | Small lexicon — Apple, Tesla, Mercury, Amazon, Java, Python, Oracle, Mars, Phoenix, Sun, Galaxy, Edge, etc. | "Amazon" |
| `comparison_signal` | Lexicon: `vs`, `versus`, `compare`, `compared to`, `or`, `between` (in question position) | "X vs Y" |
| `legality_terms` | Lexicon: `legal`, `illegal`, `allowed`, `regulation`, `compliance`, `permit`, `licensed`, `tax` | "is X legal" |

Output:

```python
@dataclass
class ExtractionResult:
    proper_nouns: list[str]
    temporal_signal: bool
    platform_hint: str | None
    first_person_evidence: bool
    referential_phrase: bool
    polysemous_terms: list[str]
    comparison_signal: bool
    legality_terms: bool
    raw_features: dict[str, Any]   # for telemetry
```

### Layer 2 — Slot Extraction (Haiku)

One call to Claude Haiku. Input: the user query + Layer 1 hints rendered as a short advisory block. Output: strict JSON parsed into `SlotResult`.

**Hints are advisory, not authoritative.** Haiku may override a Layer 1 hit if the surrounding context contradicts it (e.g., "java the village" → not the polysemous programming language).

**Confidence floor.** Haiku is instructed: *"If your confidence in a slot value is below 0.7, leave the field null. Do not guess."* This is the structural guard that keeps Tier 2 from triggering on noise.

```python
@dataclass
class SubjectSlot:
    kind: Literal["named", "described", "referential"]
    value: str
    confidence: float                                  # 0.0–1.0
    disambiguation_risk: Literal["low", "medium", "high"]

@dataclass
class ProvenanceSlot:
    present: bool
    value: str | None        # e.g., "Netflix", "YouTube ad", "billboard on I-95"
    confidence: float

@dataclass
class ScopeSlot:
    time: str | None         # e.g., "2026", "last 30 days"
    geo: str | None          # e.g., "US", "Metro Manila"
    platform: str | None
    domain: str | None       # e.g., "tax law", "fintech"

@dataclass
class GoalSlot:
    answer_shape: Literal[
        "identify", "verify", "find", "compare", "monitor", "explain",
        "legality_check", "regulation", "pricing", "compliance",
    ] | None
    confidence: float

@dataclass
class DisambiguatorSlot:
    present: bool
    value: str | None        # the user-supplied disambiguator, if any

@dataclass
class SlotResult:
    subject: SubjectSlot
    provenance: ProvenanceSlot
    scope: ScopeSlot
    goal: GoalSlot
    disambiguator: DisambiguatorSlot
    raw_response: str        # for audit/telemetry
```

Latency budget: ~300ms. Cost budget: ~$0.0005/query. On Haiku failure (timeout, parse error, 5xx) the layer returns a `SlotResult` with all confidences `0.0` and all values null — Layer 3 then routes to **Tier 3** (proceed with disclaimer), never Tier 2. PreFlight is not a hard dependency on Haiku availability.

### Layer 3 — Requirements Rules

Pure Python, deterministic, ordered evaluation. Each rule returns either nothing or a `MissingSlot` with priority. Lower priority number = higher urgency.

```python
@dataclass
class MissingSlot:
    slot: str                              # e.g., "provenance"
    priority: int                          # 1 (highest) … 4 (lowest)
    rule_id: str                           # for telemetry (e.g., "R1")
    question: str                          # rendered question text
    options: list[str] | None              # suggested choices, if any
    rationale: str                         # why this slot is required
```

After all rules execute, the firing rules are sorted by `(priority, rule_id)`. The first becomes `first_question`.

## Rules Table (Phase 1)

| ID  | Priority | Condition | Slot to Ask | What query type it catches |
|-----|----------|-----------|-------------|----------------------------|
| R1  | 1 | `(extraction.first_person_evidence OR extraction.referential_phrase) AND NOT slots.provenance.present` | `provenance` ("Where did you see/hear this?") | **Amazon ad**, **Dyson**, "this ad I saw", "that show" |
| R2  | 2 | `slots.subject.kind == "described" AND NOT slots.disambiguator.present AND slots.goal.answer_shape in {"identify", None}` | `disambiguator` ("Anything else you remember? Actor, year, platform?") | "the show with the girl with the dragon tattoo and the hacker" |
| R3  | 2 | `extraction.polysemous_terms != [] AND slots.subject.disambiguation_risk in {"medium","high"} AND NOT slots.disambiguator.present` | `disambiguator` ("Which Amazon — the company, the river, or the streaming service?") | "tell me about Amazon", "what is Apple's plan" |
| R4  | 2 | `slots.goal.answer_shape == "compare" AND slots.subject.kind == "named" AND len(extraction.proper_nouns) < 2` | `comparison_target` ("Compare X with what?") | "compare Tesla" |
| R5  | 3 | `slots.goal.answer_shape is None OR slots.goal.confidence < 0.6` | `intent` ("Are you trying to identify it, verify a fact, find more, or something else?") | "Tesla 2026" |
| R6  | 3 | `extraction.temporal_signal AND slots.scope.time is None` | `time_period` ("What time window — past week, past month, this year?") | "new Dyson stuff" |
| R7  | 4 | `slots.goal.answer_shape in {"legality_check","regulation","pricing","compliance"} AND slots.scope.geo is None` | `jurisdiction` ("Which country/region?") | "is X legal", "what's the tax on X" |
| R8  | 4 | `slots.goal.answer_shape == "monitor" AND slots.scope.time is None` | `cadence` ("How far back, and how often do you want updates?") | "track Acme Corp" |
| R9  | 3 | `slots.subject.kind == "referential" AND extraction.platform_hint is None AND NOT slots.provenance.present` | `provenance` (same as R1) | "the article about X" |
| R10 | 4 | `slots.goal.answer_shape == "find" AND slots.scope.domain is None AND len(slots.subject.value.split()) <= 2` | `domain` ("In what context — software, music, finance?") | "find Mercury" |

R1 supersedes R9 if both fire (deduplicated by slot name; highest-priority instance kept).

Rules are pure functions over `(ExtractionResult, SlotResult)`. Adding a rule is a one-line append to the `RULES` list — no engine changes.

## Tiered Output

```python
class Tier(IntEnum):
    PROCEED = 1                  # complete + high confidence
    BLOCK = 2                    # gap detected; brain must ask
    PROCEED_WITH_DISCLAIMER = 3  # low-confidence parse, no firm gap

@dataclass
class ValidationResult:
    tier: Tier
    missing: list[MissingSlot]                    # priority-ordered, may be empty
    blocking: bool                                # True iff tier == 2
    first_question: str | None                    # populated for tier 2
    first_question_options: list[str] | None
    slots: SlotResult                             # from Layer 2
    extraction: ExtractionResult                  # from Layer 1
    confidence: float                             # overall completeness 0..1
    disclaimer: str | None                        # populated for tier 3
    rules_fired: list[str]                        # rule_ids, for telemetry
    latency_ms: dict[str, float]                  # per-layer
```

**Tier selection logic** (evaluated after rules):

```
if any rule fired:
    tier = 2 (BLOCK)
    first_question = highest-priority MissingSlot.question
    blocking = True
elif overall_confidence >= 0.8 and slots.subject.confidence >= 0.7 and slots.goal.confidence >= 0.6:
    tier = 1 (PROCEED)
elif Layer 2 failed OR overall_confidence < 0.5:
    tier = 3 (PROCEED_WITH_DISCLAIMER)
    disclaimer = render_disclaimer(slots)
else:
    tier = 1 (PROCEED)
```

`overall_confidence` = mean of `subject.confidence`, `goal.confidence`, and (if `temporal_signal` present) `scope.time` populated → 1.0 else 0.5.

`render_disclaimer(slots)` produces strings like: *"I interpreted this as: identifying the {subject.value} on {scope.platform or 'an unspecified platform'} in {scope.time or 'no specified time window'}. If that's not what you meant, please clarify."*

## Integration

### `app/routers/v3/agent.py` changes

After the grounding pass and before brain launch:

```python
# Existing
past_research = run_grounding_pass(query, user_id=uid)

# New
preflight = run_preflight(query, hints={"past_research": past_research})

if preflight.tier == Tier.BLOCK:
    # Inject [PREFLIGHT: CLARIFICATION REQUIRED] into prompt; brain's first
    # tool call MUST be ask_user(first_question, options).
    prompt = build_prompt(
        query=query,
        past_research=past_research,
        preflight=preflight,
    )
elif preflight.tier == Tier.PROCEED_WITH_DISCLAIMER:
    prompt = build_prompt(
        query=query,
        past_research=past_research,
        preflight=preflight,           # disclaimer rendered into context
    )
else:  # Tier.PROCEED
    prompt = build_prompt(
        query=query,
        past_research=past_research,
        preflight=preflight,           # validated slots injected as context
    )

# Telemetry
log_preflight_event(run_id=run_id, result=preflight)

launch_brain(prompt, ...)
```

PreFlight failure (timeout, exception) is **non-fatal**: a warning is logged and execution proceeds with `tier = 3` and a generic disclaimer. PreFlight is a quality lift, not a hard dependency.

### `app/is_prompt.py` changes

A new templated section is added to `RESEARCH_PROMPT`:

```
{preflight_section}
```

Rendered per tier:

**Tier 1 (PROCEED).** Slots are injected as a `## VALIDATED CONTEXT` block listing subject/provenance/scope/goal. The brain is instructed to skip independent decomposition: *"PreFlight has decomposed this query. Use the slots below as ground truth and proceed to STEP 1 (BOOTSTRAP)."*

**Tier 2 (BLOCK).** A `## [PREFLIGHT: CLARIFICATION REQUIRED]` block is inserted at the very top of the prompt with this body:

> PreFlight detected a missing required slot: **{slot}**. Your **first and only action** must be:
>
>     ask_user(question="{first_question}", options={first_question_options})
>
> Do **not** call any other tool. Do **not** answer from training knowledge. After the user replies, re-enter STEP 0 with the new context. Maximum two clarification turns total.

This reuses the existing `ask_user()` tool — no new blocking mechanism is required.

**Tier 3 (PROCEED_WITH_DISCLAIMER).** A `## INTERPRETATION DISCLAIMER` block carries the rendered disclaimer string. The brain is instructed: *"Prepend this disclaimer verbatim to your final summary."*

`build_prompt()` accepts a new `preflight: ValidationResult | None` argument. When `None`, `{preflight_section}` is rendered empty (backward compatible with non-agent callers).

## Coverage

| # | Ambiguity category | Example | Phase 1 catch | Phase 2 catch |
|---|---|---|---|---|
| 1 | Referential / first-person provenance | "the Dyson commercial", "ad I saw" | R1, R9 — **yes** | yes |
| 2 | Described entity needing disambiguator | "the new spy show with the redhead" | R2 — yes | yes |
| 3 | Polysemous named term | "tell me about Mercury" | R3 — partial (lexicon limited) | R3 — yes (~500-entry lexicon) |
| 4 | Underspecified comparison | "compare Tesla" | R4 — yes | yes |
| 5 | Missing intent | "Tesla 2026" | R5 — yes | yes |
| 6 | Temporal signal w/o window | "new Dyson stuff" | R6 — yes | yes |
| 7 | Jurisdiction-dependent (legal/tax/pricing) | "is X legal" | R7 — yes | yes |
| 8 | Common-name cardinality (world-state) | "John Smith" | **no** (handle at output stage) | partial — cardinality probe |
| 9 | Coherent-but-false self-description | "I'm the CEO of Acme" | **no** (verification problem) | **no** |

**Phase 1 estimated coverage: 60–70%** of real-world ambiguity in observed query logs.
**Phase 2 estimated coverage: 88–93%** with the additions below.

## Phase Boundary

### Phase 1 — this spec — implement now

- Layer 1 deterministic extraction (regex + small lexicons listed above).
- Layer 2 single Haiku call with strict JSON schema and `confidence < 0.7 → null` rule.
- Layer 3 rules R1–R10 as listed.
- Three-tier `ValidationResult` and renderer.
- Integration in `app/routers/v3/agent.py`.
- `is_prompt.py` `{preflight_section}` template + tier-specific instructions.
- Telemetry: per-rule fire counts, per-layer latency, tier distribution.

### Phase 2 — deferred

- **Polysemous lexicon (~500 entries).** Replaces the seed lexicon used by R3 for higher recall.
- **Conversation slot history.** PreFlight accepts prior-turn `SlotResult` and treats already-filled slots as defaults; rules then fire only on slots still missing across the conversation.
- **Cardinality probe.** When `goal.answer_shape == "identify"` and the subject is a common name, run a quick search-count probe; if cardinality is high, ask for a disambiguator.
- **Self-consistency check.** Run Haiku twice with temperature jitter; if slot values diverge, downgrade confidence and surface as Tier 3.
- **Slot-aware `ask_user` follow-ups.** Generate options from observed prior-turn slot values to make the first question one-tap.

## Inherent Limitations (accepted, not patched)

- **World-state ambiguity.** "John Smith" — 40K matches on LinkedIn — cannot be resolved by parsing the query. The query is well-formed; the world is ambiguous. **Handled at the output stage** (the brain returns ranked candidates with disambiguating attributes), not by PreFlight.
- **Coherent-but-false self-description.** A user claiming a false identity produces a syntactically valid query. This is a **verification** problem, not a parsing problem; PreFlight cannot detect it and should not try.
- **Shared-context assumptions the user did not articulate.** A user says "the report" referring to a document only they have. PreFlight's Tier 3 disclaimer (*"I interpreted this as…"*) handles this gracefully without forcing a clarification turn for every referential phrase.

These are documented limits, not TODOs. Patching them would expand scope without proportionate gain.

## Testing Approach

### Unit tests — per layer

- `tests/pipeline/test_preflight_layer1.py` — for each Layer 1 feature: ≥3 positive and ≥3 negative example queries; assert detection.
- `tests/pipeline/test_preflight_layer2.py` — Haiku is mocked. For ~15 representative queries, the test fixes the Haiku JSON response and asserts `SlotResult` parsing handles: well-formed JSON, malformed JSON (→ all-null slots), partial JSON (→ missing fields → defaults), confidence-floor enforcement.
- `tests/pipeline/test_preflight_layer3.py` — for each rule R1–R10: a hand-crafted `(ExtractionResult, SlotResult)` pair that **must fire** the rule and one that **must not**. 20 tests minimum.

### Tier selection tests

- `tests/pipeline/test_preflight_tier.py` — table-driven test covering all three tiers and the priority/dedup logic when multiple rules fire.

### Regression tests — the failure cases that motivated this work

- **Amazon ad regression** (`test_preflight_amazon_ad_regression`). Query: `"new series with girl in spiderman where man has a shotgun"`. Assert: `tier == BLOCK`, `first_question` is the provenance question (R1 via `referential_phrase`), brain prompt contains the `[PREFLIGHT: CLARIFICATION REQUIRED]` block.
- **Dyson regression** (`test_preflight_dyson_regression`). Query: `"who is the person in the Dyson commercial"`. Assert: `tier == BLOCK`, `first_question` is the provenance question (R1 via `referential_phrase` "the … commercial"), and Layer 1 also flags `platform_hint = "commercial"`.

These two tests gate any future change to the rules or layers.

### Failure-mode tests

- **Haiku timeout / 5xx.** Mock the SDK to raise; assert PreFlight returns `tier == 3` with a disclaimer and `latency_ms["layer2"]` recorded.
- **Haiku returns malformed JSON.** Assert Layer 2 returns all-null slots, Layer 3 fires no rules, tier collapses to 3.
- **Total PreFlight exception.** Assert `agent.py` logs a warning and proceeds with a synthetic `tier == 3` result (PreFlight is non-fatal).

### End-to-end tests

- `tests/integration/test_preflight_e2e.py` — exercise `/v3/agent` with the Amazon and Dyson queries; assert the brain's first tool call is `ask_user` with the expected question. Use the existing brain test harness with a stubbed Claude Code subprocess.

### Evaluation set (out of test suite, run before promoting Phase 1 to default)

A 100-query labeled evaluation set covering the 9 ambiguity categories above plus 30 unambiguous control queries. Track:
- True-positive Tier 2 firing rate per category.
- False-positive Tier 2 rate on controls (target ≤ 5%).
- Tier 3 rate on controls (target ≤ 10%).
- p50 / p95 PreFlight latency (target p50 ≤ 350ms, p95 ≤ 700ms).

## Key Design Decisions

1. **PreFlight is outside the brain.** The brain cannot reliably self-assess sufficiency; lifting the gate out of the brain is the entire point of the module. STEP 0 inside `is_prompt.py` remains as a safety net but is no longer the primary mechanism.

2. **Layer 1 hints are advisory.** Haiku may override regex hits when context contradicts them. Locking Layer 1 outputs as authoritative would make PreFlight brittle to lexicon errors and edge cases.

3. **`confidence < 0.7 → null` is structural.** This single rule is what keeps Tier 2 from triggering on noise. It is enforced in the Haiku prompt, not by post-processing — Haiku is better at conditional null than at post-hoc thresholding.

4. **`ask_user` reuse, not a new mechanism.** A new "blocking clarification" channel would be a parallel control flow. Reusing `ask_user` keeps the brain's tool surface unchanged; PreFlight only changes the **prompt**, which forces the brain's first tool call to be `ask_user`.

5. **Non-fatal everywhere.** Haiku failure → Tier 3. PreFlight exception → Tier 3 with synthetic disclaimer. Grounding-pass failure (already non-fatal) is unaffected. The system degrades to "old behavior" gracefully.

6. **Rules are data, not code.** Adding a rule is appending to `RULES`. This keeps the engine small and the rule set auditable.

7. **Phase 1 ships at 60–70% coverage on purpose.** The marginal coverage from Phase 2 (polysemous lexicon, conversation history, cardinality probe, self-consistency) requires meaningful infrastructure (lexicon ingestion, conversation state, second Haiku call). Shipping Phase 1 first lets us measure tier distributions on real traffic and prioritize Phase 2 components by observed gap, not speculation.

## Scope

In-scope (Phase 1):
- New module `app/pipeline/preflight.py`.
- Integration point in `app/routers/v3/agent.py` (single call site).
- Templated section in `app/is_prompt.py`.
- Test suite per "Testing Approach" above.
- Telemetry hooks for per-rule fire rate, latency, tier distribution.

Out of scope (Phase 1):
- Polysemous lexicon expansion (Phase 2).
- Conversation slot history persistence (Phase 2).
- Cardinality probe (Phase 2).
- Self-consistency check (Phase 2).
- Tool-call enforcement that the brain's first tool on Tier 2 actually is `ask_user` (logged as future work; the prompt already mandates it).
- World-state ambiguity ("John Smith") and self-description verification (accepted as inherent limitations).

## Open Questions

- **Haiku model pinning.** Should we pin the exact Haiku model version to keep slot-extraction behavior reproducible across deployments? Recommendation: yes, pin in config; bump explicitly.
- **Tier 3 disclaimer formatting in the UI.** The brain prepends the disclaimer to its summary, but should the UI also render it as a distinct banner above results? Out of scope for this spec; tracked as a follow-up frontend ticket.
- **Maximum clarification turns.** Spec sets a hard cap of 2. Should the cap be configurable per route? Defer until we have data on how often the second clarification fires.
