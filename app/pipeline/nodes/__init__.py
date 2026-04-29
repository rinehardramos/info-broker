from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.pipeline.nodes.base import PipelineNode


class NodeRegistry:
    _nodes: dict[str, "PipelineNode"] = {}

    @classmethod
    def register(cls, node: "PipelineNode") -> None:
        cls._nodes[node.node_type] = node

    @classmethod
    def get(cls, node_type: str) -> "PipelineNode":
        if node_type not in cls._nodes:
            raise KeyError(f"Unknown node type: {node_type!r}")
        return cls._nodes[node_type]

    @classmethod
    def all(cls) -> list["PipelineNode"]:
        return list(cls._nodes.values())

    @classmethod
    def auto_discover(cls) -> None:
        from app.pipeline.nodes.ddg_search import DdgSearchNode
        from app.pipeline.nodes.qdrant_search import QdrantSearchNode
        from app.pipeline.nodes.rss_monitor import RssMonitorNode
        from app.pipeline.nodes.apify_actor import ApifyActorNode
        from app.pipeline.nodes.ai_scoring import AiScoringNode
        from app.pipeline.nodes.manual_scoring import ManualScoringNode

        for node in [DdgSearchNode(), QdrantSearchNode(), RssMonitorNode(), ApifyActorNode(), AiScoringNode(), ManualScoringNode()]:
            cls.register(node)
