"""Technique catalog entry: image_search.

TOOL NAME FLAG: ``run_image_search`` is referenced in ``app/is_prompt.py``
(line 156) as an expected MCP tool name, but as of 2026-05-15 no function
with that exact name exists in ``mcp_server/server.py`` or the node registry.

The nearest equivalents are:
- ``run_face_search`` — reverse facial recognition (exists as a node but is
  NOT registered as an MCP tool in the server)
- ``run_web_search_fetch`` — web search with optional full-page content fetch
  (registered, but not image-specific)

This catalog entry binds to ``run_image_search`` — the tool name the prompt
layer already references — so that when the tool is eventually implemented it
slots in without catalog edits.  The specialist will return a ``tool_error``
until the tool is registered.  This is the correct behavior per §7.3 of the
design doc ("no opinions").

If you need image search now, use ``web_search`` with a query like
``"[subject] image site:getty.com"`` or route through ``run_web_search_fetch``.
"""
from __future__ import annotations

TECHNIQUE = {
    "id": "image_search",
    "tool_name": "run_image_search",  # FLAG: not yet registered in mcp_server/server.py
    "input_schema": {
        "type": "object",
        "required": ["query"],
        "properties": {
            "query": {"type": "string", "description": "Image search query"},
            "max_results": {
                "type": "integer",
                "default": 10,
                "minimum": 1,
                "maximum": 50,
                "description": "Maximum number of image results to return",
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
                    "required": ["title", "image_url", "source_url"],
                    "properties": {
                        "title": {"type": "string"},
                        "image_url": {"type": "string"},
                        "source_url": {"type": "string"},
                        "alt": {"type": "string"},
                    },
                },
            }
        },
    },
    "cost_class": "moderate",
    "failure_modes": [
        "tool_not_registered",
        "no_results",
        "rate_limited",
    ],
    "retry_policy": {
        "max_retries": 2,
        "backoff_s": 1,
        "retryable_on": ["transport_error", "timeout"],
    },
}
