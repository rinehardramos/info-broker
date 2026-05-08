# tests/pipeline/strategies/test_orchestrator_complexity.py
"""TDD tests for classify_complexity() in the research query orchestrator."""

from __future__ import annotations

import pytest

from app.pipeline.strategies.orchestrator import classify_complexity


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _tier(query: str) -> str:
    """Return just the tier string from classify_complexity."""
    tier, _ = classify_complexity(query)
    return tier


def _score(query: str) -> int:
    """Return just the numeric score from classify_complexity."""
    _, score = classify_complexity(query)
    return score


# ---------------------------------------------------------------------------
# Simple queries
# ---------------------------------------------------------------------------


def test_simple_find_email():
    """Single entity + simple lookup verb -> simple."""
    assert _tier("find email of John Doe") == "simple"


def test_simple_what_is():
    """Simple lookup verb -> simple."""
    assert _tier("what is Acme Corp?") == "simple"


def test_simple_who_is_ceo():
    """Simple lookup verb -> simple."""
    assert _tier("who is the CEO of TechCorp") == "simple"


def test_simple_empty_string():
    """Empty input -> simple, score 0."""
    tier, score = classify_complexity("")
    assert tier == "simple"
    assert score == 0


def test_simple_short_ambiguous():
    """Short word with no signal -> simple."""
    assert _tier("hello") == "simple"


def test_simple_phone_of():
    """Single entity marker 'phone of' -> simple."""
    assert _tier("phone of Jane Doe") == "simple"


def test_simple_address_of():
    """Single entity marker 'address of' -> simple."""
    assert _tier("address of John Smith") == "simple"


# ---------------------------------------------------------------------------
# Complex queries
# ---------------------------------------------------------------------------


def test_complex_investigate():
    """Open-ended verb 'investigate' -> complex."""
    assert _tier("investigate TechCorp") == "complex"


def test_complex_compare_vs():
    """Multi-entity comparison and 'vs' signal -> complex."""
    assert _tier("compare AWS vs Azure vs GCP") == "complex"


def test_complex_why_causal():
    """Causal 'why ' -> complex."""
    assert _tier("why did revenue drop?") == "complex"


def test_complex_and_analyze():
    """Multi-domain conjunction + open-ended verb -> complex."""
    assert _tier("find their team and analyze financials") == "complex"


def test_complex_predict():
    """Predictive 'predict' signal -> complex."""
    assert _tier("predict what happens if they merge") == "complex"


def test_complex_research():
    """Open-ended verb 'research ' -> complex."""
    assert _tier("research the competitive landscape of AI agents") == "complex"


def test_complex_long_query():
    """Query longer than 50 words gets +1, tipping into complex if no other signals offset."""
    long_query = " ".join(["word"] * 51)  # 51 words, no negative signals
    assert _tier(long_query) == "complex"


# ---------------------------------------------------------------------------
# Score boundary — ensure score <= 0 -> simple, score > 0 -> complex
# ---------------------------------------------------------------------------


def test_score_boundary_simple_is_nonpositive():
    """Score for a simple query must be <= 0."""
    assert _score("find email of John Doe") <= 0


def test_score_boundary_complex_is_positive():
    """Score for a complex query must be > 0."""
    assert _score("investigate TechCorp") > 0


def test_investigate_score_value():
    """'investigate' alone scores +2 (open-ended verb)."""
    assert _score("investigate TechCorp") == 2


def test_root_cause_causal():
    """'root cause' is a causal signal -> complex."""
    assert _tier("find the root cause of the outage") == "complex"
