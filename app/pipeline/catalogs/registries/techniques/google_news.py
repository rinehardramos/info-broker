"""Technique catalog entry: google_news.

Maps to the ``run_google_news`` MCP tool (``mcp_server/server.py`` line 460),
backed by ``app/pipeline/nodes/google_news.py`` (node_type = "google_news").
"""
from __future__ import annotations

TECHNIQUE = {
    "id": "google_news",
    "tool_name": "run_google_news",
    "input_schema": {
        "type": "object",
        "required": ["query"],
        "properties": {
            "query": {
                "type": "string",
                "description": "News search query string",
            },
            "days_back": {
                "type": "integer",
                "default": 30,
                "minimum": 1,
                "description": "Restrict results to articles published within this many days",
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
                    "required": ["title", "url", "source", "published_at"],
                    "properties": {
                        "title": {"type": "string"},
                        "url": {"type": "string"},
                        "source": {"type": "string"},
                        "published_at": {"type": "string"},
                    },
                },
            }
        },
    },
    "cost_class": "moderate",
    "failure_modes": [
        "no_results",
        "rate_limited",
        "service_unavailable",
    ],
    "retry_policy": {
        "max_retries": 2,
        "backoff_s": 1,
        "retryable_on": ["transport_error", "timeout"],
    },
}
