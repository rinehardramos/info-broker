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
    {
        "name": "name_origin_analysis",
        "description": "Infer nationality and diaspora probability from a person's name before committing to a locale",
        "tactic": "geo_scope",
        "tool_sequence": ["name_origin_lookup"],
        "when_to_use": "At the START of any person investigation — run before any locale-specific tool calls",
        "category": "person",
    },
    {
        "name": "migration_corridor_research",
        "description": "Identify top destination countries when initial locale search is low-yield",
        "tactic": "geo_scope",
        "tool_sequence": ["migration_corridor_lookup", "multi_search"],
        "when_to_use": "When initial locale yields < 0.5 confidence — expand to migration corridors",
        "category": "person",
    },
    {
        "name": "geographic_widening",
        "description": "Systematic locale expansion: name-origin → corridors → parallel sweep → anchor-pivot",
        "tactic": "geo_scope",
        "tool_sequence": ["name_origin_lookup", "migration_corridor_lookup", "multi_search", "opencorporates", "web_crawl"],
        "when_to_use": "When person investigation yields < 0.5 confidence after 3+ locale-specific tool calls",
        "category": "person",
    },
    {
        "name": "diaspora_record_search",
        "description": "Diaspora-specific public records: H-1B disclosure, UK Gazette naturalization, ICIJ offshore leaks, alumni cross-border",
        "tactic": "geo_scope",
        "tool_sequence": ["multi_search", "opencorporates", "web_crawl"],
        "when_to_use": "When origin is IN/PH/CN/PK/VN/NG and subject not found in origin-country sources",
        "category": "person",
    },
    {
        "name": "cross_border_footprint",
        "description": "Digital shadow triangulation: phone prefix, messaging app, LinkedIn location mismatch, posting timezone",
        "tactic": "geo_scope",
        "tool_sequence": ["phone_osint", "messaging_check", "username_enumerator", "multi_search"],
        "when_to_use": "When phone or messaging handle available — check for country-of-use vs country-of-registration mismatch",
        "category": "person",
    },
    {
        "name": "financial_trail",
        "description": "Follow-the-money: identify monetary anchor, walk upstream to source and downstream to UBO, enumerate intermediaries",
        "tactic": "financial_intel",
        "tool_sequence": ["sec_edgar", "opencorporates", "web_crawl", "multi_search"],
        "when_to_use": "Whenever money, contract, asset, or ownership appears in the query — run before biographical work",
        "category": "general",
    },
    {
        "name": "beneficial_ownership_walk",
        "description": "Company → directors → shareholders → parent → UBO; check OpenSanctions at each node",
        "tactic": "financial_intel",
        "tool_sequence": ["opencorporates", "sec_edgar", "web_crawl", "pep_sanctions_screen"],
        "when_to_use": "For any company investigation or due diligence — trace ownership to ultimate beneficial owner",
        "category": "company",
    },
    {
        "name": "network_mapping",
        "description": "Map entity relationship graph before deep-profiling individuals; identify structural roles (hub, broker, isolate)",
        "tactic": "network_intel",
        "tool_sequence": ["opencorporates", "linkedin_profile", "apollo_zoominfo", "multi_search"],
        "when_to_use": "Multi-actor situations, conspiracy/coordination questions, corporate structure questions",
        "category": "general",
    },
    {
        "name": "hypothesis_testing_ach",
        "description": "ACH: enumerate ≥3 hypotheses including deception; collect diagnostic evidence that distinguishes between them; reject most-disconfirmed",
        "tactic": "analysis",
        "tool_sequence": ["multi_search", "web_search_fetch", "document_search"],
        "when_to_use": "Any 'is X true?' or verification query — prevents confirmation bias",
        "category": "general",
    },
    {
        "name": "opsec_failure_hunting",
        "description": "Red cell: target early-career artifacts, family footprints, archive snapshots, infrastructure not hardened alongside human surface",
        "tactic": "adversarial",
        "tool_sequence": ["wayback_machine", "web_crawl", "shodan_search", "whois_lookup", "face_search"],
        "when_to_use": "OPSEC-aware subjects who have sanitized their current surface — look for historical artifacts",
        "category": "person",
    },
    {
        "name": "job_posting_intelligence",
        "description": "Job postings reveal strategy 6-12 months early: R&D bets, tech stack migrations, market entry via role titles and department clustering",
        "tactic": "competitive_intel",
        "tool_sequence": ["multi_search", "glassdoor_reviews", "web_crawl"],
        "when_to_use": "Company/competitor research — search LinkedIn Jobs, Greenhouse, Lever for role patterns",
        "category": "company",
    },
    {
        "name": "coordinated_behavior_detection",
        "description": "Detect coordinated inauthentic behavior: account creation clustering, posting lockstep, shared infrastructure, cross-platform identity correlation",
        "tactic": "platform_intel",
        "tool_sequence": ["username_enumerator", "reverse_lookup", "face_search", "multi_search"],
        "when_to_use": "Influence operations, sock puppet networks, astroturfing investigations",
        "category": "general",
    },
]


