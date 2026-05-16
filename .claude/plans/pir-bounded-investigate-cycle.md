# PIR-Bounded Recursive INVESTIGATE Cycle — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:[REDACTED:high-entropy-base64:27ch:hash=88f76bb3] to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the linear STEP 1–7 pipeline in is_prompt.py with a recursive INVESTIGATE(PIR) cycle that forces competing hypothesis exploration before committing, eliminates tunnel vision, and closes branches only when PIRs are confirmed/rejected.

**Architecture:** Prompt-only change (no Python code changes required for the cycle itself); domain hypothesis templates added to strategy files; existing dynamic injection slots preserved.

**Tech Stack:** Python (prompt engineering), pytest (prompt structure tests)

---

## Files in scope

| Path | Role |
|---|---|
| `/Users/rinehardramos/Projects/info-broker/app/is_prompt.py` | Core file — `RESEARCH_PROMPT` STEP 0–7 block replaced with INVESTIGATE(PIR) cycle (lines 53–382) |
| `/Users/rinehardramos/Projects/info-broker/tests/test_is_prompt.py` | New structure tests for INVESTIGATE cycle sections |
| `/Users/rinehardramos/Projects/info-broker/app/pipeline/strategies/media_identification.py` | Already has PIR template; verify alignment with new cycle vocabulary |
| `/Users/rinehardramos/Projects/info-broker/app/pipeline/strategies/person.py` | Already has PIR template; verify alignment |
| `/Users/rinehardramos/Projects/info-broker/app/pipeline/strategies/company.py` | Already has PIR template; verify alignment |
| `/Users/rinehardramos/Projects/info-broker/app/pipeline/strategies/analyzer.py` | Add factual/research PIR + hypothesis table (representative of factual-type) |

## Mapping: old STEPS → INVESTIGATE(PIR) cycle

| Old | New cycle phase | Notes |
|---|---|---|
| STEP 0 (DECOMPOSE / ASK) | Preserved as **STEP A — DECOMPOSE & SIGNALS** (runs once before the cycle starts) | Output feeds top-level PIR construction |
| STEP 0 ask_user logic | Preserved as **STEP B — GAP-FILL (one question max 3)** | Unchanged behavior |
| STEP 1 (implicit BOOTSTRAP) | Folded into **PIR DECLARATION** | Top-level PIR derived from signals + PreFlight |
| STEP 2 (BROADEN) | **HYPOTHESIZE + BROADEN** phases of cycle | Hypothesis-first; hard gate retained |
| STEP 3 (PLAN) | **Replaced** — plan is per-cycle, regenerated each RECURSE | No fixed one-shot plan |
| STEP 4 (RECURSE) | **RECURSE** phase | Re-hypothesize on dead end; spawn child PIR on new questions |
| STEP 5 (KAC + ADVERSARIAL) | Absorbed into **RANK** at each cycle | Penalty-based scoring against PIR criteria |
| STEP 6 (UNCONVENTIONAL) | Absorbed into **H_last** | Always-unconventional hypothesis declared upfront |
| STEP 7 (DELIVER) | **DELIVER** trigger | Only when top-level PIR confirmed/rejected/exhausted |

---

## Task 1 — Map current STEPS to INVESTIGATE phases and lock down call sites

- [ ] Read `/Users/rinehardramos/Projects/info-broker/app/is_prompt.py` lines 53–382 (the STEP 0–7 block).
- [ ] Confirm `RESEARCH_PROMPT.format(...)` placeholders in use: `query`, `context_section`, `max_depth`, `max_branches`, `today`, `tools_section`, `strategies_section`, `entity_strategy`, `techniques_section`, `research_plan`, `user_sources`, `meta_strategies_section`, `session_context`. ALL placeholders MUST survive the rewrite (lines 633–647).
- [ ] Read `/Users/rinehardramos/Projects/info-broker/app/is_brain.py` line 17 (`from app.is_prompt import build_prompt`) and line 76 (`build_prompt(`) to confirm no other caller passes additional placeholders.
- [ ] Verify no other module references `RESEARCH_PROMPT` directly: `grep -r "RESEARCH_PROMPT" /Users/rinehardramos/Projects/info-broker/app /Users/rinehardramos/Projects/info-broker/tests`.
- [ ] Confirm strategies with existing PIR templates: `person.py`, `media_identification.py`, `company.py`, `place.py`. The factual-type strategy `analyzer.py` lacks one and will get the factual hypothesis table in Task 4.
- [ ] Note: lines 9–52 (header, motto, temporal grounding, query, dynamic injection slots) MUST be preserved verbatim. Lines 384–479 (BUDGET, OUTPUT FORMAT, SOURCE CLASS RULES, CONFIDENCE RULES) MUST be preserved verbatim.
- [ ] No code commit for this task — investigation only.

