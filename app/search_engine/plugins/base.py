from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass
class PluginResult:
    title: str
    url: str | None
    snippet: str
    full_text: str | None
    published_at: datetime | None
    source_name: str
    metadata: dict = field(default_factory=dict)


@runtime_checkable
class SearchPlugin(Protocol):
    name: str
    description: str
    requires_api_key: bool

    async def search(
        self,
        query: str,
        *,
        max_results: int = 5,
        config: dict | None = None,
    ) -> list[PluginResult]: ...

    def available(self) -> bool: ...
