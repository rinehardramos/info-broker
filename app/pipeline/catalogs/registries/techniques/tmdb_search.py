"""Technique catalog entry: tmdb_search.

Maps to the ``run_tmdb_search`` MCP tool — The Movie Database search for
movies, TV series, and people.  Referenced in
``app/pipeline/strategies/media_identification.py`` as ``run_tmdb_search``.

The node type is ``tmdb_search`` (see ``app/pipeline/nodes/tmdb_search.py``
line 99); MCP tool name follows the ``run_{node_type}`` convention used
throughout ``app/is_prompt.py``.
"""
from __future__ import annotations

TECHNIQUE = {
    "id": "tmdb_search",
    "tool_name": "run_tmdb_search",
    "input_schema": {
        "type": "object",
        "required": ["query"],
        "properties": {
            "query": {
                "type": "string",
                "description": "Title, person name, or keyword to search TMDB",
            },
            "year": {
                "type": "integer",
                "description": "Optional release/air year filter",
            },
            "content_type": {
                "type": "string",
                "enum": ["movie", "tv"],
                "description": "Restrict results to movies or TV series",
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
                    "required": ["tmdb_id", "title", "year", "type", "overview"],
                    "properties": {
                        "tmdb_id": {"type": "integer"},
                        "title": {"type": "string"},
                        "year": {"type": ["integer", "null"]},
                        "type": {
                            "type": "string",
                            "enum": ["movie", "tv", "person"],
                        },
                        "overview": {"type": "string"},
                    },
                },
            }
        },
    },
    "cost_class": "cheap",
    "failure_modes": [
        "no_results",
        "api_key_missing",
        "api_unauthorized",
        "rate_limited",
    ],
    "retry_policy": {
        "max_retries": 2,
        "backoff_s": 1,
        "retryable_on": ["transport_error", "timeout"],
    },
}