## Task 2 — Write prompt structure tests (RED first)

- [ ] Open `/Users/rinehardramos/Projects/info-broker/tests/test_is_prompt.py`.
- [ ] Append the following test cases (full text, not placeholders):

```python
def _prompt():
    from app.is_brain import build_prompt
    return build_prompt(query="test", max_depth=3, max_branches=20)

def test_investigate_cycle_headers_present():
    p = _prompt()
    for header in [
        "STEP A — DECOMPOSE & SIGNALS",
        "STEP B — GAP-FILL",
        "STEP C — TOP-LEVEL PIR",
        "INVESTIGATE(PIR) CYCLE",
        "HYPOTHESIZE",
        "BROADEN",
        "RANK",
        "RECURSE",
        "DELIVER",
    ]:
        assert header in p, f"missing section: {header}"

def test_pir_format_block_present():
    p = _prompt()
    assert "PIR:" in p
    assert "MANDATORY:" in p
    assert "SUPPORTING:" in p
    assert "REJECT IF:" in p

def test_hypothesize_rules_present():
    p = _prompt()
    assert "minimum 3 hypotheses" in p.lower() or ">=3 hypotheses" in p.lower() or "≥3 hypotheses" in p
    assert "H_last" in p
    assert "unconventional" in p.lower()
    assert "no search until all hypotheses" in p.lower()

def test_broaden_hard_gate_present():
    p = _prompt()
    assert "hard gate" in p.lower()
    assert "minimum searches = number of hypotheses" in p.lower() or \
           "min searches = hypothesis count" in p.lower()

def test_rank_is_penalty_based():
    p = _prompt()
    assert "penalty-based" in p.lower()
    assert "not elimination" in p.lower()

def test_recurse_rehypothesize_on_dead_end():
    p = _prompt()
    assert "re-hypothesize" in p.lower()
    assert "child PIR" in p or "child_PIR" in p

def test_deliver_only_when_pir_settled():
    p = _prompt()
    assert "PIR confirmed" in p or "PIR is confirmed" in p
    assert "all hypotheses exhausted" in p.lower() or "hypotheses exhausted" in p.lower()

def test_old_linear_steps_removed():
    p = _prompt()
    # Old numeric step headers should not appear in the cycle block
    assert "### STEP 3 — PLAN" not in p
    assert "### STEP 6 — UNCONVENTIONAL" not in p
    assert "### STEP 7 — DELIVER" not in p

def test_log_cycle_instruction_present():
    p = _prompt()
    assert "log_cycle" in p
    assert "parent_cycle_id" in p

def test_preserved_dynamic_slots():
    # Ensure rewrite did not break placeholder substitution
    from app.is_brain import build_prompt
    p = build_prompt(query="X", max_depth=3, max_branches=20,
                    strategies_section="STRATX", session_context="SESSX")
    assert "STRATX" in p
    assert "SESSX" in p

def test_output_format_block_preserved():
    p = _prompt()
    assert "OUTPUT FORMAT" in p
    assert "pir_answered" in p
    assert "considered_alternatives" in p

def test_factual_hypothesis_template_in_analyzer():
    from app.pipeline.strategies import analyzer
    s = analyzer.STRATEGY
    assert "PIR:" in s
    assert "H_last" in s
    assert "contrarian" in s.lower() or "minority view" in s.lower()
```

- [ ] Run `pytest /Users/rinehardramos/Projects/info-broker/tests/test_is_prompt.py -x` and confirm new tests FAIL (the cycle headers do not exist yet).
- [ ] Commit: `test(is_prompt): add INVESTIGATE(PIR) cycle structure tests (red)`

## Task 3 — Rewrite STEP 0–7 block as the INVESTIGATE(PIR) cycle in `is_prompt.py`

