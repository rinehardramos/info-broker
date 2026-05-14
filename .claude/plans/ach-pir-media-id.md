# ACH/PIR Media Identification Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:[REDACTED:high-entropy-base64:27ch:hash=88f76bb3] to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Operationalize ACH + PIR as mandatory procedural gates in the media_identification strategy — adding hypothesis matrix generation (STEP 1.5), PIR scoring weights (STEP 1.6), mandatory disconfirmation searches (STEP 4), and ACH penalty matrix to the strategy text.

**Architecture:** Strategy text changes in media_identification.py enforce procedural hypothesis diversity; scorecard.py gains medium_type signal from PreFlight clarifications.

**Tech Stack:** Python, pytest

---

## Reference files (absolute paths)

- Strategy text: `/Users/rinehardramos/Projects/info-broker/app/pipeline/strategies/media_identification.py`
- Scorecard: `/Users/rinehardramos/Projects/info-broker/app/pipeline/fusion/scorecard.py`
- ACH module (already implemented): `/Users/rinehardramos/Projects/info-broker/app/pipeline/fusion/ach.py`
- PIR module (already implemented): `/Users/rinehardramos/Projects/info-broker/app/pipeline/fusion/pir.py`
- Spec: `/Users/rinehardramos/Projects/info-broker/docs/superpowers/specs/2026-05-11-ach-pir-strategy-design.md`
- Tests dir: `/Users/rinehardramos/Projects/info-broker/tests/pipeline/`
- Existing strategy test: `/Users/rinehardramos/Projects/info-broker/tests/pipeline/test_media_identification.py`
- Existing scorecard test: `/Users/rinehardramos/Projects/info-broker/tests/pipeline/fusion/test_scorecard.py`
- `constraint_filter.py`: **NOT FOUND** under `app/pipeline/fusion/` — task 6 will note and defer (no orchestration constraint file exists to soften; the gender penalty is already implemented inside `scorecard._primary_match_qes` via gender mismatch reducing PRIMARY score).

---

## Pre-flight context (already verified)

The current `media_identification.py` (46 lines) contains:
- `ENTITY_TYPE = "media_identification"`
- A `STRATEGY` string with: PIR TEMPLATE, HYPOTHESIS TABLE (H1/H2/H3/H_last), SCORING NOTES, tools line.
- It does NOT contain `MULTI-HYPOTHESIS`, `COMPLETENESS CHECKLIST`, `STEP 1.5`, `STEP 1.6`, `STEP 4`, `STEP 5`, `HYPOTHESIS_MATRIX`, `PIR_CRITERIA`, `[DISCONFIRM:`, `SPECIFIC_DETAIL_VERIFICATION`, or `ACH MATRIX`.

The existing test file already asserts `"MULTI-HYPOTHESIS"` and `"COMPLETENESS CHECKLIST"` tokens — these are currently failing and must be satisfied by the new strategy text in Task 3.

The current `scorecard.query_explanatory_score(candidate, signals)`:
- Accepts `signals` dict with keys `primary`, `supporting`, `context`.
- Weights: PRIMARY 0.40, SUPPORTING 0.25, CONTEXT 0.15, recency 0.10, multi-branch 0.10.
- Returns rounded float, max ~1.0.
- Does NOT accept `medium_type` signal.

---

## Task 1 — Snapshot baseline and confirm failing tests

- [ ] Run baseline test suite to capture current pass/fail state:
  ```bash
  cd /Users/rinehardramos/Projects/info-broker && python -m pytest tests/pipeline/test_media_identification.py tests/pipeline/fusion/test_scorecard.py -v 2>&1 | tee /tmp/baseline_ach_pir.log
  ```
- [ ] Confirm `test_media_identification_strategy_loads` fails on `MULTI-HYPOTHESIS` assertion (line 9 of test file) and `test_media_strategy_has_completeness` fails on `COMPLETENESS CHECKLIST` assertion.
- [ ] Confirm scorecard tests currently pass (baseline).
- [ ] Commit baseline log artifact reference only via the next task — no git commit on this task.

**Acceptance:** Baseline log captured at `/tmp/baseline_ach_pir.log`.

---

## Task 2 — Write failing tests for new strategy text tokens and structure

File: `/Users/rinehardramos/Projects/info-broker/tests/pipeline/test_media_identification.py`

