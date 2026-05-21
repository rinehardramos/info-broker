"""Generic-search fallback strategy.

Used whenever the orchestrator classifies a query into an intent that does
not yet have a dedicated strategy module. Single-phase live retrieval, no
hypothesis competition, no red-team — purely "ask the search engines and
return what they say."

This is also the canonical example of a no-overlay skeleton strategy: the
factory call below produces the same shape as a hand-written 3-phase
module would, with no per-phase customisation. When a dedicated strategy
module ships for an intent, ``_resolve_strategy`` will prefer it
automatically — this is a *floor*, not a ceiling.
"""
from __future__ import annotations

from app.pipeline.catalogs.builders.research_skeleton import build_research_strategy

STRATEGY = build_research_strategy(
    id="generic_search",
    default_mode="quick_lookup",
    hypothesis_count="single",
    applies_to={"signals": ["fallback_any_intent"], "entity_types": []},
)
