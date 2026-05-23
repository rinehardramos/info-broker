# Research-skeleton tactic completion + unified phase taxonomy — design

> **Date:** 2026-05-23
> **Status:** Draft (pending implementation plan)
> **Triggering incident:** Following PR #116, the diagnostic surfaces revealed that 8 skeleton strategies (real_estate, lead, company, place, generation, explanation, prediction, synthesis) complete in ~90 ms with `failing_check_kind="no_brain_work"` for every query. Root cause: the tactic catalog declares 5 tactics covering 4 legacy phase ids (`signal_extraction`, `broaden`, `red_team`, `rank_verify`), while the 8 skeleton strategies use 3 different phase ids (`extract`, `gather`, `synthesize`). Zero phase-name overlap → `_select_tactic` returns `None` → tactician early-returns empty TacticianOutput → brain subprocess never runs.

## Problem

Three intertwined defects in the strategy/tactic catalog:

1. **Missing tactics for the research-skeleton phases.** The 8 skeleton strategies declare phases `extract`, `gather`, `synthesize`, but no tactic in the catalog declares those phase ids in its `phase_compatibility` list. `_select_tactic` in `app/pipeline/tactician.py:115` filters tactics by phase, finds none compatible, returns `None`, and the tactician at line 297-306 returns a stub `TacticianOutput` without invoking the brain.

2. **Two parallel phase taxonomies in the codebase.** ACH-shaped strategies (`person`, `due_diligence`, `media_identification`) use `signal_extraction → broaden → red_team → rank_verify`. Research-skeleton strategies use `extract → gather → synthesize`. The two coexist with no mapping; mental load is doubled and the catalog must be kept aligned twice.

3. **No startup audit catches strategy/tactic misalignment.** A strategy can ship referencing a phase id with no compatible tactic. Today the only signal is a per-run WARNING log at runtime. Commit `629c161` introduced a startup audit for unknown gate-check kinds (fail-CLOSED) — the same protection is missing for phase/tactic alignment, which is why this regression shipped silently.

## Goal

After this spec ships:

- A single phase taxonomy is used everywhere: `extract → gather → [disconfirm] → synthesize`. `disconfirm` is optional; strategies that need ACH-style hypothesis refutation opt in.
- Every registered strategy has at least one compatible tactic for every phase it declares — enforced at API boot via a fail-CLOSED audit.
- Real-estate queries do real domain-aware work via the Apify Zillow actor (`apify/zillow-search-scraper`). The canonical query `"show all properties for rent in chicago with a budget of $500 to $1000"` returns real listings with sources cited.
- ACH strategies (`person`, `due_diligence`, `media_identification`) preserve their epistemic flow (disconfirmation, ACH-matrix ranking) after migration to the new phase names via `preferred_tactic_id` overrides.
- The 7 non-real-estate skeleton strategies (lead, company, place, generation, explanation, prediction, synthesis) gain functional defaults — they invoke `web_search` + `google_news` at minimum. Domain-specific techniques for those strategies are explicit follow-up work.
- All legacy phase-name strings (`signal_extraction`, `broaden`, `red_team`, `rank_verify`) are removed from `app/`, `tests/`, and `frontend/src/`. Old DB trail rows retain their legacy ids as historical records.

## Approach

This spec implements **Approach C from brainstorming** (the largest of the three approaches considered):

- 4 new default tactics (one per phase) plus 1 specialized `listings_gather` tactic.
- 1 new technique wrapping the Apify Zillow actor.
- Optional `preferred_tactic_id: str | None` field on `PhaseSpec` for strategy-author overrides.
- Startup audit covering both directions (strategy → tactic + tactic → legal phase id).
- ACH strategy migration to the unified taxonomy with appropriate overrides.
- Removal of legacy phase ids from all live code.

The smaller "spec + minimal hot-patch" alternative was rejected per the user's stated preference to **unify the taxonomy in one coherent change** rather than ship two PRs over the same surface area.

The two other rejected options from brainstorming:
- **Per-strategy-per-phase tactics (24 separate files):** breaks the existing "tactics are phase-shaped, strategies are domain-shaped" convention; high maintenance cost.
- **Force-fold `red_team` into `gather`:** loses Heuer ACH's discrete disconfirmation step; compromises epistemic discipline for naming simplicity.

## Architecture

### Phase taxonomy (single, unified)

```
extract → gather → [disconfirm] → synthesize
```

- `extract` — parse the query into typed signals. No tool calls.
- `gather` — run live retrieval against the signals. Tool calls expected.
- `disconfirm` (optional) — actively seek evidence that refutes the leading hypothesis (Heuer ACH).
- `synthesize` — rank, dedupe, finalize. No tool calls.

Strategies omit `disconfirm` by default; strategies that need ACH-style competing-hypothesis analysis opt in by including a `disconfirm={…}` overlay in their `build_research_strategy(...)` call.

### Four touchpoints