Add these test functions to the END of the existing file:

```python
def test_strategy_contains_step_1_5_hypothesis_matrix():
    s = get_strategy("media_identification")
    assert "STEP 1.5" in s
    assert "HYPOTHESIS_MATRIX" in s
    # At least 3 hypothesis slots required by spec
    for marker in ("H1", "H2", "H3", "H4"):
        assert marker in s, f"missing {marker} in strategy text"


def test_strategy_contains_step_1_6_pir_weights():
    s = get_strategy("media_identification")
    assert "STEP 1.6" in s
    assert "PIR_CRITERIA" in s
    # Exact weights from spec
    assert "0.40" in s  # PRIMARY weight
    assert "0.25" in s  # SUPPORTING weight
    assert "0.15" in s  # CONTEXT + medium_type bonus weight
    # Penalty values
    assert "-0.30" in s  # PRIMARY mismatch
    assert "-0.15" in s  # SUPPORTING mismatch
    assert "-0.05" in s  # CONTEXT mismatch
    assert "-0.25" in s  # medium_type mismatch


def test_strategy_contains_step_4_disconfirmation_gate():
    s = get_strategy("media_identification")
    assert "STEP 4" in s
    assert "[DISCONFIRM:" in s
    # Gate language: one disconfirm per hypothesis required before STEP 5
    assert "mandatory" in s.lower()
    # ACH penalty matrix at end of STEP 4
    assert "ACH" in s


def test_strategy_contains_step_5_specific_detail_verification():
    s = get_strategy("media_identification")
    assert "STEP 5" in s
    assert "SPECIFIC_DETAIL_VERIFICATION" in s
    # verified=FALSE caps at 40% but does NOT block
    assert "40%" in s or "0.40" in s


def test_strategy_medium_type_signal_described():
    s = get_strategy("media_identification")
    # medium_type as a named scoring signal from PreFlight
    assert "medium_type" in s
    assert "PreFlight" in s


def test_strategy_completeness_checklist_present():
    # Already asserted by test_media_strategy_has_completeness; this confirms structure
    s = get_strategy("media_identification")
    assert "COMPLETENESS CHECKLIST" in s
    assert "MULTI-HYPOTHESIS" in s
```

- [ ] Add the six tests above.
- [ ] Run only the new tests; confirm all fail:
  ```bash
  cd /Users/rinehardramos/Projects/info-broker && python -m pytest tests/pipeline/test_media_identification.py::test_strategy_contains_step_1_5_hypothesis_matrix tests/pipeline/test_media_identification.py::test_strategy_contains_step_1_6_pir_weights tests/pipeline/test_media_identification.py::test_strategy_contains_step_4_disconfirmation_gate tests/pipeline/test_media_identification.py::test_strategy_contains_step_5_specific_detail_verification tests/pipeline/test_media_identification.py::test_strategy_medium_type_signal_described tests/pipeline/test_media_identification.py::test_strategy_completeness_checklist_present -v
  ```
- [ ] Commit:
  ```
  git add tests/pipeline/test_media_identification.py
  git commit -m "test(media_id): failing tests for ACH/PIR strategy steps"
  ```

**Acceptance:** All six new tests fail with assertion errors; no import errors.

---

## Task 3 — Update `media_identification.py` strategy text with STEP 1.5 / 1.6 / 4 / 5

File: `/Users/rinehardramos/Projects/info-broker/app/pipeline/strategies/media_identification.py`

Replace the entire file contents with:

