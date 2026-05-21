"""Strategy catalog entry: lead.

Lead/contact extraction across N targets. Default mode: leads_generation.
"""
from __future__ import annotations

from app.pipeline.catalogs.builders.research_skeleton import build_research_strategy

STRATEGY = build_research_strategy(
    id="lead",
    default_mode="leads_generation",
    hypothesis_count="single",
    applies_to={
        "signals": ["find_leads", "prospect_list", "contact_list", "outreach"],
        "entity_types": ["person", "company"],
    },
    extract={
        "briefing": (
            "Parse the lead-generation brief. Identify the N target entities "
            "(people, companies, or role titles within companies) and the "
            "contact channels needed (email, phone, LinkedIn URL). Note any "
            "qualification criteria (industry, seniority, geography, headcount). "
            "Emit one entry per target."
        ),
    },
    gather={
        "briefing": (
            "For each target, search public sources for contact details: "
            "LinkedIn, company About pages, ZoomInfo-style aggregators, "
            "business registries, conference speaker lists. Per target, "
            "capture: full name, role, email (if discoverable), LinkedIn URL, "
            "company, and a confidence score for the match. Run lookups in "
            "parallel where possible."
        ),
        "gate_checks": [
            {"kind": "contact_info_per_target", "params": {"min": 1}},
        ],
    },
    synthesize={
        "briefing": (
            "Dedupe contacts by (name, company). Format as a flat list with "
            "the same shape per row. Mark targets with insufficient evidence "
            "as 'unverified' rather than dropping them, so the caller can "
            "decide whether to retry."
        ),
    },
)
