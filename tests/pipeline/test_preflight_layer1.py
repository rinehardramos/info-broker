"""Layer 1 (deterministic regex extraction) tests for app.pipeline.preflight.extract().

Each of the 5 detectable features gets at least 3 positive and 3 negative cases.
No LLM, no mocking required — extract() is pure regex.
"""
from __future__ import annotations

import pytest

from app.pipeline.preflight import extract


# ---------------------------------------------------------------------------
# first_person_evidence
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "query",
    [
        "I saw an ad last night",
        "heard a podcast about this guy",
        "watched a documentary on Netflix",
        "I noticed this commercial yesterday",
        "I came across this article",
        "stumbled upon a weird video",
    ],
)
def test_first_person_evidence_positive(query: str) -> None:
    assert extract(query).first_person_evidence is True


@pytest.mark.parametrize(
    "query",
    [
        "who is the founder of Acme Corp",
        "explain quantum tunnelling",
        "list the top 10 SaaS companies",
        "compare iPhone vs Pixel",
        "what is the GDP of Japan",
        "translate this sentence to Spanish",
    ],
)
def test_first_person_evidence_negative(query: str) -> None:
    # "founder" must not trigger "found"
    assert extract(query).first_person_evidence is False


# ---------------------------------------------------------------------------
# referential_phrases
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "query",
    [
        "who is that guy in the commercial",
        "what is this ad about",
        "tell me about the show with the lawyer",
        "new series with girl in spiderman where man has a shotgun",
        "who is the person in the Dyson commercial",
        "explain that movie I keep hearing about",
    ],
)
def test_referential_phrase_positive(query: str) -> None:
    assert extract(query).referential_phrases, f"expected referential match for: {query!r}"


@pytest.mark.parametrize(
    "query",
    [
        "who founded Apple Inc",
        "compare GDP of France and Germany",
        "list top universities in Asia",
        "weather forecast for Tokyo tomorrow",
        "summarize quantum mechanics",
        "average house price in Manila",
    ],
)
def test_referential_phrase_negative(query: str) -> None:
    assert extract(query).referential_phrases == []


# ---------------------------------------------------------------------------
# platform_hints
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "query,expected_hint",
    [
        ("I saw this on YouTube last night", "youtube"),
        ("the ad on Netflix was weird", "netflix"),
        ("a TikTok trend about cooking", "tiktok"),
        ("Amazon Prime original series", "amazon"),
        ("watched on Hulu yesterday", "hulu"),
        ("this Instagram reel", "instagram"),
    ],
)
def test_platform_hint_positive(query: str, expected_hint: str) -> None:
    hints = extract(query).platform_hints
    assert expected_hint in hints, f"expected {expected_hint!r} in {hints}"


@pytest.mark.parametrize(
    "query",
    [
        "who is the president of France",
        "explain photosynthesis",
        "what's the capital of Mongolia",
        "list the planets in order",
        "average rainfall in Manila",
        "compare two motorcycle brands",
    ],
)
def test_platform_hint_negative(query: str) -> None:
    assert extract(query).platform_hints == []


# ---------------------------------------------------------------------------
# temporal_signal
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "query",
    [
        "new series about robots",
        "the latest iPhone launch",
        "what happened yesterday in Manila",
        "current state of the housing market",
        "recent advances in fusion",
        "movies released in 2025",
    ],
)
def test_temporal_signal_positive(query: str) -> None:
    assert extract(query).temporal_signal is True


@pytest.mark.parametrize(
    "query",
    [
        "who founded Microsoft",
        "explain the Pythagorean theorem",
        "list provinces of the Philippines",
        "compare Coke and Pepsi",
        "what is dark matter",
        "translate hello to Japanese",
    ],
)
def test_temporal_signal_negative(query: str) -> None:
    assert extract(query).temporal_signal is False


# ---------------------------------------------------------------------------
# polysemous_term
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "query",
    [
        "tell me about Apple",
        "what is Amazon doing this quarter",
        "Tesla launched something new",
        "Oracle vs SAP",
        "is Python a good first language",
        "Mercury orbit period",
    ],
)
def test_polysemous_term_positive(query: str) -> None:
    assert extract(query).polysemous_term is True


@pytest.mark.parametrize(
    "query",
    [
        "who founded Microsoft Corporation",
        "average rainfall in Manila",
        "explain photosynthesis briefly",
        "list the seven wonders",
        "best ramen shop in Tokyo",
        "translate good morning to French",
    ],
)
def test_polysemous_term_negative(query: str) -> None:
    assert extract(query).polysemous_term is False
