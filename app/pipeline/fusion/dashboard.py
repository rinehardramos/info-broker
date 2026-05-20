"""Global technique/tactic performance dashboard — aggregate grades across runs."""
from __future__ import annotations
import logging
from collections import defaultdict

log = logging.getLogger(__name__)

# Admiralty source → numeric (A=5 best, F=0)
_SOURCE_VALUES = {"A": 5, "B": 4, "C": 3, "D": 2, "E": 1, "F": 0}
_VALUE_SOURCES = {5: "A", 4: "B", 3: "C", 2: "D", 1: "E", 0: "F"}
# Credibility → numeric (1=5 best, 6=0)
_CRED_VALUES = {"1": 5, "2": 4, "3": 3, "4": 2, "5": 1, "6": 0}
_VALUE_CREDS = {5: "1", 4: "2", 3: "3", 2: "4", 1: "5", 0: "6"}


def _parse_grade(grade: str) -> tuple[str, str]:
    """Parse Admiralty code 'B2' into ('B', '2'). Handles legacy single-letter."""
    if len(grade) == 2 and grade[0] in _SOURCE_VALUES and grade[1] in _CRED_VALUES:
        return grade[0], grade[1]
    if len(grade) == 1 and grade in _SOURCE_VALUES:
        return grade, "3"
    return "F", "6"


def _numeric_to_grade(src_val: float, cred_val: float | None = None) -> str:
    """Convert numeric averages back to Admiralty code."""
    src = _VALUE_SOURCES.get(max(0, min(5, round(src_val))), "C")
    if cred_val is None:
        return src
    cred = _VALUE_CREDS.get(max(0, min(5, round(cred_val))), "3")
    return src + cred


def build_dashboard(user_id: str | None = None) -> dict:
    """Build the performance dashboard from scorecard data.

    Pass `user_id` to scope the dashboard to a single user's runs (default
    behavior for non-admin callers). `None` returns the global aggregate —
    only safe to expose to admin callers.
    """
    try:
        from app.routers.v3.db import fetch_all
    except ImportError:
        return {"techniques": [], "tactics": [], "error": "DB not available"}

    if user_id is None:
        rows = fetch_all(
            "SELECT scorecard FROM research_trails "
            "WHERE scorecard IS NOT NULL "
            "ORDER BY created_at DESC LIMIT 100"
        ) or []
    else:
        rows = fetch_all(
            "SELECT scorecard FROM research_trails "
            "WHERE scorecard IS NOT NULL AND user_id = %s "
            "ORDER BY created_at DESC LIMIT 100",
            (user_id,),
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
        src_vals = [_SOURCE_VALUES.get(_parse_grade(g)[0], 2) for g in stats["grades"]]
        cred_vals = [_CRED_VALUES.get(_parse_grade(g)[1], 3) for g in stats["grades"]]
        avg_src = sum(src_vals) / max(len(src_vals), 1)
        avg_cred = sum(cred_vals) / max(len(cred_vals), 1)
        avg_numeric = avg_src  # sort by source reliability
        techniques.append(
            {
                "tool": tool,
                "avg_grade": _numeric_to_grade(avg_src, avg_cred),
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
        src_vals = [_SOURCE_VALUES.get(_parse_grade(g)[0], 2) for g in stats["grades"]]
        cred_vals = [_CRED_VALUES.get(_parse_grade(g)[1], 3) for g in stats["grades"]]
        avg_src = sum(src_vals) / max(len(src_vals), 1)
        avg_cred = sum(cred_vals) / max(len(cred_vals), 1)
        avg_numeric = avg_src
        avg_yield = sum(stats["yield_rates"]) / max(len(stats["yield_rates"]), 1)
        tactics.append(
            {
                "name": name,
                "avg_grade": _numeric_to_grade(avg_src, avg_cred),
                "avg_numeric": round(avg_numeric, 1),
                "runs": stats["runs"],
                "avg_yield": round(avg_yield, 2),
            }
        )
    tactics.sort(key=lambda t: -t["avg_numeric"])

    return {"techniques": techniques, "tactics": tactics, "total_runs": len(rows)}
