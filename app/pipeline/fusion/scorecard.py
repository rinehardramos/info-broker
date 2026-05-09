"""Strategy scorecard engine — decompose research trails into graded strategy/tactic/technique trees."""

from __future__ import annotations
import logging
from collections import defaultdict

# Import the tool-to-selector mapping from the analyzer
from app.pipeline.strategies.analyzer import PIVOT_TOOL_MAP

log = logging.getLogger(__name__)


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


def grade_comment_technique(tool: str, grade: str, result_count: int, error: str | None) -> str:
    """Generate an actionable comment for a technique grade."""
    if grade == "A":
        return f"{tool} produced {result_count} findings — highly effective, prioritize in future."
    elif grade == "B":
        return f"{tool} produced {result_count} finding(s) — effective, continue using."
    elif grade == "C":
        return f"{tool} returned no results but ran cleanly — may not apply to this target type."
    elif grade == "D":
        return f"{tool} returned no results with warnings — consider skipping for similar queries."
    elif grade == "E":
        return f"{tool} encountered recoverable error: {error or 'timeout/rate limit'} — retry with different params or defer."
    else:  # F
        return f"{tool} FAILED: {error or 'crashed/blocked'} — investigate tool config or skip until fixed."


def grade_comment_tactic(name: str, grade: str, yield_rate: float, technique_grades: list[str]) -> str:
    """Generate an actionable comment for a tactic grade."""
    if grade in ("A", "B"):
        return f"Tactic '{name}' is effective (yield {yield_rate:.0%}). Use as primary approach for this selector type."
    elif grade == "C":
        return f"Tactic '{name}' produced some results (yield {yield_rate:.0%}). Consider supplementing with additional tools."
    elif grade in ("D", "E"):
        failed = sum(1 for g in technique_grades if g in ("E", "F"))
        return f"Tactic '{name}' underperformed (yield {yield_rate:.0%}, {failed} tools failed). Try alternative approaches."
    else:  # F
        return f"Tactic '{name}' completely failed. All tools returned errors. Investigate tool configurations."


def grade_comment_strategy(name: str, grade: str, completeness_pct: float, gaps: list[str] | None) -> str:
    """Generate an actionable comment for a strategy grade."""
    if grade in ("A", "B"):
        return f"Strategy '{name}' achieved {completeness_pct:.0%} coverage. Well-executed investigation."
    elif grade == "C":
        gap_str = f" Gaps: {', '.join(gaps[:3])}" if gaps else ""
        return f"Strategy '{name}' achieved {completeness_pct:.0%} coverage.{gap_str} Go deeper on missing domains."
    elif grade in ("D", "E"):
        gap_str = f" Missing: {', '.join(gaps[:5])}" if gaps else ""
        return f"Strategy '{name}' only {completeness_pct:.0%} coverage.{gap_str} Increase depth and use more tools."
    else:
        return f"Strategy '{name}' failed — no meaningful coverage. Check that tools are configured and accessible."


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

            auto_grade = auto_grade_technique(int(per_tool), error)
            technique = {
                "tool": tool,
                "result_count": int(per_tool),
                "error": error,
                "auto_grade": auto_grade,
                "user_grade": None,
                "branch_name": branch.get("name", ""),
                "branch_status": branch_status,
                "comment": grade_comment_technique(tool, auto_grade, int(per_tool), error),
            }
            tactic_groups[selector_type].append(technique)

    # Build tactic scorecards
    tactics = []
    for selector_type, techniques in tactic_groups.items():
        name = f"{selector_type}_investigation"
        yield_rate = sum(t["result_count"] for t in techniques) / max(len(techniques), 1)
        auto_grade = auto_grade_tactic(techniques)
        tactic = {
            "name": name,
            "selector_type": selector_type,
            "yield_rate": yield_rate,
            "auto_grade": auto_grade,
            "user_grade": None,
            "techniques": techniques,
            "comment": grade_comment_tactic(name, auto_grade, yield_rate, [t["auto_grade"] for t in techniques]),
        }
        tactics.append(tactic)

    # Sort tactics by grade (best first)
    grade_order = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4, "F": 5}
    tactics.sort(key=lambda t: grade_order.get(t["auto_grade"], 5))

    # Build strategy scorecard
    strategy_grade = auto_grade_strategy(tactics, completeness_pct)
    strategy = {
        "name": entity_type,
        "auto_grade": strategy_grade,
        "user_grade": None,
        "completeness_pct": completeness_pct,
        "comment": grade_comment_strategy(entity_type, strategy_grade, completeness_pct, []),
    }

    return {"strategy": strategy, "tactics": tactics}


def backfill_scorecards() -> int:
    """Backfill scorecards for existing research trails that don't have one."""
    try:
        from app.routers.v3.db import fetch_all, execute
        import json

        rows = fetch_all(
            "SELECT run_id, trail, findings, query FROM research_trails WHERE scorecard IS NULL AND trail IS NOT NULL LIMIT 50"
        ) or []

        count = 0
        for row in rows:
            trail = row.get("trail")
            findings = row.get("findings")
            if not trail or not isinstance(trail, dict):
                continue

            # Infer entity_type from trail or default to person
            entity_type = "person"

            # Build scorecard with 0% completeness (can't assess retroactively)
            scorecard = build_scorecard(
                trail=trail,
                findings=findings if isinstance(findings, list) else [],
                completeness_pct=0.0,
                entity_type=entity_type,
            )

            execute(
                "UPDATE research_trails SET scorecard = %s WHERE run_id = %s",
                (json.dumps(scorecard), str(row["run_id"])),
            )
            count += 1

        return count
    except Exception as exc:
        log.warning("Scorecard backfill failed: %s", exc)
        return 0
