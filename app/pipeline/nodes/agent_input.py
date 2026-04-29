from __future__ import annotations

from app.pipeline.nodes.base import RunContext


class AgentInputNode:
    node_type = "agent_input"
    display_name = "Agent Input"
    category = "source"
    config_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "title": "Input Query",
            },
            "label": {
                "type": "string",
                "title": "Item Label",
                "default": "agent_query",
            },
        },
        "required": ["query"],
    }

    async def execute(self, config: dict, inputs: list[dict], context: RunContext) -> list[dict]:
        query = config.get("query", "")
        label = config.get("label", "agent_query")
        return [{"query": query, "content": query, "label": label, "source": "agent_input"}]
