from __future__ import annotations

from app.pipeline.nodes.base import RunContext


class DdgSearchNode:
    node_type = "ddg_search"
    display_name = "DDG Search"
    category = "enrich"
    config_schema = {
        "type": "object",
        "properties": {
            "max_results": {"type": "integer", "title": "Max Results", "default": 10, "minimum": 1, "maximum": 100},
            "search_type": {
                "type": "string",
                "title": "Search Type",
                "enum": ["web", "images", "videos", "news"],
                "default": "web",
                "description": "Type of search: web (default), images, videos, or news",
            },
        },
        "required": [],
    }

    async def execute(self, config: dict, inputs: list[dict], context: RunContext) -> list[dict]:
        from app.search_engine.plugins.ddg import DdgPlugin

        max_results = int(config.get("max_results", 10))
        search_type = config.get("search_type", "web")
        plugin = DdgPlugin()

        all_results: list[dict] = []
        for item in inputs:
            query = item.get("query") or item.get("message") or item.get("title") or ""
            if not query:
                continue

            if search_type == "images":
                raw = await plugin.search_images(query, max_results=max_results)
                all_results.extend(
                    {
                        "title": r.get("title", ""),
                        "image": r.get("image", ""),
                        "thumbnail": r.get("thumbnail", ""),
                        "url": r.get("url", ""),
                        "source": "ddg",
                        "search_type": "images",
                        "query": query,
                    }
                    for r in raw
                )
            elif search_type == "videos":
                raw = await plugin.search_videos(query, max_results=max_results)
                all_results.extend(
                    {
                        "title": r.get("title", ""),
                        "content": r.get("content", ""),
                        "publisher": r.get("publisher", ""),
                        "url": r.get("url", ""),
                        "source": "ddg",
                        "search_type": "videos",
                        "query": query,
                    }
                    for r in raw
                )
            elif search_type == "news":
                raw = await plugin.search_news(query, max_results=max_results)
                all_results.extend(
                    {
                        "title": r.get("title", ""),
                        "snippet": r.get("body", ""),
                        "date": r.get("date", ""),
                        "url": r.get("url", ""),
                        "news_source": r.get("source", ""),
                        "source": "ddg",
                        "search_type": "news",
                        "query": query,
                    }
                    for r in raw
                )
            else:
                # web (default)
                results = await plugin.search(query, max_results=max_results)
                all_results.extend(
                    {
                        "title": r.title,
                        "url": r.url,
                        "snippet": r.snippet or "",
                        "source": "ddg",
                        "query": query,
                    }
                    for r in results
                )

        return all_results
