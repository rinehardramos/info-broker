"""Test that budget contract is injected into IS brain prompt."""
import inspect
import pytest
from app.pipeline.budget import RunBudgetIn, plan_run_budget
from app.is_prompt import build_prompt


def test_budget_section_appears_in_prompt():
    plan = plan_run_budget(RunBudgetIn(resource="tiny", depth="shallow"))
    sig = inspect.signature(build_prompt)
    assert "budget_plan" in sig.parameters, "budget_plan param missing from build_prompt"

    prompt = build_prompt(
        query="test query",
        budget_plan=plan,
    )
    assert "RUN BUDGET CONTRACT" in prompt
    assert str(plan.execution_limits.max_tool_calls) in prompt


def test_budget_section_absent_when_no_plan():
    prompt = build_prompt(
        query="test query",
        budget_plan=None,
    )
    assert "RUN BUDGET CONTRACT" not in prompt


def test_budget_section_includes_effort_label():
    plan = plan_run_budget(RunBudgetIn(speed="fast", resource="medium", depth="search"))
    prompt = build_prompt(query="test", budget_plan=plan)
    assert plan.effort_label in prompt