```
PhaseSpec (Pydantic)              Tactic catalog                          Strategist                Technique catalog
─────────────────────             ──────────────                          ──────────                ─────────────────
+ preferred_tactic_id             + extract_default                       _select_tactic:           + apify_listings_search
  (str | None, validated)           gather_default                          1. honor preferred       (wraps apify/
                                    disconfirm_default                       _tactic_id (if           zillow-search-scraper)
+ optional builder param            synthesize_default                       compatible)
  in research_skeleton           + listings_gather                         2. fallback to
                                    (real_estate's preferred)                existing prefs
                                                                          3. fall back to
                                  EXISTING (renamed phase_compatibility):    *_default for the
                                  + hypothesis_first_search → ["gather"]     phase
                                  + prior_research_seed → ["gather"]
                                  + ach_rank → ["synthesize"]               + startup audit
                                                                            (fail-CLOSED)
                                  RETIRED:
                                  - decompose_query (was signal_extraction)
                                  - disconfirm_search (was red_team) →
                                    becomes disconfirm_default

Strategy files                                                            Constants
─────────────                                                             ─────────
+ person.py: extract/gather/disconfirm/synthesize                          LEGAL_PHASE_IDS = {
  with preferred_tactic_id="hypothesis_first_search" on gather,              "extract", "gather",
       preferred_tactic_id="ach_rank" on synthesize                          "disconfirm", "synthesize"
+ due_diligence.py: same pattern                                           }
+ media_identification.py: migrated
+ real_estate.py: preferred_tactic_id="listings_gather" on gather
+ 7 other skeleton strategies: unchanged (use defaults)
```

### Conceptual changes

1. **`PhaseSpec` gains optional `preferred_tactic_id: str | None = None`.** Strategy authors name a specific tactic for a phase; the resolver honors it before applying default preference logic. The field is per-PhaseSpec (not a strategy-level map) for locality with sibling phase config (briefing, gate_checks, on_fail).

2. **Four default tactics for the four canonical phases.** Domain-agnostic; per-strategy briefings carry the domain context to the brain via the existing `_build_tactic_prompt` path. The defaults catch all strategies that don't override.

3. **Specialized tactics retained but re-phase-bound.** `hypothesis_first_search`, `prior_research_seed`, and `ach_rank` keep their tactic ids and produce shapes, but their `phase_compatibility` lists are migrated to the new taxonomy. ACH strategies reference them via `preferred_tactic_id`.

4. **Apify Zillow technique** wraps the existing Apify integration pattern (`app/pipeline/nodes/apify_actor.py` + `facebook_pages.py`) for property listings. `listings_gather` tactic owns this technique.

5. **Startup audit fails-CLOSED on misalignment.** Mirrors `629c161`'s pattern. Two checks: (a) every strategy phase has ≥1 compatible tactic; (b) every tactic's `phase_compatibility` contains only ids in `LEGAL_PHASE_IDS`. Either check failing prevents API boot.

### Boundaries (out of scope)

- No changes to `_run_gate`, `_aggregate`, `_build_tactic_prompt`, `_build_brain_summary`, `engine_v2._write_research_trail`, `engine_v2._phase_complete_cb`, or any of PR #116's structures.
- No changes to the budget / wallet layer (existing `budget_ru` per produce-template + `cost_class` Literal already accommodate the Apify cost surface).
- No new technique for the 7 non-real-estate skeleton strategies — they ship with `gather_default` (web_search + google_news). Domain-specific Apify actors for those verticals (e.g., LinkedIn for lead, business registries for company) are explicit follow-up specs.
- No backfill of old `research_trails` rows. Legacy phase ids in history stay as-is.

## Components and data shapes

### PhaseSpec.preferred_tactic_id (new field)

```python
# app/pipeline/catalogs/schemas.py (extends existing PhaseSpec)
class PhaseSpec(BaseModel):
    id: str
    depends_on: list[str] = []
    unit_of_work_contract: dict[str, Any]
    hypothesis_count_policy: Literal["from_dial", "fixed:1", "fixed:2", "fixed:3",
                                     "fixed:4", "fixed:5", "from_prior_phase"]
    gate: GateSpec
    preferred_tactic_id: str | None = None   # NEW

    @field_validator("preferred_tactic_id")
    @classmethod
    def _validate_tactic_id_format(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("preferred_tactic_id, if set, must be non-empty after strip()")
        # Cross-reference happens in the startup audit, not here.
        return v

    @field_validator("id")
    @classmethod
    def _validate_phase_id_is_legal(cls, v: str) -> str:
        from app.pipeline.catalogs.constants import LEGAL_PHASE_IDS
        if v not in LEGAL_PHASE_IDS:
            raise ValueError(
                f"Phase id {v!r} is not in LEGAL_PHASE_IDS={LEGAL_PHASE_IDS}. "
                f"Legacy ids (signal_extraction/broaden/red_team/rank_verify) were retired."
            )
        return v
```

### LEGAL_PHASE_IDS constant (new)