def format_techniques_for_prompt() -> str:
    """Format technique catalog as compact prompt text for the IS brain."""
    label_map = {
        "email_discovery": "Email Discovery (name→email)",
        "social_media_mapping": "Social Mapping (name→social)",
        "professional_profiling": "Professional (name→work)",
        "breach_analysis": "Breach Analysis (email→breach)",
        "phone_reconnaissance": "Phone Recon (phone→info)",
        "regulatory_verification": "Regulatory (company→records)",
        "negative_screening": "Neg Screening (name→risk)",
        "visual_intelligence": "Visual Intel (photo→matches)",
        "web_deep_search": "Web Deep (query→findings)",
        "domain_investigation": "Domain (domain→info)",
        "crypto_wallet_analysis": "Crypto (wallet→txns)",
    }
    sentinel = {"negative_screening", "crypto_wallet_analysis"}

    lines = ["## INVESTIGATION TECHNIQUES (proven tool sequences)", "Use these proven tool sequences when executing a tactic:"]
    for t in TECHNIQUES:
        name = t["name"]
        label = label_map.get(name)
        if label is None:
            continue
        tools_str = " → ".join(f"run_{tool}" for tool in t["tool_sequence"])
        suffix = " [SENTINEL]" if name in sentinel else ""
        lines.append(f"{label}: {tools_str}{suffix}")

    return "\n".join(lines)


# --- Celebrity / advertisement identification techniques ---
TECHNIQUES.extend([
    {
        "name": "celebrity_identification",
        "description": "Identify a celebrity from physical description, appearance, or partial context",
        "tactic": "person_identification",
        "tool_sequence": ["multi_search", "web_search_fetch", "google_news"],
        "when_to_use": "When a query describes a person by physical traits (mole, hair, eye shape, skin) or role (kpop idol, actor, model) without a name — identify them FIRST before anything else",
        "category": "person",
    },
    {
        "name": "brand_ambassador_lookup",
        "description": "Find which celebrity is the brand ambassador / spokesperson for a product or company",
        "tactic": "advertisement_intel",
        "tool_sequence": ["multi_search", "google_news", "web_crawl"],
        "when_to_use": "When looking for a celebrity in a commercial/ad, or connecting a brand to its ambassador — search '[brand] ambassador [year]' AND '[brand] commercial [celebrity type]'",
        "category": "person",
    },
    {
        "name": "korean_entertainment_search",
        "description": "Search Korean entertainment news, Naver, and K-pop databases in both English and Korean",
        "tactic": "cross_language",
        "tool_sequence": ["multi_search", "google_news", "web_crawl"],
        "when_to_use": "Any query involving K-pop, Korean celebrities, Korean commercials, Korean brands — ALWAYS run in Korean (한국어) using Naver/Daum AND English",
        "category": "person",
    },
])