- [ ] Open `/Users/rinehardramos/Projects/info-broker/app/is_prompt.py`.
- [ ] **DELETE lines 53–382** (the block beginning `## YOUR WORKFLOW` through end of `### STEP 7 — DELIVER` and its body, stopping immediately before `## BUDGET`).
- [ ] **INSERT** the following block in their place (line 53 onwards). The text below is the exact prompt content to write (do NOT paraphrase):

```
## YOUR WORKFLOW

Your investigation is a tree of **INVESTIGATE(PIR)** cycles. Every branch — top-level and every child question — runs the same five-phase cycle: HYPOTHESIZE → BROADEN → RANK → RECURSE → DELIVER. A cycle is bounded by its PIR (Priority Intelligence Requirement), not by a search count or depth limit. The cycle ends only when the PIR is confirmed, rejected, or all hypotheses are exhausted.

Three pre-cycle steps run ONCE before the top-level INVESTIGATE begins.

---

### STEP A — DECOMPOSE & SIGNALS (pre-cycle, runs once)

Extract every distinct signal from the user's query.

**RESEARCH GOAL extraction**: If the query starts with `[RESEARCH GOAL: ...]`, treat it as the explicit top-level PIR. Every branch is evaluated against it. The `pir_answered` output field must directly address this goal.

**Extract every distinct signal:**
- **Named entities**: people, companies, brands, places explicitly mentioned
- **Descriptive signals**: appearance, role, genre, tone, visual/audio cues
- **Temporal signals**: "new", "recent", "2025", "upcoming", "latest" → LIVE QUERY
- **Platform/medium signals**: where was this seen/heard?
- **Intent**: identify X / verify Y / find Z / compare A and B

**SIGNAL HIERARCHY (for IDENTIFICATION queries):**
Pick ONE primary signal — the entity/subject the user is trying to identify, not the most distinctive element.
1. Grammatical subject of the user's description is the primary ("girl in spiderman" → girl-as-Spider-Man is the subject; the shotgun-wielding man is a supporting detail).
2. Franchise/IP names ("spiderman", "marvel") are CONTEXT — they constrain the search space, they don't identify the entity.
3. Tag each signal: `primary | supporting | context`. The candidate MUST satisfy the primary signal in its primary role.

**LIVE QUERY DETECTION:**
If ANY temporal signal appears → `temporal_sensitivity = HIGH`
→ Training data CANNOT be used as primary evidence
→ Every confirmed claim requires at least one live tool result

---

### STEP B — GAP-FILL (pre-cycle, max 3 ask_user calls total)

A query is EXPLICIT (skip to STEP C) only if ALL are true:
  ✓ Entity is named, not described (proper noun / specific title / URL)
  ✓ Intent is retrieval ("find", "lookup", "get", "show"), not discovery ("what is", "who is", "identify")
  ✓ All context needed for the query type is present (platform, time period, format)

If ANY condition fails, ask about the single highest-value gap before declaring the PIR.

DISCOVERY QUERY (user saw/heard something unidentified — highest priority gap is platform):
→ ask_user("Where did you see or hear this?",
    options=["YouTube", "Facebook/Instagram/TikTok", "Netflix/Amazon/Disney+ (streaming)", "TV broadcast", "Cinema", "Other"])

Follow-up if social platform answered:
→ ask_user("Was it an ad, or organic content (a video/post/clip)?",
    options=["An ad", "A video/post/clip", "Not sure"])

Follow-up if streaming platform answered:
→ ask_user("Was it a trailer for one specific title, or a general platform promo showing multiple titles?",
    options=["Trailer for one specific title", "General platform promo / multiple titles", "Not sure"])

AMBIGUOUS ENTITY (description not name):
→ ask_user("Which [person/company/product] do you mean?", options=[<2-4 specific candidates from signal extraction>])

MISSING INTENT:
→ ask_user("What do you need?", options=["Identify what it is", "Find more about it", "Verify a claim", "Compare with alternatives"])

TEMPORAL AMBIGUITY on live query:
→ ask_user("Is this about something current or recent?",
    options=["Very recent (2025–2026)", "A few years ago", "Historical", "Not sure"])

---

### STEP C — TOP-LEVEL PIR DECLARATION (pre-cycle, runs once)

Construct the top-level PIR from STEP A signals + STEP B answers + PreFlight findings. Use the exact format:

```
PIR: [the specific question this cycle must answer — one sentence]
MANDATORY: [evidence that must be present to confirm — all must pass]
SUPPORTING: [evidence that increases confidence but is not required]
REJECT IF: [evidence that definitively closes this branch as "no"]
```

The PIR does NOT say which hypothesis is correct. It says what kind of evidence would settle the question either way.

If the query came with `[RESEARCH GOAL: ...]`, the PIR question is the research goal verbatim.

Use the domain strategy's PIR TEMPLATE (in strategies_section) as the starting structure for the MANDATORY/SUPPORTING/REJECT IF criteria, then customize for this specific query.

---

### INVESTIGATE(PIR) CYCLE

Run this cycle for the top-level PIR. Spawn a nested INVESTIGATE(child_PIR) for every new question raised mid-cycle. Same five phases at every level.

```
INVESTIGATE(PIR):
  HYPOTHESIZE   — ≥3 competing answers to THIS PIR (no search yet)
  BROADEN       — ≥1 dedicated search per hypothesis (hard gate)
  RANK          — score each hypothesis against PIR criteria (penalty-based)
  for each surviving hypothesis:
    RECURSE → deeper searches on this hypothesis
    PIR CONFIRMED?       → close branch, propagate up
    PIR REJECTED?        → close branch, mark dead end
    new question raised? → spawn child PIR → INVESTIGATE(child_PIR)
    dead end?            → re-hypothesize for SAME PIR (new angle, new BROADEN)
  all hypotheses exhausted? → ESCALATE: insufficient evidence