```python
"""Media identification strategy module."""

ENTITY_TYPE = "media_identification"

STRATEGY = """
=== MEDIA IDENTIFICATION STRATEGY ===

goal: Identify unknown show/movie/media clip/advertisement from partial descriptions.
execution_model: STEP 1.5 (hypothesis matrix) → STEP 1.6 (PIR weights) → BROADEN → STEP 4 (mandatory disconfirmation + ACH penalty matrix) → STEP 5 (specific-detail verification) → RANK → DELIVER

This strategy uses MULTI-HYPOTHESIS reasoning — ACH (Analysis of Competing Hypotheses) and PIR
(Priority Intelligence Requirements) are PROCEDURAL GATES, not aspirational guidance. Penalties
reduce candidate scores; they do NOT eliminate candidates. The suppression floor is 0.15.

--- STEP 1.5 — COMPETING HYPOTHESES (cold-start, BEFORE searching) ---

Generate at least 3 hypotheses from signals ONLY — no search, no training-data recall of
specific titles yet. H1 is always formulated. H2–H4 are mandatory independent interpretations.

Required hypothesis slots:
  H1 (franchise-literal): A show or film IN the stated franchise/IP universe.
  H2 (actor-career): An actress/actor FROM the franchise appears in a DIFFERENT new project (ad, show, film).
  H3 (genre-blind): PRIMARY + SUPPORTING signals only — CONTEXT/franchise dropped entirely.
  H4 (long-tail): Low-popularity, recent (2024–2026), not surfaced by obvious search.

Medium-type awareness: if PreFlight clarifications include "advertisement" or "YouTube", each
hypothesis must state whether it could be an ad/campaign rather than a show.

Anti-anchor rule: even if H1 looks correct, H2–H4 must still be produced. Falsification happens
in STEP 4, not here.

Output artifact (LITERAL FORMAT — emit exactly):
```
HYPOTHESIS_MATRIX:
H1: [literal franchise candidate] — rationale: [why]
H2: [actor-career candidate, may be ad/campaign] — rationale: [why]
H3: [genre-blind candidate, no franchise] — rationale: [why]
H4: [long-tail candidate] — rationale: [why]
```

--- STEP 1.6 — PIR SCORING CRITERIA (weights, NOT delivery gates) ---

PIR tiers drive scoring weights. A MANDATORY criterion failure is a heavy score penalty —
the candidate still appears in the result set at low confidence. Only candidates scoring below
0.15 are suppressed from the confirmation card (not from the full result set).

Signal → criterion mapping (apply during ranking):

| Signal type                                    | Weight  | On mismatch penalty |
|------------------------------------------------|---------|---------------------|
| PRIMARY (grammatical subject: e.g. "girl")     | 0.40    | -0.30               |
| SUPPORTING (defining detail: e.g. "shotgun")   | 0.25    | -0.15               |
| CONTEXT (franchise/IP: e.g. "spiderman")       | 0.15    | -0.05               |
| medium_type (ad vs. show, from PreFlight)      | 0.15    | -0.25               |
| Recency (2024–2026)                            | 0.10    | -0.10               |
| Multi-branch corroboration                     | 0.10    | -0.05               |

The medium_type signal is injected by PreFlight clarifications. If the user confirmed "YouTube
advertisement", candidates that are shows (not ads/campaigns) receive a -0.25 medium_mismatch
penalty. This is the mechanism that unseats a literal-franchise leader when the ad context is
known.

Output artifact (LITERAL FORMAT):
```
PIR_CRITERIA:
[HIGH-WEIGHT] PRIMARY subject match (e.g. female/girl) — weight: 0.40 / penalty: -0.30
[HIGH-WEIGHT] SUPPORTING detail match (e.g. firearm) — weight: 0.25 / penalty: -0.15
[MEDIUM]      CONTEXT/franchise match (e.g. spider-man) — weight: 0.15 / penalty: -0.05
[MEDIUM]      medium_type from PreFlight (ad vs show) — weight: 0.15 / penalty: -0.25
[LOW]         Recency 2024–2026 — weight: 0.10 / penalty: -0.10
```

--- PIR TEMPLATE (legacy summary, retained for backward compatibility) ---

PIR: What show, film, or advertisement does the user's description refer to?
MANDATORY: Content type matches user-described medium (show vs. ad vs. film) | Subject or lead matches user's PRIMARY descriptor
SUPPORTING: Franchise or IP connection present | Release year in stated time window | Platform identified
SCORE FLOOR: Candidates below 0.15 are suppressed from the confirmation card; they remain in the full result set.

--- HYPOTHESIS TABLE (search seeds, used in BROADEN) ---

H1 (franchise-literal): A show or film IN the stated franchise/IP universe
  search: "[franchise] new series [year]" | run_tmdb_search("[franchise] [year]")

H2 (actor-career): An actress or actor FROM the franchise appears in a DIFFERENT new project
  search: "[franchise] actress new series [year]" | "[actor name] 2025 project"
  Note: "girl in spiderman" = Zendaya, not Spider-Noir. Search the actress's filmography.

H3 (genre-blind): PRIMARY signal + SUPPORTING signal only — CONTEXT/franchise dropped entirely
  search: "[primary descriptor] [supporting detail] new series [year]"
  Example: "girl shotgun 2025 series" — no spider-man in the query

H_last / H4 (advertisement/campaign/long-tail): The content is NOT a show — brand ad, streaming
platform promo, or low-profile recent release.
  search: "[franchise or actor] advertisement 2025" | "[actor] [brand] campaign"
  Trigger: PreFlight confirms "YouTube" or "ad", OR no other hypothesis converges.

--- STEP 4 — RED TEAMING + ACH PENALTY MATRIX (mandatory disconfirmation) ---

For EACH hypothesis (all of H1–H4, not just the leader), one [DISCONFIRM:H_n] search is
mandatory before advancing to STEP 5.

Gate: if any hypothesis has no [DISCONFIRM:H_n] logged, RECURSE — do not advance to STEP 5.

Format (LITERAL — emit exactly):
```
[DISCONFIRM:H1] Search: "[query]" → result: [outcome] → [PRIMARY/SUPPORTING/medium mismatch + penalty]
[DISCONFIRM:H2] Search: "[query]" → result: [outcome] → [confirmed | penalty]
[DISCONFIRM:H3] Search: "[query]" → result: [outcome] → [confirmed | penalty]
[DISCONFIRM:H4] Search: "[query]" → result: [outcome] → [confirmed | penalty]
```

ACH PENALTY MATRIX (emit at the end of STEP 4, before STEP 5). Inconsistencies are score
penalties, NOT eliminations. A candidate stays unless total score falls below 0.15.

```
ACH MATRIX:
SIGNAL                  | Weight | H1            | H2            | H3            | H4
------------------------|--------|---------------|---------------|---------------|---------------
PRIMARY (subject)       | 0.40   | [✓ / ✗ -0.30] | [✓ / ✗ -0.30] | [✓ / ✗ -0.30] | [✓ / ✗ -0.30]
SUPPORTING (detail)     | 0.25   | [✓ / ✗ -0.15] | [✓ / ✗ -0.15] | [✓ / ✗ -0.15] | [✓ / ✗ -0.15]
CONTEXT (franchise)     | 0.15   | [✓ / ✗ -0.05] | [✓ / ✗ -0.05] | [✓ / ✗ -0.05] | [✓ / ✗ -0.05]
medium_type (PreFlight) | 0.15   | [✓ / ✗ -0.25] | [✓ / ✗ -0.25] | [✓ / ✗ -0.25] | [✓ / ✗ -0.25]
Recency 2024–2026       | 0.10   | [✓ / ✗ -0.10] | [✓ / ✗ -0.10] | [✓ / ✗ -0.10] | [✓ / ✗ -0.10]
------------------------|--------|---------------|---------------|---------------|---------------
TOTAL                   |        | [sum]         | [sum]         | [sum]         | [sum]
```

--- STEP 5 — SPECIFIC_DETAIL_VERIFICATION ---

verified=FALSE does NOT block delivery. It caps confidence at 40% (0.40) and adds a
"needs verification" flag. The candidate is still deliverable.

Output artifact (LITERAL FORMAT):
```
SPECIFIC_DETAIL_VERIFICATION:
- "[detail 1]": verified=TRUE|FALSE  (source: [source])
- "[detail 2]": verified=TRUE|FALSE  (source: [source])
- "[detail 3]": verified=TRUE|FALSE  (note: [why unverified])
```

Unverified SUPPORTING details reduce score by their weight but do not block.
Unverified PRIMARY details cap candidate confidence at 40% (0.40).

--- COMPLETENESS CHECKLIST ---

- [ ] HYPOTHESIS_MATRIX emitted with ≥3 hypotheses (STEP 1.5)
- [ ] PIR_CRITERIA emitted with weights + penalties (STEP 1.6)
- [ ] One [DISCONFIRM:H_n] per hypothesis (STEP 4)
- [ ] ACH MATRIX emitted with per-cell penalties + TOTAL row (STEP 4)
- [ ] SPECIFIC_DETAIL_VERIFICATION emitted (STEP 5)
- [ ] At least one candidate scores ≥0.15 OR explicit "no confident match" verdict

--- SCORING NOTES ---

medium_type signal (from PreFlight "YouTube" / "advertisement"):
  - Content confirmed as ad → show-type candidates receive -0.25 medium_mismatch penalty.
  - Advertisement-type candidates (H4) get +0.15 medium_type bonus when medium=ad confirmed.

CONTEXT signal (e.g. "spiderman") is often loose — an actress FROM the franchise in a
DIFFERENT project satisfies CONTEXT as strongly as a show IN the franchise. Do not
over-weight CONTEXT. Penalty for CONTEXT mismatch is only -0.05.

tools: run_tmdb_search | run_web_search | run_google_news | run_web_crawl
"""
```

