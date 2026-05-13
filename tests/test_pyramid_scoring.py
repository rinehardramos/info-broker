from app.pipeline.fusion.pyramid_scoring import score_finding, annotate_findings


def test_ttp_scores_highest():
    f = {"title": "Fraud scheme detected", "content": "Subject uses phishing tactic consistently across multiple campaigns"}
    assert score_finding(f) == 6


def test_ip_scores_level_2():
    f = {"title": "IP found", "content": "Server at 192.168.1.100 identified in logs"}
    assert score_finding(f) == 2


def test_behavioral_pattern_scores_5():
    f = {"title": "Behavioral pattern", "content": "Subject regularly posts at 3am, suggesting timezone mismatch with claimed residence"}
    assert score_finding(f) >= 5


def test_annotate_adds_field():
    findings = [
        {"title": "LinkedIn profile", "content": "Found on linkedin.com"},
        {"title": "TTP", "content": "Phishing technique identified"},
    ]
    annotate_findings(findings)
    assert all("pyramid_level" in f for f in findings)
    assert findings[1]["pyramid_level"] >= findings[0]["pyramid_level"]


def test_domain_scores_level_3():
    f = {"title": "Domain registered", "content": "example.com found in WHOIS records"}
    assert score_finding(f) >= 3


def test_empty_finding_scores_1():
    f = {"title": "", "content": ""}
    assert score_finding(f) == 1


def test_annotate_empty_list():
    result = annotate_findings([])
    assert result == []


def test_platform_account_scores_level_4():
    f = {"title": "Social media account", "content": "Subject has active twitter and telegram accounts"}
    assert score_finding(f) >= 4
