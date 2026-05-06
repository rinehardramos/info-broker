"""Apify Actor (Generic) node — MCP bridge to run any Apify actor by ID."""

from __future__ import annotations

import asyncio
import logging

from app.pipeline.nodes.base import RunContext

log = logging.getLogger(__name__)


class ApifyMcpNode:
    node_type = "apify_mcp"
    display_name = "Apify Actor (Generic)"
    category = "enrich"

    config_schema = {
        "type": "object",
        "properties": {
            "actor_id": {
                "type": "string",
                "title": "Actor ID",
                "description": "Apify actor identifier, e.g. 'apify/web-scraper' or 'owner~actor-name'",
            },
            "input": {
                "type": "object",
                "title": "Actor Input",
                "description": "JSON object passed as run input to the actor",
                "default": {},
            },
            "max_items": {
                "type": "integer",
                "title": "Max Items",
                "default": 50,
                "minimum": 1,
                "maximum": 1000,
            },
            "timeout": {
                "type": "integer",
                "title": "Timeout (seconds)",
                "default": 120,
                "minimum": 10,
                "maximum": 3600,
            },
        },
        "required": ["actor_id"],
    }

    async def execute(self, config: dict, inputs: list[dict], context: RunContext) -> list[dict]:
        from app.pipeline.nodes.apify_actor import _resolve_api_key

        api_key = _resolve_api_key()
        actor_id = config.get("actor_id", "").strip()
        if not actor_id:
            return [{"error": "actor_id is required", "source": "apify"}]

        actor_input = config.get("input") or {}
        max_items = int(config.get("max_items", 50))
        timeout = int(config.get("timeout", 120))

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._run_sync, api_key, actor_id, actor_input, max_items, timeout
        )

    def _run_sync(
        self,
        api_key: str,
        actor_id: str,
        actor_input: dict,
        max_items: int,
        timeout: int,
    ) -> list[dict]:
        from apify_client import ApifyClient
        from app.pipeline.nodes.apify_actor import _actor_slug

        client = ApifyClient(api_key)
        slug = _actor_slug(actor_id)
        log.info(
            "ApifyMcpNode: starting actor %s max_items=%d timeout=%ds input=%s",
            slug, max_items, timeout, actor_input,
        )

        try:
            run = client.actor(slug).call(
                run_input=actor_input,
                timeout_secs=timeout,
            )
        except Exception as exc:
            log.error("ApifyMcpNode: actor %s call failed: %s", slug, exc)
            return [{"error": str(exc), "source": "apify"}]

        if not run:
            return [{"error": f"Apify actor {slug} returned no run result", "source": "apify"}]

        dataset_id = run.get("defaultDatasetId")
        if not dataset_id:
            return [{"error": f"Apify run for {slug} has no dataset", "source": "apify"}]

        items: list[dict] = []
        for item in client.dataset(dataset_id).iterate_items():
            raw = dict(item)
            raw.setdefault("source", "apify")
            items.append(raw)
            if len(items) >= max_items:
                break

        log.info("ApifyMcpNode: actor %s returned %d items", slug, len(items))
        return items
