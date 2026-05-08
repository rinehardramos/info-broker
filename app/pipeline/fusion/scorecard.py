"""Strategy scorecard engine — decompose research trails into graded strategy/tactic/technique trees."""

from __future__ import annotations
from collections import defaultdict

# Import the tool-to-selector mapping from the analyzer
from app.pipeline.strategies.analyzer import PIVOT_TOOL_MAP


def auto_grade_technique(result_count: int, error: str | None) -> str:
    """Grade a single tool call A-F."""
    if error:
        if "timeout" in str(error).lower() or "rate" in str(error).lower():
            return "E"
        return "F"
    if result_count >= 3:
        return "A"
    if result_count >= 1:
        return "B"
    return "C"  # Clean negative (no error, no results)


def auto_grade_tactic(techniques: list[dict]) -> str:
    """Grade a tactic group based on its technique grades and yield."""
    if not techniques:
        return "F"

    grades = [t["auto_grade"] for t in techniques]
    total_results = sum(t.get("result_count", 0) for t in techniques)
    yield_rate = total_results / max(len(techniques), 1)

    # Count grade distribution
    a_count = grades.count("A")
    fail_count = sum(1 for g in grades if g in ("E", "F"))

    if fail_count == len(grades):
        return "F"
    if yield_rate >= 0.7 and a_count >= 1:
        return "A"
    if yield_rate >= 0.4 or sum(1 for g in grades if g in ("A", "B")) >= 2:
        return "B"
    if total_results >= 1:
        return "C"
    if total_results == 0 and fail_count > 0:
        return "E"
    return "D"


def auto_grade_strategy(tactics: list[dict], completeness_pct: float) -> str:
    """Grade the overall strategy based on tactic grades and coverage."""
    if not tactics:
        return "F"

    grades = [t["auto_grade"] for t in tactics]
    b_plus = sum(1 for g in grades if g in ("A", "B"))
    f_count = grades.count("F")

    if completeness_pct >= 0.8 and b_plus >= 3 and f_count == 0:
        return "A"
    if completeness_pct >= 0.6 and b_plus >= 2:
        return "B"
    if completeness_pct >= 0.4 and b_plus >= 1:
        return "C"
    if completeness_pct >= 0.2:
        return "D"
    if any(g not in ("E", "F") for g in grades):
        return "E"
    return "F"


def build_scorecard(
    trail: dict,
    findings: list[dict],
    completeness_pct: float,
    entity_type: str,
) -> dict:
    """Build the full strategy -> tactic -> technique scorecard from a research trail."""
    branches = trail.get("branches", [])

    if not branches:
        return {
            "strategy": {"name": entity_type, "auto_grade": "F", "user_grade": None,
                         "completeness_pct": completeness_pct},
            "tactics": [],
        }

    # Group tool calls by selector type (= tactic)
    tactic_groups: dict[str, list[dict]] = defaultdict(list)

    for branch in branches:
        tools = branch.get("tools_used", [])
        branch_findings = branch.get("findings_count", 0)
        branch_status = branch.get("status", "unknown")

        # Distribute findings roughly equally across tools in the branch
        per_tool = branch_findings / max(len(tools), 1)

        for tool in tools:
            clean_tool = tool.replace("run_", "")
            selector_type = PIVOT_TOOL_MAP.get(clean_tool, "unknown")

            # Determine error
            error = None
            if branch_status in ("needs_tool", "depth_exhausted") and branch_findings == 0:
                error = f"Branch status: {branch_status}"

            technique = {
                "tool": tool,
                "result_count": int(per_tool),
                "error": error,
                "auto_grade": auto_grade_technique(int(per_tool), error),
                "user_grade": None,
                "branch_name": branch.get("name", ""),
                "branch_status": branch_status,
            }
            tactic_groups[selector_type].append(technique)

    # Build tactic scorecards
    tactics = []
    for selector_type, techniques in tactic_groups.items():
        tactic = {
            "name": f"{selector_type}_investigation",
            "selector_type": selector_type,
            "yield_rate": sum(t["result_count"] for t in techniques) / max(len(techniques), 1),
            "auto_grade": auto_grade_tactic(techniques),
            "user_grade": None,
            "techniques": techniques,
        }
        tactics.append(tactic)

    # Sort tactics by grade (best first)
    grade_order = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4, "F": 5}
    tactics.sort(key=lambda t: grade_order.get(t["auto_grade"], 5))

    # Build strategy scorecard
    strategy = {
        "name": entity_type,
        "auto_grade": auto_grade_strategy(tactics, completeness_pct),
        "user_grade": None,
        "completeness_pct": completeness_pct,
    }

    return {"strategy": strategy, "tactics": tactics}
