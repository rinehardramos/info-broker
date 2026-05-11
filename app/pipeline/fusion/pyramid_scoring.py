"""Pyramid of Pain scoring for investigation findings."""
from __future__ import annotations
import re

# Pattern sets for each pyramid level
_LEVEL_PATTERNS = [
    # Level 1 — exact hashes, account IDs, transaction IDs
    (1, [
        r'\b[0-9a-f]{32,64}\b',          # MD5/SHA hash
        r'\btxn[-_]?[0-9a-f]{8,}\b',     # transaction ID
        r'\buid[-_]?[0-9a-f]{8,}\b',     # UID
    ]),
    # Level 2 — IPs, specific URLs, direct phone numbers
    (2, [
        r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',  # IPv4
        r'https?://[^\s]+',                             # URL
        r'\+\d{8,15}\b',                               # phone
        r'\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b',           # US phone
    ]),
    # Level 3 — domains, email domains, hosting patterns
    (3, [
        r'\b[\w.-]+\.(com|net|org|io|gov|edu|ph|uk|ae|sa)\b',  # domain
        r'@[\w.-]+\.\w+',                                        # email domain
        r'\b(?:cloudflare|aws|azure|gcp|digitalocean|linode)\b', # hosting
    ]),
    # Level 4 — platform accounts, tools, apps
    (4, [
        r'\b(?:linkedin|github|twitter|facebook|instagram|telegram|whatsapp|viber|tiktok|reddit)\b',
        r'\b(?:salesforce|hubspot|jira|slack|notion|trello|asana)\b',
        r'@\w{3,}',   # @username
    ]),
    # Level 5 — behavioral patterns, org relationships, timing
    (5, [
        r'\b(?:pattern|habit|routine|behavior|behaviour|relationship|associate|network|connected|linked)\b',
        r'\b(?:regularly|consistently|typically|always|never|usually|often)\b',
        r'\b(?:employer|employee|officer|director|founder|co-founder|partner|colleague)\b',
        r'\b(?:timezone|circadian|schedule|timing|cadence)\b',
    ]),
    # Level 6 — TTPs: tactics, techniques, procedures
    (6, [
        r'\b(?:tactic|technique|procedure|ttp|methodology|modus operandi|mbo|method)\b',
        r'\b(?:strategy|approach|scheme|operation|campaign|playbook)\b',
        r'\b(?:phishing|social engineering|fraud|laundering|evasion|obfuscation)\b',
    ]),
]


def score_finding(finding: dict) -> int:
    """Return the Pyramid of Pain level (1-6) for a finding. Higher = more durable intel."""
    text = f"{finding.get('title', '')} {finding.get('content', '')}".lower()
    max_level = 1
    for level, patterns in _LEVEL_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                max_level = max(max_level, level)
    return max_level


def annotate_findings(findings: list[dict]) -> list[dict]:
    """Add pyramid_level field to each finding in-place. Returns the same list."""
    for f in findings:
        f["pyramid_level"] = score_finding(f)
    return findings


PYRAMID_LABELS = {
    1: "Value/Hash",
    2: "Network Artifact",
    3: "Domain/Infrastructure",
    4: "Tool/Platform Account",
    5: "Behavioral Pattern",
    6: "TTP",
}
