# app/pipeline/strategies/planner.py
"""Formatters that render research plan dicts and clarification Q&A into
prompt-ready strings for injection into the IS brain system prompt."""

from __future__ import annotations


def format_plan_for_prompt(plan: dict | None) -> str:
    """Format a research plan dict for injection into the IS prompt.

    Returns an empty string when *plan* is None, empty, or contains no steps.

    Expected plan shape::

        {
            "steps": [
                {
                    "category": "retrieval",
                    "goal": "Gather Company X financial data",
                    "tools": ["ddg_search", "linkedin_profile", "sec_edgar"],
                },
                ...
            ],
            "completeness_criteria": [          # optional
                "Financial data found",
                ...
            ],
        }
    """
    if not plan:
        return ""

    steps: list[dict] = plan.get("steps") or []
    if not steps:
        return ""

    lines: list[str] = ["## YOUR RESEARCH PLAN", ""]

    for idx, step in enumerate(steps, start=1):
        category = step.get("category", "")
        goal = step.get("goal", "")
        tools: list[str] = step.get("tools") or []

        lines.append(f"Step {idx} [{category}]: {goal}")
        if tools:
            lines.append(f"  Tools: {', '.join(tools)}")
        lines.append("")

    criteria: list[str] = plan.get("completeness_criteria") or []
    if criteria:
        lines.append("Completeness criteria:")
        for criterion in criteria:
            lines.append(f"- {criterion}")

    return "\n".join(lines).rstrip()


def format_clarification_for_prompt(clarification: list[dict] | None) -> str:
    """Format a clarification Q&A list for injection into the IS prompt.

    *clarification* is a list of message dicts::

        [
            {"role": "brain", "content": "What aspect interests you?"},
            {"role": "user",  "content": "Financials and leadership"},
            ...
        ]

    Returns an empty string when *clarification* is None or empty.
    Brain messages are rendered as ``Q:`` lines; user messages as ``A:`` lines.
    """
    if not clarification:
        return ""

    lines: list[str] = ["## CLARIFICATION CONTEXT", ""]

    for message in clarification:
        role = message.get("role", "")
        content = message.get("content", "")
        if role == "brain":
            lines.append(f"Q: {content}")
        elif role == "user":
            lines.append(f"A: {content}")
            lines.append("")

    return "\n".join(lines).rstrip()
