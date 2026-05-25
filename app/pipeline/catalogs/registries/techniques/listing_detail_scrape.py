"""Technique catalog entry: listing_detail_scrape.

Key-free per-listing contact enrichment. Maps to ``run_web_search_fetch`` with
fetch_content=true — searches for a specific listing/address and fetches the
listing's own detail page text, from which the brain extracts the listing-agent
and (often) owner contact details. This is the FREE primary path for contact
enrichment: listing detail pages routinely carry agent name + phone + a contact
form, and FSBO pages carry the owner directly. No API key required.
"""
from __future__ import annotations

TECHNIQUE = {
    "id": "listing_detail_scrape",
    "tool_name": "run_web_search_fetch",
    "input_schema": {
        "type": "object",
        "required": ["query"],
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Targeted query for one listing/address, e.g. "
                    "'123 Main St Chicago IL listing agent contact' or the "
                    "listing detail URL's address."
                ),
            },
            "max_results": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
            "fetch_content": {
                "type": "boolean",
                "default": True,
                "description": "Must be true — fetch + extract the detail-page text to read contacts.",
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
                    "required": ["url"],
                    "properties": {
                        "title": {"type": "string"},
                        "url": {"type": "string"},
                        "snippet": {"type": "string"},
                        "content": {"type": "string"},
                    },
                },
            }
        },
    },
    "cost_class": "moderate",
    "failure_modes": ["no_results", "rate_limited", "engine_unreachable", "empty_page"],
    "retry_policy": {"max_retries": 2, "backoff_s": 1, "retryable_on": ["transport_error", "timeout"]},
}
