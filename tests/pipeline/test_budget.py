"""TDD tests for app.pipeline.budget — planner and cost estimator."""
import pytest
from app.pipeline.budget import (
    RunBudgetIn,
    BudgetPlan,
    ExecutionLimits,
    CostEstimate,
    plan_run_budget,
    estimate_cost,
    DEFAULT_BUDGET,
)


# ---- RunBudgetIn defaults ----
def test_default_budget_has_all_fields():
    b = RunBudgetIn()
    assert b.speed == "normal"
    assert b.capability == "general"
    assert b.resource == "medium"
    assert b.depth == "search"
    assert b.volume == "normal"
    assert b.optimization_mode == "general"


# ---- plan_run_budget: resource → breadth ----
def test_tiny_resource_gives_low_branch_count():
    limits = plan_run_budget(RunBudgetIn(resource="tiny")).execution_limits
    assert limits.max_branches == 2
    assert limits.max_tool_calls == 6


def test_medium_resource_gives_standard_limits():
    limits = plan_run_budget(RunBudgetIn(resource="medium")).execution_limits
    assert limits.max_branches == 10
    assert limits.max_tool_calls == 30


def test_heavy_resource_gives_high_limits():
    limits = plan_run_budget(RunBudgetIn(resource="heavy")).execution_limits
    assert limits.max_branches == 20
    assert limits.max_tool_calls == 60


# ---- plan_run_budget: depth → max_depth ----
def test_shallow_depth_maps_to_2():
    limits = plan_run_budget(RunBudgetIn(depth="shallow")).execution_limits
    assert limits.max_depth == 2


def test_search_depth_maps_to_4():
    limits = plan_run_budget(RunBudgetIn(depth="search")).execution_limits
    assert limits.max_depth == 4


def test_deep_depth_maps_to_5():
    limits = plan_run_budget(RunBudgetIn(depth="deep")).execution_limits
    assert limits.max_depth == 5


# ---- plan_run_budget: volume → passes ----
def test_normal_volume_gives_2_passes():
    limits = plan_run_budget(RunBudgetIn(volume="normal")).execution_limits
    assert limits.max_passes_per_branch == 2


def test_exhaustive_volume_gives_4_or_5_passes():
    limits = plan_run_budget(RunBudgetIn(volume="exhaustive")).execution_limits
    assert limits.max_passes_per_branch >= 4


# ---- estimate_cost: formula weights ----
def test_default_budget_cost_is_reasonable():
    est = estimate_cost(RunBudgetIn())
    # default: capability=general(2.0) * resource=medium(3) * depth=search(2) * volume=normal(1.5) * speed=normal(1.0) = 18
    assert est.estimated_cost_units == pytest.approx(18.0)


def test_light_tiny_shallow_cost_is_minimum():
    est = estimate_cost(RunBudgetIn(capability="light", resource="tiny", depth="shallow", volume="low", speed="extreme"))
    # 1.0 * 1 * 1 * 1 * 0.7 = 0.7
    assert est.estimated_cost_units == pytest.approx(0.7)


def test_high_heavy_abyss_cost_is_maximum():
    est = estimate_cost(RunBudgetIn(capability="high", resource="unlimited", depth="abyss", volume="exhaustive", speed="slow"))
    # 4.0 * 8 * 5 * 3 * 1.2 = 576
    assert est.estimated_cost_units == pytest.approx(576.0)


# ---- effort label ----
def test_effort_label_matches_dimensions():
    plan = plan_run_budget(RunBudgetIn(speed="fast", capability="general", resource="medium", depth="search"))
    assert "fast" in plan.effort_label
    assert "general" in plan.effort_label


# ---- plan returns model plan ----
def test_general_capability_selects_sonnet():
    plan = plan_run_budget(RunBudgetIn(capability="general"))
    assert "sonnet" in plan.model_plan.planning_model.lower()


def test_high_capability_selects_opus():
    plan = plan_run_budget(RunBudgetIn(capability="high"))
    assert "opus" in plan.model_plan.planning_model.lower()
