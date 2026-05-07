"""Regex-based selector extraction from research finding text."""

from __future__ import annotations
import re

# Patterns
_EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
_PHONE_RE = re.compile(r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}')
_DOMAIN_RE = re.compile(r'\b(?:[a-zA-Z0-9-]+\.)+(?:com|org|net|io|co|gov|edu|info|biz)\b')
_USERNAME_RE = re.compile(r'@([a-zA-Z0-9_]{3,30})')


def extract_selectors(text: str) -> list[dict]:
    """Extract all identifiable selectors from text. Returns deduplicated list."""
    if not text:
        return []

    seen: set[tuple[str, str]] = set()
    results: list[dict] = []

    # Emails first (to exclude email domains from domain matches)
    email_domains: set[str] = set()
    for match in _EMAIL_RE.finditer(text):
        email = match.group().lower()
        email_domains.add(email.split("@")[1])
        key = ("email", email)
        if key not in seen:
            seen.add(key)
            results.append({"type": "email", "value": email})

    # Phones
    for match in _PHONE_RE.finditer(text):
        phone = match.group().strip()
        # Filter out short numbers that are probably not phones
        digits = re.sub(r'\D', '', phone)
        if len(digits) < 7:
            continue
        key = ("phone", digits)
        if key not in seen:
            seen.add(key)
            results.append({"type": "phone", "value": phone})

    # Domains (exclude email domains already captured)
    for match in _DOMAIN_RE.finditer(text):
        domain = match.group().lower()
        if domain in email_domains:
            continue
        key = ("domain", domain)
        if key not in seen:
            seen.add(key)
            results.append({"type": "domain", "value": domain})

    # Usernames (@mentions)
    for match in _USERNAME_RE.finditer(text):
        username = match.group(1).lower()
        key = ("username", username)
        if key not in seen:
            seen.add(key)
            results.append({"type": "username", "value": username})

    return results


def extract_selectors_from_findings(findings: list[dict]) -> list[dict]:
    """Extract selectors from all findings' title + content fields."""
    all_selectors: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for finding in findings:
        text = (finding.get("title", "") + " " + finding.get("content", "")).strip()
        for selector in extract_selectors(text):
            key = (selector["type"], selector["value"])
            if key not in seen:
                seen.add(key)
                all_selectors.append(selector)

    return all_selectors
