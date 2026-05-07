"""Central LLM model configuration — all nodes read from here.

Two tiers:
- reasoning_model: Most capable model for analysis, orchestration, synthesis.
  Default: claude-opus-4-6
- general_model: Cost-effective model for leaf tasks (scoring, summarizing, extraction).
  Default: claude-sonnet-4-6

Both are configurable via core_settings in the DB (Settings UI).
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

_DEFAULT_REASONING = "claude-opus-4-6"
_DEFAULT_GENERAL = "claude-sonnet-4-6"

# In-memory cache (refreshed on each call — DB reads are cheap)
_cache: dict[str, str] = {}


def _read_setting(key: str, default: str) -> str:
    try:
        from app.routers.v3.db import fetch_one
        row = fetch_one("SELECT value FROM core_settings WHERE key = %s", (key,))
        if row and row["value"]:
            return row["value"]
    except Exception:
        pass
    return default


def reasoning_model() -> str:
    """Most capable model — for analyzer, orchestrator, financial projections."""
    return _read_setting("llm.reasoning_model", _DEFAULT_REASONING)


def general_model() -> str:
    """Cost-effective model — for scoring, summarizing, entity extraction leaves."""
    return _read_setting("llm.general_model", _DEFAULT_GENERAL)
