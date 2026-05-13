"""TDD tests for app.pipeline.fusion.merger."""
import pytest
from app.pipeline.fusion.merger import merge_research_results, _findings_similar

FINDING_A = {
    "url": "https://example.com/profile/alice",
    "title": "Alice Johnson LinkedIn",
    "confidence": 75, "branch": "linkedin", "source_class": "B2",
}
FINDING_B = {
    "url": "https://example.com/profile/alice",
    "title": "Alice Johnson LinkedIn Profile",
    "confidence": 80, "branch": "deep", "source_class": "B2",
}
FINDING_C = {
    "url": "https://news.example.com/article",
    "title": "Acme Corp raises funding",
    "confidence": 85, "branch": "news", "source_class": "A1",
}


def test_same_url_is_similar():
    assert _findings_similar(FINDING_A, FINDING_B) is True


def test_different_url_different_title_not_similar():
    assert _findings_similar(FINDING_A, FINDING_C) is False


def test_similar_title_counted_as_match():
    a = {"url": "https://a.example.com/x", "title": "Alice Johnson Senior Engineer"}
    b = {"url": "https://b.example.com/y", "title": "Alice Johnson Senior Engineer Role"}
    assert _findings_similar(a, b) is True


def test_unrelated_titles_not_similar():
    a = {"url": "https://a.example.com", "title": "Acme Corp Funding Round"}
    b = {"url": "https://b.example.com", "title": "Bob Smith Career"}
    assert _findings_similar(a, b) is False


def test_fast_finding_confirmed_when_thorough_has_match():
    fast = {"findings": [FINDING_A], "summary": "fast"}
    thorough = {"findings": [FINDING_B, FINDING_C], "summary": "thorough"}
    merged = merge_research_results(fast, thorough, "alice johnson")
    fast_f = next(f for f in merged["findings"] if f["phase"] == "fast")
    assert fast_f["confirmed_by_thorough"] is True


def test_thorough_only_finding_marked_new():
    fast = {"findings": [FINDING_A], "summary": "fast"}
    thorough = {"findings": [FINDING_B, FINDING_C], "summary": "thorough"}
    merged = merge_research_results(fast, thorough, "alice johnson")
    thorough_only = [f for f in merged["findings"] if f["phase"] == "thorough"]
    assert any(f["url"] == FINDING_C["url"] for f in thorough_only)


def test_counts_correct():
    fast = {"findings": [FINDING_A], "summary": ""}
    thorough = {"findings": [FINDING_B, FINDING_C], "summary": ""}
    merged = merge_research_results(fast, thorough, "q")
    assert merged["fast_count"] == 1
    assert merged["thorough_count"] == 2


def test_empty_fast_all_thorough():
    merged = merge_research_results(
        {"findings": [], "summary": ""},
        {"findings": [FINDING_C], "summary": ""},
        "q",
    )
    assert all(f["phase"] == "thorough" for f in merged["findings"])


def test_empty_thorough_fast_unconfirmed():
    merged = merge_research_results(
        {"findings": [FINDING_A], "summary": ""},
        {"findings": [], "summary": ""},
        "q",
    )
    assert merged["findings"][0]["confirmed_by_thorough"] is False


def test_confirmed_count_matches():
    fast = {"findings": [FINDING_A], "summary": ""}
    thorough = {"findings": [FINDING_B, FINDING_C], "summary": ""}
    merged = merge_research_results(fast, thorough, "q")
    expected = sum(1 for f in merged["findings"] if f.get("confirmed_by_thorough"))
    assert merged["confirmed_count"] == expected


def test_merged_count_equals_findings_length():
    fast = {"findings": [FINDING_A], "summary": ""}
    thorough = {"findings": [FINDING_B, FINDING_C], "summary": ""}
    merged = merge_research_results(fast, thorough, "q")
    assert merged["merged_count"] == len(merged["findings"])
