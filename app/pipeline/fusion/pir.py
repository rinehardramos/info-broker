"""PIR (Priority Intelligence Requirements) decomposition and coverage tracking."""

from __future__ import annotations
import re as _re


def _keyword_matches(keyword: str, content: str) -> bool:
    """Word-boundary aware keyword match. Handles @ specially.

    Uses word boundaries AND negative lookbehind/lookahead for hyphens so that
    compound words like 'anti-fraud' do not match the keyword 'fraud'.
    """
    if keyword == "@":
        return bool(_re.search(r'@\S+', content))
    pattern = rf'(?<!-)\b{_re.escape(keyword)}\b(?!-)'
    return bool(_re.search(pattern, content, _re.IGNORECASE))

# Pre-defined PIR templates per entity type
PERSON_PIRS = [
    {
        "name": "Identity Verification",
        "description": "Confirm the person's identity and basic biographical data",
        "sirs": [
            {"name": "Full legal name and aliases", "eeis": [
                {"name": "full_name", "keywords": ["name", "full name", "legal name"]},
                {"name": "aliases", "keywords": ["alias", "aka", "also known", "nickname"]},
            ]},
            {"name": "Biographical basics", "eeis": [
                {"name": "date_of_birth", "keywords": ["born", "dob", "birth", "age", "year old"]},
                {"name": "nationality", "keywords": ["citizen", "nationality", "passport", "filipino", "american"]},
                {"name": "current_location", "keywords": ["lives in", "based in", "located", "address", "residence"]},
            ]},
        ],
    },
    {
        "name": "Professional Profile",
        "description": "Map employment history, roles, and business relationships",
        "sirs": [
            {"name": "Current employment", "eeis": [
                {"name": "employer", "keywords": ["works at", "employed", "company", "corp", "inc"]},
                {"name": "role_title", "keywords": ["vp", "ceo", "director", "manager", "title", "position", "role"]},
            ]},
            {"name": "Business ownership", "eeis": [
                {"name": "companies_owned", "keywords": ["founder", "owner", "registered", "director", "officer"]},
                {"name": "business_registration", "keywords": ["sec", "dti", "registered", "incorporated"]},
            ]},
        ],
    },
    {
        "name": "Risk Assessment",
        "description": "Evaluate potential risks — sanctions, adverse media, legal issues",
        "sirs": [
            {"name": "Sanctions and PEP status", "eeis": [
                {"name": "pep_status", "keywords": ["pep", "politically exposed", "government official"]},
                {"name": "sanctions_status", "keywords": ["sanction", "ofac", "watchlist", "blacklist"]},
            ]},
            {"name": "Adverse media", "eeis": [
                {"name": "negative_news", "keywords": ["fraud", "scandal", "lawsuit", "arrest", "corruption", "adverse"]},
            ]},
            {"name": "Legal records", "eeis": [
                {"name": "court_records", "keywords": ["court", "legal", "case", "judgment", "criminal"]},
            ]},
        ],
    },
    {
        "name": "Digital Footprint",
        "description": "Map all digital identifiers and online presence",
        "sirs": [
            {"name": "Contact information", "eeis": [
                {"name": "email", "keywords": ["email", "@", "mail"]},
                {"name": "phone", "keywords": ["phone", "mobile", "call", "contact number"]},
            ]},
            {"name": "Social media presence", "eeis": [
                {"name": "social_accounts", "keywords": ["linkedin", "facebook", "instagram", "twitter", "social"]},
                {"name": "username", "keywords": ["username", "handle", "@", "account"]},
            ]},
        ],
    },
]

COMPANY_PIRS = [
    {
        "name": "Corporate Identity",
        "description": "Confirm legal entity status and registration",
        "sirs": [
            {"name": "Legal registration", "eeis": [
                {"name": "registration_number", "keywords": ["registered", "sec", "dti", "incorporation"]},
                {"name": "jurisdiction", "keywords": ["jurisdiction", "country", "state", "registered in"]},
            ]},
            {"name": "Leadership", "eeis": [
                {"name": "officers", "keywords": ["director", "officer", "ceo", "founder", "board"]},
            ]},
        ],
    },
    {
        "name": "Financial Profile",
        "description": "Assess financial health and business activity",
        "sirs": [
            {"name": "Revenue and funding", "eeis": [
                {"name": "revenue", "keywords": ["revenue", "sales", "income", "earnings"]},
                {"name": "funding", "keywords": ["funding", "raised", "investment", "series", "valuation"]},
            ]},
        ],
    },
    {
        "name": "Market Position",
        "description": "Understand competitive position and reputation",
        "sirs": [
            {"name": "Competitors", "eeis": [
                {"name": "competitors", "keywords": ["competitor", "rival", "alternative", "vs"]},
            ]},
            {"name": "Reviews", "eeis": [
                {"name": "reviews", "keywords": ["review", "rating", "glassdoor", "clutch", "reputation"]},
            ]},
        ],
    },
]

