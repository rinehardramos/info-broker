"""Apify Zillow property-listing scraper as a research-pipeline technique.

Wraps the apify/zillow-search-scraper actor via the existing apify_actor_run
dispatch pattern (see app/pipeline/nodes/apify_actor.py + facebook_pages.py).

Used by the listings_gather tactic for real_estate strategy's gather phase.
"""

TECHNIQUE = {
    "id": "apify_listings_search",
    "tool_name": "apify_actor_run",
    "actor_slug": "apify/zillow-search-scraper",
    "input_schema": {
        "location": "str — city + optional state (e.g. 'Chicago, IL')",
        "min_price": "int | null — minimum price in USD",
        "max_price": "int | null — maximum price in USD",
        "listing_type": "Literal['rent', 'sale']",
        "max_results": "int — default 20",
    },
    "cost_class": "expensive",
    "cost_per_call_ru": 10,
}
