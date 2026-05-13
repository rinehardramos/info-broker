# ACH + PIR Strategy Upgrade — Design Spec

## Problem

The IS brain generates hypotheses FROM search results (reactive posture). This means:
- The hypothesis space is already biased by the retrieval corpus
- Anchoring: the first plausible match (e.g., Spider-Noir) dominates because it has corroborating sources
- Confirmation searches amplify the anchor rather than test alternatives
- Disconfirmation never happens because no hypothesis explicitly demands it

Root cause: strategy is aspirational ("explore alternatives"), not procedural. The brain has no structured obligation to falsify its leading candidate before delivering.

**A second wrong assumption (corrected from earlier draft):** Hard elimination of Spider-Noir is wrong. Spider-Noir IS a valid candidate — it's a new 2025 series in the Spider-Man franchise with a gun-wielding lead. The problem is it scores 95% when the full signal set (girl + YouTube + advertisement) should rank it at ~25%. The fix is progressive scoring, not elimination. The TMDB gender constraint filter in the orchestration layer is similarly corrected: it downgrades, it does not block.

## Goal

Operationalize ACH, PIR, and Red Teaming as **mandatory procedural gates for ranking** — not as elimination rules. Each additional signal narrows the ranking. The PreFlight clarifications (YouTube + advertisement) are the mechanism that should unseat Spider-Noir, not a hard filter.

**Progressive signal model:**

| Signals available | Expected top candidate |
|---|---|
| "girl in spiderman" only | Spider-Noir valid candidate (~35%), Zendaya-unknown (~20% low-confidence) |
| + 2025–2026 timeline | Spider-Noir stays plausible (IS 2025 series), Zendaya rises if 2025 project found |
| + YouTube + advertisement | Medium-type mismatch tanks Spider-Noir (~5%), Zendaya Amazon campaign surfaces |

The advertisement signal from PreFlight is the kill shot. Not gender.

## Design

### STEP 1.5 — Competing Hypotheses (cold-start, before searching)

**Position:** After enriched query parsing (including any PreFlight clarifications), before BROADEN.

**Rule:** Generate ≥3 hypotheses from signals ONLY — no search, no training-data recall of specific titles yet.

**Required hypotheses:**
- H1: Literal franchise interpretation (show/movie IN the Spider-Man universe)
- H2: Actor-Career interpretation (actress FROM Spider-Man franchise in a NEW, different project — ad, show, film)
- H3: Genre-blind (PRIMARY + SUPPORTING only; CONTEXT dropped entirely — what matches "girl + shotgun + new" without "spiderman"?)
- H4: Long-tail candidate (low-popularity, recent, not returned by obvious search)

**Anti-anchor rule:** H1 is always formulated. H2 through H4 must be independent interpretations. If the analyst believes H1 is correct, they still produce H2–H4 — falsification happens in STEP 4, not here.

**Medium-type awareness:** If PreFlight clarifications include "advertisement" or "YouTube", add to each hypothesis whether it could be an ad campaign, not a show. Zendaya as brand ambassador in a franchise-adjacent campaign becomes H2 explicitly.

**Output artifact:**
```
HYPOTHESIS_MATRIX:
H1: [Spider-Man universe show/film — new 2025 series] — rationale: literal franchise + gun signal
H2: [Zendaya or other Spider-Man actress in Amazon/brand campaign] — rationale: actress-career tracking; YouTube+ad context
H3: [Female-led drama/thriller 2025 with firearm, no franchise] — rationale: genre-blind, PRIMARY+SUPPORTING only
H4: [Low-profile 2025 series, female lead, action genre] — rationale: long-tail, not surfaced by obvious search
```

### STEP 1.6 — PIR Scoring Criteria

**Position:** Immediately after STEP 1.5, before searching.

**Correction from earlier draft:** PIR tiers drive **scoring weights**, not delivery gates. A MANDATORY criterion failure is a heavy score penalty — the candidate still appears in results at low confidence, it is not blocked. Only a candidate scoring <15% across all signals is suppressed from the confirmation card (not from the full result set).

**Signal → criterion mapping:**
| Signal type | Scoring weight | On mismatch |
|---|---|---|
| PRIMARY (grammatical subject: "girl") | 0.40 | −0.30 score penalty |
| SUPPORTING (defining detail: "shotgun") | 0.25 | −0.15 penalty |
| CONTEXT (franchise/IP: "spiderman") | 0.15 | −0.05 penalty (CONTEXT is often loose/misleading) |
| Recency (2024–2026) | 0.10 | −0.10 penalty |
| Multi-branch corroboration | 0.10 | −0.05 penalty |
| **Medium-type** (ad vs. show, from PreFlight) | 0.15 bonus | −0.25 penalty if mismatch |

