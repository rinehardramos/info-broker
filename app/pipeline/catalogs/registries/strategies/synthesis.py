"""Strategy catalog entry: synthesis.

Multi-source review / literature review / "compare and summarize".
Default mode: academic_research (depth-first, primary sources).
"""
from __future__ import annotations

from app.pipeline.catalogs.builders.research_skeleton import build_research_strategy

STRATEGY = build_research_strategy(
    id="synthesis",
    default_mode="academic_research",
    hypothesis_count="competing",
    applies_to={
        "signals": ["review_", "summarize_", "compare_", "evaluate_", "assess_", "state_of"],
        "entity_types": [],
    },
    extract={
        "briefing": (
            "Identify the topic to synthesize and the source classes the "
            "user wants consulted (peer-reviewed papers, industry reports, "
            "blog posts with named authors, official datasets, news). Note "
            "any explicit recency cut-off."
        ),
    },
    gather={
        "briefing": (
            "Locate sources in each named class. For each source extract "
            "(a) the central claim, (b) the evidence type it cites, (c) the "
            "date and author. Aim for ≥3 sources per claim before concluding "
            "consensus exists."
        ),
    },
    synthesize={
        "briefing": (
            "Merge claims across sources. Surface: (1) where sources agree "
            "(with citation count), (2) where they disagree (and the basis "
            "of disagreement), (3) gaps where no source spoke. Cite per "
            "claim, not per source. Do not paper over disagreement."
        ),
        "gate_checks": [
            {"kind": "min_sources_synthesized", "params": {"min": 3}},
        ],
    },
)
