"""Apify Zillow property-listing scraper as a research-pipeline technique.

Wraps the apify/zillow-search-scraper actor via the existing apify_actor_run
dispatch pattern (see app/pipeline/nodes/apify_actor.py).
Used by the listings_gather tactic for real_estate strategy's gather phase.
"""
from __future__ import annotations

TECHNIQUE = {
    "id": "apify_listings_search",
    "tool_name": "apify_actor_run",
    "actor_slug": "apify/zillow-search-scraper",
    "input_schema": {
        "type": "object",
        "required": ["location"],
        "properties": {
            "location": {
                "type": "string",
                "description": "City + optional state (e.g. 'Chicago, IL')",
            },
            "min_price": {
                "type": ["integer", "null"],
                "description": "Minimum price in USD",
            },
            "max_price": {
                "type": ["integer", "null"],
                "description": "Maximum price in USD",
            },
            "listing_type": {
                "type": "string",
                "enum": ["rent", "sale"],
                "description": "Type of listing to search",
            },
            "max_results": {
                "type": "integer",
                "default": 20,
                "minimum": 1,
                "maximum": 100,
                "description": "Maximum number of results to return",
            },
        },
        "additionalProperties": False,
    },
    "output_schema": {
        "type": "object",
        "required": ["results"],
        "properties": {
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "address": {"type": "string"},
                        "price": {"type": ["integer", "number", "null"]},
                        "beds": {"type": ["integer", "null"]},
                        "baths": {"type": ["number", "null"]},
                        "sqft": {"type": ["integer", "null"]},
                        "listing_type": {"type": "string"},
                    },
                },
            },
        },
    },
    "cost_class": "expensive",
    "cost_per_call_ru": 10,
    "failure_modes": [
        "no_results",
        "rate_limited",
        "actor_timeout",
    ],
    "retry_policy": {
        "max_retries": 1,
        "backoff_s": 5,
        "retryable_on": ["transport_error", "timeout"],
    },
}