**Medium-type signal** is injected by PreFlight clarifications. If user confirmed "YouTube advertisement": candidates that are shows (not ads/campaigns) receive a −0.25 medium_mismatch penalty. This is the mechanism that unseats Spider-Noir when the ad context is known.

**PIR_CRITERIA output artifact:**
```
PIR_CRITERIA:
[HIGH-WEIGHT] Lead character or subject is female/girl — weight: 0.40
[HIGH-WEIGHT] Scene or content includes a firearm (shotgun) — weight: 0.25
[MEDIUM] Connection to Spider-Man franchise or cast — weight: 0.15
[MEDIUM] Content is an advertisement/campaign (from PreFlight) — weight: 0.15 bonus / −0.25 mismatch
[LOW] Released/active 2024–2026 — weight: 0.10
```

### STEP 4 — Red Teaming (mandatory disconfirmation)

For each hypothesis (all H1–H4, not just the leader), one `[DISCONFIRM:H_n]` search is mandatory before advancing to STEP 5.

**Format:**
```
[DISCONFIRM:H1] Search: "Spider-Noir 2025 female protagonist" → result: lead is male (Nicolas Cage) → PRIMARY mismatch; score −0.30
[DISCONFIRM:H2] Search: "Zendaya Amazon Prime advertisement 2025" → result: confirmed Amazon campaign → H2 score rises
[DISCONFIRM:H3] Search: "2025 drama series female lead gun scene new" → result: [candidates]
[DISCONFIRM:H4] Search: "2025 female action series low budget streaming" → result: [candidates]
```

**Gate:** If any hypothesis has no disconfirmation search logged, RECURSE before STEP 5. Do not advance.

### ACH Scoring Matrix

**Position:** End of STEP 4, before STEP 5.

