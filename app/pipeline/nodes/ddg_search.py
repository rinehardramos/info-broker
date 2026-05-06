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
        },
        "required": [],
    }

    async def execute(self, config: dict, inputs: list[dict], context: RunContext) -> list[dict]:
        from app.search_engine.plugins.ddg import DdgPlugin

        max_results = int(config.get("max_results", 10))
        plugin = DdgPlugin()

        all_results: list[dict] = []
        for item in inputs:
            # Derive query from upstream item fields
            query = item.get("query") or item.get("message") or item.get("title") or ""
            if not query:
                continue

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
