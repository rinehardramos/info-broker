"""Technique catalog entry: opencorporates_owner.

Maps to the ``run_opencorporates`` MCP tool — searches OpenCorporates global
business registry for company registration data and officers. Used by
leads_enrich_gather to research owner LLCs and property-holding entities
during real-estate leads generation.
"""
from __future__ import annotations

TECHNIQUE = {
    "id": "opencorporates_owner",
    "tool_name": "run_opencorporates",
    "input_schema": {
        "type": "object",
        "required": ["company_name"],
        "properties": {
            "company_name": {
                "type": "string",
                "description": "Company or LLC name to search (e.g. 'Main Street Holdings LLC')",
            },
            "jurisdiction": {
                "type": "string",
                "description": "Optional jurisdiction filter (e.g. 'us_il' for Illinois)",
            },
        },
        "additionalProperties": False,
    },
    "output_schema": {
        "type": "object",
        "required": ["companies"],
        "properties": {
            "companies": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "company_number": {"type": ["string", "null"]},
                        "jurisdiction_code": {"type": ["string", "null"]},
                        "incorporation_date": {"type": ["string", "null"]},
                        "company_type": {"type": ["string", "null"]},
                        "current_status": {"type": ["string", "null"]},
                        "registered_address": {"type": ["string", "null"]},
                        "officers": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "role": {"type": ["string", "null"]},
                                    "start_date": {"type": ["string", "null"]},
                                },
                            },
                        },
                        "source_url": {"type": ["string", "null"]},
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
        "company_not_found",
    ],
    "retry_policy": {
        "max_retries": 2,
        "backoff_s": 2,
        "retryable_on": ["transport_error", "timeout"],
    },
}
