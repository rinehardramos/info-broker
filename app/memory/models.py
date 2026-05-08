"""MemoryResult data model for multi-signal retrieval fusion."""

from dataclasses import dataclass, field


@dataclass
class MemoryResult:
    ref: str
    title: str
    content: str
    source: str           # "semantic" | "bm25" | "entity" | "temporal" | "feedback"
    score: float
    run_id: str | None = None
    entity_refs: list[str] = field(default_factory=list)
    observed_at: str | None = None
    user_score: int = 0   # -1/0/+1
    signals: dict[str, float] = field(default_factory=dict)
    source_tool: str = ""  # original source tool, e.g. "file_upload"