**Correction from earlier draft:** The matrix ranks by fewest inconsistencies (Heuer's ACH). But inconsistencies are **score penalties, not eliminations**. A candidate stays in the result set unless its total score falls below the suppression floor (~0.15).

```
SIGNAL                  | Weight | H1: Spider-Noir | H2: Zendaya Ad | H3: Genre-blind | H4: Long-tail
------------------------|--------|-----------------|----------------|-----------------|---------------
Lead is female/girl     | 0.40   | ✗ (−0.30)       | ✓              | ?               | ?
Shotgun/firearm         | 0.25   | ✓               | ? (unknown)    | ?               | ?
Spider-Man franchise    | 0.15   | ✓               | ✓              | ✗ (−0.05)       | ?
Medium: advertisement   | 0.15   | ✗ (−0.25)       | ✓              | ?               | ?
Recency 2024+           | 0.10   | ✓ (2025)        | ✓              | ?               | ?
```

**Spider-Noir score (with ad context):** 0.25(shotgun) + 0.15(franchise) + 0.10(recency) − 0.30(no female) − 0.25(not an ad) = **−0.05 → floor at 0.10** — appears as low-confidence candidate, not top result.

**Zendaya ad (H2, confirmed):** 0.40 + 0.15(franchise) + 0.15(ad match) + 0.10(recency) = **0.80** — surfaces as top candidate.

**Without ad context (raw "girl in spiderman"):** Spider-Noir: 0.25 + 0.15 + 0.10 − 0.30 = **0.20**. Zendaya unknown project: 0.40 + 0.15 = **0.55 but unverified → capped at 0.35**. Spider-Noir and Zendaya are close, both low — correct behavior for an ambiguous query. PreFlight is triggered to resolve.

### STEP 5 — SPECIFIC_DETAIL_VERIFICATION

**Correction from earlier draft:** `verified=FALSE` does NOT block delivery. It caps confidence at 40% and adds a "needs verification" flag. The candidate is still deliverable — the user may have additional context that resolves it.

```
SPECIFIC_DETAIL_VERIFICATION:
- "girl/female subject": verified=TRUE (Zendaya, actress in Amazon campaign, confirmed)
- "shotgun/firearm": verified=? (advertisement may or may not include gun — needs confirmation)
- "spider-man connection": verified=TRUE (Zendaya in Spider-Man: No Way Home, TMDB)
- "advertisement": verified=TRUE (Amazon Prime campaign, YouTube)
```

Unverified SUPPORTING details reduce the score by their weight but do not block. Unverified PRIMARY details cap confidence at 40%.

### Filter coverage review

| Filter | Current status | Role in new design |
|---|---|---|
| **ACH** | Aspirational in strategy text | Procedural: STEP 1.5 matrix + STEP 4 scoring (penalty-based, not elimination) |
| **PIR** | Not present | New: STEP 1.6 scoring weights with medium-type signal from PreFlight |
| **Red Teaming** | Aspirational | Procedural: mandatory `[DISCONFIRM:H_n]` per hypothesis |
| **KAC** | Not present | Folded into STEP 1.5 anti-anchor rule (H1 is always formulated, alternatives mandatory) |
| **Adversarial Check** | Not present | Folded into STEP 4 Red Teaming — adversarial = trying to falsify your leader |
| **Falsifiers** | Present in STEP 4 | Kept; now explicitly required before ACH matrix update |
| **Negative-space check** | Present | Kept; `SPECIFIC_DETAIL_VERIFICATION` is its identification-specific form |
| **TMDB gender constraint** | Hard-block (wrong) | **Corrected to score-penalty**: male lead when PRIMARY=female → −0.30, not blocked |

### JSON envelope

```json
{
  "hypotheses": [
    { "id": "H1", "description": "Spider-Noir (Amazon, 2025)", "score": 0.10 },
    { "id": "H2", "description": "Zendaya Amazon Prime campaign 2025", "score": 0.80 }
  ],
  "pir_criteria": [
    { "signal": "female lead/subject", "weight": 0.40, "tier": "HIGH" },
    { "signal": "firearm scene", "weight": 0.25, "tier": "HIGH" },
    { "signal": "spider-man connection", "weight": 0.15, "tier": "MEDIUM" },
    { "signal": "advertisement (from PreFlight)", "weight": 0.15, "tier": "MEDIUM" }
  ],
  "ach_matrix": {
    "signals": ["female lead", "shotgun", "franchise", "advertisement", "recency"],
    "hypotheses": ["H1: Spider-Noir", "H2: Zendaya Ad"],
    "cells": [["✗","✓"], ["✓","?"], ["✓","✓"], ["✗","✓"], ["✓","✓"]],
    "penalties": [[-0.30, 0], [0, 0], [0, 0], [-0.25, 0], [0, 0]]
  },
  "disconfirm_searches": [
    { "hypothesis": "H1", "query": "Spider-Noir female protagonist 2025", "outcome": "PENALTY: male lead" },
    { "hypothesis": "H2", "query": "Zendaya Amazon advertisement 2025", "outcome": "CONFIRMED" }
  ],
  "specific_detail_verification": [
    { "detail": "female subject", "verified": true, "source": "TMDB Zendaya" },
    { "detail": "advertisement", "verified": true, "source": "Amazon campaign YouTube" },
    { "detail": "shotgun", "verified": false, "note": "not confirmed in ad — confidence capped at 40% for this detail" }
  ]
}
```

## Files

### Modified files

| Path | Change |
|---|---|
| `app/pipeline/strategies/media_identification.py` | Add STEP 1.5 (hypothesis matrix with medium-type awareness), STEP 1.6 (PIR scoring weights not gates), Red Teaming gate (STEP 4), ACH penalty matrix, SPECIFIC_DETAIL_VERIFICATION (STEP 5) |
| `app/pipeline/fusion/constraint_filter.py` | Soften TMDB gender hard-block to score-penalty: return `score_adjustment=-0.30` instead of `passed=False` |
| `app/pipeline/fusion/scorecard.py` | Add medium_type signal from PreFlight clarifications; add penalty columns to `query_explanatory_score` |

### No new files needed

ACH/PIR lives in prompt/strategy text. Orchestration layer penalty adjustments are in existing files.

## Scope constraints

- ACH + PIR scoped to `media_identification` only in v1
- Strategy changes in `media_identification.py` only — global `is_prompt.py` steps not modified
- TMDB constraint filter stays in orchestration layer but becomes a score adjustment, not a pass/fail
- PreFlight clarification signals (ad, YouTube) must be passed through to both branch search queries and to `query_explanatory_score` as medium_type signal

## Success criterion

For "new series with girl in spiderman where man has a shotgun" (raw query, no PreFlight):
1. STEP 1.5 generates ≥3 hypotheses including H2 (actress-career) and H3 (genre-blind) before searching
2. Spider-Noir appears as a candidate but scores ≤35% due to PRIMARY penalty (no female lead)
3. Zendaya appears as low-confidence candidate (~30–40%) from actor-career branch

After PreFlight clarifies "YouTube" + "advertisement":
4. Spider-Noir score drops to ≤15% (medium-type mismatch penalty applied)
5. Zendaya Amazon campaign surfaces with score ≥70% after confirmed via disconfirmation search
6. The confirmation card candidate is the Zendaya Amazon ad, not Spider-Noir