```python
# app/pipeline/catalogs/constants.py (new file)
LEGAL_PHASE_IDS: frozenset[str] = frozenset({"extract", "gather", "disconfirm", "synthesize"})
```

### Four default tactics

```python
# app/pipeline/catalogs/registries/tactics/extract_default.py (new)
TACTIC = Tactic(
    id="extract_default",
    phase_compatibility=["extract"],
    accepts={"query": "the user's original query string", "briefing": "phase briefing from the strategy"},
    produces=[],  # pure analysis — no specialist dispatch
    cost_class="cheap",
    required_techniques=[],
    enforcement={"min_distinct_outputs": 0, "no_tool_calls_required": True},
)

# app/pipeline/catalogs/registries/tactics/gather_default.py (new)
TACTIC = Tactic(
    id="gather_default",
    phase_compatibility=["gather"],
    accepts={"signals": "dict — parsed signals from extract", "briefing": "..."},
    produces=[
        {"technique_id": "web_search",
         "params_template": {"query": "{gather_query}", "max_results": 8},
         "expect_schema": {"min_results": 1},
         "fail_modes": ["no_evidence", "tool_error", "schema_violation"],
         "budget_ru": 1},
        {"technique_id": "google_news",
         "params_template": {"query": "{gather_query}", "days_back": 90},
         "expect_schema": {},
         "fail_modes": ["no_evidence", "tool_error", "schema_violation"],
         "budget_ru": 1},
    ],
    cost_class="moderate",
    required_techniques=["web_search", "google_news"],
    enforcement={"min_distinct_outputs": 1},
)

# app/pipeline/catalogs/registries/tactics/disconfirm_default.py (new — replaces disconfirm_search.py)
TACTIC = Tactic(
    id="disconfirm_default",
    phase_compatibility=["disconfirm"],
    accepts={"hypotheses": "list — leading hypotheses from gather"},
    produces=[
        {"technique_id": "web_search",
         "params_template": {"query": "{counter_hypothesis_query}", "max_results": 6},
         "expect_schema": {},
         "fail_modes": ["no_evidence", "tool_error", "schema_violation"],
         "budget_ru": 1},
    ],
    cost_class="moderate",
    required_techniques=["web_search"],
    enforcement={"min_distinct_outputs": 0},  # 0 disconfirming findings is a valid (and informative) result
)

# app/pipeline/catalogs/registries/tactics/synthesize_default.py (new)
TACTIC = Tactic(
    id="synthesize_default",
    phase_compatibility=["synthesize"],
    accepts={"evidence": "list of findings from gather/disconfirm", "briefing": "..."},
    produces=[],  # pure analysis
    cost_class="cheap",
    required_techniques=[],
    enforcement={"min_distinct_outputs": 0, "no_tool_calls_required": True},
)
```

### Specialized tactics — renamed phase_compatibility, ids unchanged

```python
# app/pipeline/catalogs/registries/tactics/hypothesis_first_search.py (existing — edit)
TACTIC = {
    "id": "hypothesis_first_search",
    "phase_compatibility": ["gather"],   # was ["broaden"]
    # ... rest unchanged ...
}

# app/pipeline/catalogs/registries/tactics/prior_research_seed.py (existing — edit)
TACTIC = {
    "id": "prior_research_seed",
    "phase_compatibility": ["gather"],   # was ["broaden"]
    # ... rest unchanged ...
}

# app/pipeline/catalogs/registries/tactics/ach_rank.py (existing — edit)
TACTIC = Tactic(
    id="ach_rank",
    phase_compatibility=["synthesize"],   # was ["rank_verify"]
    # ... rest unchanged ...
)
```

### Retired tactics

- `app/pipeline/catalogs/registries/tactics/decompose_query.py` (was `signal_extraction.py`) — **delete the file.** `extract_default` replaces it; the existing tactic id `decompose_query` had no compatibility with the new phase ids.
- `app/pipeline/catalogs/registries/tactics/disconfirm_search.py` — **delete the file.** `disconfirm_default` replaces it.

### New domain tactic + technique

```python
# app/pipeline/catalogs/registries/tactics/listings_gather.py (new)
TACTIC = Tactic(
    id="listings_gather",
    phase_compatibility=["gather"],
    accepts={"signals": "parsed real-estate criteria from extract"},
    produces=[
        {"technique_id": "apify_listings_search",
         "params_template": {
             "location": "{location}",
             "min_price": "{price_min}",
             "max_price": "{price_max}",
             "listing_type": "{listing_type}",
             "max_results": 20,
         },
         "expect_schema": {"min_results": 1},
         "fail_modes": ["no_evidence", "tool_error", "schema_violation"],
         "budget_ru": 10},   # heavier than web_search to surface Apify cost
    ],
    cost_class="expensive",
    required_techniques=["apify_listings_search"],
    enforcement={"min_distinct_outputs": 1},
)

# app/pipeline/catalogs/registries/techniques/apify_listings_search.py (new)
TECHNIQUE = {
    "id": "apify_listings_search",
    "tool_name": "apify_actor_run",   # mirrors facebook_pages.py / headless_crawler.py pattern
    "actor_slug": "apify/zillow-search-scraper",
    "input_schema": {
        "location": "str — city + optional state (e.g. 'Chicago, IL')",
        "min_price": "int | null — minimum price in USD",
        "max_price": "int | null — maximum price in USD",
        "listing_type": "Literal['rent', 'sale']",
        "max_results": "int — default 20",
    },
    "cost_class": "expensive",
    "cost_per_call_ru": 10,
}
```

