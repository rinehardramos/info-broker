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
        from app.pipeline.nodes.agent_input import AgentInputNode
        from app.pipeline.nodes.ddg_search import DdgSearchNode
        from app.pipeline.nodes.qdrant_search import QdrantSearchNode
        from app.pipeline.nodes.rss_monitor import RssMonitorNode
        from app.pipeline.nodes.apify_actor import ApifyActorNode
        from app.pipeline.nodes.ai_scoring import AiScoringNode
        from app.pipeline.nodes.ai_provider import AiProviderNode
        from app.pipeline.nodes.manual_scoring import ManualScoringNode
        from app.pipeline.nodes.aggregator import AggregatorNode
        from app.pipeline.nodes.obsidian_vault import ObsidianVaultNode
        from app.pipeline.nodes.local_files import LocalFilesNode
        from app.pipeline.nodes.web_crawl import WebCrawlNode
        from app.pipeline.nodes.intelligent_search import IntelligentSearchNode
        from app.pipeline.nodes.summarizer import SummarizerNode
        from app.pipeline.nodes.clutch_goodfirms import ClutchGoodfirmsNode
        from app.pipeline.nodes.linkedin_profile import LinkedInProfileNode
        from app.pipeline.nodes.apify_mcp import ApifyMcpNode
        from app.pipeline.nodes.web_search_fetch import WebSearchFetchNode
        from app.pipeline.nodes.wikipedia_api import WikipediaApiNode
        from app.pipeline.nodes.apollo_zoominfo import ApolloZoominfoNode
        from app.pipeline.nodes.ph_sec_dti import PhSecDtiNode
        from app.pipeline.nodes.linkedin_navigator import LinkedinNavigatorNode

        for node in [
            AgentInputNode(), DdgSearchNode(), QdrantSearchNode(), RssMonitorNode(),
            ApifyActorNode(), AiScoringNode(), AiProviderNode(), ManualScoringNode(),
            AggregatorNode(), ObsidianVaultNode(), LocalFilesNode(), WebCrawlNode(),
            IntelligentSearchNode(), SummarizerNode(),
            ClutchGoodfirmsNode(), LinkedInProfileNode(), ApifyMcpNode(), WebSearchFetchNode(),
            WikipediaApiNode(), ApolloZoominfoNode(), PhSecDtiNode(), LinkedinNavigatorNode(),
        ]:
            cls.register(node)
