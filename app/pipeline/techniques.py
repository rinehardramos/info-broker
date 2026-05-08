"""Technique catalog — structured mapping of investigation tactics to tool sequences."""

from __future__ import annotations

TECHNIQUES: list[dict] = [
    {
        "name": "email_discovery",
        "description": "Discover and verify email addresses for a person",
        "tactic": "digital_footprint",
        "tool_sequence": ["email_enumerator", "smtp_verifier", "hibp_lookup"],
        "when_to_use": "When you have a person's name and need their email address",
        "category": "person",
    },
    {
        "name": "social_media_mapping",
        "description": "Map social media presence across platforms",
        "tactic": "digital_footprint",
        "tool_sequence": ["username_enumerator", "instagram_profile", "facebook_pages", "twitter_search"],
        "when_to_use": "When you have a name or username and need to find all social accounts",
        "category": "person",
    },
    {
        "name": "professional_profiling",
        "description": "Build a professional profile with employment and contact details",
        "tactic": "professional_history",
        "tool_sequence": ["linkedin_profile", "apollo_zoominfo", "hunter_io"],
        "when_to_use": "When you need employment history, title, and professional email",
        "category": "person",
    },
    {
        "name": "breach_analysis",
        "description": "Check email exposure in data breaches and leaked databases",
        "tactic": "breach_intel",
        "tool_sequence": ["hibp_lookup", "reverse_lookup"],
        "when_to_use": "When you have an email and need to check breach exposure",
        "category": "person",
    },
    {
        "name": "phone_reconnaissance",
        "description": "Investigate a phone number for carrier, type, and messaging presence",
        "tactic": "communication_intel",
        "tool_sequence": ["phone_osint", "messaging_check", "reverse_lookup"],
        "when_to_use": "When you have a phone number and need carrier/messaging details",
        "category": "person",
    },
    {
        "name": "regulatory_verification",
        "description": "Verify corporate registration and regulatory compliance",
        "tactic": "public_records",
        "tool_sequence": ["ph_sec_dti", "ph_bir", "opencorporates", "sec_edgar"],
        "when_to_use": "When you need to verify a company's legal status and officers",
        "category": "company",
    },
    {
        "name": "negative_screening",
        "description": "Screen for PEP status, sanctions, and adverse media",
        "tactic": "risk_assessment",
        "tool_sequence": ["pep_sanctions_screen", "adverse_media"],
        "when_to_use": "When you need to assess risk — always run for due diligence",
        "category": "person",
    },
    {
        "name": "visual_intelligence",
        "description": "Analyze photos for identity matches and metadata",
        "tactic": "visual_intel",
        "tool_sequence": ["face_search", "exif_extractor"],
        "when_to_use": "When you have a photo and need to find matching profiles or extract location data",
        "category": "person",
    },
    {
        "name": "web_deep_search",
        "description": "Comprehensive web search across multiple engines with document discovery",
        "tactic": "general_research",
        "tool_sequence": ["multi_search", "web_crawl", "document_search"],
        "when_to_use": "When you need thorough web coverage — use at the start of any investigation",
        "category": "general",
    },
    {
        "name": "domain_investigation",
        "description": "Investigate a domain for ownership, infrastructure, and associated emails",
        "tactic": "digital_footprint",
        "tool_sequence": ["whois_lookup", "shodan_search", "hunter_io"],
        "when_to_use": "When you have a domain name and need ownership + technical details",
        "category": "company",
    },
    {
        "name": "crypto_wallet_analysis",
        "description": "Analyze blockchain wallet for balance and transaction history",
        "tactic": "financial_intel",
        "tool_sequence": ["crypto_tracer"],
        "when_to_use": "When you have a wallet address — always check for financial investigations [SENTINEL]",
        "category": "person",
    },
]


def format_techniques_for_prompt() -> str:
    """Format technique catalog as prompt text for the IS brain."""
    lines = ["## INVESTIGATION TECHNIQUES (proven tool sequences)", ""]
    lines.append("When executing a tactic, use these proven tool sequences:")
    lines.append("")

    for t in TECHNIQUES:
        tools_str = " -> ".join(f"run_{tool}" for tool in t["tool_sequence"])
        lines.append(f"**{t['name'].replace('_', ' ').title()}** ({t['when_to_use']})")
        lines.append(f"  {tools_str}")
        lines.append("")

    return "\n".join(lines)
