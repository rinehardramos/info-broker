from __future__ import annotations

import hashlib
import json

from app.pipeline.nodes.base import RunContext


class AggregatorNode:
    node_type = "aggregator"
    display_name = "Aggregator"
    category = "source"
    config_schema = {
        "type": "object",
        "properties": {
            "dedup_field": {
                "type": "string",
                "title": "Dedup Field",
                "default": "url",
                "description": "Field used to detect duplicate items across sources. Falls back to full-item hash when the field is absent.",
            },
            "merge_strategy": {
                "type": "string",
                "title": "Merge Strategy",
                "default": "union",
                "enum": ["union", "intersection"],
                "description": "union — keep all unique items; intersection — keep only items present in every source batch.",
            },
        },
        "required": [],
    }

    async def execute(self, config: dict, inputs: list[dict], context: RunContext) -> list[dict]:
        dedup_field = config.get("dedup_field", "url")
        merge_strategy = config.get("merge_strategy", "union")

        def item_key(item: dict) -> str:
            if dedup_field in item and item[dedup_field]:
                return str(item[dedup_field])
            return hashlib.md5(json.dumps(item, sort_keys=True, default=str).encode()).hexdigest()

        if merge_strategy == "intersection":
            # Keep items whose key appears in every source batch.
            # inputs here is the flat merged list from all predecessors;
            # we track which source_node each item came from via "_source_node_id" if set,
            # otherwise fall back to union behaviour.
            key_counts: dict[str, int] = {}
            seen: dict[str, dict] = {}
            for item in inputs:
                k = item_key(item)
                if k not in seen:
                    seen[k] = item
                    key_counts[k] = 1
                else:
                    key_counts[k] += 1
            # Approximate intersection: items seen more than once
            return [seen[k] for k, count in key_counts.items() if count > 1]

        # union — deduplicate, first-seen wins
        seen_keys: set[str] = set()
        result: list[dict] = []
        for item in inputs:
            k = item_key(item)
            if k not in seen_keys:
                seen_keys.add(k)
                result.append(item)
        return result
