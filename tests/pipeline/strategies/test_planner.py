# tests/pipeline/strategies/test_planner.py
"""TDD tests for the research plan formatter module."""

from __future__ import annotations

import pytest

from app.pipeline.strategies.planner import (
    format_clarification_for_prompt,
    format_plan_for_prompt,
)


# ---------------------------------------------------------------------------
# format_plan_for_prompt
# ---------------------------------------------------------------------------


class TestFormatPlanForPrompt:
    def test_none_returns_empty_string(self) -> None:
        assert format_plan_for_prompt(None) == ""

    def test_empty_dict_returns_empty_string(self) -> None:
        assert format_plan_for_prompt({}) == ""

    def test_empty_steps_list_returns_empty_string(self) -> None:
        assert format_plan_for_prompt({"steps": []}) == ""

    def test_two_steps_contains_step_numbers(self) -> None:
        plan = {
            "steps": [
                {
                    "category": "retrieval",
                    "goal": "Gather Company X financial data",
                    "tools": ["ddg_search", "linkedin_profile", "sec_edgar"],
                },
                {
                    "category": "explanation",
                    "goal": "Analyze why revenue declined",
                    "tools": ["ddg_search", "google_news"],
                },
            ]
        }
        result = format_plan_for_prompt(plan)
        assert "Step 1" in result
        assert "Step 2" in result

    def test_two_steps_contains_category_names(self) -> None:
        plan = {
            "steps": [
                {
                    "category": "retrieval",
                    "goal": "Gather Company X financial data",
                    "tools": ["ddg_search"],
                },
                {
                    "category": "explanation",
                    "goal": "Analyze why revenue declined",
                    "tools": ["google_news"],
                },
            ]
        }
        result = format_plan_for_prompt(plan)
        assert "retrieval" in result
        assert "explanation" in result

    def test_two_steps_contains_goals(self) -> None:
        plan = {
            "steps": [
                {
                    "category": "retrieval",
                    "goal": "Gather Company X financial data",
                    "tools": ["ddg_search"],
                },
                {
                    "category": "explanation",
                    "goal": "Analyze why revenue declined",
                    "tools": ["google_news"],
                },
            ]
        }
        result = format_plan_for_prompt(plan)
        assert "Gather Company X financial data" in result
        assert "Analyze why revenue declined" in result

    def test_two_steps_contains_tools(self) -> None:
        plan = {
            "steps": [
                {
                    "category": "retrieval",
                    "goal": "Gather data",
                    "tools": ["ddg_search", "sec_edgar"],
                },
            ]
        }
        result = format_plan_for_prompt(plan)
        assert "ddg_search" in result
        assert "sec_edgar" in result

    def test_completeness_criteria_included(self) -> None:
        plan = {
            "steps": [
                {
                    "category": "retrieval",
                    "goal": "Gather financial data",
                    "tools": ["ddg_search"],
                },
            ],
            "completeness_criteria": [
                "Financial data found",
                "Leadership identified",
                "Root cause identified",
            ],
        }
        result = format_plan_for_prompt(plan)
        assert "Financial data found" in result
        assert "Leadership identified" in result
        assert "Root cause identified" in result

    def test_header_present(self) -> None:
        plan = {
            "steps": [
                {
                    "category": "retrieval",
                    "goal": "Gather data",
                    "tools": ["ddg_search"],
                },
            ]
        }
        result = format_plan_for_prompt(plan)
        assert "## YOUR RESEARCH PLAN" in result

    def test_missing_tools_key_does_not_crash(self) -> None:
        plan = {
            "steps": [
                {
                    "category": "retrieval",
                    "goal": "Gather data",
                },
            ]
        }
        result = format_plan_for_prompt(plan)
        assert "Step 1" in result
        assert "Gather data" in result

    def test_steps_missing_returns_empty(self) -> None:
        # plan dict exists but "steps" key absent
        assert format_plan_for_prompt({"completeness_criteria": ["x"]}) == ""


# ---------------------------------------------------------------------------
# format_clarification_for_prompt
# ---------------------------------------------------------------------------


class TestFormatClarificationForPrompt:
    def test_none_returns_empty_string(self) -> None:
        assert format_clarification_for_prompt(None) == ""

    def test_empty_list_returns_empty_string(self) -> None:
        assert format_clarification_for_prompt([]) == ""

    def test_two_qa_pairs_contains_q_and_a_labels(self) -> None:
        clarification = [
            {"role": "brain", "content": "What aspect interests you?"},
            {"role": "user", "content": "Financials and leadership"},
            {"role": "brain", "content": "Any geographic constraints?"},
            {"role": "user", "content": "Focus on Southeast Asia"},
        ]
        result = format_clarification_for_prompt(clarification)
        assert "Q:" in result
        assert "A:" in result

    def test_two_qa_pairs_contains_question_text(self) -> None:
        clarification = [
            {"role": "brain", "content": "What aspect interests you?"},
            {"role": "user", "content": "Financials and leadership"},
        ]
        result = format_clarification_for_prompt(clarification)
        assert "What aspect interests you?" in result

    def test_two_qa_pairs_contains_answer_text(self) -> None:
        clarification = [
            {"role": "brain", "content": "What aspect interests you?"},
            {"role": "user", "content": "Financials and leadership"},
        ]
        result = format_clarification_for_prompt(clarification)
        assert "Financials and leadership" in result

    def test_header_present(self) -> None:
        clarification = [
            {"role": "brain", "content": "Question?"},
            {"role": "user", "content": "Answer."},
        ]
        result = format_clarification_for_prompt(clarification)
        assert "## CLARIFICATION CONTEXT" in result

    def test_two_questions_two_answers(self) -> None:
        clarification = [
            {"role": "brain", "content": "What aspect interests you?"},
            {"role": "user", "content": "Financials and leadership"},
            {"role": "brain", "content": "Any geographic constraints?"},
            {"role": "user", "content": "Focus on Southeast Asia"},
        ]
        result = format_clarification_for_prompt(clarification)
        assert "What aspect interests you?" in result
        assert "Financials and leadership" in result
        assert "Any geographic constraints?" in result
        assert "Focus on Southeast Asia" in result

    def test_unpaired_brain_message_still_renders(self) -> None:
        # brain asks, no user reply yet — should not crash
        clarification = [
            {"role": "brain", "content": "What aspect interests you?"},
        ]
        result = format_clarification_for_prompt(clarification)
        assert "What aspect interests you?" in result
