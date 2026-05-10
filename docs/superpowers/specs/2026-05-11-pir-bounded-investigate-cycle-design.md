# PIR-Bounded Recursive INVESTIGATE Cycle — Design Spec

## Problem

The IS brain's current STEP 1–7 structure is a linear pipeline. Planning is one-shot (STEP 3), BROADEN searches one hypothesis from multiple angles, and the unconventional branch is a late afterthought (STEP 6). This produces:

- **Tunnel vision**: the brain commits to the first plausible candidate and searches it exhaustively before considering alternatives (Spider-Noir at 95%)
- **Geography anchoring**: person searches default to the obvious locale (Philippines) without exploring migration or diaspora before ranking
- **Dead planning**: when a branch dies, the investigation ends rather than re-hypothesizing for the same question
- **Misplaced diversity**: multi-branch retrieval was a Python orchestration workaround to force corpus diversity that the brain should generate itself

Root cause: the brain has no structured obligation to explore competing interpretations before committing, and no boundary condition that forces it to keep widening until the question is actually settled.

## Goal

Replace the linear STEP 1–7 pipeline with a single **INVESTIGATE cycle** that repeats at every branch. Every cycle is bounded by a **PIR** (Priority Intelligence Requirements) — a pre-stated question with acceptance and rejection criteria. The cycle runs until its PIR is settled, not until a search count or depth limit is hit. Planning is iterative: each cycle re-hypothesizes and replans based on what the current depth surfaced.

Remove the multi-branch Python pre-fetch entirely — the brain's hypothesis-first BROADEN replaces it universally across all query types.

## Core Concepts

### PIR — Priority Intelligence Requirements

PIR is the specific question a cycle must answer, stated **before any search begins**, with pre-stated criteria for what a satisfying answer looks like.

```
PIR: [the specific question this cycle answers]
MANDATORY: [evidence that must be present — all must pass]
SUPPORTING: [evidence that increases confidence but is not required]
REJECT IF: [evidence that definitively closes the branch as "no"]
```

PIR is **both entry and exit boundary**:
- Entry: state what you need to confirm or deny before searching
- Exit: cycle closes when PIR is confirmed (MANDATORY met), rejected (REJECT IF triggered), or all hypotheses exhausted (escalate: insufficient evidence)

PIR does not say which hypothesis is correct. It says what kind of evidence would settle the question either way.

**Top-level PIR** is derived from the user's question + PreFlight signals.
**Child PIRs** are spawned mid-investigation when a finding raises a new question that must be settled before the parent can advance. Child PIRs inherit the parent's CONTEXT signal but define their own MANDATORY/SUPPORTING/REJECT IF criteria.

### INVESTIGATE cycle

Every branch of the investigation is one instance of the same cycle:

```
INVESTIGATE(PIR):
  HYPOTHESIZE   — ≥3 competing answers to this PIR (no search yet)
  BROADEN       — ≥1 dedicated search per hypothesis (min searches = hypothesis count)
  RANK          — score each hypothesis against PIR criteria; prune weak candidates
  for each surviving hypothesis:
    RECURSE → deeper search on this hypothesis
    PIR CONFIRMED?       → close branch, propagate answer up
    PIR REJECTED?        → close branch, mark dead end
    new question raised? → spawn child PIR → INVESTIGATE(child_PIR)
    dead end?            → re-hypothesize for same PIR (new angle, new searches)
  all hypotheses exhausted? → ESCALATE: insufficient evidence, report what was found
```

This cycle replaces the current STEP 1–7 linear structure. STEP 3 (plan) is no longer one-shot — planning happens fresh at each cycle iteration as new evidence reshapes the hypothesis space.

## Design

### HYPOTHESIZE rules

Generated at the start of every cycle, for THIS PIR specifically — not the global query.

- **≥3 hypotheses** minimum
- **H_last** is always unconventional: the interpretation that obvious searches would miss
- **Anti-anchor rule**: if H1 is the obvious answer, H2 through H_last must be genuinely competing, not variations of H1
- Hypotheses are scoped to the PIR — competing answers to its question, not free associations
- No search until all hypotheses are formulated

**Domain hypothesis templates (built into each strategy file):**

| Query type | H1 | H2 | H3 | H_last |
|---|---|---|---|---|
| Person | Obvious locale | Alternate geography (migration, diaspora) | Alias / name variant | No public trace (private individual, deceased) |
| Media | Literal franchise match | Actor-career (same actress, different project) | Genre-blind (drop franchise signal) | Ad / campaign (not a show at all) |
| Company | Primary jurisdiction | Parent / subsidiary | Entity lineage (renamed/dissolved) | Foreign subsidiary or shell |
| Factual / Research | Conventional answer | Contrarian / minority view | Domain-specific nuance | Recent development that overturns prior answer |

### BROADEN rules