```

**MANDATORY CYCLE DECLARATION (before any search in any cycle):**
At the start of EVERY cycle — top-level and every child PIR — call:

log_cycle(pir="<the specific question this cycle answers>", hypotheses=["H1: <desc>", "H2: <desc>", "H3: <desc>", "H_last: <desc>"], cycle_id="<unique id>", parent_cycle_id="<parent id or empty for top-level>")

You CANNOT run any search before calling log_cycle for the current cycle. This is a hard gate. The cycle declaration registers your PIR and competing hypotheses in the investigation graph.

---

#### HYPOTHESIZE — formulate ≥3 competing answers (no search yet)

Generated at the START of every cycle, scoped to THIS PIR — not the global query.

Rules:
- **Minimum 3 hypotheses** — exactly 3 is acceptable for tight PIRs; more for ambiguous ones.
- **H_last is always unconventional** — the interpretation that obvious searches would miss. This is mandatory. It replaces the old "STEP 6 unconventional branch" — declared upfront, not as an afterthought.
- **Anti-anchor rule**: if H1 is the obvious answer, H2 through H_last must be GENUINELY COMPETING, not variations of H1. "H1: Spider-Noir show / H2: Spider-Noir trailer / H3: Spider-Noir behind-the-scenes" violates this — all three commit to Spider-Noir.
- **Scoped to PIR**: each hypothesis is a competing answer to THIS PIR's question, not a free association.
- **No search until all hypotheses are formulated** — you may not call log_cycle with fewer than 3 hypotheses, and you may not search before log_cycle.

Use the domain strategy's HYPOTHESIS TABLE (in strategies_section) as the H1/H2/H3/H_last starting points. The table gives the archetypes; you customize per query.

Domain archetypes (full templates live in each strategy file):

| Query type | H1 | H2 | H3 | H_last |
|---|---|---|---|---|
| Person | Obvious locale | Alternate geography (migration, diaspora) | Alias / name variant | No public trace (private/deceased) |
| Media | Literal franchise match | Actor-career (same person, different project) | Genre-blind (drop franchise signal) | Ad / campaign (not a show at all) |
| Company | Primary jurisdiction | Parent / subsidiary | Entity lineage (renamed/dissolved) | Foreign subsidiary or shell |
| Factual | Conventional answer | Contrarian / minority view | Domain-specific nuance | Recent development that overturns prior answer |

ANTI-PATTERN: matching "girl in [franchise]" to a [franchise] work where the lead is male and a woman appears only in a supporting role. The lead/title role must match the gender/description the user stated as PRIMARY. If H1 fails this subject-role coherence, demote H1 and elevate H2/H3.

---

#### BROADEN — minimum searches = number of hypotheses (hard gate)

For EACH hypothesis declared in log_cycle, run ≥1 dedicated search derived from that hypothesis.

- The search query is **hypothesis-specific**: ask "what would I search to confirm or deny H_n?" — not "what combination of signals do I search?".
- H1 search: what confirms the most obvious interpretation?
- H2 search: what confirms the alternate-geography / actor-career / parent-subsidiary interpretation?
- H3 search: what confirms the genre-blind / alias / lineage interpretation?
- H_last search: what confirms the unconventional interpretation (ad, no-trace, shell entity, recent overturn)?

Also call get_past_research(query) once per top-level cycle — prior research may have already settled the PIR.

**SOURCE CLASS POLICY:**
- `training_knowledge` = hypothesis fuel only. It tells you WHAT to look for, not WHAT IS TRUE.
- For LIVE QUERIES (temporal_sensitivity: HIGH): training data is PROHIBITED as primary evidence.
- Every finding with confidence ≥ 70% must come from a live tool call.
- Tag each finding's basis: `live_search` | `prior_research` | `training_generated`

**HARD GATE:** You CANNOT enter RANK until every declared hypothesis has at least one BROADEN search recorded. No partial ranking. No early commitment. The minimum searches = number of hypotheses, and the floor is 3.

The hypothesis with the strongest initial signal does NOT get its second search here — additional corroborating searches happen in RECURSE, not BROADEN. BROADEN is breadth; RECURSE is depth.

---

#### RANK — penalty-based scoring against PIR criteria (no elimination)

Score each hypothesis against the PIR criteria declared in STEP C / log_cycle:

- **MANDATORY criterion failure** → heavy score penalty. The hypothesis survives but ranks low. (Heuer's ACH: rank by fewest inconsistencies with MANDATORY criteria.)
- **SUPPORTING criterion match** → score boost.
- **REJECT IF triggered** → hypothesis closed as ruled out. NOT deleted from output — reported as "considered, ruled out, with reason".
- **Signal mismatches**:
  - PRIMARY signal mismatch → heavy penalty
  - SUPPORTING signal mismatch → moderate penalty
  - CONTEXT signal mismatch → light penalty (CONTEXT is often loose or misleading)
  - Medium-type mismatch (ad vs. show, from PreFlight) → heavy penalty when medium is known
  - Recency mismatch → moderate penalty if outside the stated window

**No candidate is eliminated from the result set.** Every hypothesis appears in output at its earned score. The top-ranked hypothesis or hypotheses proceed to RECURSE. Low-scoring hypotheses are reported as `considered_alternatives` with the inconsistencies that demoted them.

ANTI-PATTERN: ranking a candidate high because it matches CONTEXT + SUPPORTING while mismatching PRIMARY. PRIMARY mismatch is the heaviest penalty — a franchise + weapon match with wrong lead gender/medium scores BELOW a partial match that satisfies PRIMARY.

---

#### RECURSE — deepen each surviving hypothesis

For each hypothesis that survives RANK with a non-trivial score, run deeper searches:

1. **More specific queries** — narrow on the specific lead the BROADEN search surfaced.
   - Bad: "man on fire" (too broad)
   - Good: "man on fire netflix 2026 cast list actors"
2. **Crawl promising URLs** with run_web_crawl for full article content.
3. **Sub-branch on found entities** — cast member found → search their bio; producer found → search their projects.
4. **Verify against PIR MANDATORY** at every iteration. Each new finding updates hypothesis scores.

**Outcomes — evaluate after every RECURSE iteration:**

- **PIR CONFIRMED**: MANDATORY criteria satisfied with sufficient evidence → close branch, propagate the answer up. If this is the top-level PIR → DELIVER.

- **PIR REJECTED**: REJECT IF condition fired → close branch, mark as ruled out, propagate.

- **New question raised**: a finding raises a sub-question that must be settled before the parent can advance (e.g., "Is the Italy hit the same person as our PH subject?") → **spawn child PIR**, run INVESTIGATE(child_PIR) with its own MANDATORY/SUPPORTING/REJECT IF criteria, propagate result back to parent.

- **Dead end (no new signal after ≥2 searches on this hypothesis)**: do NOT close the PIR. **Re-hypothesize for the SAME PIR** — formulate a different angle (different locale, different name variant, different source type), call log_cycle again with the same PIR but new hypotheses, and run new BROADEN searches. The PIR is the boundary, not the hypothesis.

- **All hypotheses exhausted** (every hypothesis at this PIR has hit dead end after re-hypothesis): escalate as `insufficient_evidence`. Report what was found and what was ruled out. Close the branch.

**BLOCKED tool handling** (HTTP 403, paywall, rate limit, etc.):
- DO NOT retry the same dead end.
- The block reason is itself evidence: 403 on a specific record → subject may have restricted it; paywall → content exists and is commercially valued; DNS failure → domain may be taken down.
- Run the PIVOT PROTOCOL:
  1. GOAL — what was this tool supposed to surface?
  2. ALTERNATIVES — which available tools satisfy the same goal?
     employment → run_apollo_search | run_linkedin_profile_search | run_web_search("site:linkedin.com <name>")
     business registry → run_opencorporates | run_web_crawl on registry URL | run_sec_edgar | run_wayback_machine
     PH government (403) → run_ph_bir | run_ph_prc_license_search | run_ph_comelec_voter_search
     email discovery → run_email_enumerator | run_hunter_io | run_reverse_lookup
     social media → run_username_enumerator | run_facebook_pages | run_messaging_check
  3. PATTERN — ≥2 failures in same locale/category → reassess: is the subject even findable there? Consider name_origin_lookup + migration_corridor_lookup if locale assumption may be wrong.
  4. ADAPT — choose ONE: alternative tool, different angle, scope expansion, or ask_user if ≥3 tools blocked with no alternatives.

**MID-RESEARCH CONFIRMATION** (during RECURSE, after a strong candidate emerges and you are genuinely uncertain between two leading hypotheses):
→ ask_user("Was this [specific hypothesis — one sentence]?", options=["Yes", "No", "Not sure"])
Binary confirmation only. One question. Counts against the max-3 ask_user budget.

**MULTIMEDIA ENRICHMENT** (media identification, celebrity, product queries):
- YouTube trailer / official video found → include URL, set media_type="video".
- Official image / poster / screenshot corroborating the finding → set image_url, media_type="image".
- For streaming shows/films: search "[title] official trailer YouTube" and include the URL.
- For person identification: include a verified headshot URL if available (official source only).
Media assets help users CONFIRM the finding matches what they saw — prioritize them when relevant.

Planning re-runs at each RECURSE iteration — the branch list and search priorities update as evidence accumulates. There is no fixed plan from a one-shot planning step; the plan is always current.

---

#### DELIVER — only when top-level PIR is settled

Trigger DELIVER (and emit the OUTPUT FORMAT JSON below) only when ONE of these holds at the **top-level** PIR:

- **PIR CONFIRMED** — MANDATORY criteria met with sufficient coverage; leading hypothesis is the answer.
- **PIR REJECTED** — REJECT IF fired on every candidate; report what was ruled out and why.
- **All top-level hypotheses exhausted** — every hypothesis hit dead end after re-hypothesis; emit `insufficient_evidence` report.

Do NOT deliver from a child cycle. Child PIRs propagate their result up to the parent; only the top-level cycle delivers.

DELIVER output must include:
- All surviving hypotheses with their PIR scores
- Ruled-out hypotheses with the evidence that ruled them out (in `considered_alternatives`)
- Child PIR results that contributed to parent settlement (as findings)
- For identification queries: SPECIFIC_DETAIL_VERIFICATION — each user-described detail logged as verified/unverified

**Pre-DELIVER negative-space check** (person/company investigations):
For every PRIMARY-SELF claim (subject's own assertion about themselves):
  → "If this claim is true, where would it leave an independent record?"
  → Did you find that record? If not → mark as `provisionally_absent` not confirmed.
  Examples:
  - Claims Forbes-listed entrepreneur → search Forbes directly, not their bio
  - Claims Stanford MBA → check Stanford alumni directory
  - Claims founded Company X → check SEC/DTI/Companies House for founding record
  Any claim only on the subject's own properties → confidence cap 50%, flag as `primary_self` source class.
```

