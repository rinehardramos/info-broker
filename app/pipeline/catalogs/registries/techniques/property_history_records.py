"""Technique catalog entry: property_history_records.

Key-free PROPERTY HISTORY + FINANCIAL/TAX records from public sources. Maps to
``run_web_crawl`` — crawls a county recorder-of-deeds / treasurer / assessor page
(or the listing's price-history section) for a property and returns its parsed
text, from which the brain extracts:
  - ownership / deed history → PREVIOUS OWNERS + transfer dates + sale prices
  - tax records → assessed value history + tax-bill amounts + delinquency
  - financial signals → recorded mortgages / liens, last sale price
These are authoritative public records (recorder/assessor/treasurer are official),
so findings sourced from them are classed primary_official. No API key.
"""
from __future__ import annotations

TECHNIQUE = {
    "id": "property_history_records",
    "tool_name": "run_web_crawl",
    "input_schema": {
        "type": "object",
        "required": ["urls"],
        "properties": {
            "urls": {
                "type": "string",
                "description": (
                    "Recorder-of-deeds / treasurer / assessor history URL(s) for the "
                    "property, or the listing's price-history page (JSON array, single "
                    "URL, or comma-separated)."
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
