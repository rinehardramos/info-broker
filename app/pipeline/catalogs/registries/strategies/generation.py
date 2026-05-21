"""Strategy catalog entry: generation.

Idea/option proposal — "design a", "invent", "come up with N options".
Default mode: investigation (the brain needs to think; not a simple lookup).
"""
from __future__ import annotations

from app.pipeline.catalogs.builders.research_skeleton import build_research_strategy

STRATEGY = build_research_strategy(
    id="generation",
    default_mode="investigation",
    hypothesis_count="competing",
    applies_to={
        "signals": ["build_a", "create_a", "design_a", "invent", "develop_a", "make_a_new"],
        "entity_types": [],
    },
    extract={
        "briefing": (
            "Decompose the design brief. Identify: the artifact type "
            "(product, plan, design, recipe, system), the goal it must "
            "achieve, the explicit constraints (budget, time, materials, "
            "audience), and any anti-requirements the user named. Emit a "
            "brief spec the gather phase can search prior art against."
        ),
    },
    gather={
        "briefing": (
            "Search for prior art, comparable solutions, design patterns, "
            "and reference examples that satisfy similar constraints. "
            "Surface 3–5 references per option direction. Tag each with the "
            "constraints it satisfies/violates."
        ),
    },
    synthesize={
        "briefing": (
            "Propose N distinct options (default 3). Each option must: "
            "1) describe the approach in two sentences, 2) cite ≥1 reference "
            "from the gather phase, 3) make explicit trade-offs against the "
            "constraints, 4) name the failure mode. Rank by best-overall-fit."
        ),
        "gate_checks": [
            {"kind": "min_options_with_rationale", "params": {"min": 2}},
        ],
    },
)
