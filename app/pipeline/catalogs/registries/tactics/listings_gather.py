"""Domain-specific gather tactic for real-estate queries.

Invokes the apify/zillow-search-scraper actor via apify_listings_search
technique. Used by real_estate strategy via preferred_tactic_id.
"""
from app.pipeline.catalogs.schemas import Tactic


TACTIC = Tactic(
    id="listings_gather",
    phase_compatibility=["gather"],
    accepts={
        "signals": "parsed real-estate criteria from extract (location, "
                   "price_min, price_max, listing_type)",
    },
    produces=[
        {
            "technique_id": "apify_listings_search",
            "params_template": {
                "location": "{location}",
                "min_price": "{price_min}",
                "max_price": "{price_max}",
                "listing_type": "{listing_type}",
                "max_results": 20,
            },
            "expect_schema": {"min_results": 1},
            "fail_modes": ["no_evidence", "tool_error", "schema_violation"],
            "budget_ru": 10,  # heavier than web_search to surface Apify cost to the budget layer
        },
    ],
    cost_class="expensive",
    required_techniques=["apify_listings_search"],
    enforcement={"min_distinct_outputs": 1},
)
