"""Tests for RAG-based strategy rule store."""
from unittest.mock import patch, MagicMock

from app.pipeline.strategies.meta.rule_store import (
    index_rules,
    retrieve_rules,
    _split_into_rules,
    _rule_id,
    index_from_meta_files,
)


def test_rule_id_deterministic():
    assert _rule_id("test") == _rule_id("test")
    assert _rule_id("a") != _rule_id("b")


def test_split_into_rules_by_header():
    text = "RULE_A: do this thing\ndetails here\n\nRULE_B: do that thing\nmore details"
    rules = _split_into_rules(text, "test")
    assert len(rules) == 2
    assert "RULE_A" in rules[0]["text"]
    assert "RULE_B" in rules[1]["text"]


def test_split_into_rules_no_headers():
    text = "just some text without headers, short but valid content here."
    rules = _split_into_rules(text, "fallback")
    assert len(rules) == 1
    assert rules[0]["name"] == "fallback"


def test_index_rules_returns_count():
    mock_client = MagicMock()
    mock_client.get_collection.return_value = True
    with patch("app.pipeline.strategies.meta.rule_store._get_qdrant", return_value=mock_client):
        with patch("app.pipeline.strategies.meta.rule_store._embed", return_value=[0.1] * 768):
            count = index_rules([
                {"name": "test_rule", "rule_text": "do the thing", "category": "universal"},
            ])
    assert count == 1
    assert mock_client.upsert.called


def test_retrieve_rules_returns_string():
    mock_client = MagicMock()
    mock_point = MagicMock()
    mock_point.payload = {
        "name": "test",
        "rule_text": "RULE: do it",
        "priority": 1,
        "tokens": 10,
        "always_on": True,
    }
    mock_client.scroll.return_value = ([mock_point], None)
    mock_client.query_points.return_value = MagicMock(points=[])

    with (
        patch("app.pipeline.strategies.meta.rule_store._get_qdrant", return_value=mock_client),
        patch("app.pipeline.strategies.meta.rule_store._embed", return_value=[0.1] * 768),
    ):
        result = retrieve_rules("test query", "person", max_tokens=500)
    assert "RULE: do it" in result


def test_retrieve_rules_respects_token_budget():
    mock_client = MagicMock()

    # Always-on rule that fills most of the budget
    big_point = MagicMock()
    big_point.payload = {
        "name": "big",
        "rule_text": "x" * 400,
        "priority": 1,
        "tokens": 400,
        "always_on": True,
    }
    mock_client.scroll.return_value = ([big_point], None)

    # Semantic hit — 200 tokens, but only 100 remain after big_point (max_tokens=500)
    extra_point = MagicMock()
    extra_point.payload = {
        "name": "extra",
        "rule_text": "y" * 200,
        "priority": 2,
        "tokens": 200,
    }
    mock_client.query_points.return_value = MagicMock(points=[extra_point])

    with (
        patch("app.pipeline.strategies.meta.rule_store._get_qdrant", return_value=mock_client),
        patch("app.pipeline.strategies.meta.rule_store._embed", return_value=[0.1] * 768),
    ):
        result = retrieve_rules("test", "person", max_tokens=500)

    assert "x" * 100 in result   # Big rule is included
    assert "y" * 200 not in result  # Extra exceeds remaining budget so it's excluded


def test_retrieve_rules_fallback_on_error():
    with patch("app.pipeline.strategies.meta.rule_store._get_qdrant", side_effect=Exception("no qdrant")):
        result = retrieve_rules("test", "person")
    assert result == ""  # Graceful fallback


def test_index_from_meta_files_returns_count():
    with (
        patch("app.pipeline.strategies.meta.rule_store.index_rules") as mock_index,
        patch("app.pipeline.strategies.meta.rule_store._embed", return_value=[0.1] * 768),
    ):
        mock_index.return_value = 15
        count = index_from_meta_files()
    assert count == 15