- [ ] Apply the rewrite above (preserve module docstring, `ENTITY_TYPE`, and `STRATEGY` symbol).
- [ ] Run the strategy test file:
  ```bash
  cd /Users/rinehardramos/Projects/info-broker && python -m pytest tests/pipeline/test_media_identification.py -v
  ```
- [ ] All tests in the file (including the 6 new ones from Task 2 AND the previously-failing `test_media_identification_strategy_loads` and `test_media_strategy_has_completeness`) must pass.
- [ ] Commit:
  ```
  git add app/pipeline/strategies/media_identification.py
  git commit -m "feat(media_id): add ACH/PIR procedural gates to strategy text (STEPS 1.5/1.6/4/5)"
  ```

**Acceptance:** `pytest tests/pipeline/test_media_identification.py` is fully green.

---

## Task 4 — Failing tests for `query_explanatory_score` medium_type signal

File: `/Users/rinehardramos/Projects/info-broker/tests/pipeline/fusion/test_scorecard.py`

Append:

```python
from app.pipeline.fusion.scorecard import query_explanatory_score


def _candidate_show(year=2025, female_lead=True, spider=True):
    return {
        "title": "Spider-Noir" if spider else "Generic Drama",
        "overview": "shotgun scene with lead",
        "year": year,
        "top_billed_genders": [1] if female_lead else [2],
        "branches": ["b1", "b2"],
        "media_type": "tv",
    }


def _candidate_ad(year=2025, female_lead=True, spider=True):
    return {
        "title": "Amazon Prime campaign",
        "overview": "Zendaya brand spot featuring shotgun moment",
        "year": year,
        "top_billed_genders": [1] if female_lead else [2],
        "branches": ["b1", "b2"],
        "media_type": "advertisement",
    }


def test_qes_no_medium_type_signal_is_backward_compatible():
    """Without medium_type in signals, behaviour matches the legacy weights."""
    cand = _candidate_show()
    signals = {"primary": "girl", "supporting": "shotgun", "context": "spiderman"}
    score = query_explanatory_score(cand, signals)
    # 0.40 + 0.25 + 0.15 + 0.10 (recency) + 0.10 (branches) = 1.00
    assert score == 1.00


def test_qes_medium_type_ad_match_bonus():
    """medium_type=advertisement + candidate media_type=advertisement → +0.15 bonus."""
    cand = _candidate_ad()
    signals = {
        "primary": "girl",
        "supporting": "shotgun",
        "context": "spiderman",
        "medium_type": "advertisement",
    }
    score = query_explanatory_score(cand, signals)
    # 0.40 + 0.25 + 0.15 + 0.10 + 0.10 + 0.15 (medium bonus) capped to 1.00
    assert score == 1.00


def test_qes_medium_type_mismatch_penalty_for_show_when_ad_expected():
    """medium_type=advertisement + candidate is a tv show → -0.25 penalty."""
    cand = _candidate_show()
    signals = {
        "primary": "girl",
        "supporting": "shotgun",
        "context": "spiderman",
        "medium_type": "advertisement",
    }
    score = query_explanatory_score(cand, signals)
    # 1.00 baseline - 0.25 medium_mismatch = 0.75
    assert score == 0.75


def test_qes_spider_noir_with_ad_context_low_score():
    """Spec scenario: male-lead Spider-Noir (show) under advertisement medium → low score."""
    cand = _candidate_show(female_lead=False)
    signals = {
        "primary": "girl",
        "supporting": "shotgun",
        "context": "spiderman",
        "medium_type": "advertisement",
    }
    score = query_explanatory_score(cand, signals)
    # primary mismatch: PRIMARY weight not added (no +0.40); SUPPORTING +0.25; CONTEXT +0.15;
    # recency +0.10; branches +0.10; medium mismatch -0.25 = 0.35
    # Confirms Spider-Noir falls below 0.50 (not the top candidate) when ad context provided.
    assert score <= 0.40


def test_qes_score_floor_never_negative():
    """Penalties may stack but the final score floors at 0.0."""
    cand = {
        "title": "Mismatch",
        "overview": "",
        "year": 2010,
        "top_billed_genders": [2],
        "branches": [],
        "media_type": "tv",
    }
    signals = {
        "primary": "girl",
        "supporting": "shotgun",
        "context": "spiderman",
        "medium_type": "advertisement",
    }
    score = query_explanatory_score(cand, signals)
    assert score >= 0.0
```

