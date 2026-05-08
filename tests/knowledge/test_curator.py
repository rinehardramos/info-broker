"""Tests for app.knowledge.curator — Memory Phase 3, Task 3.

Strategy
--------
All DB helpers (fetch_all, fetch_one, execute) are mocked from the
*curator module namespace* so no real Postgres connection is needed.
psycopg2 itself is stubbed out before the import via sys.modules patching.
"""
from __future__ import annotations

import sys
import types
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# Stub psycopg2 before importing curator so the module-level import of
# app.routers.v3.db doesn't blow up in an environment without psycopg2.
# ---------------------------------------------------------------------------

_psycopg2_stub = types.ModuleType("psycopg2")
_psycopg2_stub.connect = MagicMock()
_extras_stub = types.ModuleType("psycopg2.extras")
_extras_stub.RealDictCursor = MagicMock()
_psycopg2_stub.extras = _extras_stub
sys.modules.setdefault("psycopg2", _psycopg2_stub)
sys.modules.setdefault("psycopg2.extras", _extras_stub)

# Now safe to import the module under test
from app.knowledge.curator import (  # noqa: E402
    STALENESS_TTL,
    KGCurator,
    pick_winner,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 5, 8, 12, 0, 0, tzinfo=timezone.utc)
_OLD = _NOW - timedelta(days=30)
_RECENT = _NOW - timedelta(days=2)


# ===========================================================================
# pick_winner
# ===========================================================================

class TestPickWinner:
    """Unit tests for the pure pick_winner function."""

    def test_high_confidence_gap_a_wins(self):
        """Gap >= 15: higher confidence wins → auto_resolved."""
        winner, status = pick_winner(90, _OLD, 70, _RECENT)
        assert winner == "a"
        assert status == "auto_resolved"

    def test_high_confidence_gap_b_wins(self):
        """Gap >= 15 but b has higher confidence → b wins."""
        winner, status = pick_winner(60, _RECENT, 80, _OLD)
        assert winner == "b"
        assert status == "auto_resolved"

    def test_close_confidence_recent_wins(self):
        """Gap < 15: more recent observation wins → auto_resolved."""
        winner, status = pick_winner(70, _OLD, 72, _RECENT)
        assert winner == "b"
        assert status == "auto_resolved"

    def test_same_confidence_close_dates_needs_review(self):
        """Same confidence AND within 7 days → needs_review, more recent wins."""
        at_a = _NOW - timedelta(days=3)
        at_b = _NOW - timedelta(days=1)
        winner, status = pick_winner(75, at_a, 75, at_b)
        assert winner == "b"
        assert status == "needs_review"


# ===========================================================================
# STALENESS_TTL
# ===========================================================================

class TestStalenessTTL:
    def test_name_ttl_is_zero(self):
        """name attribute should never be considered stale (TTL = 0)."""
        assert STALENESS_TTL["name"] == 0

    def test_known_attributes_present(self):
        for attr in ("role", "title", "company", "email", "phone", "location"):
            assert attr in STALENESS_TTL


# ===========================================================================
# KGCurator.detect_contradictions
# ===========================================================================