### `_select_tactic` update (the only resolver change)

```python
# app/pipeline/tactician.py:_select_tactic
def _select_tactic(
    slot_idx: int,
    unit_of_work: dict[str, Any],
    tactics_catalog: dict[str, Tactic],
    phase: PhaseSpec,
) -> Tactic | None:
    compatible = {tid: t for tid, t in tactics_catalog.items() if phase.id in t.phase_compatibility}
    if not compatible:
        return None

    # NEW: honor strategy author's explicit override first
    preferred_override = getattr(phase, "preferred_tactic_id", None)
    if preferred_override and preferred_override in compatible:
        return compatible[preferred_override]
    # (If preferred_override is set but NOT compatible, the startup audit has
    # already failed — runtime fallback here is defensive only.)

    # Existing preference logic (kept for backward compat with prior_research_seed / hypothesis_first_search)
    has_prior = bool(unit_of_work.get("prior_research_summary"))
    preferred_id = "prior_research_seed" if (slot_idx == 0 and has_prior) else "hypothesis_first_search"
    if preferred_id in compatible:
        return compatible[preferred_id]
    return next(iter(compatible.values()))
```

### `research_skeleton._build_phase` update

```python
# app/pipeline/catalogs/builders/research_skeleton.py
_RECOGNIZED_OVERLAY_KEYS = {"briefing", "gate_checks", "on_fail",
                            "hypothesis_count_policy", "inputs",
                            "preferred_tactic_id"}   # NEW

def _build_phase(phase_id: str, overlay: dict[str, Any] | None, depends_on: list[str]) -> dict[str, Any]:
    overlay = overlay or {}
    unknown = set(overlay.keys()) - _RECOGNIZED_OVERLAY_KEYS
    if unknown:
        raise ValueError(f"Unknown overlay keys for phase {phase_id}: {unknown}")
    spec = {
        "id": phase_id,
        "depends_on": depends_on,
        "briefing": overlay.get("briefing", _DEFAULT_BRIEFINGS[phase_id]),
        "inputs": overlay.get("inputs", _DEFAULT_INPUTS[phase_id]),
        # ... existing fields ...
        "preferred_tactic_id": overlay.get("preferred_tactic_id"),   # NEW
    }
    return spec


def build_research_strategy(
    id: str,
    default_mode: str,
    hypothesis_count: str,
    extract: dict | None = None,
    gather: dict | None = None,
    disconfirm: dict | None = None,   # NEW — optional 4th phase
    synthesize: dict | None = None,
    ach_signals: list[dict] | None = None,
    applies_to: dict | None = None,
) -> dict:
    phases = [
        _build_phase("extract", extract, depends_on=[]),
        _build_phase("gather", gather, depends_on=["extract"]),
    ]
    if disconfirm is not None:
        phases.append(_build_phase("disconfirm", disconfirm, depends_on=["gather"]))
        phases.append(_build_phase("synthesize", synthesize, depends_on=["disconfirm"]))
    else:
        phases.append(_build_phase("synthesize", synthesize, depends_on=["gather"]))
    return {
        "id": id,
        # ... existing fields ...
        "phases": phases,
    }
```

### Startup audit (new module)

