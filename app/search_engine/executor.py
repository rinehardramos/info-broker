from __future__ import annotations

from app.search_engine.plugins.base import PluginResult


def _deduplicate_results(results: list[PluginResult]) -> list[PluginResult]:
    """Return results with duplicate URLs removed (first occurrence wins; None URLs are kept)."""
    seen_urls: set[str] = set()
    deduped: list[PluginResult] = []
    for r in results:
        if r.url is None:
            deduped.append(r)
        elif r.url not in seen_urls:
            seen_urls.add(r.url)
            deduped.append(r)
    return deduped
