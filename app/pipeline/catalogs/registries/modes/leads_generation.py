"""Mode catalog entry: leads_generation.

Fast, resource-heavy mode for contact/lead extraction with paired hypotheses.
Design ref: docs/intelligence/three-tier-brain-architecture.md §4.4
"""
from __future__ import annotations

MODE = {
    "id": "leads_generation",
    "dial_defaults": {
        "speed": "fast",
        "capability": "general",
        "resource": "heavy",
        "depth": "shallow",
        "hypothesis_count": "paired",
    },
    # TODO post-MVP: populate tactic_bias (contact_extraction, linkedin_lookup)
    "tactic_bias": {},
    # TODO post-MVP: populate strategy_suggestions from classifier calibration
    "strategy_suggestions": [],
}
