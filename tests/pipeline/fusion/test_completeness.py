"""Tests for investigation completeness assessment."""
from app.pipeline.fusion.completeness import assess_completeness, PERSON_DOMAINS


def test_person_domains_has_10():
    assert len(PERSON_DOMAINS) == 10


def test_person_domains_have_keywords():
    for domain in PERSON_DOMAINS:
        assert "name" in domain
        assert "keywords" in domain
        assert len(domain["keywords"]) >= 3


def test_full_coverage():
    findings = [
        {"content": "John Doe, born 1985, American nationality", "source": "web_search"},
        {"content": "Email: john@acme.com, username johndoe42, LinkedIn profile", "source": "linkedin"},
        {"content": "Wife: Jane Doe, children: 2, brother: Mike", "source": "facebook"},
        {"content": "VP Sales at Acme Corp, MBA from Harvard, career in tech", "source": "linkedin"},
        {"content": "Owns property in NYC, business registered, investment portfolio", "source": "sec_edgar"},
        {"content": "No court records, clean criminal history, licensed CPA", "source": "opencorporates"},
        {"content": "Profile photo found, avatar on LinkedIn", "source": "face_search"},
        {"content": "Active on WhatsApp, Telegram username found", "source": "messaging_check"},
        {"content": "Email found in LinkedIn breach, credentials leaked", "source": "hibp_lookup"},
        {"content": "Active on Reddit and Discord, posts on tech forums", "source": "web_search"},
    ]
    result = assess_completeness(findings, [], "person")
    confirmed = [d for d in result["domains"] if d["status"] == "CONFIRMED"]
    # Most domains should be CONFIRMED or PARTIAL with these findings
    assert result["coverage_pct"] >= 0.8
    assert len(result["gaps"]) <= 2


def test_partial_coverage():
    findings = [
        {"content": "John Doe works at Acme Corp as VP Sales", "source": "linkedin"},
    ]
    result = assess_completeness(findings, [], "person")
    # Only professional + identity covered
    assert result["coverage_pct"] < 1.0
    assert len(result["gaps"]) >= 5


def test_empty_findings():
    result = assess_completeness([], [], "person")
    assert result["coverage_pct"] == 0.0
    assert len(result["gaps"]) == 10
    assert all(d["status"] == "NOT_ATTEMPTED" for d in result["domains"])


def test_selectors_contribute():
    findings = []
    selectors = [
        {"type": "email", "value": "john@acme.com"},
        {"type": "phone", "value": "+14155551234"},
    ]
    result = assess_completeness(findings, selectors, "person")
    # digital_footprint + communication should get partial credit
    digital = next(d for d in result["domains"] if d["name"] == "digital_footprint")
    assert digital["status"] in ("CONFIRMED", "PARTIAL")


def test_confirmed_requires_two_sources():
    findings = [
        {"content": "email: john@acme.com", "source": "hunter_io"},
        {"content": "john@acme.com found on LinkedIn", "source": "linkedin"},
    ]
    result = assess_completeness(findings, [], "person")
    digital = next(d for d in result["domains"] if d["name"] == "digital_footprint")
    assert digital["status"] == "CONFIRMED"  # 2 sources
    assert digital["sources"] >= 2


def test_partial_with_one_source():
    findings = [
        {"content": "email: john@acme.com", "source": "hunter_io"},
    ]
    result = assess_completeness(findings, [], "person")
    digital = next(d for d in result["domains"] if d["name"] == "digital_footprint")
    assert digital["status"] == "PARTIAL"  # 1 source only


def test_unknown_entity_type_returns_empty():
    result = assess_completeness([], [], "unknown_xyz")
    assert result["coverage_pct"] == 0.0
