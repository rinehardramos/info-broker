# ACH + PIR Strategy Upgrade — Design Spec

## Problem

The IS brain generates hypotheses FROM search results (reactive posture). This means:
- The hypothesis space is already biased by the retrieval corpus
- Anchoring: the first plausible match (e.g., Spider-Noir) dominates because it has corroborating sources
- Confirmation searches amplify the anchor rather than test alternatives
- Disconfirmation never happens because no hypothesis explicitly demands it

Root cause: strategy is aspirational ("explore alternatives"), not procedural. The brain has no structured obligation to falsify its leading candidate before delivering.

## Goal

Operationalize ACH (Analysis of Competing Hypotheses), PIR (Priority Intelligence Requirements), and Red Teaming as **mandatory procedural gates** — not aspirational principles. These run in-prompt within the IS brain; the orchestration layer (multi-branch retrieval, TMDB constraint filter) is kept as belt-and-suspenders.

## Design

### STEP 1.5 — Competing Hypotheses (cold-start, before searching)

**Position:** After enriched query parsing, before any BROADEN search.

**Rule:** Generate ≥3 hypotheses from signals ONLY — no search, no training-data recall of specific titles.

**Required:**
- H1: The most obvious match (what a literal reading of the PRIMARY signal suggests)
- H2: Actor-Career interpretation (actress FROM franchise context in a NEW project)
- H3: Genre-blind interpretation (PRIMARY + SUPPORTING only; CONTEXT dropped)
- H4: Long-tail candidate (low-popularity, recent release, not what an obvious search returns — mandatory, must be distinct from H1–H3)

**Anti-anchor rule:** H1 cannot be the only hypothesis. If the analyst finds H2–H4 implausible, they must still formulate them — falsification happens later, not here.

**Output artifact:**
```
HYPOTHESIS_MATRIX:
H1: [title guess or description] — rationale: [1 sentence]
H2: [title guess or description] — rationale: [1 sentence]
H3: [title guess or description] — rationale: [1 sentence]
H4: [title guess or description] — rationale: [1 sentence]
```

### STEP 1.6 — PIR Acceptance Criteria

**Position:** Immediately after STEP 1.5, before searching.

**Rule:** Derive MANDATORY and SUPPORTING criteria from signals. These are not preferences — they are delivery gates.

**Signal → criterion mapping:**
| Signal type | Criterion tier |
|---|---|
| PRIMARY (grammatical subject, e.g. "girl") | MANDATORY |
| SUPPORTING (named defining detail, e.g. "shotgun") | MANDATORY if it's a defining scene element, else SUPPORTING |
| CONTEXT (franchise/IP, e.g. "spiderman") | SUPPORTING — often misleading or loose association |

**Disqualification rule:** Any MANDATORY criterion failure blocks delivery regardless of confidence score. The candidate is eliminated, not downgraded.

**Output artifact:**
```
PIR_CRITERIA:
[MANDATORY] Lead character is female
[MANDATORY] Scene includes a firearm (shotgun or similar)
[SUPPORTING] Connection to Spider-Man franchise or cast
[SUPPORTING] Streaming platform: [unknown — must identify]
```

### STEP 4 — Red Teaming (mandatory disconfirmation)

**Addition to existing STEP 4 (Falsifiers):**

For each surviving hypothesis (not yet eliminated by ACH), one `[DISCONFIRM:H_n]` search is mandatory before advancing to STEP 5.

**Format:**
```
[DISCONFIRM:H1] Search: "Spider-Noir female lead" → result: no female lead found → H1 ELIMINATED
[DISCONFIRM:H2] Search: "Zendaya 2025 series shotgun scene" → result: Euphoria S3 trailer confirmed → H2 SURVIVES
```

**Gate:** If any surviving hypothesis has no disconfirmation search logged, the analyst must RECURSE — do not advance to STEP 5.

### ACH Scoring Matrix (replaces corroboration counting)

**Position:** End of STEP 4, before STEP 5.

**Format:** Signals × Hypotheses matrix.
- ✓ = consistent with hypothesis
- ✗ = inconsistent
- ? = unknown / not verified

```
SIGNAL              | H1: Spider-Noir | H2: Euphoria S3 | H3: Genre-blind | H4: Long-tail
--------------------|-----------------|-----------------|-----------------|---------------
Lead is female      | ✗               | ✓               | ?               | ?
Shotgun/firearm     | ✗               | ✓               | ?               | ?
Spider-Man context  | ✓               | ✓               | ✗               | ?
Recent (2024+)      | ✗               | ✓               | ?               | ?
```

