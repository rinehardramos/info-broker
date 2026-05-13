"""Tests for PIR (Priority Intelligence Requirements) decomposition."""
from app.pipeline.fusion.pir import (
    decompose_query_to_pirs, map_findings_to_pirs, generate_coverage_report,
    _keyword_matches, PERSON_PIRS,
)

def test_person_pirs_defined():
    assert len(PERSON_PIRS) >= 3
    for pir in PERSON_PIRS:
        assert "name" in pir
        assert "sirs" in pir
        assert len(pir["sirs"]) >= 2

def test_decompose_person_query():
    pirs = decompose_query_to_pirs("Find everything about John Doe", "person")
    assert len(pirs) >= 3
    pir_names = [p["name"] for p in pirs]
    assert any("identity" in n.lower() for n in pir_names)

def test_decompose_unknown_type():
    pirs = decompose_query_to_pirs("random query", "unknown_xyz")
    assert len(pirs) >= 1  # Should return at least a generic PIR

def test_map_findings_to_pirs():
    pirs = PERSON_PIRS
    findings = [
        {"content": "John Doe, born 1985, American citizen", "source": "web_search"},
        {"content": "Email: john@acme.com, phone +1234567890", "source": "hunter_io"},
        {"content": "VP Sales at Acme Corp since 2020", "source": "linkedin"},
        {"content": "No sanctions matches found", "source": "pep_sanctions_screen"},
    ]
    mapped = map_findings_to_pirs(pirs, findings)
    # At least some EEIs should be resolved
    total_resolved = sum(
        sum(1 for eei in sir["eeis"] if eei.get("resolved"))
        for pir in mapped
        for sir in pir["sirs"]
    )
    assert total_resolved >= 2

def test_coverage_report_structure():
    pirs = PERSON_PIRS
    findings = [
        {"content": "John works at Acme Corp", "source": "linkedin"},
    ]
    mapped = map_findings_to_pirs(pirs, findings)
    report = generate_coverage_report(mapped)
    assert "pirs" in report
    assert "overall_coverage" in report
    assert "gaps" in report
    assert isinstance(report["overall_coverage"], float)
    assert 0.0 <= report["overall_coverage"] <= 1.0

def test_coverage_report_identifies_gaps():
    pirs = PERSON_PIRS
    findings = []  # No findings
    mapped = map_findings_to_pirs(pirs, findings)
    report = generate_coverage_report(mapped)
    assert report["overall_coverage"] == 0.0
    assert len(report["gaps"]) > 0

def test_full_pir_flow():
    pirs = decompose_query_to_pirs("Profile John Doe for due diligence", "person")
    findings = [
        {"content": "John Doe, age 40, Filipino citizen, lives in Manila", "source": "web_search"},
        {"content": "john.doe@acme.ph verified email", "source": "smtp_verifier"},
        {"content": "VP Operations at Acme Philippines Inc", "source": "linkedin"},
        {"content": "Acme Philippines registered with SEC, directors: John Doe", "source": "ph_sec_dti"},
        {"content": "No PEP or sanctions matches", "source": "pep_sanctions_screen"},
        {"content": "No adverse media found", "source": "adverse_media"},
    ]
    mapped = map_findings_to_pirs(pirs, findings)
    report = generate_coverage_report(mapped)
    assert report["overall_coverage"] > 0.3
    # Should have some high-confidence PIRs
    high_conf = [p for p in report["pirs"] if p["confidence"] in ("high", "moderate")]
    assert len(high_conf) >= 1


# ---------------------------------------------------------------------------
# New tests: word-boundary keyword matching
# ---------------------------------------------------------------------------

def test_panamerican_does_not_match_american():
    """'panamerican' should NOT match the keyword 'american' (substring false positive)."""
    assert not _keyword_matches("american", "panamerican airlines flies routes")


def test_anti_fraud_does_not_match_fraud():
    """'anti-fraud certification' should NOT match the keyword 'fraud' at word boundary."""
    assert not _keyword_matches("fraud", "anti-fraud certification completed")


def test_exact_word_matches():
    """'american' should match when it appears as a standalone word."""
    assert _keyword_matches("american", "american company based in new york")


def test_at_symbol_matches_email():
    """The '@' keyword should match when an email address is present."""
    assert _keyword_matches("@", "contact@example.com for more info")


def test_at_symbol_no_match_without_email():
    """The '@' keyword should not match plain text without an email pattern."""
    assert not _keyword_matches("@", "no email address here at all")
