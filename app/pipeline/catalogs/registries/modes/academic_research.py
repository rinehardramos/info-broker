"""Mode catalog entry: academic_research.

Slow, high-capability, abyss-depth mode for primary-source citation research.
Design ref: docs/intelligence/three-tier-brain-architecture.md §4.4
"""
from __future__ import annotations

MODE = {
    "id": "academic_research",
    "dial_defaults": {
        "speed": "slow",
        "capability": "high",
        "resource": "medium",
        "depth": "abyss",
        "hypothesis_count": "competing",
    },
    # TODO post-MVP: populate tactic_bias (primary_source, citation_chain)
    "tactic_bias": {},
    # Academic intents in priority order. "researcher" alias of the
    # citation-chain shape; synthesis covers literature-review queries.
    "strategy_suggestions": ["researcher", "synthesis", "generic_search"],
}
