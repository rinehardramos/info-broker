"""Tests for Budget Phase 2 — reservation gate, admission check, release."""
from __future__ import annotations

import pytest
from unittest.mock import patch

from app.pipeline.budget import (
    RunBudgetIn,
    BudgetPlan,
    estimate_run_cost,
    reserve_budget,
    release_budget,
    check_admission,
    plan_run_budget,
)


# ---------------------------------------------------------------------------
# estimate_run_cost
# ---------------------------------------------------------------------------

def test_estimate_run_cost_default():
    # default: general(2) * medium(3) * search(2) * normal(1.5) * normal(1.0) = 18
    result = estimate_run_cost(RunBudgetIn())
    assert result == pytest.approx(18.0)


def test_estimate_run_cost_quick_low():
    budget = RunBudgetIn(research_type="quick", complexity="low", search_scope="search",
                         quality_tier="draft", priority="low")
    # 1.0 * 1.5 * 2.0 * 1.0 * 0.8 = 2.4
    assert estimate_run_cost(budget) == pytest.approx(2.4)


def test_plan_run_budget_returns_budget_plan():
    plan = plan_run_budget(RunBudgetIn())
    assert isinstance(plan, BudgetPlan)
    assert plan.estimated_cost_units == pytest.approx(18.0)
    assert plan.max_tool_calls == 30


# ---------------------------------------------------------------------------
# reserve_budget
# ---------------------------------------------------------------------------

def test_reserve_budget_returns_true_when_wallet_updated():
    mock_row = {"balance_units": 100, "reserved_units": 18}
    with patch("app.routers.v3.db.fetch_one", return_value=mock_row):
        assert reserve_budget("u1", "org-1", 18.0) is True


def test_reserve_budget_returns_false_when_no_row_updated():
    with patch("app.routers.v3.db.fetch_one", return_value=None):
        assert reserve_budget("u1", "org-1", 18.0) is False


def test_reserve_budget_true_on_exception_non_fatal():
    with patch("app.routers.v3.db.fetch_one", side_effect=Exception("no wallet")):
        assert reserve_budget("u1", "org-1", 18.0) is True


# ---------------------------------------------------------------------------
# check_admission
# ---------------------------------------------------------------------------

def test_check_admission_within_limit():
    assert check_admission("u1", "run-1", 5, 30) is True


def test_check_admission_at_limit():
    assert check_admission("u1", "run-1", 30, 30) is False


def test_check_admission_over_limit():
    assert check_admission("u1", "run-1", 35, 30) is False


def test_check_admission_zero_calls():
    assert check_admission("u1", "run-1", 0, 30) is True


# ---------------------------------------------------------------------------
# release_budget (non-fatal — always succeeds from caller's perspective)
# ---------------------------------------------------------------------------

def test_release_budget_calls_execute():
    with patch("app.routers.v3.db.execute") as mock_execute:
        release_budget("u1", "run-1", 18.0, 12.5)
        mock_execute.assert_called_once()
        call_args = mock_execute.call_args[0]
        # params: (estimated, actual, actual, user_id)
        assert call_args[1] == (18.0, 12.5, 12.5, "u1")


def test_release_budget_swallows_exception():
    with patch("app.routers.v3.db.execute", side_effect=Exception("db down")):
        # Must not raise
        release_budget("u1", "run-1", 18.0, 12.5)
