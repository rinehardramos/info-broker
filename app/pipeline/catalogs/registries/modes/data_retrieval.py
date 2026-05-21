"""Mode catalog entry: data_retrieval.

Fast, light mode for structured-source data fetching (e.g., TMDB, databases).
Design ref: docs/intelligence/three-tier-brain-architecture.md §4.4
"""
from __future__ import annotations

MODE = {
    "id": "data_retrieval",
    "dial_defaults": {
        "speed": "fast",
        "capability": "light",
        "resource": "medium",
        "depth": "search",
        "hypothesis_count": "single",
    },
    # TODO post-MVP: populate tactic_bias (tmdb, structured-source-first)
    "tactic_bias": {},
    # Structured-source intents in priority order, then generic floor.
    "strategy_suggestions": ["real_estate", "place", "company", "generic_search"],
}
