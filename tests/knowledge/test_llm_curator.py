"""Tests for app.knowledge.llm_curator — Memory Phase 5.

Strategy
--------
psycopg2 is stubbed before any import so DB helpers never need a real connection.
Module-level DB helpers (fetch_all, fetch_one, execute) are patched at the
app.knowledge.llm_curator namespace.
Async tests are driven via asyncio.run() — no pytest-asyncio plugin required.
"""
from __future__ import annotations

import asyncio
import sys
import types
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub psycopg2 before importing anything that touches app.routers.v3.db
# ---------------------------------------------------------------------------

_psycopg2_stub = types.ModuleType("psycopg2")
_psycopg2_stub.connect = MagicMock()
_extras_stub = types.ModuleType("psycopg2.extras")
_extras_stub.RealDictCursor = MagicMock()
_psycopg2_stub.extras = _extras_stub
sys.modules.setdefault("psycopg2", _psycopg2_stub)
sys.modules.setdefault("psycopg2.extras", _extras_stub)

# Now safe to import module under test
from app.knowledge.llm_curator import (  # noqa: E402
    find_duplicate_entities,
    generate_curation_suggestions,
    resolve_contradictions_batch,
)


# ===========================================================================
# resolve_contradictions_batch
# ===========================================================================


class TestResolveContradictionsBatch:
    """Tests for resolve_contradictions_batch."""

    def _make_contradiction_rows(self):
        return [
            {
                "id": "c-uuid-1",
                "entity_ref": "person:alice",
                "attribute": "company",
                "value_a": "Acme Corp",
                "value_b": "Initech",
                "confidence_a": 70,
                "confidence_b": 68,
            }
        ]

    def test_resolves_contradiction_with_valid_llm_response(self):
        """LLM returns valid JSON array → contradiction is updated to llm_resolved."""
        rows = self._make_contradiction_rows()
        llm_response = json.dumps(
            [{"index": 1, "winner": "Acme Corp", "reason": "Higher confidence source."}]
        )

        async def _run():
            with (
                patch("app.knowledge.llm_curator.fetch_all", return_value=rows),
                patch("app.knowledge.llm_curator.execute") as mock_execute,
                patch(
                    "app.knowledge.llm_curator._call_llm",
                    new=AsyncMock(return_value=llm_response),
                ),
            ):
                result = await resolve_contradictions_batch(limit=10)
                return result, mock_execute

        result, mock_execute = asyncio.run(_run())
        assert result["resolved"] == 1
        assert result["failed"] == 0
        mock_execute.assert_called_once()
        call_args = mock_execute.call_args[0]
        assert "llm_resolved" in call_args[0]
        assert "Acme Corp" in call_args[1]

    def test_returns_zero_resolved_on_empty_db(self):
        """No needs_review rows → returns {resolved: 0, failed: 0} without LLM call."""
        mock_llm = AsyncMock()

        async def _run():
            with (
                patch("app.knowledge.llm_curator.fetch_all", return_value=[]),
                patch("app.knowledge.llm_curator._call_llm", new=mock_llm),
            ):
                return await resolve_contradictions_batch(limit=10)

        result = asyncio.run(_run())
        assert result == {"resolved": 0, "failed": 0}
        mock_llm.assert_not_called()

    def test_llm_failure_returns_all_failed(self):
        """LLM returns unparseable content → resolved=0, failed=len(rows)."""
        rows = self._make_contradiction_rows()

        async def _run():
            with (
                patch("app.knowledge.llm_curator.fetch_all", return_value=rows),
                patch("app.knowledge.llm_curator.execute") as mock_execute,
                patch(
                    "app.knowledge.llm_curator._call_llm",
                    new=AsyncMock(return_value="not json at all"),
                ),
            ):
                result = await resolve_contradictions_batch(limit=10)
                return result, mock_execute

        result, mock_execute = asyncio.run(_run())
        assert result["resolved"] == 0
        assert result["failed"] == len(rows)
        mock_execute.assert_not_called()

    def test_partial_llm_response_handles_missing_winner(self):
        """LLM returns objects missing required 'winner' field → items count as failed."""
        rows = self._make_contradiction_rows()
        llm_response = json.dumps([{"index": 1, "reason": "unclear"}])

        async def _run():
            with (
                patch("app.knowledge.llm_curator.fetch_all", return_value=rows),
                patch("app.knowledge.llm_curator.execute") as mock_execute,
                patch(
                    "app.knowledge.llm_curator._call_llm",
                    new=AsyncMock(return_value=llm_response),
                ),
            ):
                result = await resolve_contradictions_batch(limit=10)
                return result, mock_execute

        result, mock_execute = asyncio.run(_run())
        assert result["resolved"] == 0
        assert result["failed"] == 1
        mock_execute.assert_not_called()

    def test_markdown_fenced_json_is_parsed(self):
        """LLM wraps JSON in markdown code fences — should still parse."""
        rows = self._make_contradiction_rows()
        llm_response = (
            "```json\n"
            + json.dumps([{"index": 1, "winner": "Initech", "reason": "More recent."}])
            + "\n```"
        )

        async def _run():
            with (
                patch("app.knowledge.llm_curator.fetch_all", return_value=rows),
                patch("app.knowledge.llm_curator.execute"),
                patch(
                    "app.knowledge.llm_curator._call_llm",
                    new=AsyncMock(return_value=llm_response),
                ),
            ):
                return await resolve_contradictions_batch(limit=10)

        result = asyncio.run(_run())
        assert result["resolved"] == 1
        assert result["failed"] == 0


