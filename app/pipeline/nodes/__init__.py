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
        from app.pipeline.nodes.facebook_pages import FacebookPagesNode
        from app.pipeline.nodes.twitter_search import TwitterSearchNode
        from app.pipeline.nodes.opencorporates import OpenCorporatesNode
        from app.pipeline.nodes.instagram_profile import InstagramProfileNode
        from app.pipeline.nodes.hunter_io import HunterIoNode
        from app.pipeline.nodes.whois_lookup import WhoisLookupNode
        from app.pipeline.nodes.google_news import GoogleNewsNode
        from app.pipeline.nodes.shodan_search import ShodanSearchNode
        from app.pipeline.nodes.clutch_buyer import ClutchBuyerNode
        from app.pipeline.nodes.headless_crawler import HeadlessCrawlerNode
        from app.pipeline.nodes.ph_bir import PhBirNode
        from app.pipeline.nodes.analyzer import AnalyzerNode
        from app.pipeline.nodes.stripe_marketplace import StripeMarketplaceNode
        from app.pipeline.nodes.financial_projections import FinancialProjectionsNode
        from app.pipeline.nodes.wayback_machine import WaybackMachineNode
        from app.pipeline.nodes.ftc_foia import FtcFoiaNode
        from app.pipeline.nodes.ibpap import IbpapNode
        from app.pipeline.nodes.polish_krs import PolishKrsNode
        from app.pipeline.nodes.sec_edgar import SecEdgarNode
        from app.pipeline.nodes.glassdoor_reviews import GlassdoorReviewsNode
        from app.pipeline.nodes.maven_gumroad import MavenGumroadNode
        from app.pipeline.nodes.smtp_verifier import SmtpVerifierNode
        from app.pipeline.nodes.hibp_lookup import HibpLookupNode
        from app.pipeline.nodes.reverse_lookup import ReverseLookupNode
        from app.pipeline.nodes.email_enumerator import EmailEnumeratorNode
        from app.pipeline.nodes.username_enumerator import UsernameEnumeratorNode
        from app.pipeline.nodes.phone_osint import PhoneOsintNode
        from app.pipeline.nodes.messaging_check import MessagingCheckNode
        from app.pipeline.nodes.pep_sanctions_screen import PepSanctionsScreenNode
        from app.pipeline.nodes.adverse_media import AdverseMediaNode
        from app.pipeline.nodes.exif_extractor import ExifExtractorNode
        from app.pipeline.nodes.document_search import DocumentSearchNode
        from app.pipeline.nodes.face_search import FaceSearchNode
        from app.pipeline.nodes.crypto_tracer import CryptoTracerNode
        from app.pipeline.nodes.export_pdf import ExportPdfNode
        from app.pipeline.nodes.export_csv import ExportCsvNode
        from app.pipeline.nodes.export_excel import ExportExcelNode
        from app.pipeline.nodes.multi_search import MultiSearchNode
        from app.pipeline.nodes.serper_search import SerperSearchNode
        from app.pipeline.nodes.github_search import GithubSearchNode
        from app.pipeline.nodes.openalex_search import OpenAlexSearchNode
        from app.pipeline.nodes.semantic_scholar import SemanticScholarNode

        for node in [
            AgentInputNode(), DdgSearchNode(), QdrantSearchNode(), RssMonitorNode(),
            ApifyActorNode(), AiScoringNode(), AiProviderNode(), ManualScoringNode(),
            AggregatorNode(), ObsidianVaultNode(), LocalFilesNode(), WebCrawlNode(),
            IntelligentSearchNode(), SummarizerNode(),
            ClutchGoodfirmsNode(), LinkedInProfileNode(), ApifyMcpNode(), WebSearchFetchNode(),
            WikipediaApiNode(), ApolloZoominfoNode(), PhSecDtiNode(), LinkedinNavigatorNode(),
            FacebookPagesNode(), TwitterSearchNode(), OpenCorporatesNode(),
            InstagramProfileNode(), HunterIoNode(), WhoisLookupNode(),
            GoogleNewsNode(), ShodanSearchNode(),
            ClutchBuyerNode(), HeadlessCrawlerNode(), PhBirNode(),
            AnalyzerNode(),
            StripeMarketplaceNode(), FinancialProjectionsNode(),
            WaybackMachineNode(), FtcFoiaNode(), IbpapNode(), PolishKrsNode(),
            SecEdgarNode(), GlassdoorReviewsNode(), MavenGumroadNode(),
            ExportPdfNode(), ExportCsvNode(), ExportExcelNode(),
            SmtpVerifierNode(), HibpLookupNode(), ReverseLookupNode(),
            EmailEnumeratorNode(), UsernameEnumeratorNode(), PhoneOsintNode(),
            MessagingCheckNode(), PepSanctionsScreenNode(), AdverseMediaNode(),
            ExifExtractorNode(), DocumentSearchNode(), FaceSearchNode(),
            CryptoTracerNode(),
            MultiSearchNode(),
            SerperSearchNode(), GithubSearchNode(),
            OpenAlexSearchNode(), SemanticScholarNode(),
        ]:
            cls.register(node)