class TestDetectContradictions:
    """Tests for KGCurator.detect_contradictions()."""

    def _make_rows(self):
        """Two conflicting observations for the same entity+attribute."""
        return [
            {
                "id_a": "oid-1",
                "id_b": "oid-2",
                "entity_ref": "person:alice",
                "attribute": "company",
                "value_a": "Acme Corp",
                "value_b": "Initech",
                "confidence_a": 80,
                "confidence_b": 60,
                "observed_at_a": _OLD,
                "observed_at_b": _RECENT,
                "source_run_a": None,
                "source_run_b": None,
            }
        ]

    def test_finds_and_resolves_contradiction(self):
        rows = self._make_rows()
        with (
            patch("app.knowledge.curator.fetch_all") as mock_fetch_all,
            patch("app.knowledge.curator.fetch_one") as mock_fetch_one,
            patch("app.knowledge.curator.execute") as mock_execute,
        ):
            mock_fetch_all.return_value = rows
            # No existing contradiction record
            mock_fetch_one.return_value = None

            curator = KGCurator()
            result = curator.detect_contradictions()

        assert result["contradictions_found"] == 1
        assert result["auto_resolved"] == 1
        assert result["needs_review"] == 0
        assert mock_execute.called

    def test_skips_equivalent_values(self):
        """Values that normalise to the same string should be skipped."""
        rows = [
            {
                "id_a": "oid-3",
                "id_b": "oid-4",
                "entity_ref": "person:bob",
                "attribute": "email",
                "value_a": "Bob@Example.COM",
                "value_b": "bob@example.com",
                "confidence_a": 70,
                "confidence_b": 70,
                "observed_at_a": _OLD,
                "observed_at_b": _RECENT,
                "source_run_a": None,
                "source_run_b": None,
            }
        ]
        with (
            patch("app.knowledge.curator.fetch_all") as mock_fetch_all,
            patch("app.knowledge.curator.fetch_one") as mock_fetch_one,
            patch("app.knowledge.curator.execute") as mock_execute,
        ):
            mock_fetch_all.return_value = rows
            mock_fetch_one.return_value = None

            curator = KGCurator()
            result = curator.detect_contradictions()

        assert result["contradictions_found"] == 0
        mock_execute.assert_not_called()

    def test_skips_already_tracked(self):
        """If the contradiction is already in kg_contradictions, skip it."""
        rows = self._make_rows()
        with (
            patch("app.knowledge.curator.fetch_all") as mock_fetch_all,
            patch("app.knowledge.curator.fetch_one") as mock_fetch_one,
            patch("app.knowledge.curator.execute") as mock_execute,
        ):
            mock_fetch_all.return_value = rows
            # Simulate existing record
            mock_fetch_one.return_value = {"id": "existing-uuid"}

            curator = KGCurator()
            result = curator.detect_contradictions()

        assert result["contradictions_found"] == 0
        mock_execute.assert_not_called()


# ===========================================================================
# KGCurator.detect_staleness
# ===========================================================================

class TestDetectStaleness:
    """Tests for KGCurator.detect_staleness()."""

    def test_flags_stale_observations(self):
        stale_row = {
            "id": "obs-99",
            "entity_ref": "person:carol",
            "attribute": "phone",
            "value": "555-1234",
            "observed_at": _NOW - timedelta(days=200),
        }
        with (
            patch("app.knowledge.curator.fetch_all") as mock_fetch_all,
            patch("app.knowledge.curator.fetch_one") as mock_fetch_one,
            patch("app.knowledge.curator.execute") as mock_execute,
        ):
            # _fetch_stale_for_attribute returns one row; no existing flag
            mock_fetch_all.return_value = [stale_row]
            mock_fetch_one.return_value = None

            curator = KGCurator()
            result = curator.detect_staleness()

        # phone TTL = 180 days; row is 200 days old → should be flagged
        assert result["stale_flagged"] >= 1
        assert mock_execute.called

    def test_skips_already_flagged(self):
        stale_row = {
            "id": "obs-100",
            "entity_ref": "person:dave",
            "attribute": "role",
            "value": "Engineer",
            "observed_at": _NOW - timedelta(days=200),
        }
        with (
            patch("app.knowledge.curator.fetch_all") as mock_fetch_all,
            patch("app.knowledge.curator.fetch_one") as mock_fetch_one,
            patch("app.knowledge.curator.execute") as mock_execute,
        ):
            mock_fetch_all.return_value = [stale_row]
            # Already flagged
            mock_fetch_one.return_value = {"id": "flag-uuid"}

            curator = KGCurator()
            result = curator.detect_staleness()

        assert result["stale_flagged"] == 0
        mock_execute.assert_not_called()
