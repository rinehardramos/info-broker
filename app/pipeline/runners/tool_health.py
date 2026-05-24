"""tool_health.py — Sync health lookup for techniques via the node health cache.

Reads the module-level ``_health_cache`` populated by
``app.routers.v3.pipelines.get_nodes_health``.  Never calls async
health_check() directly — best-effort read of whatever is already cached.
Unknown / cache-miss → treated as healthy (don't over-suppress).

Usage::

    from app.pipeline.runners.tool_health import is_unhealthy, missing_key

    if is_unhealthy("hunter_email_search"):
        key = missing_key("hunter_email_search")  # "HUNTER_API_KEY"
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Technique → node_type resolution
# ---------------------------------------------------------------------------
# Primary rule: strip "run_" prefix from tool_name (run_hunter_io → hunter_io).
# Explicit overrides for tool_names that don't follow the convention.

_TOOL_NAME_TO_NODE: dict[str, str | None] = {
    # Non-run_ prefixed special cases
    "apify_actor_run": "apify_actor",
    "get_past_research": None,          # internal; no node, always healthy
    # run_* convention (listed explicitly so grepping is easy)
    "run_web_search":      "web_search",
    "run_hunter_io":       "hunter_io",
    "run_apollo_search":   "apollo_search",
    "run_opencorporates":  "opencorporates",
    "run_whois_lookup":    "whois_lookup",
    "run_phone_osint":     "phone_osint",
    "run_pipl_search":     "pipl_search",
    "run_google_news":     "google_news",
    "run_tmdb_search":     "tmdb_search",
    "run_image_search":    "image_search",
}


def _tool_name_to_node(tool_name: str) -> str | None:
    """Resolve a technique's tool_name to the pipeline node_type that backs it.

    Returns None when the tool has no backing node (treat as healthy).
    Falls back to stripping the "run_" prefix for unknown tool_names.
    """
    if tool_name in _TOOL_NAME_TO_NODE:
        return _TOOL_NAME_TO_NODE[tool_name]
    # Generic fallback: strip run_ prefix
    if tool_name.startswith("run_"):
        return tool_name[4:]
    # Unknown pattern — can't map; treat as healthy
    return None


# ---------------------------------------------------------------------------
# Health lookup
# ---------------------------------------------------------------------------

def technique_health(technique_id: str) -> dict | None:
    """Return the cached HealthStatus for the node backing *technique_id*.

    Reads the technique from the catalog, resolves the node_type, then
    reads ``_health_cache`` from the pipelines router.

    Returns:
        A HealthStatus-shaped dict if the node has a fresh cached status,
        else None.  None means unknown — callers MUST treat None as healthy
        (best-effort; don't over-suppress).
    """
    from pathlib import Path

    from app.pipeline.catalogs.loader import load_catalog

    # Load the technique catalog to get the tool_name
    technique_dir = (
        Path(__file__).parent.parent / "catalogs" / "registries" / "techniques"
    )
    try:
        techniques = load_catalog("technique", technique_dir)
    except Exception as exc:
        log.debug("tool_health: could not load technique catalog: %s", exc)
        return None

    technique = techniques.get(technique_id)
    if technique is None:
        log.debug("tool_health: technique %r not in catalog", technique_id)
        return None

    node_type = _tool_name_to_node(technique.tool_name)
    if node_type is None:
        # No node backing this tool — treat as healthy
        return None

    # Read the shared health cache from the pipelines router (no async needed)
    try:
        import time

        from app.routers.v3.pipelines import _HEALTH_CACHE_TTL, _health_cache

        entry = _health_cache.get(node_type)
        if entry is None:
            return None
        cached_time, status = entry
        if time.time() - cached_time > _HEALTH_CACHE_TTL:
            # Stale — treat as unknown (healthy)
            return None
        return status
    except Exception as exc:
        log.debug("tool_health: error reading _health_cache: %s", exc)
        return None


def is_unhealthy(technique_id: str) -> bool:
    """Return True only if the technique's node is KNOWN to be unhealthy.

    Unknown / cache-miss → False (don't over-suppress).
    """
    status = technique_health(technique_id)
    if status is None:
        return False
    return not status.get("healthy", True)


def missing_key(technique_id: str) -> str | None:
    """Return the requires_key string if the node is unhealthy due to a missing key.

    Returns None if the node is healthy, unknown, or unhealthy for another reason.
    """
    status = technique_health(technique_id)
    if status is None:
        return None
    if status.get("healthy", True):
        return None
    return status.get("requires_key") or None
