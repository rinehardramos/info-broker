"""Mode catalog entry: quick_lookup.

Speed-first mode for single-answer factual lookups.
Design ref: docs/intelligence/three-tier-brain-architecture.md §4.4
"""
from __future__ import annotations

MODE = {
    "id": "quick_lookup",
    "dial_defaults": {
        "speed": "fast",
        "capability": "light",
        "resource": "tiny",
        "depth": "shallow",
        "hypothesis_count": "single",
    },
    # TODO post-MVP: populate tactic_bias with retrieval-heavy weights
    "tactic_bias": {},
    # Walked by _resolve_strategy when intent has no dedicated module.
    # quick_lookup is the catch-all speed-first mode → generic_search is
    # the natural fit.
    "strategy_suggestions": ["generic_search"],
}
