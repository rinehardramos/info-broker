from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol, TypedDict


@dataclass
class RunContext:
    user_id: str
    run_id: str
    node_id: str
    push_event: Callable = field(default=lambda *a, **kw: None)
    org_id: str | None = None


class HealthStatus(TypedDict):
    healthy: bool
    error: str | None
    requires_key: str | None
    setup_url: str | None
    setup_instructions: str | None


class PipelineNode(Protocol):
    node_type: str
    display_name: str
    category: str  # "source" | "enrich" | "score" | "filter" | "datastore"
    config_schema: dict

    async def execute(
        self,
        config: dict,
        inputs: list[dict],
        context: RunContext,
    ) -> list[dict]: ...


class ToolCallable(Protocol):
    """Nodes that can be invoked as tools by the intelligent_search node."""

    node_type: str
    display_name: str

    def tool_schema(self) -> dict:
        """Return a Claude tool-use JSON schema for this tool."""
        ...

    async def tool_invoke(self, params: dict, context: RunContext) -> list[dict]:
        """Execute a single tool call with LLM-provided params."""
        ...
