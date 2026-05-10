# Multi-Branch Retrieval for Media Identification — Design Spec

## Problem

The IS brain returns Spider-Noir (95% confidence, 15 corroborating sources) for every run of
"new series with girl in spiderman where man has a shotgun" (YouTube ad), despite a correct
answer existing (likely Euphoria S3 / Zendaya or a female-led Spider-Man adjacent series).

Root cause (Opus diagnosis): single-stream retrieval + corroboration-weighted confidence.
Any query containing "spiderman" floods the search corpus with Spider-Noir documents. The LLM
ranks what it has, not what fits. Six layers of prompt instruction did not change this — prompts
shape interpretation, not retrieval.

## Goal

Fix media identification queries so the LLM sees a **balanced corpus** before reasoning, a
**hard structural filter** blocks candidates whose lead character contradicts the PRIMARY signal,
and **confidence measures query fit** (P(query|candidate)) rather than source count
(P(candidate exists)).

## Architecture

### Data flow

```
brain_questions.py  →  signals: PRIMARY/SUPPORTING/CONTEXT
                     ↓
agent._run_is_research
  classify_query() → "media_identification"
  compile_strategy() → media_identification strategy text
  prefetch_branches(signals, "media_identification")   ← NEW
                     ↓ ~15 balanced docs across 3 branches
  run_research(query, prefetched_evidence=evidence)
                     ↓
  build_prompt injects {prefetched_evidence} block      ← NEW PROMPT SLOT
                     ↓
  Claude Code subprocess (sees balanced corpus, must produce ≥1/branch)
                     ↓
  passes_lead_constraint(top_candidate, signals.primary)  ← NEW HARD FILTER
                     ↓ Spider-Noir blocked (lead is male)
  query_explanatory_score(candidate, signals)             ← NEW CONFIDENCE
                     ↓
  _CONFIRM_PENDING (unchanged)
```

### Three retrieval branches (media_identification only)

Branches run in parallel via `asyncio.gather`. Quota: 5 hits per branch maximum.
Each branch is forbidden from using other branches' keywords to prevent cross-contamination.

**Branch A — Character-in-Universe** (`character_in_universe`)
- Hypothesis: A female character IS Spider-Man / is in the Spider-Man universe
- Signals: PRIMARY + CONTEXT + SUPPORTING
- Searches:
  - `tmdb.search_tv("spider female lead", year_gte=2024)`
  - `web_search("new spider-man series 2025 female lead")`
  - `google_news("spider-man series female lead announcement")`

**Branch B — Actor-Career-Tracking** (`actor_career`)
- Hypothesis: An actress FROM Spider-Man films appears in a *different* new series
- Signals: CONTEXT → enumerate actresses → search each independently
- Two stages:
  1. Fetch cast of recent Spider-Man films (No Way Home, Across Spider-Verse, Madame Web,
     Kraven) via TMDB → collect female cast members
  2. For each actress: `tmdb.filmography(actor_id, type="tv", year_gte=2024)`
     and `web_search("<actress> new series 2025")`

**Branch C — Genre-Signal** (`genre_signal`)
- Hypothesis: "spiderman" is misheard/loose; the real signal is female lead + shotgun
- Signals: PRIMARY + SUPPORTING only — CONTEXT dropped entirely
- Searches:
  - `tmdb.search_tv("drama thriller female lead 2025")`
  - `web_search("new tv series 2025 girl protagonist shotgun viral ad")`
  - `web_search("youtube ad 2025 new series girl shotgun")`

### Balanced corpus injection (prompt)

```
## PRE-RETRIEVED EVIDENCE (do not re-search — work from this corpus)

### Branch A — Character-in-Spider-Man-Universe
1. <title> (<year>) — top cast: [...]
...

### Branch B — Actress-from-Spider-Man-in-New-Series
1. Euphoria S3 (2025) — Zendaya (known from Spider-Man: No Way Home)
...

### Branch C — Young-Female-Lead-with-Shotgun (franchise-blind)
1. Fallout (2024) — Ella Purnell
...

YOU MUST produce ≥1 candidate from each non-empty branch before ranking.
State "no viable candidate" for any branch you cannot satisfy — do not skip silently.
```

### Lead-character constraint filter (hard filter, TMDB, Python-side)

Called after brain returns, before `_CONFIRM_PENDING`. Deterministic — no LLM.

