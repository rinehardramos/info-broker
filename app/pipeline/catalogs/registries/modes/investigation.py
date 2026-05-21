"""Mode catalog entry: investigation.

Slow, high-capability, adversarial mode for deep OSINT investigations.
This is the default mode for media_identification (anti-tunneling optimized).
Design ref: docs/intelligence/three-tier-brain-architecture.md §4.4, §9
"""
from __future__ import annotations

MODE = {
    "id": "investigation",
    "dial_defaults": {
        "speed": "slow",
        "capability": "high",
        "resource": "heavy",
        "depth": "deep",
        "hypothesis_count": "adversarial",
    },
    # TODO post-MVP: populate tactic_bias (counter_curation, disconfirm, wayback)
    "tactic_bias": {},
    # Investigative intents in priority order. media_identification is the
    # only ACH-shaped one today; person + due_diligence are placeholders
    # for future ACH-shaped strategy modules.
    "strategy_suggestions": ["media_identification", "person", "due_diligence", "generic_search"],
}
