"""Three-phase research-strategy skeleton: extract → gather → synthesize.

Most domain strategies fit this shape — parse the query into typed signals,
run live retrieval against those signals, then rank+dedupe the results.
This factory emits the boilerplate so each domain strategy file only has
to supply per-phase overlays (briefing + gate checks + the occasional
hypothesis-count tweak).

Strategies that need the ACH backbone (broaden / red_team / rank_verify)
do NOT use this skeleton — they stay hand-written. See media_identification.

Convention contract with the catalog loader:
    Each strategy module exports ``STRATEGY = build_research_strategy(...)``
    at module top-level. The loader picks it up via the ``STRATEGY``
    constant; no registration step.
"""
from __future__ import annotations

from typing import Any


# Default briefings used when an overlay doesn't supply one. Phrased generically
# enough that they read sensibly for any intent that didn't bother overriding
# them — they describe what the phase *does*, not what domain it does it for.
_DEFAULT_BRIEFINGS: dict[str, str] = {
    "extract": (
        "Parse the user's query into typed signals. No tool calls — pure analysis. "
        "Identify the primary subject, supporting attributes, and any explicit "
        "constraints (price, location, date range, entity type, etc)."
    ),
    "gather": (
        "Run live searches against the extracted signals. Use the search engines "
        "and any structured registries appropriate to the query. Return raw "
        "evidence with source attribution."
    ),
    "synthesize": (
        "Rank and dedupe the gathered evidence. Return the final result set "
        "with sources cited per claim."
    ),
}

# Default phase inputs — describe what each phase reads from the prior step.
# extract reads the raw query, gather reads extract's signals, synthesize reads
# gather's evidence.
_DEFAULT_INPUTS: dict[str, list[str]] = {
    "extract":   ["query", "classifier_output"],
    "gather":    ["signals"],
    "synthesize": ["evidence"],
}


def _build_phase(phase_id: str, overlay: dict[str, Any] | None, depends_on: list[str]) -> dict[str, Any]:
    """Compose one phase dict from defaults + overlay.

    Recognised overlay keys:
        briefing:                str — phase briefing
        gate_checks:             list[dict] — gate check specs ({kind, params})
        on_fail:                 str — "replan" | "swap_tactic" | "ask_user" | "terminate"
        hypothesis_count_policy: str — "fixed:N" | "from_dial" | "from_prior_phase"
        inputs:                  list[str] — override default phase inputs
    """
    ov = overlay or {}
    return {
        "id": phase_id,
        "depends_on": depends_on,
        "unit_of_work_contract": {
            "inputs": ov.get("inputs", _DEFAULT_INPUTS[phase_id]),
            "briefing": ov.get("briefing", _DEFAULT_BRIEFINGS[phase_id]),
        },
        "hypothesis_count_policy": ov.get("hypothesis_count_policy", "fixed:1"),
        "gate": {
            # Empty checks list = the gate auto-passes. Domain strategies opt in
            # to enforcement by supplying gate_checks. Unknown check kinds also
            # auto-pass (strategist.py:303-306), so forward-looking checks like
            # min_listings_matching_criteria are safe to declare before they're
            # implemented in the runtime — they document intent without breaking
            # phases.
            "checks": ov.get("gate_checks", []),
            "on_fail": ov.get("on_fail", "ask_user"),
        },
    }


def build_research_strategy(
    *,
    id: str,
    default_mode: str = "quick_lookup",
    hypothesis_count: str = "single",
    extract: dict[str, Any] | None = None,
    gather: dict[str, Any] | None = None,
    synthesize: dict[str, Any] | None = None,
    ach_signals: list[dict[str, Any]] | None = None,
    applies_to: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a 3-phase research-strategy STRATEGY dict.

    Args:
        id:               strategy id (e.g. "real_estate")
        default_mode:     mode this strategy naturally aligns to
        hypothesis_count: ``budget_minimums.hypothesis_count`` value
        extract / gather / synthesize: per-phase overlays — see _build_phase
        ach_signals:      optional ACH signal list (rare for skeleton strategies)
        applies_to:       optional classifier-signal selector dict

    Returns:
        A STRATEGY dict ready for catalog loader validation.
    """
    return {
        "id": id,
        "ach_signals": ach_signals or [
            {"id": "match", "label": "Result relevance", "weight": 1.0, "penalty_on_mismatch": 0.5},
        ],
        "applies_to": applies_to or {"signals": [], "entity_types": []},
        "default_mode": default_mode,
        "budget_minimums": {"hypothesis_count": hypothesis_count},
        "phases": [
            _build_phase("extract",    extract,    depends_on=[]),
            _build_phase("gather",     gather,     depends_on=["extract"]),
            _build_phase("synthesize", synthesize, depends_on=["gather"]),
        ],
    }
