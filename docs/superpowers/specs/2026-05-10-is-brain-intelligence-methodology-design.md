# IS Brain Intelligence Methodology Improvements — Design Spec

**Date:** 2026-05-10
**Status:** Implemented (Tier 0)
**Depends on:** Memory Phase 1 retrieval fusion (`fused_retrieve`), Qdrant `research_memory`, IS brain research prompt (`app/is_prompt.py`)
**Living methodology doc:** `docs/intelligence/is-brain-methodology.md`

## Problem Statement

The IS brain was producing confidently wrong answers on two recurring failure modes:

1. **Composite-signal queries (the "Amazon ad" case).** A user asked about a streaming-ad spot that mixed signals from multiple shows in a single 2026 Amazon promo reel. The brain treated the incoherent signal bundle as belonging to a single show, ranked hypotheses by corroboration count rather than signal coverage, and confidently returned the wrong title. There was no step where the brain asked "can ALL these signals plausibly belong to the same entity?"

2. **Stale-knowledge queries (the "Dyson" case).** A user asked about a recent Dyson product. The brain answered from training data without invoking any live tool, returning a confident-but-outdated answer. There was no concept of `temporal_sensitivity` and no rule against using training knowledge as primary evidence on live queries.

Both failures share a root cause: the prompt did not distinguish between **hypothesis fuel** (training knowledge, prior research) and **evidence** (live tool calls), and it did not force a coherence check before committing to a single-entity assumption.

A third underlying issue: every brain launch started from a blank slate. Past run findings sat in Qdrant `research_memory` but were only retrieved on explicit "Go Deeper" runs, so the brain rediscovered the same facts on every related query and never built on graded prior work.

## Goal

Transform the brain's research methodology from informal heuristics into a numbered, auditable 7-step pipeline that:
- **Grounds** every run in semantically retrieved prior research (verified vs. unverified).
- **Decomposes** the query into typed signals and runs an explicit coherence check before hypothesizing.
- **Separates** source classes — training knowledge can seed hypotheses but cannot confirm claims.
- **Adversarially challenges** the leading hypothesis before delivery.
- **Reports** what was answered, what was assumed, and what remains open.

This is the Tier 0 cut. The full nation-state methodology (PIRs, ACH matrix, Human Review Queue, SNA, D&D analysis) is documented in `docs/intelligence/is-brain-methodology.md` and tracked as future work.

## Architecture

### Component Overview

