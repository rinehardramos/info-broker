"""Strategy catalog entry: explanation.

Causal / mechanism explanation — "why X happened", "root cause", "diagnose".
Default mode: investigation (needs alternative-hypothesis reasoning).
"""
from __future__ import annotations

from app.pipeline.catalogs.builders.research_skeleton import build_research_strategy

STRATEGY = build_research_strategy(
    id="explanation",
    default_mode="investigation",
    hypothesis_count="competing",
    applies_to={
        "signals": ["why_", "root_cause", "diagnose", "how_does", "what_caused", "debug"],
        "entity_types": [],
    },
    extract={
        "briefing": (
            "Identify the phenomenon the user wants explained. Capture the "
            "observed effect, the time/context in which it occurred, and any "
            "candidate causes the user has already named. Note whether the "
            "question is asking for a mechanism (how does X work) vs an "
            "incident root cause (why did X fail)."
        ),
    },
    gather={
        "briefing": (
            "Search for established mechanisms, prior case studies, and "
            "expert commentary on the phenomenon. For each candidate cause, "
            "gather supporting and disconfirming evidence. Treat absence of "
            "evidence against a cause as soft support, not proof."
        ),
    },
    synthesize={
        "briefing": (
            "Rank candidate mechanisms/causes by support strength. Surface "
            "≥1 alternative explanation the user did NOT name. For each, "
            "state: the mechanism, the evidence chain, the open questions. "
            "Do not collapse to a single answer if the evidence is mixed."
        ),
        "gate_checks": [
            {"kind": "min_mechanisms_with_support", "params": {"min": 2}},
        ],
    },
)
