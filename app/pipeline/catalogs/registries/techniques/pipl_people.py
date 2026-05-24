"""Technique catalog entry: pipl_people.

Maps to the ``run_pipl_search`` MCP tool — people search via Pipl for
contact aggregation (email, phone, address, social profiles). Used by
leads_enrich_gather to find listing-agent and property-owner personal
contact details during real-estate leads generation.
"""
from __future__ import annotations

TECHNIQUE = {
    "id": "pipl_people",
    "tool_name": "run_pipl_search",
    "input_schema": {
        "type": "object",
        "properties": {
            "first_name": {
                "type": "string",
                "description": "First name of the person",
            },
            "last_name": {
                "type": "string",
                "description": "Last name of the person",
            },
            "email": {
                "type": "string",
                "description": "Email address to cross-reference",
            },
            "phone": {
                "type": "string",
                "description": "Phone number to cross-reference",
            },
            "city": {
                "type": "string",
                "description": "City to narrow the search",
            },
            "state": {
                "type": "string",
                "description": "State abbreviation (e.g. 'IL')",
            },
        },
        "additionalProperties": False,
    },
    "output_schema": {
        "type": "object",
        "required": ["people"],
        "properties": {
            "people": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": ["string", "null"]},
                        "emails": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "phones": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "addresses": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "social_profiles": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "match_score": {"type": ["number", "null"]},
                    },
                },
            },
        },
    },
    "cost_class": "moderate",
    "cost_per_call_ru": 3,
    "failure_modes": [
        "no_results",
        "rate_limited",
        "api_key_missing",
        "insufficient_query_data",
    ],
    "retry_policy": {
        "max_retries": 2,
        "backoff_s": 2,
        "retryable_on": ["transport_error", "timeout"],
    },
}
