"""Technique catalog entry: prior_research.

Maps to the ``get_past_research`` MCP tool (``mcp_server/server.py`` line 1087).
Performs semantic similarity search over stored research trails in Qdrant.

The tool is used in ``app/is_prompt.py`` as ``get_past_research(query)`` and
returns a JSON-serialised list of prior run summaries.
"""
from __future__ import annotations

TECHNIQUE = {
    "id": "prior_research",
    "tool_name": "get_past_research",
    "input_schema": {
        "type": "object",
        "required": ["query"],
        "properties": {
            "query": {
                "type": "string",
                "description": "Semantic query to search prior research trails",
            },
            "k": {
                "type": "integer",
                "default": 5,
                "minimum": 1,
                "maximum": 20,
                "description": "Number of top results to retrieve (maps to 'limit' param)",
            },
            "min_grade": {
                "type": "string",
                "description": "Minimum research grade filter (e.g. 'B', 'A')",
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
                    "required": ["run_id", "summary", "findings", "grade", "similarity"],
                    "properties": {
                        "run_id": {"type": "string"},
                        "summary": {"type": "string"},
                        "findings": {
                            "type": "array",
                            "items": {"type": "object"},
                        },
                        "grade": {"type": "string"},
                        "similarity": {"type": "number"},
                    },
                },
            }
        },
    },
    "cost_class": "cheap",
    "failure_modes": [
        "no_prior_research",
        "qdrant_unavailable",
        "db_connection_error",
    ],
    "retry_policy": {
        "max_retries": 2,
        "backoff_s": 1,
        "retryable_on": ["transport_error", "timeout"],
    },
}
