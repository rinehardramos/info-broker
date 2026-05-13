"""DDG Search node — DEPRECATED. Delegates to MultiSearchNode (ddg engine only).

Kept for backward compatibility with existing pipelines that reference node_type='ddg_search'.
New pipelines should use node_type='multi_search' instead.
"""
from __future__ import annotations

import logging

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)


class DdgSearchNode:
    node_type = "ddg_search"
    display_name = "DDG Search (deprecated — use Multi-Engine Search)"
    category = "source"
    deprecated = True
    config_schema = {
        "type": "object",
        "properties": {
            "max_results": {"type": "integer", "title": "Max Results", "default": 10, "minimum": 1, "maximum": 100},
            "search_type": {
                "type": "string",
                "title": "Search Type",
                "enum": ["web", "images", "videos", "news"],
                "default": "web",
                "description": "Deprecated — web type delegates to multi_search. images/videos/news still use DDG directly.",
            },
        },
        "required": [],
    }

    async def execute(self, config: dict, inputs: list[dict], context: RunContext) -> list[dict]:
        search_type = config.get("search_type", "web")

        # Web searches delegate to MultiSearchNode for consensus ranking
        if search_type == "web":
            log.info("ddg_search: delegating to multi_search (ddg engine)")
            from app.pipeline.nodes.multi_search import MultiSearchNode
            multi_config = {
                "engines": ["ddg"],
                "max_results": int(config.get("max_results", 10)),
            }
            # Pass query through from inputs
            if inputs and (inputs[0].get("query") or inputs[0].get("message")):
                multi_config["query"] = inputs[0].get("query") or inputs[0].get("message") or ""
            node = MultiSearchNode()
            return await node.execute(multi_config, inputs, context)

        # images/videos/news — still use DDG directly
        from app.search_engine.plugins.ddg import DdgPlugin
        max_results = int(config.get("max_results", 10))
        plugin = DdgPlugin()
        all_results: list[dict] = []

        for item in inputs:
            query = item.get("query") or item.get("message") or item.get("title") or ""
            if not query:
                continue
            if search_type == "images":
                raw = await plugin.search_images(query, max_results=max_results)
                all_results.extend({"title": r.get("title", ""), "image": r.get("image", ""), "url": r.get("url", ""), "source": "ddg", "search_type": "images"} for r in raw)
            elif search_type == "videos":
                raw = await plugin.search_videos(query, max_results=max_results)
                all_results.extend({"title": r.get("title", ""), "content": r.get("content", ""), "url": r.get("url", ""), "source": "ddg", "search_type": "videos"} for r in raw)
            elif search_type == "news":
                raw = await plugin.search_news(query, max_results=max_results)
                all_results.extend({"title": r.get("title", ""), "snippet": r.get("body", ""), "date": r.get("date", ""), "url": r.get("url", ""), "source": "ddg", "search_type": "news"} for r in raw)

        return all_results