```python
# app/pipeline/catalogs/audit.py (new file)

class StrategyTacticAuditError(RuntimeError):
    pass


def audit_strategy_tactic_alignment(
    strategies: dict[str, Any],
    tactics_catalog: dict[str, Tactic],
) -> list[str]:
    """Return a list of error strings. Empty list = audit passes."""
    from app.pipeline.catalogs.constants import LEGAL_PHASE_IDS
    errors: list[str] = []

    # Check 1: every tactic declares only legal phase ids
    for tid, tactic in tactics_catalog.items():
        phase_compat = tactic.phase_compatibility if hasattr(tactic, "phase_compatibility") else tactic.get("phase_compatibility", [])
        illegal = set(phase_compat) - LEGAL_PHASE_IDS
        if illegal:
            errors.append(
                f"tactic={tid}: phase_compatibility contains illegal ids {illegal}. "
                f"Legal: {sorted(LEGAL_PHASE_IDS)}"
            )

    # Check 2: every strategy phase has at least one compatible tactic
    for sid, strategy in strategies.items():
        for phase in strategy.phases:
            compatible = [tid for tid, t in tactics_catalog.items()
                          if phase.id in t.phase_compatibility]
            if not compatible:
                errors.append(
                    f"strategy={sid} phase={phase.id}: zero compatible tactics. "
                    f"Register a tactic whose phase_compatibility includes {phase.id!r}."
                )
            preferred = getattr(phase, "preferred_tactic_id", None)
            if preferred and preferred not in compatible:
                errors.append(
                    f"strategy={sid} phase={phase.id}: preferred_tactic_id={preferred!r} "
                    f"is not in the compatible set {sorted(compatible)}."
                )

    return errors


def run_audit_or_fail() -> None:
    """Called at API boot. Raises StrategyTacticAuditError if catalog is broken."""
    from app.pipeline.catalogs.loader import load_strategies, load_tactics
    errors = audit_strategy_tactic_alignment(load_strategies(), load_tactics())
    if errors:
        msg = (
            "Strategy/tactic catalog audit FAILED (fail-CLOSED — see spec "
            "2026-05-23-research-skeleton-tactic-completion):\n\n"
            + "\n".join(f"  ✗ {e}" for e in errors)
            + "\n\nAPI will not start until the above are fixed."
        )
        raise StrategyTacticAuditError(msg)
```

Audit invocation: at API boot, in the v3 router init (or wherever `Strategist` is first constructed). Adopt the same pattern as commit `629c161`'s gate-check audit.

### Strategy migrations

**`app/pipeline/catalogs/registries/strategies/person.py` — before:**

```python
STRATEGY = {
    "id": "person",
    "phases": [
        {"id": "signal_extraction", ...},
        {"id": "broaden", "depends_on": ["signal_extraction"], ...},
        {"id": "red_team", "depends_on": ["broaden"], ...},
        {"id": "rank_verify", "depends_on": ["red_team"], ...},
    ],
}
```

**After (using build_research_strategy):**

```python
from app.pipeline.catalogs.builders.research_skeleton import build_research_strategy

STRATEGY = build_research_strategy(
    id="person",
    default_mode="comprehensive_investigation",
    hypothesis_count="multi",
    applies_to={"signals": ["who_is", "biographical"], "entity_types": ["person"]},
    extract={"briefing": "...person-specific extraction briefing..."},
    gather={
        "preferred_tactic_id": "hypothesis_first_search",
        "briefing": "...person-specific gather briefing..."
    },
    disconfirm={
        "briefing": "Actively seek evidence refuting each leading candidate...",
        # No preferred_tactic_id — uses disconfirm_default
    },
    synthesize={
        "preferred_tactic_id": "ach_rank",
        "briefing": "Rank candidates using the ACH matrix...",
    },
)
```

`due_diligence.py` and `media_identification.py` follow the same migration template, adapted per their domain briefings.

### Real-estate strategy (existing) — only one line added

```python
# app/pipeline/catalogs/registries/strategies/real_estate.py
STRATEGY = build_research_strategy(
    id="real_estate",
    # ... existing fields unchanged ...
    gather={
        "preferred_tactic_id": "listings_gather",   # NEW — only new line
        "briefing": "...existing briefing...",
        "gate_checks": [{"kind": "min_listings_returned", "params": {"min": 1}}],
    },
    # ...
)
```

### Legacy phase name removal

Grep + cleanup pass across the codebase:

```bash
grep -rn '"signal_extraction"\|"broaden"\|"red_team"\|"rank_verify"' \
  app/ tests/ frontend/src/ \
  --exclude-dir=__pycache__ --exclude-dir=node_modules
```

Categorize each hit:
- **Live code that needs renaming:** updated as part of this spec.
- **Trail-rendering code:** must continue to accept any string (legacy rows in DB). Add a comment explaining the historical exception.
- **Tests:** updated to use new phase ids.
- **Docs/specs:** updated unless they're frozen historical references (clearly dated).

A CI lint test enforces zero occurrences of the legacy ids in `app/` and `frontend/src/` after the spec lands (with a documented allowlist for trail-rendering paths).

## Data flow

After this spec, the canonical real-estate query produces this flow:

