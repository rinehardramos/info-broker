"""Technique catalog entry: hunter_email_search.

Maps to the ``run_hunter_io`` MCP tool — finds email addresses for a company
domain via Hunter.io. Used by leads_enrich_gather to find listing-agent and
property-owner contact emails during real-estate leads generation.
"""
from __future__ import annotations

TECHNIQUE = {
    "id": "hunter_email_search",
    "tool_name": "run_hunter_io",
    "input_schema": {
        "type": "object",
        "properties": {
            "domain": {
                "type": "string",
                "description": "Domain to search emails for (e.g. 'remax.com')",
            },
            "company": {
                "type": "string",
                "description": "Company name to search when domain is unknown",
            },
            "max_results": {
                "type": "integer",
                "default": 10,
                "minimum": 1,
                "maximum": 100,
                "description": "Maximum number of email results to return",
            },
        },
        "additionalProperties": False,
    },
    "output_schema": {
        "type": "object",
        "required": ["emails"],
        "properties": {
            "emails": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "email": {"type": "string"},
                        "first_name": {"type": ["string", "null"]},
                        "last_name": {"type": ["string", "null"]},
                        "type": {"type": ["string", "null"]},
                        "confidence": {"type": ["integer", "number", "null"]},
                        "department": {"type": ["string", "null"]},
                        "linkedin_url": {"type": ["string", "null"]},
                        "phone_number": {"type": ["string", "null"]},
                    },
                },
            },
            "domain": {"type": ["string", "null"]},
            "company": {"type": ["string", "null"]},
        },
    },
    "cost_class": "moderate",
    "cost_per_call_ru": 3,
    "failure_modes": [
        "no_results",
        "rate_limited",
        "domain_not_found",
    ],
    "retry_policy": {
        "max_retries": 2,
        "backoff_s": 2,
        "retryable_on": ["transport_error", "timeout"],
    },
}
