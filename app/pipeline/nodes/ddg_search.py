from __future__ import annotations

from app.pipeline.nodes.base import RunContext


class DdgSearchNode:
    node_type = "ddg_search"
    display_name = "DDG Search"
    category = "enrich"
    config_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "title": "Search Query"},
            "max_results": {"type": "integer", "title": "Max Results", "default": 10, "minimum": 1, "maximum": 100},
        },
        "required": ["query"],
    }

    async def execute(self, config: dict, inputs: list[dict], context: RunContext) -> list[dict]:
        from app.search_engine.plugins.ddg import DdgPlugin

        query = config.get("query", "")
        max_results = int(config.get("max_results", 10))

        plugin = DdgPlugin()
        results = await plugin.search(query, max_results=max_results)

        return [
            {
                "title": r.title,
                "url": r.url,
                "snippet": r.snippet or "",
                "source": "ddg",
            }
            for r in results
        ]
