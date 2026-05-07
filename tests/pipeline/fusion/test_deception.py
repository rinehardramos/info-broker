"""Tests for deception detection flags."""
from app.pipeline.fusion.deception import detect_deception, _check_source_echo, _check_copied_content


def test_no_deception_clean_findings():
    findings = [
        {"title": "A", "content": "John works at Acme", "source": "linkedin"},
        {"title": "B", "content": "John listed as VP Sales", "source": "apollo"},
    ]
    results = detect_deception(findings)
    assert all(r["deception_risk"] < 0.3 for r in results)


def test_source_echo_detected():
    findings = [
        {"title": "Profile", "content": "Exact same content about John Doe working at Acme Corp as VP", "source": "source_a"},
        {"title": "Profile", "content": "Exact same content about John Doe working at Acme Corp as VP", "source": "source_b"},
    ]
    results = detect_deception(findings)
    flagged = [r for r in results if "source_echo" in r.get("deception_flags", [])]
    assert len(flagged) >= 1


def test_copied_content_detected():
    shared = "This is a long piece of text that appears in multiple findings verbatim and should trigger the copied content flag"
    findings = [
        {"title": "A", "content": f"Context: {shared}", "source": "source_a"},
        {"title": "B", "content": f"Other: {shared}", "source": "source_b"},
    ]
    results = detect_deception(findings)
    flagged = [r for r in results if "copied_content" in r.get("deception_flags", [])]
    assert len(flagged) >= 1


def test_low_source_diversity():
    findings = [
        {"title": "A", "content": "Finding 1", "source": "ddg_search"},
        {"title": "B", "content": "Finding 2", "source": "ddg_search"},
        {"title": "C", "content": "Finding 3", "source": "ddg_search"},
    ]
    results = detect_deception(findings)
    flagged = [r for r in results if "low_source_diversity" in r.get("deception_flags", [])]
    assert len(flagged) >= 1


def test_too_perfect_detection():
    # Finding with suspiciously many extra fields (7+ beyond title/content/source)
    findings = [
        {
            "title": "Complete Profile",
            "content": "Full bio available",
            "source": "web",
            "phone": "+1234567890",
            "address": "123 Main St",
            "company": "Acme Corp",
            "role": "CEO",
            "education": "Harvard University",
            "linkedin": "john-doe",
            "twitter": "johndoe",
            "dob": "1980-01-01",
        },
    ]
    results = detect_deception(findings)
    flagged = [r for r in results if "too_perfect" in r.get("deception_flags", [])]
    assert len(flagged) >= 1


def test_risk_capped_at_one():
    # Even with multiple flags, risk should not exceed 1.0
    findings = [
        {"title": "Same", "content": "Same exact long content that triggers multiple deception detection flags in the system", "source": "same_source"},
        {"title": "Same", "content": "Same exact long content that triggers multiple deception detection flags in the system", "source": "same_source"},
    ]
    results = detect_deception(findings)
    assert all(r["deception_risk"] <= 1.0 for r in results)


def test_empty_findings():
    assert detect_deception([]) == []


def test_single_finding_no_echo():
    findings = [{"title": "A", "content": "Some content", "source": "linkedin"}]
    results = detect_deception(findings)
    assert all("source_echo" not in r.get("deception_flags", []) for r in results)
