"""Technique catalog entry: phone_osint.

Maps to the ``run_phone_osint`` MCP tool — phone number OSINT lookup.
Used by leads_enrich_gather to find or validate phone contact info for
listing agents and property owners during real-estate leads generation.
"""
from __future__ import annotations

TECHNIQUE = {
    "id": "phone_osint",
    "tool_name": "run_phone_osint",
    "input_schema": {
        "type": "object",
        "required": ["phone"],
        "properties": {
            "phone": {
                "type": "string",
                "description": "Phone number to look up (e.g. '+13125550100')",
            },
            "country": {
                "type": "string",
                "description": "Optional ISO-2 country code to disambiguate (e.g. 'US')",
            },
        },
        "additionalProperties": False,
    },
    "output_schema": {
        "type": "object",
        "required": ["result"],
        "properties": {
            "result": {
                "type": "object",
                "properties": {
                    "phone": {"type": ["string", "null"]},
                    "carrier": {"type": ["string", "null"]},
                    "line_type": {"type": ["string", "null"]},
                    "country_code": {"type": ["string", "null"]},
                    "owner_name": {"type": ["string", "null"]},
                    "owner_address": {"type": ["string", "null"]},
                    "is_valid": {"type": ["boolean", "null"]},
                    "is_active": {"type": ["boolean", "null"]},
                },
            },
        },
    },
    "cost_class": "moderate",
    "cost_per_call_ru": 2,
    "failure_modes": [
        "no_results",
        "rate_limited",
        "invalid_phone",
        "api_key_missing",
    ],
    "retry_policy": {
        "max_retries": 2,
        "backoff_s": 2,
        "retryable_on": ["transport_error", "timeout"],
    },
}