- Resolve candidate to TMDB id
- Fetch `/tv/{id}/credits` (or `/movie/{id}/credits`)
- Take `cast[0]` (top-billed actor)
- If `primary_signal.gender == "female"` and `cast[0].gender == 2` (TMDB: 2=male): `passed=False`
- Spider-Noir: Nicolas Cage top-billed, gender=2 → **blocked**
- Euphoria S3: Zendaya top-billed, gender=1 → **passes**

If ALL candidates fail: trigger a re-run with a "no viable candidate passed lead constraint"
note injected into the enriched query (not a silent drop).

### Match-weighted confidence (replaces corroboration counting)

```python
def query_explanatory_score(candidate, signals) -> float:
    score = 0.0
    score += 0.40 if primary_signal_match(signals.primary, candidate) else 0.0
    score += 0.25 if supporting_signal_match(signals.supporting, candidate) else 0.0
    score += 0.15 if context_signal_match(signals.context, candidate) else 0.0
    score += 0.10 if candidate.year >= CURRENT_YEAR - 1 else 0.0
    score += 0.10 if len(candidate.branches) >= 2 else 0.0
    return score
```

Signal match functions:
- `primary_signal_match("girl", candidate)`: `cast[0].gender == 1` (female top-billed)
- `supporting_signal_match("shotgun", candidate)`: `"shotgun" OR "firearm" OR "weapon" in overview or keywords`
- `context_signal_match("spiderman", candidate)`: title/overview contains "spider" OR any cast member
  has a Spider-Man film in their TMDB filmography

Spider-Noir: PRIMARY=fail → score 0.25
Euphoria S3: PRIMARY=pass, CONTEXT=pass (Zendaya in No Way Home), RECENCY=pass → score 0.80+

## Files

### New files

| Path | Purpose |
|---|---|
| `app/pipeline/retrieval/__init__.py` | Package init |
| `app/pipeline/retrieval/multi_branch.py` | `prefetch_branches()`, `BranchEvidence`, `BranchHit` dataclasses |
| `app/pipeline/retrieval/branches/media_identification.py` | 3 branch coroutines — `branch_character_in_universe`, `branch_actor_career`, `branch_genre_signal` |
| `app/pipeline/retrieval/tmdb_client.py` | Direct TMDB HTTP client (httpx): search, credits, filmography, person details |
| `app/pipeline/fusion/constraint_filter.py` | `passes_lead_constraint(candidate, primary_signal) -> ConstraintResult` |

### Modified files

| Path | Change |
|---|---|
| `app/routers/v3/agent.py` | Call `prefetch_branches` when `classification == "media_identification"`; pass evidence to `run_research`; apply `passes_lead_constraint` post-brain before `_CONFIRM_PENDING` |
| `app/is_brain.py` | Accept `prefetched_evidence: BranchEvidence \| None` param; pass to `build_prompt` |
| `app/is_prompt.py` | Add `{prefetched_evidence}` slot to `RESEARCH_PROMPT`; add ≥1/branch directive |
| `app/pipeline/fusion/scorecard.py` | Replace `compute_confidence` with `query_explanatory_score`; keep function name stable |
| `app/pipeline/strategies/media_identification.py` | Add one sentence: "The orchestrator pre-fetches retrieval branches. Work from PRE-RETRIEVED EVIDENCE; do not re-search it." |

### Do NOT touch

- `brain_questions.py` signal decomposition (PRIMARY/SUPPORTING/CONTEXT) — correct as-is
- `classify_query` and `compile_strategy` routing — `media_identification` classification is correct
- Claude Code subprocess model — brain still handles synthesis, narrative, cross-referencing
- `_CONFIRM_PENDING` confirmation gate — correctly placed, no changes needed
- Other strategy files — multi-branch is scoped to `media_identification` for v1
- MCP tool surface — tools keep their existing signatures

## Scope constraints

- Multi-branch retrieval is **media_identification only** — no other query types in v1
- TMDB API key must be present; if absent, skip pre-fetch and warn (brain runs as today)
- Added latency: ~2–4s for parallel TMDB/web calls before brain launch
- Branch quota: 5 hits per branch, hard cap — no branch floods the corpus

## Success criterion

For "new series with girl in spiderman where man has a shotgun" (YouTube ad):
1. Spider-Noir does not appear in the confirmation card (blocked by lead constraint filter)
2. At least one female-led candidate (Euphoria S3, Silk, Fallout, etc.) reaches the confirmation card
3. The confirmation card candidate's confidence score is driven by PRIMARY signal match, not source count
