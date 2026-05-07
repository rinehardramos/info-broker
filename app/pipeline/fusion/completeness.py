"""Investigation completeness assessment against domain checklists."""

from __future__ import annotations

PERSON_DOMAINS = [
    {"name": "identity", "description": "Full name, aliases, DOB, nationality, location",
     "keywords": ["name", "alias", "dob", "birth", "nationality", "age", "gender", "born", "citizen"]},
    {"name": "digital_footprint", "description": "Emails, phones, usernames, social accounts",
     "keywords": ["email", "@", "phone", "username", "social", "account", "profile", "handle", "mobile"]},
    {"name": "family", "description": "Relatives, spouse, children, associates",
     "keywords": ["family", "spouse", "wife", "husband", "child", "children", "parent", "sibling", "brother", "sister", "relative", "married"]},
    {"name": "professional", "description": "Employment, roles, education, skills",
     "keywords": ["employ", "job", "title", "company", "work", "career", "education", "degree", "university", "mba", "ceo", "vp", "manager", "director"]},
    {"name": "financial", "description": "Property, business ownership, investments",
     "keywords": ["property", "asset", "business", "own", "bank", "invest", "wealth", "fund", "stock", "real estate", "registered"]},
    {"name": "public_records", "description": "Court, regulatory, licenses, criminal",
     "keywords": ["court", "legal", "lawsuit", "license", "regulatory", "criminal", "arrest", "filing", "record", "case"]},
    {"name": "visual", "description": "Photos, images, avatars",
     "keywords": ["photo", "image", "picture", "avatar", "portrait", "headshot", "face"]},
    {"name": "communication", "description": "Messaging platforms, chat presence",
     "keywords": ["telegram", "whatsapp", "signal", "messenger", "chat", "messaging", "viber", "wechat"]},
    {"name": "breach", "description": "Data breaches, dark web, leaked credentials",
     "keywords": ["breach", "pwned", "leak", "hack", "credential", "password", "dark web", "exposed", "dump"]},
    {"name": "communities", "description": "Forums, Reddit, Discord, online groups",
     "keywords": ["forum", "reddit", "discord", "community", "group", "board", "post", "thread", "subreddit"]},
]

# Domain lists for other entity types can be added here
_DOMAIN_MAP: dict[str, list[dict]] = {
    "person": PERSON_DOMAINS,
}

# Map selector types to the domain they contribute evidence for
_SELECTOR_DOMAIN_MAP: dict[str, str] = {
    "email": "digital_footprint",
    "phone": "digital_footprint",
    "username": "digital_footprint",
    "domain": "digital_footprint",
}


def assess_completeness(
    findings: list[dict],
    selectors: list[dict],
    entity_type: str,
) -> dict:
    """Assess investigation completeness against domain checklist.

    Returns:
        {"domains": [...], "coverage_pct": float, "gaps": [str]}

    Each domain entry has:
        {"name": str, "status": str, "sources": int, "findings_count": int}

    Status values:
        "NOT_ATTEMPTED" — no findings were supplied at all
        "NOT_FOUND"     — findings exist but none matched this domain
        "PARTIAL"       — at least one match but from a single source
        "CONFIRMED"     — matches from two or more distinct sources
    """
    domains = _DOMAIN_MAP.get(entity_type, [])
    if not domains:
        return {"domains": [], "coverage_pct": 0.0, "gaps": []}

    # Build (text, source) pairs from findings
    finding_texts: list[tuple[str, str]] = []
    for f in findings:
        text = ((f.get("title") or "") + " " + (f.get("content") or "")).lower()
        source = f.get("source") or f.get("source_tool") or "unknown"
        finding_texts.append((text, source))

    # Selector values contribute pseudo-findings for their mapped domain
    selector_pseudo: dict[str, list[tuple[str, str]]] = {}
    for sel in selectors:
        domain_name = _SELECTOR_DOMAIN_MAP.get(sel.get("type", ""), "")
        if domain_name:
            value = sel.get("value", "").lower()
            selector_pseudo.setdefault(domain_name, []).append((value, "selector"))

    domain_results = []
    covered_count = 0
    gaps: list[str] = []

    for domain in domains:
        # Keyword matches from findings
        matches = _match_domain(domain, finding_texts)

        # Selector pseudo-findings for this domain
        extra = selector_pseudo.get(domain["name"], [])
        all_matches = matches + extra

        sources = len({src for _, src in all_matches})
        findings_count = len(all_matches)

        if findings_count == 0:
            # Distinguish between "we had no data" vs "data existed but missed"
            status = "NOT_ATTEMPTED" if not findings and not selectors else "NOT_FOUND"
        elif sources >= 2:
            status = "CONFIRMED"
        else:
            status = "PARTIAL"

        if status in ("CONFIRMED", "PARTIAL"):
            covered_count += 1
        else:
            gaps.append(domain["name"])

        domain_results.append({
            "name": domain["name"],
            "status": status,
            "sources": sources,
            "findings_count": findings_count,
        })

    coverage_pct = covered_count / len(domains) if domains else 0.0

    return {
        "domains": domain_results,
        "coverage_pct": round(coverage_pct, 2),
        "gaps": gaps,
    }


def _match_domain(
    domain: dict,
    finding_texts: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Return findings (text, source) that contain at least one domain keyword."""
    matches = []
    for text, source in finding_texts:
        for kw in domain["keywords"]:
            if kw in text:
                matches.append((text, source))
                break  # one match per finding is sufficient
    return matches
