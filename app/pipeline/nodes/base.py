from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol


@dataclass
class RunContext:
    user_id: str
    run_id: str
    node_id: str
    push_event: Callable = lambda *a, **kw: None


class PipelineNode(Protocol):
    node_type: str
    display_name: str
    category: str  # "source" | "enrich" | "score" | "filter"
    config_schema: dict

    async def execute(
        self,
        config: dict,
        inputs: list[dict],
        context: RunContext,
    ) -> list[dict]: ...