- [ ] Lines 384+ (`## BUDGET`, `## OUTPUT FORMAT`, `SOURCE CLASS RULES`, `CONFIDENCE RULES`) remain unchanged.
- [ ] Lines 9–52 (header, motto, temporal grounding, dynamic injection slots) remain unchanged.
- [ ] Run `pytest /Users/rinehardramos/Projects/info-broker/tests/test_is_prompt.py -x` — all Task 2 tests now GREEN (except `test_factual_hypothesis_template_in_analyzer`, addressed in Task 4).
- [ ] Run `python -c "from app.is_brain import build_prompt; print(build_prompt(query='hi', max_depth=3, max_branches=20)[:200])"` from `/Users/rinehardramos/Projects/info-broker` to confirm `.format()` has no missing/extra placeholders.
- [ ] Commit: `refactor(is_prompt): replace linear STEP 0-7 with INVESTIGATE(PIR) cycle`

## Task 4 — Verify domain templates and add factual template to analyzer.py

The strategies `person.py`, `media_identification.py`, `company.py`, and `place.py` already carry PIR TEMPLATE + HYPOTHESIS TABLE blocks aligned with the new cycle (verified in Task 1). Only the factual/research strategy needs the template added.

- [ ] **Verify existing four strategies** — open each and confirm H1/H2/H3/H_last labels match the archetypes in the rewritten prompt. NO edits expected unless a label drifted.
  - `/Users/rinehardramos/Projects/info-broker/app/pipeline/strategies/person.py` — locale → migration → alias → no-trace ✓
  - `/Users/rinehardramos/Projects/info-broker/app/pipeline/strategies/media_identification.py` — franchise → actor-career → genre-blind → advertisement ✓
  - `/Users/rinehardramos/Projects/info-broker/app/pipeline/strategies/company.py` — jurisdiction → parent → lineage → shell ✓
  - `/Users/rinehardramos/Projects/info-broker/app/pipeline/strategies/place.py` — verify present; if missing, add geography template.

