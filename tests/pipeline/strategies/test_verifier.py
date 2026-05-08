# tests/pipeline/strategies/test_verifier.py
"""TDD tests for the rule-based finding verifier module."""

from __future__ import annotations

import pytest

from app.pipeline.strategies.verifier import verify_findings


# ---------------------------------------------------------------------------
# Empty input
# ---------------------------------------------------------------------------


def test_empty_findings_returns_pass():
    result = verify_findings([])
    assert result == {"status": "PASS", "issues": []}


# ---------------------------------------------------------------------------
# Clean finding — should produce no issues
# ---------------------------------------------------------------------------


def test_clean_finding_returns_pass():
    findings = [
        {
            "source": "https://example.com",
            "content": "This is a sufficiently long content string.",
            "confidence": 70,
        }
    ]
    result = verify_findings(findings)
    assert result["status"] == "PASS"
    assert result["issues"] == []


def test_normal_finding_with_reasonable_confidence_passes():
    findings = [
        {
            "source": "reuters.com",
            "content": "Detailed research content that is long enough.",
            "confidence": 60,
            "error_flagged": False,
        }
    ]
    result = verify_findings(findings)
    assert result["status"] == "PASS"
    assert result["issues"] == []


# ---------------------------------------------------------------------------
# missing_source
# ---------------------------------------------------------------------------


def test_finding_without_source_field_flagged():
    findings = [{"content": "Some valid content here.", "confidence": 50}]
    result = verify_findings(findings)
    issue_types = [i["type"] for i in result["issues"]]
    assert "missing_source" in issue_types
    assert result["issues"][0]["finding_index"] == 0


def test_finding_with_empty_source_flagged():
    findings = [{"source": "", "content": "Some valid content here.", "confidence": 50}]
    result = verify_findings(findings)
    issue_types = [i["type"] for i in result["issues"]]
    assert "missing_source" in issue_types


# ---------------------------------------------------------------------------
# empty_content
# ---------------------------------------------------------------------------


def test_finding_without_content_field_flagged():
    findings = [{"source": "https://example.com", "confidence": 50}]
    result = verify_findings(findings)
    issue_types = [i["type"] for i in result["issues"]]
    assert "empty_content" in issue_types


def test_finding_with_empty_content_flagged():
    findings = [{"source": "https://example.com", "content": "", "confidence": 50}]
    result = verify_findings(findings)
    issue_types = [i["type"] for i in result["issues"]]
    assert "empty_content" in issue_types


def test_finding_with_short_content_flagged():
    """Content shorter than 10 chars should be flagged."""
    findings = [{"source": "https://example.com", "content": "short", "confidence": 50}]
    result = verify_findings(findings)
    issue_types = [i["type"] for i in result["issues"]]
    assert "empty_content" in issue_types


def test_finding_with_exactly_9_chars_content_flagged():
    findings = [{"source": "https://example.com", "content": "123456789", "confidence": 50}]
    result = verify_findings(findings)
    issue_types = [i["type"] for i in result["issues"]]
    assert "empty_content" in issue_types


def test_finding_with_exactly_10_chars_content_passes():
    findings = [{"source": "https://example.com", "content": "1234567890", "confidence": 50}]
    result = verify_findings(findings)
    issue_types = [i["type"] for i in result["issues"]]
    assert "empty_content" not in issue_types


# ---------------------------------------------------------------------------
# confidence_overreach
# ---------------------------------------------------------------------------


def test_error_flagged_with_high_confidence_flagged():
    findings = [
        {
            "source": "https://example.com",
            "content": "Sufficiently long content string.",
            "confidence": 80,
            "error_flagged": True,
        }
    ]
    result = verify_findings(findings)
    issue_types = [i["type"] for i in result["issues"]]
    assert "confidence_overreach" in issue_types


def test_error_flagged_with_confidence_exactly_50_not_flagged():
    """Threshold is > 50, so confidence == 50 should NOT trigger."""
    findings = [
        {
            "source": "https://example.com",
            "content": "Sufficiently long content string.",
            "confidence": 50,
            "error_flagged": True,
        }
    ]
    result = verify_findings(findings)
    issue_types = [i["type"] for i in result["issues"]]
    assert "confidence_overreach" not in issue_types


