"""TDD tests for app.memory.lifecycle — tier lifecycle sweep module."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch, call

# Stub psycopg2 before any app imports.
for _mod in ["psycopg2", "psycopg2.extras"]:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

import importlib
import app.memory.lifecycle as lifecycle  # noqa: E402 — stubs must be set first


# ---------------------------------------------------------------------------
# TIER_THRESHOLDS structure
# ---------------------------------------------------------------------------


def test_tier_thresholds_has_three_entries():
    assert len(lifecycle.TIER_THRESHOLDS) == 3


def test_tier_thresholds_keys():
    keys = set(lifecycle.TIER_THRESHOLDS.keys())
    assert ("hot", "warm") in keys
    assert ("warm", "cold") in keys
    assert ("cold", "archive") in keys


def test_tier_thresholds_values():
    hw = lifecycle.TIER_THRESHOLDS[("hot", "warm")]
    assert hw["age_days"] == 30
    assert hw["idle_days"] == 30

    wc = lifecycle.TIER_THRESHOLDS[("warm", "cold")]
    assert wc["age_days"] == 90
    assert wc["idle_days"] == 60

    ca = lifecycle.TIER_THRESHOLDS[("cold", "archive")]
    assert ca["age_days"] == 365
    assert ca["idle_days"] == 180


# ---------------------------------------------------------------------------
# demote_tier — SQL correctness
# ---------------------------------------------------------------------------


def test_demote_tier_calls_execute_with_correct_sql():
    with patch("app.memory.lifecycle.execute") as mock_exec:
        mock_exec.return_value = None

        # Patch rowcount via the cursor mock returned inside execute
        # Since execute() is patched entirely, we just check call args.
        lifecycle.demote_tier("hot", "warm", 30, 30)

    assert mock_exec.called
    sql_arg = mock_exec.call_args[0][0]
    params_arg = mock_exec.call_args[0][1]

    assert "UPDATE entity_observations" in sql_arg
    assert "SET tier" in sql_arg
    assert "WHERE tier" in sql_arg
    assert "observed_at" in sql_arg
    assert "last_accessed_at" in sql_arg

    # params should carry to_tier, from_tier, age_days interval, idle_days interval
    assert "warm" in params_arg
    assert "hot" in params_arg


def test_demote_tier_returns_integer():
    with patch("app.memory.lifecycle.execute"):
        result = lifecycle.demote_tier("hot", "warm", 30, 30)
    assert isinstance(result, int)


def test_demote_tier_passes_age_and_idle_as_params():
    with patch("app.memory.lifecycle.execute") as mock_exec:
        lifecycle.demote_tier("warm", "cold", 90, 60)

    params = mock_exec.call_args[0][1]
    # tier values
    assert "cold" in params
    assert "warm" in params
    # interval values
    assert 90 in params
    assert 60 in params


# ---------------------------------------------------------------------------
# promote_recently_accessed — SQL correctness
# ---------------------------------------------------------------------------


def test_promote_recently_accessed_calls_execute_with_correct_sql():
    with patch("app.memory.lifecycle.execute") as mock_exec:
        lifecycle.promote_recently_accessed(accessed_within_days=7, target_tier="hot")

    assert mock_exec.called
    sql_arg = mock_exec.call_args[0][0]
    params_arg = mock_exec.call_args[0][1]

    assert "UPDATE entity_observations" in sql_arg
    assert "SET tier" in sql_arg
    assert "last_accessed_at" in sql_arg
    assert "archive" in sql_arg

    assert "hot" in params_arg
    assert 7 in params_arg


def test_promote_recently_accessed_returns_integer():
    with patch("app.memory.lifecycle.execute"):
        result = lifecycle.promote_recently_accessed()
    assert isinstance(result, int)


def test_promote_recently_accessed_default_args():
    """Default call uses accessed_within_days=7 and target_tier='hot'."""
    with patch("app.memory.lifecycle.execute") as mock_exec:
        lifecycle.promote_recently_accessed()

    params = mock_exec.call_args[0][1]
    assert "hot" in params
    assert 7 in params