```
1. /v3/preflight → real_estate strategy selected

2. engine_v2 starts the strategist with real_estate
   STARTUP AUDIT already ran at API boot:
     real_estate.extract  → extract_default ✓
     real_estate.gather   → listings_gather (via preferred_tactic_id) ✓
     real_estate.synthesize → synthesize_default ✓
   (All 11 strategies × all declared phases audited cleanly.)

3. Strategist runs real_estate.extract
   _select_tactic → extract_default (only compatible)
   Tactician: required_techniques=[] → brain analyzes query, no tool calls
   PhaseOutput: tool_calls=0, findings>=1, source_class="training_knowledge"
   Gate: no checks declared → passes
   gate_result.passed=True

4. Strategist runs real_estate.gather
   _select_tactic: compatible={gather_default, hypothesis_first_search, prior_research_seed, listings_gather}
                   phase.preferred_tactic_id="listings_gather" → honored
   Tactician: required_techniques=["apify_listings_search"]
              → brain emits TaskSpec with {location: "chicago", min_price: 500, max_price: 1000, listing_type: "rent"}
              → specialist invokes apify_actor_run on apify/zillow-search-scraper
              → real listings returned
   PhaseOutput: tool_calls=1, findings=N, invoked_tools=["apify_listings_search"]
   Gate: min_listings_returned passes if N >= 1
   gate_result.passed=True

5. Strategist runs real_estate.synthesize
   _select_tactic: compatible={synthesize_default, ach_rank}
                   phase.preferred_tactic_id is None → fall back
                   → existing pref logic returns synthesize_default
   Tactician: required_techniques=[] → brain ranks + dedupes findings from gather
   PhaseOutput: tool_calls=0, findings=N (ranked subset)
   Gate: passes
   gate_result.passed=True

6. RunResult.status = "completed", real listings surfaced in UI.
```

Compare to ACH person flow post-migration:

```
1. /v3/preflight → person strategy selected (matches "who is" signals)
2. STARTUP AUDIT already passed.
3. extract → extract_default (parse "top 3 AI founders" → signals)
4. gather → hypothesis_first_search (via preferred_tactic_id)
            multi-hypothesis search across web/image/news
5. disconfirm → disconfirm_default (refute leading candidates)
6. synthesize → ach_rank (via preferred_tactic_id, ACH matrix ranking)
7. RunResult with ranked, ACH-scored candidates.
```

ACH semantics preserved; the only difference is phase-name convention.

### Invariants preserved

1. The PR #116 `no_brain_work` invariant still fires correctly. For extract/synthesize phases (no tools by design), `findings > 0` because the brain emits analytical findings; invariant skips them. For gather/disconfirm, both `tool_calls` and `findings` are expected positive; invariant fires only on genuine failure (Apify down, OAuth expired, etc.).
2. Visibility invariant (§7.2) unchanged. Tactician signature still rejects peer-slot data.
3. Existing gate-check kinds (`min_listings_returned`, etc.) keep firing exactly as before — they're domain-shaped, not phase-shaped.
4. Wallet/budget consumption unchanged: each produce entry's `budget_ru` is read as today.

## Error handling, edge cases, security

### Startup audit error format

The error message must be operator-actionable. Each error line includes strategy id, phase id, the specific failure, and a hint. **Illustrative example** of what an error block would look like if a future regression broke the catalog (after this spec ships, the audit should pass cleanly on a default install):

```
Strategy/tactic catalog audit FAILED (fail-CLOSED — see spec 2026-05-23-research-skeleton-tactic-completion):

  ✗ strategy=real_estate phase=gather: preferred_tactic_id="listings_gather" is not in the compatible set ['gather_default', 'hypothesis_first_search', 'prior_research_seed'].
    Hint: ensure listings_gather is registered in app/pipeline/catalogs/registries/tactics/

  ✗ tactic=foo_tactic: phase_compatibility contains illegal ids {'broaden'}. Legal: ['disconfirm', 'extract', 'gather', 'synthesize']
    Hint: legacy phase ids were retired in spec 2026-05-23. Rename phase_compatibility to use the unified taxonomy.

API will not start until the above are fixed.
```

### Edge cases

| Case | Behavior |
|---|---|
| Strategy declares unknown phase id (typo) | Pydantic validator on `PhaseSpec.id` rejects at construction (`Phase id 'extracct' is not in LEGAL_PHASE_IDS`). Caught at catalog load, before audit runs. |
| Strategy omits `disconfirm` phase | Skeleton builder doesn't emit a disconfirm PhaseSpec. Resolver never tries to resolve it. Normal. |
| `preferred_tactic_id` points to a non-existent tactic | Startup audit catches it as "not in compatible set" — clear error mentions both the referenced id and the available compatible tactics. |
| `preferred_tactic_id` points to a tactic that exists but isn't phase-compatible | Same audit branch — referenced id not in compatible set. |
| Apify actor unavailable (API key missing) | Specialist returns SpecialistError with `requires_key="APIFY_API_TOKEN"` (existing pattern from `headless_crawler.py:79-100`). Tactician records finding with `source_class="error"`. Gate fails. PR #116's structured ask_user message surfaces it. |
| Apify returns 0 listings (no matches for query) | Gate fails `min_listings_returned`. User sees the spec-§Components-mapping summary for `min_listings_returned`: "We couldn't find listings matching your criteria. Try broadening location or budget." |
| Brain emits malformed TaskSpec | Specialist validates `input_schema`; returns SpecialistError; same recovery path as Apify unavailable. |
| Existing trail rows reference legacy phase ids | `replay.py` reads them as opaque strings; renders whatever id is stored. No backfill. UI labels legacy ids on historical runs. |
| New strategy author writes `preferred_tactic_id="hypothesis_first_search"` for an `extract` phase | Audit catches: `hypothesis_first_search.phase_compatibility=["gather"]`, not compatible with extract → fail. |
| Migration cherry-picked into an environment that hasn't restarted | API restart at deploy is mandatory; audit runs at startup. If operators forget, the OLD code is still running (since the new audit code isn't loaded) → no fault, no broken state. |