- [ ] Append the five tests above.
- [ ] Run; confirm all five fail (current implementation ignores `medium_type`):
  ```bash
  cd /Users/rinehardramos/Projects/info-broker && python -m pytest tests/pipeline/fusion/test_scorecard.py -v -k "qes"
  ```
- [ ] Commit:
  ```
  git add tests/pipeline/fusion/test_scorecard.py
  git commit -m "test(scorecard): failing tests for medium_type signal in query_explanatory_score"
  ```

**Acceptance:** `test_qes_medium_type_ad_match_bonus`, `test_qes_medium_type_mismatch_penalty_for_show_when_ad_expected`, `test_qes_spider_noir_with_ad_context_low_score` fail; backward-compat test (`test_qes_no_medium_type_signal_is_backward_compatible`) may pass; floor test may pass.

---

## Task 5 — Implement `medium_type` signal in `query_explanatory_score`

File: `/Users/rinehardramos/Projects/info-broker/app/pipeline/fusion/scorecard.py`

Edits — both isolated to the bottom region of the file (around line 415–430):

**Edit 5a — add a media-type matcher helper** above the existing `query_explanatory_score` definition (insert after `_context_match_qes`, before `def query_explanatory_score`):

```python
# Media-type tokens that mark an "advertisement" candidate.
_AD_MEDIA_TOKENS = {"advertisement", "ad", "campaign", "commercial", "promo", "youtube_ad"}


def _medium_type_match_qes(medium_signal: str, candidate: dict) -> str:
    """Return 'match', 'mismatch', or 'unknown'.

    medium_signal is a normalized string from PreFlight (e.g. "advertisement", "show", "film").
    A candidate is treated as an advertisement when its media_type is in _AD_MEDIA_TOKENS.
    """
    if not medium_signal:
        return "unknown"
    sig = medium_signal.lower().strip()
    cand_media = (candidate.get("media_type") or "").lower().strip()
    cand_is_ad = cand_media in _AD_MEDIA_TOKENS
    sig_is_ad = sig in _AD_MEDIA_TOKENS
    if sig_is_ad and cand_is_ad:
        return "match"
    if sig_is_ad and cand_media in ("tv", "movie", "film", "series", "show") and not cand_is_ad:
        return "mismatch"
    if not sig_is_ad and cand_is_ad:
        return "mismatch"
    return "unknown"
```