- [ ] **Add factual template to `/Users/rinehardramos/Projects/info-broker/app/pipeline/strategies/analyzer.py`** — insert at the top of `STRATEGY` (after `=== ... ===` header line). Exact text:

```
--- PIR TEMPLATE ---

PIR: What is the verified answer to the user's factual or analytical question?
MANDATORY: At least one authoritative live source corroborates the answer | Answer addresses the literal question asked
SUPPORTING: Second independent source agrees | Source is primary (paper, registry, official statement) not secondary | Date of source is within the relevant time window
REJECT IF: All authoritative sources contradict the proposed answer, OR no source can be found after H1–H_last searched

--- HYPOTHESIS TABLE ---

H1 (conventional answer): The textbook / widely accepted answer
  search: run_web_search("[question]") | run_wikipedia_api("[topic]")

H2 (contrarian / minority view): A credible minority position that disagrees with H1
  search: "[topic] criticism" | "[topic] alternative view" | "[topic] debate"
  This is not contrarianism for its own sake — only credible dissent.

H3 (domain-specific nuance): The answer depends on a definitional or scope distinction H1 glosses over
  search: "[topic] definition" | "[topic] scope" | "[topic] [domain] specific"
  Example: "Is X legal?" — H3 explores jurisdiction-specific variation.

H_last (recent development overturns prior answer): A 2024–2026 finding, ruling, or release changes the conventional answer
  search: run_google_news("[topic] 2025") | run_arxiv_search("[topic]") | "[topic] [current year] update"
  Trigger: temporal_sensitivity HIGH or topic is in a fast-moving domain (AI, regulation, geopolitics).
```

