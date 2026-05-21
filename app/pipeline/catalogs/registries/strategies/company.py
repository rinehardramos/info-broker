"""Strategy catalog entry: company.

Company profile / corporate investigation. Default mode: investigation
(competitive intel queries) but also reachable via market_analysis.
"""
from __future__ import annotations

from app.pipeline.catalogs.builders.research_skeleton import build_research_strategy

STRATEGY = build_research_strategy(
    id="company",
    default_mode="investigation",
    hypothesis_count="single",
    applies_to={
        "signals": ["company_profile", "competitor", "corporate_profile", "company_lookup"],
        "entity_types": ["company"],
    },
    extract={
        "briefing": (
            "Resolve the company's canonical identity from the query: legal "
            "name, registry/EIN id if findable, primary domain, headquarters "
            "country. Identify which signal classes the caller wants — "
            "filings, news, hiring, tech stack, leadership, products. Emit a "
            "target-company spec and a list of signal classes to gather."
        ),
    },
    gather={
        "briefing": (
            "Query corporate registries (OpenCorporates, SEC EDGAR for US, "
            "Companies House for UK, equivalent national registries), news "
            "feeds for recent coverage, hiring sites (LinkedIn jobs, "
            "Indeed) for headcount/role mix, and BuiltWith / Wappalyzer for "
            "tech stack. Capture per-signal facts with a date stamp."
        ),
        "gate_checks": [
            {"kind": "min_signal_classes_covered", "params": {"min": 2}},
        ],
    },
    synthesize={
        "briefing": (
            "Compose a structured company profile: identity (name, registry, "
            "HQ, status), activity (revenue band, headcount, recent news), "
            "and the gathered signals grouped by class. Cite a source URL "
            "per claim."
        ),
    },
)