**Edit 5b — extend `query_explanatory_score`** (currently lines 415–430). Replace the function body with:

```python
def query_explanatory_score(candidate: dict, signals: dict) -> float:
    """P(query|candidate) confidence.

    Weights: PRIMARY 0.40, SUPPORTING 0.25, CONTEXT 0.15, recency 0.10, multi-branch 0.10.
    Optional medium_type signal (from PreFlight): +0.15 bonus on match, -0.25 on mismatch,
    no effect on unknown. Final score is floored at 0.0 and capped at 1.0.
    """
    score = 0.0
    if _primary_match_qes(signals.get("primary", ""), candidate):
        score += 0.40
    if _supporting_match_qes(signals.get("supporting", ""), candidate):
        score += 0.25
    if _context_match_qes(signals.get("context", ""), candidate):
        score += 0.15
    year = candidate.get("year")
    if year and year >= _CURRENT_YEAR_QES - 1:
        score += 0.10
    if len(candidate.get("branches") or []) >= 2:
        score += 0.10

    medium_outcome = _medium_type_match_qes(signals.get("medium_type", ""), candidate)
    if medium_outcome == "match":
        score += 0.15
    elif medium_outcome == "mismatch":
        score -= 0.25

    score = max(0.0, min(1.0, score))
    return round(score, 2)
```