def test_error_flagged_with_confidence_51_is_flagged():
    findings = [
        {
            "source": "https://example.com",
            "content": "Sufficiently long content string.",
            "confidence": 51,
            "error_flagged": True,
        }
    ]
    result = verify_findings(findings)
    issue_types = [i["type"] for i in result["issues"]]
    assert "confidence_overreach" in issue_types


def test_error_not_flagged_does_not_trigger_overreach():
    findings = [
        {
            "source": "https://example.com",
            "content": "Sufficiently long content string.",
            "confidence": 90,
            "error_flagged": False,
        }
    ]
    result = verify_findings(findings)
    issue_types = [i["type"] for i in result["issues"]]
    assert "confidence_overreach" not in issue_types


# ---------------------------------------------------------------------------
# unverified_high_confidence
# ---------------------------------------------------------------------------


def test_empty_source_with_high_confidence_flagged():
    findings = [
        {
            "source": "",
            "content": "Sufficiently long content string.",
            "confidence": 90,
        }
    ]
    result = verify_findings(findings)
    issue_types = [i["type"] for i in result["issues"]]
    assert "unverified_high_confidence" in issue_types


def test_unknown_source_with_high_confidence_flagged():
    findings = [
        {
            "source": "unknown",
            "content": "Sufficiently long content string.",
            "confidence": 75,
        }
    ]
    result = verify_findings(findings)
    issue_types = [i["type"] for i in result["issues"]]
    assert "unverified_high_confidence" in issue_types


def test_source_containing_unknown_with_high_confidence_flagged():
    findings = [
        {
            "source": "unknown-site.net",
            "content": "Sufficiently long content string.",
            "confidence": 80,
        }
    ]
    result = verify_findings(findings)
    issue_types = [i["type"] for i in result["issues"]]
    assert "unverified_high_confidence" in issue_types


def test_unknown_source_with_confidence_exactly_70_not_flagged():
    """Threshold is > 70, so confidence == 70 should NOT trigger."""
    findings = [
        {
            "source": "unknown",
            "content": "Sufficiently long content string.",
            "confidence": 70,
        }
    ]
    result = verify_findings(findings)
    issue_types = [i["type"] for i in result["issues"]]
    assert "unverified_high_confidence" not in issue_types


def test_unknown_source_with_confidence_71_is_flagged():
    findings = [
        {
            "source": "unknown",
            "content": "Sufficiently long content string.",
            "confidence": 71,
        }
    ]
    result = verify_findings(findings)
    issue_types = [i["type"] for i in result["issues"]]
    assert "unverified_high_confidence" in issue_types


# ---------------------------------------------------------------------------
# Status logic
# ---------------------------------------------------------------------------


def test_any_issue_returns_pass_with_notes():
    findings = [{"content": "Some valid content here.", "confidence": 50}]  # missing source
    result = verify_findings(findings)
    assert result["status"] == "PASS_WITH_NOTES"


def test_multiple_issues_returns_pass_with_notes_with_correct_count():
    findings = [
        # Finding 0: missing source + empty content
        {"confidence": 50},
        # Finding 1: clean
        {
            "source": "https://example.com",
            "content": "Sufficiently long content.",
            "confidence": 60,
        },
        # Finding 2: error_flagged + high confidence
        {
            "source": "https://example.com",
            "content": "Sufficiently long content.",
            "confidence": 80,
            "error_flagged": True,
        },
    ]
    result = verify_findings(findings)
    assert result["status"] == "PASS_WITH_NOTES"
    # finding 0 => missing_source + empty_content (2 issues)
    # finding 2 => confidence_overreach (1 issue)
    assert len(result["issues"]) == 3


def test_issue_contains_correct_finding_index():
    findings = [
        {
            "source": "https://example.com",
            "content": "Sufficiently long content.",
            "confidence": 60,
        },
        # Index 1: missing source
        {"content": "Sufficiently long content.", "confidence": 50},
    ]
    result = verify_findings(findings)
    missing_source_issues = [i for i in result["issues"] if i["type"] == "missing_source"]
    assert len(missing_source_issues) == 1
    assert missing_source_issues[0]["finding_index"] == 1


def test_issue_has_message_field():
    findings = [{"content": "Some valid content here.", "confidence": 50}]
    result = verify_findings(findings)
    for issue in result["issues"]:
        assert "message" in issue
        assert isinstance(issue["message"], str)
        assert len(issue["message"]) > 0
