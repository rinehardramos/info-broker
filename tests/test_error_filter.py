"""Tests for IS brain error detection pre-filter."""
from app.is_brain import _classify_finding


def test_classify_finding_detects_403_error():
    finding = {"title": "Apollo blocked - 422 Unprocessable", "content": "API returned 422", "confidence": 85}
    result = _classify_finding(finding)
    assert result["finding_type"] == "error"
    assert result["confidence"] == 0
    assert result["error_flagged"] is True


def test_classify_finding_detects_missing_api_key():
    finding = {"title": "Hunter.io - HUNTER_IO_API_KEY not configured", "content": "Missing key", "confidence": 99}
    result = _classify_finding(finding)
    assert result["finding_type"] == "error"
    assert result["confidence"] == 0


def test_classify_finding_passes_real_result():
    finding = {"title": "CEO of TechPH Inc", "content": "Juan dela Cruz founded TechPH", "confidence": 80}
    result = _classify_finding(finding)
    assert result["finding_type"] == "result"
    assert result["error_flagged"] is False
    assert result["confidence"] == 80


def test_classify_finding_detects_permission_error():
    finding = {"title": "LinkedIn Apify blocked", "content": "requires full access to your account", "confidence": 99}
    result = _classify_finding(finding)
    assert result["finding_type"] == "error"


def test_classify_finding_detects_rate_limit():
    finding = {"title": "Google rate limited", "content": "429 rate limit exceeded", "confidence": 70}
    result = _classify_finding(finding)
    assert result["finding_type"] == "error"


def test_classify_finding_handles_missing_fields():
    finding = {}
    result = _classify_finding(finding)
    assert result["finding_type"] == "result"
    assert result["error_flagged"] is False


def test_classify_finding_detects_token_invalid():
    finding = {"title": "LinkedIn Apify blocked", "content": "token is not valid", "confidence": 99}
    result = _classify_finding(finding)
    assert result["finding_type"] == "error"
    assert result["confidence"] == 0
