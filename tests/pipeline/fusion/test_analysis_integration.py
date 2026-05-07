"""Integration test: completeness + deception working together."""
from app.pipeline.fusion.completeness import assess_completeness
from app.pipeline.fusion.deception import detect_deception
from app.pipeline.fusion.selectors import extract_selectors_from_findings


def test_full_analysis_flow():
    """Findings -> selectors -> completeness + deception -> structured output."""
    findings = [
        {"title": "LinkedIn", "content": "John Doe, VP Sales at acme.com. Email: john@acme.com", "source": "linkedin_profile"},
        {"title": "HIBP", "content": "john@acme.com found in breach database, credentials leaked", "source": "hibp_lookup"},
        {"title": "Facebook", "content": "John married to Jane Doe, has 2 children", "source": "facebook_pages"},
        {"title": "SEC Filing", "content": "John Doe listed as director, business registered in Delaware", "source": "sec_edgar"},
    ]

    # Step 1: Extract selectors
    selectors = extract_selectors_from_findings(findings)
    assert any(s["type"] == "email" for s in selectors)

    # Step 2: Assess completeness
    completeness = assess_completeness(findings, selectors, "person")
    assert completeness["coverage_pct"] > 0.3
    assert isinstance(completeness["gaps"], list)
    assert len(completeness["domains"]) == 10

    # Step 3: Detect deception
    deception = detect_deception(findings)
    assert len(deception) == len(findings)
    assert all("deception_risk" in d for d in deception)
    assert all("deception_flags" in d for d in deception)

    # These clean findings should have low deception risk
    assert all(d["deception_risk"] < 0.5 for d in deception)


def test_suspicious_findings_flagged():
    """Findings with deception indicators get flagged."""
    shared_text = "This is the exact same text that appears in multiple findings from supposedly independent sources and is suspicious"
    findings = [
        {"title": "Source A", "content": shared_text, "source": "source_a"},
        {"title": "Source B", "content": shared_text, "source": "source_b"},
    ]
    deception = detect_deception(findings)
    # Should detect source_echo and/or copied_content
    all_flags = []
    for d in deception:
        all_flags.extend(d.get("deception_flags", []))
    assert len(all_flags) > 0  # At least one flag raised


def test_completeness_gaps_match_missing_domains():
    """Gaps should only list domains not covered by findings."""
    findings = [
        {"title": "Work", "content": "John is employed at Acme as VP of Engineering", "source": "linkedin"},
    ]
    completeness = assess_completeness(findings, [], "person")
    # Professional should be covered, most others should be gaps
    domain_names = [d["name"] for d in completeness["domains"] if d["status"] in ("CONFIRMED", "PARTIAL")]
    assert "professional" in domain_names
    assert "professional" not in completeness["gaps"]
