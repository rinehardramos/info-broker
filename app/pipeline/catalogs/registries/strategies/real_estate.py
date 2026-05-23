"""Strategy catalog entry: real_estate.

Property-listing search — parse criteria, query listing sources, rank by fit.
Default mode: data_retrieval (structured-source-first, single hypothesis).
"""
from __future__ import annotations

from app.pipeline.catalogs.builders.research_skeleton import build_research_strategy

STRATEGY = build_research_strategy(
    id="real_estate",
    default_mode="data_retrieval",
    hypothesis_count="single",
    applies_to={
        "signals": ["properties_in", "for_rent", "for_sale", "mls_listings"],
        "entity_types": ["property", "listing"],
    },
    extract={
        "briefing": (
            "Parse the property-search criteria from the query. Extract: "
            "location (city/neighborhood/zip), price band (min/max), listing "
            "type (rent vs sale), property type (house/condo/apartment/land), "
            "bed/bath count, and any explicit must-haves (e.g. pet-friendly, "
            "furnished). Emit a signal dict the gather phase can query against. "
            "No tool calls — pure analysis of the query text."
        ),
    },
    gather={
        "preferred_tactic_id": "listings_gather",
        "briefing": (
            "Query live property-listing sources (MLS portals, Zillow, "
            "Trulia, Realtor.com, Redfin, Craigslist housing) for listings "
            "matching the extracted criteria. For each result capture: URL, "
            "list price, full address, beds/baths, sqft, listing date, and "
            "the source name. Skip results that violate hard criteria."
        ),
        "gate_checks": [
            # Unknown kind today → fails open. Implement at runtime later.
            {"kind": "min_listings_returned", "params": {"min": 1}},
        ],
    },
    synthesize={
        "briefing": (
            "Rank listings by criteria fit (price closer to mid-band, more "
            "must-haves matched). Dedupe across sources by address. Return "
            "the top listings with full record and source URL cited."
        ),
    },
)
