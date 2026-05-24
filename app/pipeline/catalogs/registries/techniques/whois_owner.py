"""Technique catalog entry: whois_owner.

Maps to the ``run_whois_lookup`` MCP tool — WHOIS lookup for domain
registration info (registrant, dates, nameservers). Used by
leads_enrich_gather to surface property-owner domain registrant details
and company background during real-estate leads generation.
"""
from __future__ import annotations

TECHNIQUE = {
    "id": "whois_owner",
    "tool_name": "run_whois_lookup",
    "input_schema": {
        "type": "object",
        "required": ["domain"],
        "properties": {
            "domain": {
                "type": "string",
                "description": "Domain to look up (e.g. 'acme-realty.com')",
            },
        },
        "additionalProperties": False,
    },
    "output_schema": {
        "type": "object",
        "required": ["registrant"],
        "properties": {
            "registrant": {
                "type": "object",
                "properties": {
                    "name": {"type": ["string", "null"]},
                    "organization": {"type": ["string", "null"]},
                    "email": {"type": ["string", "null"]},
                    "phone": {"type": ["string", "null"]},
                    "address": {"type": ["string", "null"]},
                    "country": {"type": ["string", "null"]},
                },
            },
            "domain": {"type": ["string", "null"]},
            "creation_date": {"type": ["string", "null"]},
            "expiration_date": {"type": ["string", "null"]},
            "registrar": {"type": ["string", "null"]},
            "nameservers": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
    },
    "cost_class": "cheap",
    "cost_per_call_ru": 1,
    "failure_modes": [
        "no_results",
        "domain_not_found",
        "rate_limited",
    ],
    "retry_policy": {
        "max_retries": 2,
        "backoff_s": 1,
        "retryable_on": ["transport_error", "timeout"],
    },
}
