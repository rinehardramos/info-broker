"""Tactic catalog entry: prior_research_seed.

Seeds exactly ONE candidate hypothesis (H_PRIOR) from prior research (RAG)
into the BROADEN phase.  This tactic is always paired with
``hypothesis_first_search`` — it does NOT produce the answer; it occupies
one slot among N competing hypotheses.

Anti-tunneling property (§4.4, issue #89): ``seeds_h_prior_only=True``
signals to the tactician selector and the broaden gate that this tactic
contributes a single H_PRIOR candidate.  The remaining N-1 hypothesis
slots MUST be filled by other tactics (e.g. ``hypothesis_first_search``)
that derive candidates purely from signals — no RAG anchoring.

Design ref: docs/intelligence/three-tier-brain-architecture.md §4.2, §4.4, §9
"""
from __future__ import annotations

TACTIC = {
    "id": "prior_research_seed",
    "phase_compatibility": ["gather"],
    "accepts": {
        "signals": "dict — parsed signal hierarchy from signal_extraction phase",
        "query": "str — original query string passed through from the run context",
    },
    "cost_class": "cheap",
    "required_techniques": ["prior_research"],
    # max_outputs=1 enforces a single H_PRIOR candidate — the RAG hit may not
    # expand into multiple hypotheses.  seeds_h_prior_only prevents the
    # tactician from treating the returned candidate as confirmed or
    # upweighted relative to live-search hypotheses.
    "enforcement": {
        "max_outputs": 1,
        "seeds_h_prior_only": True,
    },
    "produces": [
        {
            "technique_id": "prior_research",
            "params_template": {
                "query": "{original_query}",
                "k": 3,
            },
            "expect_schema": {},
            "fail_modes": ["no_evidence", "tool_error", "schema_violation"],
            "budget_ru": 1,
        },
    ],
}