- **Minimum searches = number of hypotheses** (≥3)
- Each search is derived from its hypothesis — not from a fixed signal-combination formula
- Search queries are hypothesis-specific: "what would I search to confirm or deny H2?"
- **No hypothesis ranking before all BROADEN searches complete** — this is the hard gate
- Corroborating search: the hypothesis with strongest initial signal gets ≥1 additional search in RECURSE, not in BROADEN

### RANK rules

Score each hypothesis against PIR acceptance criteria:

- MANDATORY criteria failure → heavy score penalty (hypothesis survives but ranks low)
- SUPPORTING criteria match → score boost
- REJECT IF triggered → hypothesis closed (not deleted from output — reported as ruled out)
- Rank by fewest inconsistencies with MANDATORY criteria (Heuer's ACH principle)
- Hypothesis scoring is **penalty-based, not elimination-based** — all candidates appear in output at their earned score

### RECURSE and re-entry

- RECURSE deepens each surviving hypothesis: more specific searches, source verification, cross-reference
- New evidence is evaluated against the current PIR acceptance/rejection criteria each iteration
- **Dead end**: no new signal after ≥2 searches → re-hypothesize for same PIR with a different angle (different locale, different name variant, different source type) and run new BROADEN searches; do not close the PIR
- **New question raised**: spawn child PIR, run INVESTIGATE(child_PIR), propagate result back to parent
- **PIR confirmed/rejected**: close branch, propagate to parent

Planning re-runs at each RECURSE iteration — the branch list and search priorities update as evidence accumulates. There is no fixed plan from STEP 3 that must be executed; the plan is always current.

### DELIVER

Triggered when:
- Top-level PIR is confirmed with sufficient MANDATORY coverage, OR
- All top-level hypotheses exhausted (insufficient evidence report)

Output includes:
- All surviving hypotheses with their PIR scores
- Ruled-out hypotheses with the evidence that ruled them out
- Child PIR results that contributed to parent settlement
- SPECIFIC_DETAIL_VERIFICATION: each user-described detail logged as verified/unverified

## Files

### Deleted

| Path | Reason |
|---|---|
| `app/pipeline/retrieval/` | Entire package — multi-branch pre-fetch replaced by brain-native hypothesis-first BROADEN |
| `app/pipeline/fusion/constraint_filter.py` | Hard gender-block removed — hypothesis scoring handles this via MANDATORY penalty |

### Modified

| Path | Change |
|---|---|
| `app/is_prompt.py` | Replace linear STEP 1–7 with INVESTIGATE cycle description; STEP 6 absorbed into H_last; STEP 5 (KAC+Adversarial) absorbed into per-cycle RANK; add PIR format block |
| `app/pipeline/strategies/media_identification.py` | Remove pre-fetch NOTE; add PIR template + hypothesis table for media queries |
| `app/pipeline/strategies/person.py` | Add PIR template + hypothesis table (locale → migration → alias → no-trace) |
| `app/pipeline/strategies/company.py` | Add PIR template + hypothesis table (jurisdiction → parent → lineage → shell) |
| `app/routers/v3/agent.py` | Remove `prefetch_branches()` call and `prefetched_evidence` injection |
| `app/pipeline/fusion/scorecard.py` | `query_explanatory_score()` accepts PIR criteria dict as input; medium_type signal from PreFlight plugs in |

### Unchanged

- PreFlight gate — runs before the top-level cycle starts
- Signal decomposition (PRIMARY / SUPPORTING / CONTEXT) — feeds into top-level PIR generation
- Confirmation gate (`_CONFIRM_PENDING`) — still holds result pending user Yes/No
- All MCP tool signatures
- DB schema

## Scope

- INVESTIGATE cycle applies universally — all query types, not scoped to `media_identification`
- Domain hypothesis templates are the per-strategy contribution — strategies customize H1–H_last for their domain
- Multi-branch Python pre-fetch is removed completely; no fallback path kept
- TMDB client (`tmdb_client.py`) deleted with the retrieval package; TMDB access remains via existing `run_tmdb_search` MCP tool

## Success criteria

**Person-in-EU case:**
1. Top-level PIR states "Where does this person live and work?" with MANDATORY: residence record in any country
2. HYPOTHESIZE generates H1=PH, H2=EU-migration, H3=alias abroad before any search
3. BROADEN runs ≥3 searches (one per hypothesis) — PH returns empty, Italy search returns hit
4. Child PIR spawned: "Is the Italy hit the same person?" — settled by employer record matching PH background
5. Top-level PIR confirmed: EU/Italy

**Media-identification case (Spider-Noir):**
1. Top-level PIR: "What show/ad is this?" — MANDATORY: content matches user-described medium (ad vs. show)
2. HYPOTHESIZE generates H1=franchise show, H2=actress-in-different-project, H3=genre-blind, H4=advertisement
3. BROADEN searches each — after PreFlight confirms "YouTube + ad", H1 (Spider-Noir, a show) accumulates medium-mismatch penalty
4. H4 search surfaces Zendaya Amazon campaign; child PIR "is this the same ad?" confirmed
5. Delivered candidate: Zendaya Amazon ad, not Spider-Noir