_PIR_TEMPLATES: dict[str, list[dict]] = {
    "person": PERSON_PIRS,
    "due_diligence": PERSON_PIRS,  # Due diligence uses the person template
    "company": COMPANY_PIRS,
}

_GENERIC_PIRS = [
    {
        "name": "Core Research Question",
        "description": "Answer the primary research question",
        "sirs": [
            {"name": "Primary findings", "eeis": [
                {"name": "key_facts", "keywords": ["found", "result", "evidence", "data"]},
            ]},
        ],
    },
]


def decompose_query_to_pirs(query: str, entity_type: str) -> list[dict]:
    """Decompose a query into PIRs based on entity type.

    Returns a deep copy of the PIR template with EEIs ready for mapping.
    """
    import copy
    template = _PIR_TEMPLATES.get(entity_type, _GENERIC_PIRS)
    # Deep copy to avoid mutating the template
    pirs = copy.deepcopy(template)

    # Initialize resolved status on all EEIs
    for pir in pirs:
        for sir in pir["sirs"]:
            for eei in sir["eeis"]:
                eei["resolved"] = False
                eei["evidence"] = []

    return pirs


def map_findings_to_pirs(pirs: list[dict], findings: list[dict]) -> list[dict]:
    """Map findings to EEIs by keyword matching.

    Marks EEIs as resolved when a finding matches their keywords.
    Always operates on a deep copy so the caller's list is not mutated.
    """
    import copy
    pirs = copy.deepcopy(pirs)

    # Ensure every EEI has the required tracking fields
    for pir in pirs:
        for sir in pir["sirs"]:
            for eei in sir["eeis"]:
                eei.setdefault("resolved", False)
                eei.setdefault("evidence", [])

    for finding in findings:
        content = (finding.get("content", "") + " " + finding.get("title", "")).lower()
        source = finding.get("source", "unknown")

        for pir in pirs:
            for sir in pir["sirs"]:
                for eei in sir["eeis"]:
                    for keyword in eei.get("keywords", []):
                        if _keyword_matches(keyword, content):
                            eei["resolved"] = True
                            eei["evidence"].append({
                                "source": source,
                                "snippet": content[:100],
                            })
                            break  # One keyword match is enough per finding

    return pirs


def generate_coverage_report(pirs: list[dict]) -> dict:
    """Generate a PIR coverage report.

    Returns: {"pirs": [...], "overall_coverage": float, "gaps": [str]}
    """
    pir_reports = []
    total_eeis = 0
    resolved_eeis = 0
    gaps = []

    for pir in pirs:
        pir_total = 0
        pir_resolved = 0
        sir_reports = []

        for sir in pir["sirs"]:
            sir_total = len(sir["eeis"])
            sir_resolved = sum(1 for eei in sir["eeis"] if eei.get("resolved"))
            pir_total += sir_total
            pir_resolved += sir_resolved

            unresolved = [eei["name"] for eei in sir["eeis"] if not eei.get("resolved")]
            if unresolved:
                gaps.extend([f"{pir['name']} > {sir['name']} > {eei}" for eei in unresolved])

            sir_reports.append({
                "name": sir["name"],
                "coverage": sir_resolved / sir_total if sir_total else 0.0,
                "resolved": sir_resolved,
                "total": sir_total,
            })

        total_eeis += pir_total
        resolved_eeis += pir_resolved

        coverage = pir_resolved / pir_total if pir_total else 0.0
        if coverage >= 0.8:
            confidence = "high"
        elif coverage >= 0.5:
            confidence = "moderate"
        else:
            confidence = "low"

        pir_reports.append({
            "name": pir["name"],
            "description": pir["description"],
            "coverage": round(coverage, 2),
            "confidence": confidence,
            "resolved": pir_resolved,
            "total": pir_total,
            "sirs": sir_reports,
        })

    overall = resolved_eeis / total_eeis if total_eeis else 0.0

    return {
        "pirs": pir_reports,
        "overall_coverage": round(overall, 2),
        "resolved_eeis": resolved_eeis,
        "total_eeis": total_eeis,
        "gaps": gaps,
    }