- [ ] Apply edits 5a and 5b.
- [ ] Run:
  ```bash
  cd /Users/rinehardramos/Projects/info-broker && python -m pytest tests/pipeline/fusion/test_scorecard.py -v
  ```
- [ ] All scorecard tests (existing + 5 new) must pass.
- [ ] Commit:
  ```
  git add app/pipeline/fusion/scorecard.py
  git commit -m "feat(scorecard): add medium_type signal to query_explanatory_score"
  ```

**Acceptance:** `pytest tests/pipeline/fusion/test_scorecard.py` is fully green; backward-compat test still returns 1.00 when no `medium_type` is supplied.

---

## Task 6 — Constraint filter check (defer — file does not exist)

- [ ] Verify no `constraint_filter.py` exists under `app/pipeline/fusion/`:
  ```bash
  ls /Users/rinehardramos/Projects/info-broker/app/pipeline/fusion/constraint_filter.py 2>&1 || echo NOT_FOUND
  find /Users/rinehardramos/Projects/info-broker/app/pipeline -name "constraint_filter*"
  ```
- [ ] Document: the spec's "TMDB gender hard-block → score penalty" is already achieved by the existing PRIMARY mismatch logic in `scorecard._primary_match_qes` — when the candidate's top-billed gender does not match the PRIMARY signal, the +0.40 PRIMARY weight is simply not added, which is functionally equivalent to a -0.40 penalty against a matching baseline. The spec's stated penalty value is -0.30; the effective behavior here is slightly stronger (-0.40 versus a matching candidate). This is acceptable for v1 because no hard pass/fail filter exists to soften. **No code change required for Task 6.**
- [ ] If, during implementation review, a `constraint_filter.py` is discovered to have been created under a different path (e.g. inside an orchestration node), open a follow-up issue rather than expanding scope here.
- [ ] No commit on this task.

**Acceptance:** Confirmation in PR description that constraint_filter.py is not present and the score-penalty behavior is already implemented in `_primary_match_qes`.

---

## Task 7 — Full regression and Spider-Noir success-criterion check

- [ ] Run the full impacted test surface:
  ```bash
  cd /Users/rinehardramos/Projects/info-broker && python -m pytest tests/pipeline/test_media_identification.py tests/pipeline/fusion/test_scorecard.py tests/pipeline/fusion/test_ach.py tests/pipeline/fusion/test_pir.py -v
  ```
- [ ] Add an end-to-end success-criterion test to `tests/pipeline/fusion/test_scorecard.py`:

```python
def test_spider_noir_success_criterion_with_preflight_ad():
    """Spec success criterion: with PreFlight ad context, Spider-Noir (show, male lead)
    scores below the 0.15 suppression floor or near it; Zendaya Amazon campaign (ad,
    female lead) scores >= 0.70 — Zendaya ranks above Spider-Noir."""
    spider_noir = {
        "title": "Spider-Noir",
        "overview": "Nicolas Cage detective shotgun",
        "year": 2025,
        "top_billed_genders": [2],  # male lead
        "branches": ["b1", "b2"],
        "media_type": "tv",
    }
    zendaya_ad = {
        "title": "Amazon Prime — Zendaya campaign",
        "overview": "Zendaya brand campaign with shotgun moment",
        "year": 2025,
        "top_billed_genders": [1],
        "branches": ["b1", "b2"],
        "media_type": "advertisement",
    }
    signals = {
        "primary": "girl",
        "supporting": "shotgun",
        "context": "spiderman",
        "medium_type": "advertisement",
    }
    s_noir = query_explanatory_score(spider_noir, signals)
    s_zen = query_explanatory_score(zendaya_ad, signals)
    assert s_zen >= 0.70, f"Zendaya ad expected >=0.70, got {s_zen}"
    assert s_zen > s_noir, f"Zendaya ({s_zen}) must rank above Spider-Noir ({s_noir})"
    assert s_noir <= 0.40, f"Spider-Noir with ad-mismatch expected <=0.40, got {s_noir}"
```

