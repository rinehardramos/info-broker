"""Tests for the domain sub-strategy registry."""

import pytest

from app.pipeline.strategies.domains.registry import (
    get_substrategy,
    get_substrategy_selectors,
    list_substrategies,
)


def test_list_substrategies_retrieval_returns_at_least_one_entry():
    result = list_substrategies("retrieval")
    assert len(result) >= 1


def test_list_substrategies_entries_have_required_keys():
    result = list_substrategies("retrieval")
    for entry in result:
        assert "name" in entry
        assert "display_name" in entry
        assert "description" in entry


def test_get_substrategy_returns_nonempty_string_for_known():
    result = get_substrategy("retrieval", "due_diligence")
    assert isinstance(result, str)
    assert len(result) > 0


def test_get_substrategy_returns_empty_string_for_nonexistent():
    result = get_substrategy("retrieval", "nonexistent")
    assert result == ""


def test_get_substrategy_selectors_returns_nonempty_list_for_known():
    result = get_substrategy_selectors("retrieval", "due_diligence")
    assert isinstance(result, list)
    assert len(result) > 0


def test_list_substrategies_unknown_category_returns_empty_list():
    result = list_substrategies("unknown")
    assert result == []