```
┌──────────────────────────────────────────────────────────────┐
│                    Agent endpoint (v3/agent.py)              │
│                                                              │
│  ┌────────────────────┐    ┌───────────────────────────┐     │
│  │ Grounding pass     │───▶│ build_prompt()            │     │
│  │ fused_retrieve()   │    │ (injects past_research)   │     │
│  └────────────────────┘    └───────────────────────────┘     │
│            │                          │                      │
│            ▼                          ▼                      │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ IS brain (RESEARCH_PROMPT, 7-step methodology)         │  │
│  │   STEP 0  Decompose + Gap Analysis + Ask If Gaps       │  │
│  │   STEP 1  (merged into STEP 0)                         │  │
│  │   STEP 1  BOOTSTRAP / BROADEN (≥3 live searches)       │  │
│  │   STEP 2  PLAN (working assumptions, branches)         │  │
│  │   STEP 3  RECURSE (per-branch investigation)           │  │
│  │   STEP 4  ADVERSARIAL CHECK                            │  │
│  │   STEP 5  UNCONVENTIONAL BRANCH                        │  │
│  │   STEP 6  DELIVER (typed JSON output)                  │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### Grounding Pass — Data Flow

Implemented in `app/routers/v3/agent.py` immediately before the brain launch.

1. Call `fused_retrieve(query, limit=12, user_id=uid)` against Qdrant `research_memory`.
2. Group results by `run_id`. Take up to 4 prior run summaries.
3. Split into two buckets by `user_score`:
   - `user_score > 0` → **VERIFIED** (grade `"A"`), brain must affirm or update with fresh evidence.
   - else → **RELATED** (unverified), brain treats as leads to verify with live tools.
4. Inject both buckets into the `past_research` slot of `build_prompt()`.
5. **Non-fatal**: any retrieval failure logs a warning and the brain proceeds without context.

Previously, `past_research` was populated only when `parent_run_id` was set (explicit "Go Deeper"). Now every query is grounded.

### Prompt Restructure — `app/is_prompt.py`

The `RESEARCH_PROMPT` was rewritten from an informal `BOOTSTRAP → PLAN → RECURSE → DELIVER` flow into a numbered 7-step pipeline. Each step has explicit entry conditions, required outputs, and source-class rules.

#### STEP 0 — Decompose + Gap Analysis + Ask If Gaps

Decomposition and clarification are a single unified step. Clarification is the natural output of decomposition when it finds a gap, not a separate exception-triggered mechanism.

The brain extracts five signal types from the query:
- **Named entities** (people, brands, titles)
- **Descriptive signals** (visual, narrative, demographic cues)
- **Temporal signals** (year, "new", "latest", "upcoming")
- **Platform/medium signals** (streaming, billboard, podcast, etc.)
- **Intent** (identify? compare? track? due-diligence?)

A **live-query detection** runs in parallel: tokens like `new`, `recent`, `latest`, `upcoming`, `2025`, `2026` set `temporal_sensitivity=HIGH`, which prohibits training data as primary evidence.

**Gap analysis.** A query is **EXPLICIT** (skip asking) only if all of:
- Named entity is given (not merely described).
- Retrieval intent is not discovery.
- All required context (platform/medium, temporal anchor, etc.) is present.

If any gap is found, the brain asks about the **single highest-value gap** before researching:
- Discovery query → "Where did you see/hear this?" (highest value — collapses platform, medium, and temporal anchor at once).
- Follow-up depends on the answer: social → "Was it an ad or organic post?"; streaming → "One title or a promo reel?"
- **Maximum 3 questions total**, including any mid-research confirmation.

**Coherence check runs AFTER gap-fill**, not as a trigger for asking. "Can ALL signals plausibly belong to a SINGLE entity?"
- YES → proceed to STEP 1.
- NO → add `H_COMPOSITE` as the mandatory first hypothesis (e.g., "the signals come from different items in a streaming ad compilation"). If the discovery question has not yet been asked, ask it now alongside flagging `H_COMPOSITE`.

#### STEP 1 — BOOTSTRAP / BROADEN

New **source class policy** enforced here:
- `training_knowledge` is **hypothesis fuel only** — it cannot confirm a claim.
- `temporal_sensitivity=HIGH` → training data is prohibited as primary evidence.
- Every finding with `confidence ≥ 70` must originate from a live tool call.

Other rules:
- **Minimum 3 live searches** before any hypothesis ranking.
- Hypotheses are ranked by **signal coverage** (which hypothesis explains the most signals), not by corroboration count.

#### STEP 2 — PLAN

- `task_type` extended with `market_research` and `competitor_analysis`.
- New required field **working assumptions**: 2–4 explicit assumptions the branch plan depends on; flagged if any later turns out wrong.
- Retained: CELEBRITY IDENTIFICATION pattern, information-landscape map, branch list, tool gap assessment.

#### STEP 3 — RECURSE

Per-branch investigation. Behavior unchanged from the prior `RECURSE` step.

#### STEP 4 — ADVERSARIAL CHECK (new)

Runs before DELIVER:
- Actively search for evidence **inconsistent** with the leading hypothesis (not just supporting evidence).
- Verify each STEP 2 working assumption; mark any that turned out wrong.
- Look for simpler explanations consistent with the same evidence.

#### STEP 5 — UNCONVENTIONAL BRANCH

Renamed only. Behavior unchanged.

#### STEP 6 — DELIVER

Renamed. New output fields below.

## Output Schema Changes

Added to the brain's typed JSON output:

| Field | Type | Purpose |
|-------|------|---------|
| `temporal_sensitivity` | `"high" \| "low"` | Set in STEP 0; gates training-data use. |
| `pir_answered` | string | One sentence stating the specific question that was answered. |
| `working_assumptions` | string[] | Assumptions the research depended on (from STEP 2). |
| `source_class` (per finding) | enum | `live_search \| prior_research \| training_generated \| primary_official \| primary_self` |
| `open_questions` | array | `{question, status, note}` with status `provisionally_absent \| confirmed_absent \| needs_tool \| needs_clarification` |

**Confidence rules** (enforced by prompt, self-reported by brain):
- `confidence ≥ 80` → requires ≥ 2 independent `live_search` sources.
- `confidence 60–79` → single live source OR strong `prior_research`.
- `confidence ≥ 70` may **never** be assigned to a `training_generated` finding on a live query.

`build_prompt()` now formats `context_section` so verified prior research is shown with a `✓` marker plus the instruction "Affirm or update with fresh evidence", while unverified items are shown as leads to verify.

## Key Design Decisions

1. **Grounding pass is non-fatal.** If Qdrant or fusion retrieval fails, the brain runs without context rather than failing the query. Grounding is a quality lift, not a hard dependency.

2. **Coherence check inside the prompt, not as a pre-flight Haiku call.** Adding a separate model call before every brain launch would double latency and cost on the cold path. The brain is capable of recognizing signal incoherence when explicitly instructed, and STEP 0 makes the instruction unambiguous.

3. **Source class is self-reported.** The brain tags `source_class` per finding; the system does not externally validate it. This is pragmatic — adding a response validator that rejects high-confidence `training_generated` findings on live queries is straightforward future work, but the prompt-level rule already changes behavior.

4. **Clarification is the output of decomposition, not a separate trigger.** When decomposition finds a missing required signal, it asks about it — this is not a special case, it is the expected flow. The gap-fill question runs before the coherence check, not after. `H_COMPOSITE` is added when coherence fails after gap-fill. The trigger-based design (Trigger A, Trigger B) was replaced because it made clarification an exception rather than the default.

5. **Default is to ask; default is not to proceed.** A query is explicit (skip asking) only when all of: entity named not described, retrieval intent not discovery, all context present. The prior design defaulted to proceeding and triggered asking only on specific failures. The new design defaults to asking and skips only when unambiguously unnecessary. This matches intelligence tradecraft: confirm requirements before executing, not after discovering the requirement was wrong.

6. **Minimum 3 live searches is policy, not enforcement.** The prompt instructs ≥3 live tool calls in BROADEN, but the response processor does not validate the count post-hoc. Tool-call-count validation is logged as future work.

## Scope

This Tier 0 cut covers practical day-to-day intelligence use cases:
- Business intelligence — competitor analysis, market research, due diligence.
- Marketing intelligence — brand research, campaign analysis, ad-spot identification.
- Data retrieval — finding specific accurate information on live topics.
- General OSINT.

Out of scope (deferred):
- Adversarial / nation-state methodology in its full form.
- Formal PIR + ACH workflow with structured output contracts.
- Human Review Queue UI.
- SNA / D&D analytics.

## Explicitly Deferred

The following Tier 1 items from `docs/intelligence/is-brain-methodology.md` are **not** in this implementation:

| Item | Why deferred |
|------|--------------|
| PIR definition UI | Requires frontend work; current `pir_answered` field is the seed. |
| Human Review Queue UI | Requires queue model + frontend; not gated on the prompt change. |
| Formal ACH structured output contract | Larger schema change; benefits compound only after evidence-matrix validation lands. |
| Upstream source collapse dedup | Independent retrieval-side change; can ship without prompt rewrite. |
| PH naming variants node (`name_variants_ph()`) | Requires a new pipeline node + dictionary work. |
| Entity lineage + Wayback diff for PH entities | Requires Wayback integration + lineage store. |
| Negative-space checks for primary-self claims | Future ADVERSARIAL CHECK extension. |
| Replan trigger on prior-research collapse | Requires runtime hook between STEP 4 and STEP 5. |

These remain tracked in the living methodology doc.

## Testing Approach

### Manual regression cases

The two motivating failures should now produce different behavior:

1. **Amazon ad case** — query mixing show signals from a streaming promo compilation:
   - STEP 0 must detect `platform/medium: NOT PRESENT` as a gap.
   - Brain asks "Where did you see this?" before any research.
   - User answers → brain narrows hypothesis space.
   - Only then does BROADEN begin.

2. **Dyson case** — query about a recent product (`temporal_sensitivity=HIGH`):
   - STEP 0 sets `temporal_sensitivity="high"`.
   - At least 3 live tool calls must occur before any hypothesis ranking.
   - No finding with `confidence ≥ 70` may have `source_class="training_generated"`.

### Output schema verification

For any run, assert:
- `temporal_sensitivity` ∈ `{"high", "low"}`.
- `pir_answered` is a non-empty single sentence.
- `working_assumptions` is an array (may be empty when N/A but should not be missing on PLAN-bearing runs).
- Every finding includes `source_class` from the enum.
- `open_questions[].status` is one of the four allowed values.

### Grounding pass verification

- Run two related queries in sequence under the same `user_id`. Confirm the second run's prompt contains the first run's findings under `past_research`.
- Mark a finding from run 1 with positive `user_score`. Confirm it appears in run 2's prompt under `VERIFIED PRIOR RESEARCH` with the `✓` marker.
- Force a Qdrant outage (or pass an invalid `user_id`). Confirm the brain still runs and a warning is logged.

### Prompt-level smoke test

Inspect a rendered prompt for any query and confirm the seven step headings appear in order and the source-class + confidence rules block is present at the end.

## File References

- `app/routers/v3/agent.py` — grounding pass and `past_research` injection.
- `app/is_prompt.py` — 7-step `RESEARCH_PROMPT`, `build_prompt()` context formatter, output schema rules.
- `docs/intelligence/is-brain-methodology.md` — living methodology doc; Tier 1+ items tracked here.
- `app/pipeline/fusion/` — `fused_retrieve` and Qdrant `research_memory` integration consumed by the grounding pass.

## Changelog

| Date | Version | Change |
|------|---------|--------|
| 2026-05-10 | 1.1 | Merged STEP 0 (decomposition) and STEP 1 (clarification) into unified STEP 0. Clarification is now the output of gap analysis in decomposition, not a separate trigger-based mechanism. Default changed from "proceed unless triggered" to "ask unless explicit". Design Decision 4 updated; Design Decision 5 added. |