### Backwards compatibility

- **DB:** zero schema migration. `research_trails.trail` is `jsonb`; new fields are additive; old rows untouched.
- **WebSocket consumers:** `is.phase_complete` event's `phase_id` is a string; consumers (replay store, AgentChat) route by string equality — they don't care about the specific id.
- **Webhook subscribers:** `webhook_deliveries` payload contains run-level data (status, error_message, run_id), not phase ids. No external break.
- **Replay endpoint:** reads `trail.phases_full[]` and returns whatever phase ids are stored. Old runs render with old ids; new runs with new ids. UI handles both opaquely.
- **Test fixtures:** every test that hardcoded a legacy phase id gets updated in lockstep within this spec's plan. CI lint test prevents regressions.

### Security checklist

- ✅ Apify API key follows the existing pattern (`apify_actor.py:_resolve_api_key` — env var → DB fallback). No new secret storage.
- ✅ Apify response data treated as untrusted: findings pass through `_FINDING_WHITELIST` (existing strategist gate at line 154). No raw HTML/JS in brain prompt or UI.
- ✅ `preferred_tactic_id` validated at Pydantic (format) + audit (cross-reference). Not eval input; just a lookup key.
- ✅ Startup audit failure exposes full detail to operator logs (intentional — admin-tier boot info). External surface is the existing 502 the tunnel returns when the API is down.
- ✅ Legacy phase name removal is a pure rename + tactic relink. No auth/identity changes.
- ✅ ACH strategy migration preserves the existing visibility invariant (§7.2) — tactician boundaries unchanged.
- ⚠️ Apify cost surface: `listings_gather` declares `budget_ru=10` per call vs `web_search`'s `budget_ru=1`. The budget envelope for the `real_estate` strategy must be sized appropriately. The audit does NOT currently compute worst-case RU; that's a follow-up observability spec.

## Testing contract

Same shape as PR #116's testing contract: both layers required (mocked unit AND real-environment functional) for every behavior. The previously committed feedback memory `feedback-real-world-testing` continues to govern.

### Both-layer coverage required

| Behavior | Mocked unit test | Real-env functional test |
|---|---|---|
| 4 default tactics registered with correct phase_compatibility | Import each, assert structure | n/a — structural |
| `listings_gather` tactic + `apify_listings_search` technique registered | Import, assert produce templates | Real Apify call (see canonical regression) |
| `PhaseSpec.preferred_tactic_id` field validator accepts None / valid string / rejects empty | Pydantic validator unit tests | n/a — structural |
| `PhaseSpec.id` field validator rejects legacy phase ids | Pydantic validator unit tests | n/a — structural |
| `_select_tactic` honors `preferred_tactic_id` first | Mocked phase + catalog; assert returned tactic | End-to-end via canonical real-estate regression run |
| Startup audit fails-CLOSED on missing tactic / bad preferred / illegal phase id | Adversarial-catalog unit tests assert `StrategyTacticAuditError` raised with right message | Boot local stack with a deliberately broken catalog; observe API doesn't start; revert |
| `research_skeleton._build_phase` recognizes `preferred_tactic_id` overlay | Unit test on the builder | n/a — covered by strategy load |
| `build_research_strategy` accepts optional `disconfirm=` overlay | Unit test asserting 3-phase output when omitted, 4-phase when supplied | Covered by ACH person migration test |
| ACH strategy migration preserves epistemic flow | Per-strategy snapshot test asserting phases = extract/gather/disconfirm/synthesize + correct preferred_tactic_id values | Real run of `"Who are the top 3 AI agent framework founders in 2026?"` — assert disconfirm phase ran, `findings` include `is_disconfirm=True` entries |
| Real-estate canonical query succeeds via Apify | n/a (requires live Apify) | Real run of `"show all properties for rent in chicago with a budget of $500 to $1000"` — assert `tool_calls >= 1`, `invoked_tools` contains `apify_listings_search`, findings exist with `source_class="listings"` |
| Generic skeleton path works | Strategist test with stub tactician returning findings | Real run of any non-real-estate skeleton query — assert `tool_calls >= 1`, `invoked_tools` contains `web_search` or `google_news` |
| Legacy phase ID strings removed | CI lint: `grep -r '"broaden"\|"red_team"\|"rank_verify"\|"signal_extraction"' app/ tests/ frontend/src/ --exclude-dir=__pycache__ --exclude-dir=node_modules` returns 0 hits (allowlist documented in CI script for trail-rendering paths) | n/a — static |

### Functional-test execution protocol (inherited from PR #116)

Each task or PR slice in this spec's plan must include:

