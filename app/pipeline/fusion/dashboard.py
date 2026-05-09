"""Global technique/tactic performance dashboard — aggregate grades across runs."""
from __future__ import annotations
import logging
from collections import defaultdict

log = logging.getLogger(__name__)

# Grade to numeric value for averaging
_GRADE_VALUES = {"A": 5, "B": 4, "C": 3, "D": 2, "E": 1, "F": 0}
_VALUE_GRADES = {5: "A", 4: "B", 3: "C", 2: "D", 1: "E", 0: "F"}


def _numeric_to_grade(value: float) -> str:
    """Convert a numeric average back to a letter grade."""
    rounded = round(value)
    return _VALUE_GRADES.get(max(0, min(5, rounded)), "C")


def build_dashboard() -> dict:
    """Build the global performance dashboard from scorecard data + overlays."""
    try:
        from app.routers.v3.db import fetch_all
    except ImportError:
        return {"techniques": [], "tactics": [], "error": "DB not available"}

    # Get all scorecards
    rows = fetch_all(
        "SELECT scorecard FROM research_trails WHERE scorecard IS NOT NULL ORDER BY created_at DESC LIMIT 100"
    ) or []

    # Aggregate technique grades
    technique_stats: dict[str, dict] = defaultdict(
        lambda: {"grades": [], "results": 0, "errors": 0, "runs": 0}
    )
    tactic_stats: dict[str, dict] = defaultdict(
        lambda: {"grades": [], "runs": 0, "yield_rates": []}
    )

    for row in rows:
        sc = row.get("scorecard")
        if not sc or not isinstance(sc, dict):
            continue
        for tactic in sc.get("tactics", []):
            tname = tactic.get("name", "unknown")
            tgrade = tactic.get("user_grade") or tactic.get("auto_grade", "C")
            tactic_stats[tname]["grades"].append(tgrade)
            tactic_stats[tname]["runs"] += 1
            tactic_stats[tname]["yield_rates"].append(tactic.get("yield_rate", 0))

            for tech in tactic.get("techniques", []):
                tool = tech.get("tool", "unknown")
                grade = tech.get("user_grade") or tech.get("auto_grade", "C")
                technique_stats[tool]["grades"].append(grade)
                technique_stats[tool]["results"] += tech.get("result_count", 0)
                technique_stats[tool]["runs"] += 1
                if tech.get("error"):
                    technique_stats[tool]["errors"] += 1

    # Build technique leaderboard
    techniques = []
    for tool, stats in technique_stats.items():
        avg_numeric = sum(_GRADE_VALUES.get(g, 3) for g in stats["grades"]) / max(
            len(stats["grades"]), 1
        )
        techniques.append(
            {
                "tool": tool,
                "avg_grade": _numeric_to_grade(avg_numeric),
                "avg_numeric": round(avg_numeric, 1),
                "runs": stats["runs"],
                "total_results": stats["results"],
                "errors": stats["errors"],
                "error_rate": round(stats["errors"] / max(stats["runs"], 1), 2),
            }
        )
    techniques.sort(key=lambda t: -t["avg_numeric"])

    # Build tactic summary
    tactics = []
    for name, stats in tactic_stats.items():
        avg_numeric = sum(_GRADE_VALUES.get(g, 3) for g in stats["grades"]) / max(
            len(stats["grades"]), 1
        )
        avg_yield = sum(stats["yield_rates"]) / max(len(stats["yield_rates"]), 1)
        tactics.append(
            {
                "name": name,
                "avg_grade": _numeric_to_grade(avg_numeric),
                "avg_numeric": round(avg_numeric, 1),
                "runs": stats["runs"],
                "avg_yield": round(avg_yield, 2),
            }
        )
    tactics.sort(key=lambda t: -t["avg_numeric"])

    return {"techniques": techniques, "tactics": tactics, "total_runs": len(rows)}