**Ranking rule (Heuer's ACH):** Rank by fewest ✗, not most ✓. One MANDATORY ✗ eliminates the hypothesis entirely.

Spider-Noir result: PRIMARY ✗ → eliminated by MANDATORY criterion failure.

### STEP 5 — SPECIFIC_DETAIL_VERIFICATION (identification variant)

**Addition to existing STEP 5 (Deliver):**

A `SPECIFIC_DETAIL_VERIFICATION` artifact is required for all `media_identification` queries.

**Rule:** For each user-described detail (from SUPPORTING criteria), record whether it was directly confirmed by a source, not inferred.

```
SPECIFIC_DETAIL_VERIFICATION:
- "girl/female lead": verified=TRUE (Zendaya, cast[0] in Euphoria S3, TMDB)
- "shotgun scene": verified=TRUE (trailer timestamp 0:42, YouTube)
- "spider-man connection": verified=TRUE (Zendaya in Spider-Man: No Way Home, TMDB)
```

**Gate:** Any MANDATORY detail with `verified=FALSE` blocks delivery. The analyst must search further or declare insufficient evidence.

### Filter coverage review

| Filter | Current status | Role in new design |
|---|---|---|
| **ACH** | Aspirational in strategy text | Procedural: STEP 1.5 matrix + STEP 4 scoring |
| **PIR** | Not present | New: STEP 1.6 MANDATORY/SUPPORTING gate |
| **Red Teaming** | Aspirational ("consider alternatives") | Procedural: mandatory `[DISCONFIRM:H_n]` per hypothesis |
| **KAC (Key Assumption Check)** | Not present | Folded into STEP 1.5 anti-anchor rule (H1 cannot be sole hypothesis) |
| **Adversarial Check** | Not present | Folded into STEP 4 Red Teaming — adversarial interpretation IS the disconfirmation search |
| **Falsifiers** | Present in STEP 4 | Kept; now explicitly required to run before ACH matrix update |
| **Negative-space check** | Present | Kept; `SPECIFIC_DETAIL_VERIFICATION` is its identification-specific operationalization |

KAC and Adversarial Check do not need separate steps — they are subsumed by the cold-start hypothesis generation (forces the analyst to hold multiple interpretations simultaneously) and mandatory disconfirmation (adversarial = trying to falsify your leading candidate).

### JSON envelope additions

These fields are added to the brain's output schema for `media_identification` queries:

```json
{
  "hypotheses": [
    { "id": "H1", "description": "...", "rationale": "..." },
    { "id": "H2", "description": "...", "rationale": "..." }
  ],
  "pir_criteria": [
    { "tier": "MANDATORY", "criterion": "Lead character is female" },
    { "tier": "SUPPORTING", "criterion": "Shotgun/firearm scene" }
  ],
  "ach_matrix": {
    "signals": ["Lead is female", "Shotgun/firearm", "Spider-Man context", "Recent (2024+)"],
    "hypotheses": ["H1: Spider-Noir", "H2: Euphoria S3"],
    "cells": [["✗","✓"], ["✗","✓"], ["✓","✓"], ["✗","✓"]]
  },
  "eliminated_hypotheses": [
    { "id": "H1", "reason": "MANDATORY criterion failure: lead is male" }
  ],
  "disconfirm_searches": [
    { "hypothesis": "H1", "query": "Spider-Noir female lead", "result": "no female lead", "outcome": "ELIMINATED" },
    { "hypothesis": "H2", "query": "Zendaya 2025 series shotgun", "result": "Euphoria S3 trailer confirmed", "outcome": "SURVIVES" }
  ],
  "specific_detail_verification": [
    { "detail": "female lead", "verified": true, "source": "TMDB cast[0]" },
    { "detail": "shotgun scene", "verified": true, "source": "YouTube trailer 0:42" }
  ]
}
```

## Files

### Modified files

| Path | Change |
|---|---|
| `app/pipeline/strategies/media_identification.py` | Add STEP 1.5 (hypothesis matrix), STEP 1.6 (PIR criteria), Red Teaming gate (STEP 4), ACH scoring rule, SPECIFIC_DETAIL_VERIFICATION (STEP 5) |
| `app/is_prompt.py` | Add identification-specific STEP 3 (FALSIFIERS derived from PIR criteria), STEP 5 DELIVER GATE requiring `ach_matrix`, `pir_criteria`, `disconfirm_searches_run`, `specific_detail_verification` |

### No new files needed

The ACH/PIR logic lives entirely in prompt/strategy text. The existing JSON schema in `scorecard.py` / `agent.py` is extended, not replaced.

## Scope constraints

- ACH + PIR gates are **`media_identification` only** in v1
- All methodology changes live in `media_identification.py` (the strategy text injected for this classification). The `is_prompt.py` global STEP 3 and STEP 5 are NOT modified — the strategy text itself mandates the new artifacts, which the brain produces because the strategy says to
- `is_prompt.py` only needs: (1) the `{prefetched_evidence}` slot (already added), and (2) a DELIVER GATE clause that checks for required artifacts when the strategy requested them. The gate is generic ("if strategy requested artifact X, verify it is present") — it does not need to know about ACH specifically
- No new Python files — purely prompt engineering within existing architecture
- The orchestration layer (multi-branch retrieval, TMDB constraint filter) is unmodified — ACH/PIR is additive, in-brain methodology

## Success criterion

For "new series with girl in spiderman where man has a shotgun":
1. STEP 1.5 generates ≥3 hypotheses including at least one non-Spider-Man candidate before any search
2. STEP 1.6 marks "female lead" as MANDATORY
3. Spider-Noir is eliminated in ACH matrix (MANDATORY ✗) and `eliminated_hypotheses` contains it
4. A female-led candidate survives with `specific_detail_verification.verified=TRUE` for "female lead"
5. The delivered confirmation card candidate is NOT Spider-Noir