- [ ] Run `pytest /Users/rinehardramos/Projects/info-broker/tests/test_is_prompt.py -x` — all tests GREEN including `test_factual_hypothesis_template_in_analyzer`.
- [ ] Commit: `feat(strategies): add factual PIR + hypothesis template to analyzer strategy`

## Task 5 — End-to-end smoke test (mocked LLM, Spider-Noir case)

- [ ] Create `/Users/rinehardramos/Projects/info-broker/tests/test_pir_cycle_e2e.py`:

```python
"""E2E smoke test: verify INVESTIGATE(PIR) prompt elicits ≥3 hypotheses structure.

Uses a stub that records the prompt; asserts the structural contract the LLM will see.
"""

import re

def test_spider_noir_prompt_carries_media_hypothesis_table():
    from app.is_brain import build_prompt
    from app.pipeline.strategies import media_identification

    prompt = build_prompt(
        query="new netflix series with a girl in a spiderman outfit holding a shotgun",
        max_depth=3,
        max_branches=20,
        strategies_section=media_identification.STRATEGY,
    )

    # Cycle structure visible
    assert "INVESTIGATE(PIR) CYCLE" in prompt
    assert "HYPOTHESIZE" in prompt
    assert "BROADEN" in prompt
    # Media archetypes injected via strategy
    assert "franchise-literal" in prompt or "H1 (franchise" in prompt
    assert "actor-career" in prompt or "H2 (actor-career" in prompt
    assert "advertisement" in prompt.lower()
    # PIR boundary
    assert "REJECT IF" in prompt
    # Hard gate present
    assert "hard gate" in prompt.lower()

def test_prompt_orders_hypothesize_before_broaden_before_rank():
    from app.is_brain import build_prompt
    p = build_prompt(query="x", max_depth=3, max_branches=20)
    h = p.index("HYPOTHESIZE")
    b = p.index("BROADEN")
    r = p.index("RANK")
    rec = p.index("RECURSE")
    d = p.index("DELIVER")
    assert h < b < r < rec < d, "INVESTIGATE phases must appear in order"

def test_prompt_forbids_search_before_log_cycle():
    from app.is_brain import build_prompt
    p = build_prompt(query="x", max_depth=3, max_branches=20)
    assert "CANNOT run any search before calling log_cycle" in p

def test_h_last_is_always_unconventional():
    from app.is_brain import build_prompt
    p = build_prompt(query="x", max_depth=3, max_branches=20)
    # H_last must be described as unconventional and mandatory
    assert re.search(r"H_last.*unconventional", p, re.DOTALL | re.IGNORECASE)

def test_dead_end_does_not_close_pir():
    from app.is_brain import build_prompt
    p = build_prompt(query="x", max_depth=3, max_branches=20)
    assert "re-hypothesize for the SAME PIR" in p or "re-hypothesize for SAME PIR" in p

def test_child_pir_spawns_for_new_questions():
    from app.is_brain import build_prompt
    p = build_prompt(query="x", max_depth=3, max_branches=20)
    assert "spawn child PIR" in p
    assert "INVESTIGATE(child_PIR)" in p
```

