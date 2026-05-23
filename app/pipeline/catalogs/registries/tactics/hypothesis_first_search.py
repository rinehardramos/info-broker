"""Tactic catalog entry: hypothesis_first_search.

Picks live-search techniques (web, image, news) to generate evidence for a
single hypothesis in the BROADEN phase.  The tactician instantiates one set of
these tasks per hypothesis it is responsible for.

Design ref: docs/intelligence/three-tier-brain-architecture.md §4.2, §9
"""
from __future__ import annotations

TACTIC = {
    "id": "hypothesis_first_search",
    "phase_compatibility": ["gather"],
    "accepts": {
        "signals": "dict — parsed signal hierarchy from signal_extraction phase",
        "prior_research_summary": "optional — RAG summary string; treated as H_PRIOR seed, not answer",
        "forbidden_candidates": "optional list — identities forbidden as primary hypothesis (adversarial mode)",
    },
    "cost_class": "moderate",
    "required_techniques": ["web_search", "image_search", "google_news"],
    # Hard floor checked by the broaden gate — the tactician must surface at
    # least this many distinct identity candidates across all its tasks.
    "enforcement": {
        "min_distinct_outputs": 3,
    },
    "produces": [
        {
            "technique_id": "web_search",
            "params_template": {
                "query": "{hypothesis_query}",
                "max_results": 8,
            },
            "expect_schema": {
                "min_results": 3,
            },
            "fail_modes": ["no_evidence", "tool_error", "schema_violation"],
            "budget_ru": 1,
        },
        {
            "technique_id": "image_search",
            "params_template": {
                "query": "{hypothesis_query}",
                "max_results": 8,
            },
            "expect_schema": {
                "min_results": 3,
            },
            "fail_modes": ["no_evidence", "tool_error", "schema_violation"],
            "budget_ru": 1,
        },
        {
            "technique_id": "google_news",
            "params_template": {
                "query": "{hypothesis_query} recent",
                "days_back": 90,
            },
            "expect_schema": {},
            "fail_modes": ["no_evidence", "tool_error", "schema_violation"],
            "budget_ru": 1,
        },
    ],
}