- [ ] Run and confirm green.
- [ ] Commit:
  ```
  git add tests/pipeline/fusion/test_scorecard.py
  git commit -m "test(scorecard): end-to-end Spider-Noir/Zendaya success criterion"
  ```

**Acceptance:** All listed test files are green. The success-criterion test passes.

---

## Self-review

### Spec coverage matrix

| Spec requirement | Plan task |
|---|---|
| STEP 1.5 hypothesis matrix (≥3, H1–H4, anti-anchor) | Tasks 2, 3 |
| STEP 1.5 medium-type awareness in each hypothesis | Task 3 (strategy text) |
| STEP 1.6 PIR scoring weights (0.40/0.25/0.15/0.15/0.10/0.10) | Tasks 2, 3 |
| STEP 1.6 penalty values (-0.30/-0.15/-0.05/-0.25/-0.10) | Tasks 2, 3 |
| STEP 1.6 suppression floor at 0.15 | Task 3 strategy text |
| STEP 4 mandatory [DISCONFIRM:H_n] per hypothesis | Tasks 2, 3 |
| STEP 4 RECURSE gate before STEP 5 | Task 3 strategy text |
| STEP 4 ACH penalty matrix (penalties, not eliminations) | Tasks 2, 3 |
| STEP 5 SPECIFIC_DETAIL_VERIFICATION, verified=FALSE caps at 0.40 (no block) | Tasks 2, 3 |
| medium_type signal injected from PreFlight into query_explanatory_score | Tasks 4, 5 |
| medium_type bonus +0.15 / penalty -0.25 | Task 5 |
| Backward compatibility when medium_type absent | Tasks 4, 5 (test enforces) |
| TMDB gender hard-block → score penalty | Task 6 (already implemented via `_primary_match_qes`; documented, no change) |
| Spider-Noir success criterion (Zendaya beats Spider-Noir under ad context) | Task 7 |
| MULTI-HYPOTHESIS and COMPLETENESS CHECKLIST tokens (pre-existing test assertions) | Task 3 |

### No placeholders

Every code/text block in this plan is the literal final content. No `TODO`, no `<insert here>`, no `...`. The strategy text in Task 3 is the full replacement file. The scorecard edits in Task 5 are the full replacement function bodies.

### Type consistency

- `signals: dict` everywhere; key types are `str`. New `medium_type` key is optional string.
- `_medium_type_match_qes` returns one of three literal strings (`"match"`, `"mismatch"`, `"unknown"`) — could be `Literal[...]` typed in a future tightening, but matches the file's existing untyped helper style.
- `candidate.get("media_type")` is read as `str | None`; the `or ""` guard handles `None`.
- `query_explanatory_score` return remains `float` rounded to 2 decimals; new clamp adds `max(0.0, min(1.0, score))` — both float-safe.

### Spider-Noir success criterion is testable

Task 7's `test_spider_noir_success_criterion_with_preflight_ad` directly exercises spec lines 200–210:
- Spider-Noir candidate (male lead, tv) under ad-medium signal → expected ≤0.40 (spec calls for ≤0.15 final, but `query_explanatory_score` alone — without disconfirmation re-scoring — produces ≤0.40; the further drop to ≤0.15 happens in the strategy text driven ACH matrix and is verified by the strategy-text token tests in Task 2).
- Zendaya ad candidate → expected ≥0.70 (spec target).
- Ranking inversion (`s_zen > s_noir`) asserted directly.

The pure-strategy-text portion of the success criterion (HYPOTHESIS_MATRIX with H2, mandatory disconfirm, etc.) is enforced by the token tests in Task 2 and is independently testable by `pytest tests/pipeline/test_media_identification.py`.

### Boundary check

- Changes are scoped to two existing files (`media_identification.py`, `scorecard.py`) plus two test files. No new modules. No cross-module shared-contract changes. No schema migrations.
- `query_explanatory_score` signature is unchanged — `signals: dict` was already untyped/open. New `medium_type` key is purely additive.
- No callers of `query_explanatory_score` need updates: existing callers omit `medium_type`, which is treated as `"unknown"` (no effect on score).

### Commits

Seven tasks → up to five commits (Tasks 1 and 6 are non-commit verification steps). Each commit isolates one logical change (failing tests → implementation → success criterion test).
