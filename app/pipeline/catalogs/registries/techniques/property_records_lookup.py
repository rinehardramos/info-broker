"""Technique catalog entry: property_records_lookup.

Key-free owner-of-record enrichment from PUBLIC records. Maps to
``run_web_crawl`` — crawls a county assessor / recorder-of-deeds / property-tax
page (found via web_search) for a property address and returns its parsed text,
from which the brain extracts the owner of record + mailing address. These
government sources are the authoritative, free owner identity — no API key, and
often better than paid people-search for owner names. The brain first finds the
right county-records URL via web_search, then crawls it here.
"""
from __future__ import annotations

TECHNIQUE = {
    "id": "property_records_lookup",
    "tool_name": "run_web_crawl",
    "input_schema": {
        "type": "object",
        "required": ["urls"],
        "properties": {
            "urls": {
                "type": "string",
                "description": (
                    "County assessor / recorder / property-tax URL(s) for the "
                    "address (JSON array, single URL, or comma-separated)."
                ),
            },
            "max_pages": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
            "scrape_depth": {"type": "integer", "default": 1, "minimum": 1, "maximum": 2},
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
                        "url": {"type": "string"},
                        "content": {"type": "string"},
                        "title": {"type": "string"},
                    },
                },
            }
        },
    },
    "cost_class": "moderate",
    "failure_modes": ["no_evidence", "tool_error", "empty_page", "blocked"],
    "retry_policy": {"max_retries": 1, "backoff_s": 2, "retryable_on": ["transport_error", "timeout"]},
}
