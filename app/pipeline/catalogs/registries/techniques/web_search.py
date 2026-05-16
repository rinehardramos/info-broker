"""Technique catalog entry: web_search.

Maps to the ``run_web_search`` MCP tool — multi-engine web search with
consensus ranking and auto-translation.  This is the primary search tool
for every research branch.
"""
from __future__ import annotations

TECHNIQUE = {
    "id": "web_search",
    "tool_name": "run_web_search",
    "input_schema": {
        "type": "object",
        "required": ["query"],
        "properties": {
            "query": {"type": "string", "description": "Search query string"},
            "max_results": {
                "type": "integer",
                "default": 10,
                "minimum": 1,
                "maximum": 50,
                "description": "Maximum number of results to return",
            },
            "recency": {
                "type": "string",
                "description": "Optional recency filter (e.g. 'past_week', 'past_month')",
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
                    "required": ["title", "url", "snippet"],
                    "properties": {
                        "title": {"type": "string"},
                        "url": {"type": "string"},
                        "snippet": {"type": "string"},
                        "date": {"type": "string"},
                    },
                },
            }
        },
    },
    "cost_class": "moderate",
    "failure_modes": [
        "no_results",
        "rate_limited",
        "engine_unreachable",
    ],
    "retry_policy": {
        "max_retries": 2,
        "backoff_s": 1,
        "retryable_on": ["transport_error", "timeout"],
    },
}