- [ ] Run `pytest /Users/rinehardramos/Projects/info-broker/tests/test_pir_cycle_e2e.py -x` — all GREEN.
- [ ] Run full prompt test sweep: `pytest /Users/rinehardramos/Projects/info-broker/tests/test_is_prompt.py /Users/rinehardramos/Projects/info-broker/tests/test_pir_cycle_e2e.py -v`.
- [ ] Run `pytest /Users/rinehardramos/Projects/info-broker/tests/test_is_brain.py -x` to confirm no regression in existing brain tests.
- [ ] Commit: `test(is_prompt): add E2E structural smoke test for INVESTIGATE(PIR) cycle`

---

## Out of scope (explicitly NOT in this plan)

- Removal of `app/pipeline/retrieval/` package (mentioned in spec "Deleted" — separate ticket; this plan is prompt-only as the user instructed).
- `app/routers/v3/agent.py` `prefetch_branches()` removal (separate ticket).
- `app/pipeline/fusion/constraint_filter.py` deletion (separate ticket).
- `query_explanatory_score()` PIR-criteria signature change in `scorecard.py` (separate ticket, coordinate with fusion module owner).
- Python-side cycle orchestration (the cycle runs inside the LLM's reasoning loop, driven by the prompt; no Python state machine for the cycle itself).

## Boundary notes for the architect

- `is_prompt.py` owns prompt text. `is_brain.py` owns the LLM call. Strategy modules own per-domain templates injected via `strategies_section`. These boundaries are preserved.
- Hypothesis tables live in strategy files so each domain can be evolved independently without touching `is_prompt.py`.
- The `log_cycle` MCP tool already exists (line 47 of current prompt); no new tool is introduced. If the tool's signature changes, that is a separate coordination item with the MCP server owner.
- Coordination doc: if `docs/superpowers/coordination.md` or equivalent exists, announce the prompt rewrite there before Task 3 lands (cross-cutting change to brain behavior affects everyone working downstream of the brain).
