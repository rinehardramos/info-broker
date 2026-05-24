"""Technique catalog entry: apollo_contact.

Maps to the ``run_apollo_search`` MCP tool — searches Apollo.io for people
or companies, returning tech stack, intent data, and contact info. Used by
leads_enrich_gather to find listing agent and property-owner phone/email
during real-estate leads generation.
"""
from __future__ import annotations

TECHNIQUE = {
    "id": "apollo_contact",
    "tool_name": "run_apollo_search",
    "input_schema": {
        "type": "object",
        "required": ["query"],
        "properties": {
            "query": {
                "type": "string",
                "description": "Name, company, or search query (e.g. 'Jane Smith RE/MAX Chicago')",
            },
            "search_type": {
                "type": "string",
                "enum": ["people", "companies"],
                "default": "people",
                "description": "Whether to search for people or companies",
            },
            "filters": {
                "type": "string",
                "default": "{}",
                "description": "JSON string of Apollo search filters",
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
                        "first_name": {"type": ["string", "null"]},
                        "last_name": {"type": ["string", "null"]},
                        "title": {"type": ["string", "null"]},
                        "email": {"type": ["string", "null"]},
                        "phone": {"type": ["string", "null"]},
                        "linkedin_url": {"type": ["string", "null"]},
                        "organization": {
                            "type": ["object", "null"],
                            "properties": {
                                "name": {"type": ["string", "null"]},
                                "website_url": {"type": ["string", "null"]},
                            },
                        },
                        "city": {"type": ["string", "null"]},
                        "state": {"type": ["string", "null"]},
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
    ],
    "retry_policy": {
        "max_retries": 2,
        "backoff_s": 2,
        "retryable_on": ["transport_error", "timeout"],
    },
}
