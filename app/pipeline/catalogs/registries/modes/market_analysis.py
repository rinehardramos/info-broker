"""Mode catalog entry: market_analysis.

Normal-speed, deep mode for comparative trend analysis with competing hypotheses.
Design ref: docs/intelligence/three-tier-brain-architecture.md §4.4
"""
from __future__ import annotations

MODE = {
    "id": "market_analysis",
    "dial_defaults": {
        "speed": "normal",
        "capability": "general",
        "resource": "heavy",
        "depth": "deep",
        "hypothesis_count": "competing",
    },
    # TODO post-MVP: populate tactic_bias (comparative, trend_analysis)
    "tactic_bias": {},
    # TODO post-MVP: populate strategy_suggestions from classifier calibration
    "strategy_suggestions": [],
}