1. `docker compose ps` output at test time
2. Exact query string used
3. Resulting RUN_ID
4. DB row showing the new behavior OR API response JSON OR UI screenshot
5. Confirmation of `localhost:8000` vs tunnel path tested
6. **For Apify-touching tests:** tail of `app.pipeline.tactician.specialist` logs showing the `apify_actor_run` call + response shape

### Canonical regression tests

Extend the existing PR #116 regression test set:

```
Real-estate (Apify path):
  Query: "show all properties for rent in chicago with a budget of $500 to $1000"
  Assertion: status=="succeeded" AND tool_calls>=1 AND any(t == "apify_listings_search" for t in invoked_tools) AND findings>=1 AND any(f.source_class=="listings" for f in findings)

ACH person path:
  Query: "Who are the top 3 AI agent framework founders in 2026?"
  Assertion: status in ("succeeded", "ask_user") AND tool_calls>=3 AND any(phase.phase_id=="disconfirm" for phase in trail.phases_full) AND the disconfirm phase's findings include is_disconfirm=True entries

Generic skeleton path:
  Query: "Summarize recent advancements in quantum error correction"
  Assertion: status in ("succeeded", "ask_user") AND tool_calls>=1 AND any(t in {"web_search", "google_news"} for t in invoked_tools)
```

The existing PR #116 regression test (`canonical no-brain-work query cannot silently no-op`) remains in place — after this spec, it should evaluate the `succeeded` branch (real work was done) rather than the `ask_user` branch.

### Audit unit tests (new test file)

`app/pipeline/tests/test_startup_audit.py`:

- `test_audit_passes_on_clean_catalog`
- `test_audit_fails_when_strategy_phase_has_no_compatible_tactic`
- `test_audit_fails_when_preferred_tactic_id_is_not_compatible`
- `test_audit_fails_when_tactic_declares_legacy_phase_id`
- `test_audit_error_message_includes_strategy_id_phase_id_and_compatible_set`

### Structured logging for Apify cost visibility

```python
log.info(
    "tactician.apify_actor_call",
    extra={
        "run_id": ...,
        "phase_id": "gather",
        "actor_slug": "apify/zillow-search-scraper",
        "input_summary": {"location": ..., "min_price": ..., "max_price": ...},
        "result_count": len(items),
        "duration_ms": ...,
        "ru_charged": 10,
    },
)
```

For trend analysis (how often Apify fires, average cost per real-estate run).

## Out of scope (explicit)

- Apify actors for the other 7 skeleton strategy domains (lead/company/place/generation/explanation/prediction/synthesis). They use `gather_default` (web_search + google_news) for now. Each domain may get its own follow-up spec adding specialized techniques.
- Cost-budget pre-flight check that estimates worst-case RU for a strategy ahead of run start. Useful follow-up but separate spec.
- Replacing the existing strategist preference logic (`slot_idx == 0 AND prior_research_summary`) with a more general policy. Out of scope; keep current behavior.
- Migrating the legacy `signal_extraction` / `broaden` / `red_team` / `rank_verify` ids in old `research_trails` rows. No backfill.
- Changing the Apify integration pattern (env-var-only key resolution, single actor per run, sync call). Out of scope.

## Implementation ordering constraints

The plan **must** respect these ordering rules to avoid breaking the catalog at intermediate states on `main`:

1. **`PhaseSpec.id` field validator (`LEGAL_PHASE_IDS` check) is added LAST**, after every strategy has been migrated to the unified taxonomy. Adding it earlier would crash catalog loading because unmigrated strategies still declare legacy phase ids — module-import-time crash, API won't even start to run the audit. The migration order: add tactics first → migrate strategies next → add validator + audit last.
2. **Audit runs at boot, not at every request.** Pydantic validators are enforced at catalog load, audit is enforced once during API startup. Audit should not run inside per-request hot paths.
3. **Retired tactic file deletes happen in the same commit as their replacements being registered.** Never leave a state where a strategy references a tactic that's been deleted and no replacement is registered yet.

## Open questions for implementation plan

These are deliberately deferred to the implementation plan:

1. The exact CI lint mechanism for the legacy-phase-id grep (separate test file invoked by pytest, OR a `.github/workflows/` step, OR a Makefile target). Pick during plan.
2. Whether the `media_identification` strategy can be folded into `build_research_strategy` cleanly or needs to stay hand-written. Inspect during plan; if it needs to stay hand-written, document why and ensure it still uses the unified phase ids.
3. The exact placement of `run_audit_or_fail()` invocation (in `app/main.py` startup, in `Strategist.__init__`, or in a v3 router init). Verify during plan.
4. Whether existing `app/pipeline/tests/test_strategy_gate_audit.py` should be extended to also cover the new audit, or a new test file is cleaner. Plan-time decision.
5. Apify input-schema normalization: the Zillow scraper's exact input fields may differ from `{location, min_price, max_price, listing_type}` — the plan should verify against the live actor's API and adapt the schema if necessary.
