from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from ddgs import DDGS

from app.search_engine.plugins.base import PluginResult

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)


class DdgPlugin:
    name = "ddg"
    description = "DuckDuckGo web search"
    requires_api_key = False

    def available(self) -> bool:
        try:
            from ddgs import DDGS  # noqa: F401
            return True
        except ImportError:
            return False

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        config: dict | None = None,
    ) -> list[PluginResult]:
        try:
            loop = asyncio.get_running_loop()
            results = await loop.run_in_executor(
                None, self._search_sync, query, max_results
            )
            return results
        except Exception as exc:
            log.warning("DdgPlugin.search failed for query %r: %s", query, exc)
            return []

    def _search_sync(self, query: str, max_results: int) -> list[PluginResult]:
        results: list[PluginResult] = []
        with DDGS() as ddgs:
            for hit in ddgs.text(query, max_results=max_results):
                url = hit.get("href") or hit.get("url")
                snippet = hit.get("body") or hit.get("snippet") or ""
                full_text = self._try_scrape(url) if url else None
                results.append(
                    PluginResult(
                        title=hit["title"],
                        url=url,
                        snippet=snippet,
                        full_text=full_text,
                        published_at=None,
                        source_name=self.name,
                    )
                )
        return results

    def _try_scrape(self, url: str) -> str | None:
        try:
            from app.lib.ddg_fallback import scrape_url
            return scrape_url(url, timeout=6) or None
        except Exception:
            return None