# ===========================================================================
# find_duplicate_entities
# ===========================================================================


class TestFindDuplicateEntities:
    """Tests for find_duplicate_entities (detection only, no LLM)."""

    def test_returns_candidate_pairs(self):
        """Mocked DB returns two candidate pairs — function passes them through."""
        mock_rows = [
            {
                "ref_a": "person:alice-smith",
                "ref_b": "person:alice_smith",
                "shared_attribute": "email",
                "shared_value": "alice@example.com",
            },
            {
                "ref_a": "org:acme",
                "ref_b": "org:acme-corp",
                "shared_attribute": "domain",
                "shared_value": "acme.com",
            },
        ]

        with patch("app.knowledge.llm_curator.fetch_all", return_value=mock_rows):
            result = find_duplicate_entities(limit=20)

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["ref_a"] == "person:alice-smith"
        assert result[1]["shared_value"] == "acme.com"

    def test_empty_result_returns_empty_list(self):
        """No matching rows → empty list."""
        with patch("app.knowledge.llm_curator.fetch_all", return_value=[]):
            result = find_duplicate_entities(limit=20)

        assert result == []

    def test_respects_limit_parameter(self):
        """Limit is forwarded to the DB query."""
        with patch("app.knowledge.llm_curator.fetch_all", return_value=[]) as mock_fa:
            find_duplicate_entities(limit=5)

        call_params = mock_fa.call_args[0][1]
        assert 5 in call_params


# ===========================================================================
# generate_curation_suggestions
# ===========================================================================


class TestGenerateCurationSuggestions:
    """Tests for generate_curation_suggestions."""

    def _stale_rows(self):
        return [
            {
                "entity_ref": "person:bob",
                "attribute": "phone",
                "current_value": "555-1234",
            }
        ]

    def _low_conf_rows(self):
        return [{"entity_ref": "person:carol", "avg_conf": 30, "n": 5}]

    def _contradiction_rows(self):
        return [{"entity_ref": "person:dave", "n": 3}]

    def test_creates_suggestions_for_all_signal_types(self):
        """Stale + low-conf + contradiction rows each produce one suggestion."""
        fetch_side_effects = [
            self._stale_rows(),
            self._low_conf_rows(),
            self._contradiction_rows(),
        ]

        async def _run():
            with (
                patch("app.knowledge.llm_curator.fetch_all", side_effect=fetch_side_effects),
                patch("app.knowledge.llm_curator.fetch_one", return_value=None),
                patch("app.knowledge.llm_curator.execute") as mock_execute,
            ):
                result = await generate_curation_suggestions(limit=20)
                return result, mock_execute

        result, mock_execute = asyncio.run(_run())
        assert result["suggestions_created"] == 3
        assert mock_execute.call_count == 3

    def test_skips_already_pending_suggestions(self):
        """If a pending suggestion already exists, it is not inserted again."""

        async def _run():
            with (
                patch(
                    "app.knowledge.llm_curator.fetch_all",
                    side_effect=[self._stale_rows(), [], []],
                ),
                # fetch_one returns an existing record → should skip
                patch(
                    "app.knowledge.llm_curator.fetch_one",
                    return_value={"id": "existing-uuid"},
                ),
                patch("app.knowledge.llm_curator.execute") as mock_execute,
            ):
                result = await generate_curation_suggestions(limit=20)
                return result, mock_execute

        result, mock_execute = asyncio.run(_run())
        assert result["suggestions_created"] == 0
        mock_execute.assert_not_called()

    def test_returns_zero_when_no_signals(self):
        """No stale/low-conf/contradiction rows → zero suggestions."""

        async def _run():
            with (
                patch("app.knowledge.llm_curator.fetch_all", side_effect=[[], [], []]),
                patch("app.knowledge.llm_curator.execute") as mock_execute,
            ):
                result = await generate_curation_suggestions(limit=20)
                return result, mock_execute

        result, mock_execute = asyncio.run(_run())
        assert result["suggestions_created"] == 0
        mock_execute.assert_not_called()

    def test_suggestions_contain_entity_ref(self):
        """Inserted suggestions carry the correct entity_ref."""

        async def _run():
            with (
                patch(
                    "app.knowledge.llm_curator.fetch_all",
                    side_effect=[self._stale_rows(), [], []],
                ),
                patch("app.knowledge.llm_curator.fetch_one", return_value=None),
                patch("app.knowledge.llm_curator.execute") as mock_execute,
            ):
                await generate_curation_suggestions(limit=20)
                return mock_execute

        mock_execute = asyncio.run(_run())
        insert_params = mock_execute.call_args[0][1]
        assert "person:bob" in insert_params
