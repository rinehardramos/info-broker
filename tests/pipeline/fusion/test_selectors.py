"""Tests for selector extraction from findings."""
from app.pipeline.fusion.selectors import extract_selectors, extract_selectors_from_findings


def test_extract_email():
    results = extract_selectors("Contact john.doe@example.com for info")
    emails = [r for r in results if r["type"] == "email"]
    assert len(emails) == 1
    assert emails[0]["value"] == "john.doe@example.com"


def test_extract_multiple_emails():
    results = extract_selectors("Emails: a@b.com and c@d.org")
    emails = [r for r in results if r["type"] == "email"]
    assert len(emails) == 2


def test_extract_phone_international():
    results = extract_selectors("Call +1-800-555-0199 or +63 917 123 4567")
    phones = [r for r in results if r["type"] == "phone"]
    assert len(phones) >= 1


def test_extract_phone_local():
    results = extract_selectors("Phone: 09171234567")
    phones = [r for r in results if r["type"] == "phone"]
    assert len(phones) == 1


def test_extract_domain():
    results = extract_selectors("Visit acme.com or example.org for details")
    domains = [r for r in results if r["type"] == "domain"]
    assert len(domains) >= 1


def test_extract_username():
    results = extract_selectors("Follow @johndoe on Twitter")
    usernames = [r for r in results if r["type"] == "username"]
    assert len(usernames) == 1
    assert usernames[0]["value"] == "johndoe"


def test_extract_no_selectors():
    results = extract_selectors("No identifiers here, just plain text.")
    assert results == []


def test_extract_mixed_text():
    text = "John Doe (john@acme.com, +1-800-555-0199, @johndoe42) works at acme.com"
    results = extract_selectors(text)
    types = {r["type"] for r in results}
    assert "email" in types
    assert "phone" in types
    assert "username" in types


def test_extract_deduplicates():
    text = "Email john@x.com and also john@x.com again"
    results = extract_selectors(text)
    emails = [r for r in results if r["type"] == "email"]
    assert len(emails) == 1


def test_extract_from_findings():
    findings = [
        {"title": "LinkedIn Profile", "content": "john.doe@company.com, Senior VP"},
        {"title": "Facebook", "content": "Contact: +639171234567"},
    ]
    results = extract_selectors_from_findings(findings)
    types = {r["type"] for r in results}
    assert "email" in types
    assert "phone" in types
